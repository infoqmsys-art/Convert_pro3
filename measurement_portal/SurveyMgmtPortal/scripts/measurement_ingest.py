"""
자동DB업로드프로그램 — CSV를 읽어 measurement_sample 등에 적재하는 CLI (프로토타입).

프로젝트 내 공식 호칭은 「자동DB업로드프로그램」(파일명 measurement_ingest.py)이다.

시각 열은 `logger_device.time_column_index`(또는 `--time-col` 덮어쓰기)이다.
값 열은 각 센서의 `sensor_channel.channel_index` 를 CSV에서 **0부터 세는 절대 열 번호**로
쓴다(포털 센서설정 화면의 「칼럼」은 맨 왼쪽부터 1이며 `channel_index = 표시번호 − 1`).
`first_data_column_index` 는 과거 오프셋 실험용이며 적재 시에는 사용하지 않는다.

기본 적재 모드는 **증분**(같은 센서에 이미 DB에 있는 관측 시각 이하는 건너뜀). 동일 (채널, 시각)은 파일·DB 어디에 있든 한 번만 삽입(`INSERT OR IGNORE` + 선행 집합). 전체 재수집은 `--full`.

센서 `calc_formula_1`~`6`: `m` = 스케일 적용 후 값, `r1`~`r6`는 단계 결과. 비어 있는 단계는 이전 값 유지. `value_real` 및 `value_step_*`에 단계별·최종값 저장. 균열측정계 신규 등록 시 기본으로 `calc_formula_1` 에 `m*10`(원시→mm)이 들어갑니다.

파일경로만 있고 해당 로거에 **활성(is_active=1)** 센서가 하나도 없으면 적재를 **건너뜁니다**(같은 현장 다른 로거에만 센서가 있으면 로그 진단에 힌트가 붙습니다).

인자 없이 실행하면 Tkinter **GUI**가 열립니다. CLI 예 (measurement_portal/SurveyMgmtPortal 기준):
  python scripts/measurement_ingest.py --logger 1 --csv "C:/data/sample.csv"
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

_PORTAL_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_PORTAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_PORTAL_ROOT))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    import collector_version  # noqa: E402
except ImportError:
    collector_version = None  # type: ignore

import db  # noqa: E402
from calc_formula import evaluate_formula_chain  # noqa: E402


def _channel_formulas(ch) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
    d = dict(ch)
    out: list[str | None] = []
    for i in range(1, 7):
        raw = d.get(f"calc_formula_{i}")
        s = (raw if raw is not None else "").strip()
        out.append(s if s else None)
    return (
        out[0],
        out[1],
        out[2],
        out[3],
        out[4],
        out[5],
    )


def _parse_time(cell: str) -> datetime | None:
    s = (cell or "").strip()
    if not s:
        return None
    s_iso = s.replace("T", " ").strip()
    for candidate in (s, s.replace(" ", "T", 1)):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    fmts = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
    )
    for fmt in fmts:
        try:
            return datetime.strptime(s_iso, fmt)
        except ValueError:
            continue
    if re.fullmatch(r"\d{10,13}", s):
        ts = int(s)
        if ts > 10_000_000_000:
            ts //= 1000
        try:
            return datetime.utcfromtimestamp(ts)
        except (ValueError, OSError):
            return None
    return None


def _format_observed(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def ingest_csv_for_logger(
    logger_device_id: int,
    csv_path: str | Path,
    *,
    time_column: int | None = None,
    first_data_column: int | None = None,
    encoding: str = "utf-8-sig",
    note: str | None = None,
    batch_size: int = 500,
    incremental: bool = True,
    progress_cb: Callable[[dict[str, object]], None] | None = None,
    progress_every_physical_lines: int = 45,
) -> dict:
    """
    단일 CSV를 읽어 해당 로거의 활성 채널에 측정행을 삽입한다.
    첫 데이터 행의 시각 파싱에 실패하면 그 행을 헤더로 보고 건너뜀.

    first_data_column 은 과거 호환용(호출측 호환); 적재에서는 사용하지 않음.

    progress_cb: GUI 등에서 행 스캔 진행 표시용. 물리 행 번호 기준으로 일정 간격 호출됩니다.
      페이로드 예: phase open|scan|done, physical_line, file_name, preview, time_ok_total,
      last_observed (마지막으로 시각 파싱 성공한 행).
    """
    _ = first_data_column

    path = Path(csv_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))

    mtime = int(path.stat().st_mtime)
    conn = db.connect()
    try:
        log_row = conn.execute(
            """
            SELECT COALESCE(time_column_index, 0) AS tc
            FROM logger_device WHERE id = ?
            """,
            (logger_device_id,),
        ).fetchone()
        if log_row is None:
            raise ValueError(f"logger_device id={logger_device_id} 가 없습니다.")
        if time_column is None:
            time_column = int(log_row["tc"])

        channels = [
            dict(r)
            for r in conn.execute(
            """
            SELECT id, channel_index, COALESCE(scale_k, 1.0) AS scale_k,
                   COALESCE(scale_b, 0.0) AS scale_b,
                   COALESCE(pipe_depth_m, 0.0) AS pipe_depth_m,
                   COALESCE(gauge_factor, 1.0) AS gauge_factor,
                   sensor_length_mm,
                   calc_formula_1, calc_formula_2, calc_formula_3,
                   calc_formula_4, calc_formula_5, calc_formula_6
            FROM sensor_channel
            WHERE logger_device_id = ? AND is_active = 1
            ORDER BY channel_index, id
            """,
            (logger_device_id,),
        ).fetchall()
        ]
        if not channels:
            lg_row = conn.execute(
                "SELECT name, site_id FROM logger_device WHERE id = ?",
                (logger_device_id,),
            ).fetchone()
            lg_nm = ((lg_row["name"] if lg_row else None) or "").strip() or "?"
            site_id_for_hint: int | None = None
            if lg_row is not None:
                try:
                    site_id_for_hint = int(lg_row["site_id"])
                except (TypeError, ValueError):
                    site_id_for_hint = None

            tot_row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM sensor_channel
                WHERE logger_device_id = ?
                """,
                (logger_device_id,),
            ).fetchone()
            total_n = int(tot_row["n"] or 0) if tot_row else 0

            inactive_row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM sensor_channel
                WHERE logger_device_id = ? AND COALESCE(is_active, 1) = 0
                """,
                (logger_device_id,),
            ).fetchone()
            inactive_n = int(inactive_row["n"] or 0) if inactive_row else 0

            detail_rows = conn.execute(
                """
                SELECT channel_index, COALESCE(is_active,1) AS ia, sensor_code, label
                FROM sensor_channel
                WHERE logger_device_id = ?
                ORDER BY channel_index, id
                LIMIT 30
                """,
                (logger_device_id,),
            ).fetchall()
            detail_parts: list[str] = []
            for dr in detail_rows:
                ia = int(dr["ia"] or 0)
                code = (dr["sensor_code"] or "").strip() or "—"
                ci = int(dr["channel_index"])
                detail_parts.append(
                    f"칼럼{ci + 1}·{'ON' if ia else 'OFF'}·{code}"
                )
            detail_txt = ", ".join(detail_parts) if detail_parts else "(없음)"

            cross_hint = ""
            if site_id_for_hint is not None and total_n == 0:
                oth = conn.execute(
                    """
                    SELECT ld.name AS logger_name, sc.channel_index, sc.is_active,
                           COALESCE(sc.sensor_code, '') AS sensor_code
                    FROM sensor_channel sc
                    INNER JOIN logger_device ld ON ld.id = sc.logger_device_id
                    WHERE ld.site_id = ? AND ld.id != ? AND COALESCE(sc.is_active,1) = 1
                    ORDER BY ld.name COLLATE NOCASE, sc.channel_index
                    LIMIT 12
                    """,
                    (site_id_for_hint, logger_device_id),
                ).fetchall()
                if oth:
                    bits = [
                        f"{r['logger_name']}:칼럼{int(r['channel_index']) + 1}({(r['sensor_code'] or '').strip() or '코드없음'})"
                        for r in oth
                    ]
                    cross_hint = (
                        " 같은 현장의 다른 로거에 활성 센서가 있습니다: "
                        + "; ".join(bits)
                        + " — 칼럼을 이 로거에 두었는지 확인하세요."
                    )

            if total_n == 0:
                core = (
                    f"로거 「{lg_nm}」(DB logger_device.id={logger_device_id})에는 "
                    "센서 채널(sensor_channel)이 한 개도 없습니다."
                )
            elif inactive_n >= total_n:
                core = (
                    f"로거 「{lg_nm}」(id={logger_device_id})에는 센서가 {total_n}개 있으나 "
                    f"모두 「사용」OFF(is_active=0)입니다."
                )
            else:
                core = (
                    f"로거 「{lg_nm}」(id={logger_device_id})에 활성 센서를 찾지 못했습니다 "
                    f"(전체 {total_n}개·비활성 {inactive_n}개)."
                )

            msg = (
                f"{core} 적재에는 is_active=1 인 센서만 쓰입니다. "
                f"이 로거에 등록된 센서(최대 30개): {detail_txt}.{cross_hint}"
            )

            return {
                "skipped": True,
                "reason": "no_active_sensors",
                "logger_device_id": logger_device_id,
                "source_path": str(path),
                "message": msg,
                "sensor_skip_diag": {
                    "logger_name": lg_nm,
                    "channels_total": total_n,
                    "channels_inactive": inactive_n,
                    "channels_active": 0,
                },
            }

        tick = max(1, int(progress_every_physical_lines))

        def _emit_prog(payload: dict[str, object]) -> None:
            if progress_cb:
                progress_cb(payload)

        ch_ids = [int(c["id"]) for c in channels]
        last_by_id: dict[int, str | None] = (
            db.latest_observed_at_by_channel(ch_ids) if incremental else {}
        )

        dedupe_keys: set[tuple[int, str]] = set()
        for cid in ch_ids:
            last_s = last_by_id.get(cid) if incremental else None
            if incremental and last_s:
                rows_obs = conn.execute(
                    """
                    SELECT observed_at FROM measurement_sample
                    WHERE sensor_channel_id = ? AND observed_at > ?
                    """,
                    (cid, last_s),
                ).fetchall()
            else:
                rows_obs = conn.execute(
                    "SELECT observed_at FROM measurement_sample WHERE sensor_channel_id = ?",
                    (cid,),
                ).fetchall()
            for r in rows_obs:
                dedupe_keys.add((cid, str(r[0])))

        batch_id = db.create_import_batch(
            conn, logger_device_id, str(path), mtime, None, note
        )
        src_name = path.name

        insert_sql = """
          INSERT OR IGNORE INTO measurement_sample(
            sensor_channel_id, observed_at, value_real, value_raw,
            value_step_1, value_step_2, value_step_3, value_step_4, value_step_5, value_step_6,
            quality_flag, import_batch_id, source_file, source_mtime)
          VALUES (?,?,?,?,?,?,?,?,?,?, 'ok', ?, ?, ?)
        """

        total = 0
        buf: list[tuple] = []
        diag = {
            "time_column_index": time_column,
            "active_channels": len(channels),
            "csv_rows_time_ok": 0,
            "points_prepared": 0,
            "skip_col_index_oob": 0,
            "skip_incremental_old": 0,
            "skip_duplicate_time": 0,
            "skip_empty_value": 0,
            "skip_bad_number": 0,
            "skip_formula_error": 0,
            "incremental_latest_db_observed": None,
            "incremental_per_channel_latest": "",
            "csv_first_observed": None,
            "csv_last_observed": None,
            "csv_obs_min": None,
            "csv_obs_max": None,
            "sample_time_col_raw": None,
            "sample_row_ncols": None,
            "sample_channels_cells": None,
        }
        thr_parts: list[str] = []
        for ch in channels:
            cid = int(ch["id"])
            if incremental:
                ls = last_by_id.get(cid)
                thr_parts.append(f"채널{cid}→DB최신:{ls if ls else '없음'}")
            else:
                thr_parts.append(f"채널{cid}→전체적재")
        diag["incremental_per_channel_latest"] = ", ".join(thr_parts)
        if incremental and ch_ids:
            # UI 힌트용: 첫 활성 채널 기준 DB 최신 시각
            lo = last_by_id.get(int(channels[0]["id"]))
            if lo:
                diag["incremental_latest_db_observed"] = lo

        def flush_buf() -> None:
            nonlocal total
            if not buf:
                return
            chg0 = conn.total_changes
            conn.executemany(insert_sql, buf)
            total += conn.total_changes - chg0
            buf.clear()

        _emit_prog(
            {
                "phase": "open",
                "logger_device_id": logger_device_id,
                "file_name": src_name,
                "physical_line": 0,
                "time_ok_total": 0,
                "preview": "",
                "last_observed": None,
            }
        )

        def _row_preview(cells: list[str]) -> str:
            parts: list[str] = []
            for _, cell in enumerate(cells[:10]):
                s = (cell or "").strip().replace("\n", " ")
                if len(s) > 36:
                    s = s[:33] + "…"
                parts.append(s if s else "·")
            joined = " │ ".join(parts)
            return joined[:220] + ("…" if len(joined) > 220 else "")

        last_observed_scan: str | None = None
        last_physical_line = 0

        with path.open(encoding=encoding, newline="") as f:
            reader = csv.reader(f)
            for physical_line, row in enumerate(reader, start=1):
                last_physical_line = physical_line
                if progress_cb and physical_line % tick == 0:
                    _emit_prog(
                        {
                            "phase": "scan",
                            "logger_device_id": logger_device_id,
                            "file_name": src_name,
                            "physical_line": physical_line,
                            "time_ok_total": int(diag["csv_rows_time_ok"]),
                            "preview": _row_preview(row),
                            "last_observed": last_observed_scan,
                        }
                    )
                if len(row) <= time_column:
                    continue
                raw_t = (row[time_column] or "").strip()
                probe = raw_t.lower()
                if probe in ("time", "date", "datetime", "timestamp", "시각"):
                    continue
                dt = _parse_time(raw_t)
                if dt is None:
                    continue

                observed = _format_observed(dt)
                diag["csv_rows_time_ok"] += 1
                last_observed_scan = observed
                if diag["csv_first_observed"] is None:
                    diag["csv_first_observed"] = observed
                    diag["sample_time_col_raw"] = raw_t[:240]
                    diag["sample_row_ncols"] = len(row)
                    parts: list[str] = []
                    for ch in channels:
                        ci = int(ch["channel_index"])
                        cid = int(ch["id"])
                        if 0 <= ci < len(row):
                            parts.append(f"id{cid}값열{ci}={str(row[ci])[:60]}")
                        else:
                            parts.append(
                                f"id{cid}값열{ci}=범위밖(행{len(row)}칸)"
                            )
                    diag["sample_channels_cells"] = " | ".join(parts)
                diag["csv_last_observed"] = observed
                o_min = diag["csv_obs_min"]
                o_max = diag["csv_obs_max"]
                if o_min is None or observed < o_min:
                    diag["csv_obs_min"] = observed
                if o_max is None or observed > o_max:
                    diag["csv_obs_max"] = observed
                for ch in channels:
                    col_idx = int(ch["channel_index"])
                    if col_idx < 0 or col_idx >= len(row):
                        diag["skip_col_index_oob"] += 1
                        continue
                    cid = int(ch["id"])
                    if incremental:
                        last_s = last_by_id.get(cid)
                        if last_s and observed <= last_s:
                            diag["skip_incremental_old"] += 1
                            continue
                    if (cid, observed) in dedupe_keys:
                        diag["skip_duplicate_time"] += 1
                        continue
                    raw_cell = (row[col_idx] or "").strip()
                    if raw_cell == "":
                        diag["skip_empty_value"] += 1
                        continue
                    try:
                        value_raw = float(raw_cell.replace(",", ""))
                    except ValueError:
                        diag["skip_bad_number"] += 1
                        continue
                    k = float(ch["scale_k"])
                    b = float(ch["scale_b"])
                    m_scaled = k * value_raw + b
                    formulas = _channel_formulas(ch)
                    try:
                        pipe_nv = ch.get("pipe_depth_m")
                        try:
                            pipe_f = (
                                float(pipe_nv)
                                if pipe_nv is not None and str(pipe_nv).strip() != ""
                                else 0.0
                            )
                        except (TypeError, ValueError):
                            pipe_f = 0.0
                        gf_nv = ch.get("gauge_factor")
                        try:
                            gf_f = (
                                float(gf_nv)
                                if gf_nv is not None and str(gf_nv).strip() != ""
                                else 1.0
                            )
                        except (TypeError, ValueError):
                            gf_f = 1.0
                        len_nv = ch.get("sensor_length_mm")
                        try:
                            L_f = (
                                float(len_nv)
                                if len_nv is not None and str(len_nv).strip() != ""
                                else 1000.0
                            )
                        except (TypeError, ValueError):
                            L_f = 1000.0
                        steps, value_real = evaluate_formula_chain(
                            m_scaled,
                            formulas,
                            extra_env={"pipe": pipe_f, "gf": gf_f, "L": L_f},
                        )
                    except (ValueError, ZeroDivisionError, OverflowError):
                        diag["skip_formula_error"] += 1
                        continue
                    dedupe_keys.add((cid, observed))
                    diag["points_prepared"] += 1
                    buf.append(
                        (
                            cid,
                            observed,
                            value_real,
                            value_raw,
                            steps[0],
                            steps[1],
                            steps[2],
                            steps[3],
                            steps[4],
                            steps[5],
                            batch_id,
                            src_name,
                            mtime,
                        )
                    )
                    if len(buf) >= batch_size:
                        flush_buf()

            flush_buf()

        _emit_prog(
            {
                "phase": "done",
                "logger_device_id": logger_device_id,
                "file_name": src_name,
                "physical_line": last_physical_line,
                "time_ok_total": int(diag["csv_rows_time_ok"]),
                "preview": "",
                "last_observed": last_observed_scan,
            }
        )

        db.update_import_batch_row_count(conn, batch_id, total)
        conn.commit()
        obs_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            ingest_bytes = int(path.stat().st_size)
        except OSError:
            ingest_bytes = 0
        db.update_logger(
            logger_device_id,
            last_comm_at=obs_now,
            last_ingest_at=obs_now,
            last_ingest_bytes=ingest_bytes,
        )
        return {
            "import_batch_id": batch_id,
            "rows_inserted": total,
            "source_path": str(path),
            "logger_device_id": logger_device_id,
            "incremental": incremental,
            "diag": diag,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    ver = collector_version.VERSION if collector_version else "?"
    p = argparse.ArgumentParser(
        prog="measurement_ingest.py",
        description="자동DB업로드프로그램 - CSV 측정값을 DB에 적재합니다.",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {ver}",
    )
    p.add_argument("--logger", type=int, required=True, help="logger_device.id")
    p.add_argument("--csv", type=Path, required=True, help="CSV 파일 경로")
    p.add_argument(
        "--time-col",
        type=int,
        default=None,
        help="시각 열 인덱스 (미지정 시 DB logger_device.time_column_index)",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="증분 생략: DB에 이미 있는 (센서, 시각)은 INSERT OR IGNORE로 건너뜀",
    )
    p.add_argument("--encoding", default="utf-8-sig")
    p.add_argument("--note", default=None)
    args = p.parse_args()
    db.init_database()
    out = ingest_csv_for_logger(
        args.logger,
        args.csv,
        time_column=args.time_col,
        encoding=args.encoding,
        note=args.note,
        incremental=not args.full,
    )
    print(out)


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        from measurement_ingest_gui import run_gui

        run_gui()
    else:
        main()
