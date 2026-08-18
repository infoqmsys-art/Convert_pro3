"""
Neo Blast (.blast / .txt) 로그 → 마스터 CSV 통합.

출력 7열: START_TIME·END_TIME(기존 변환본 timestamp 형식), VelPeak_X/Y/Z, PVS_Peak, Kine
- 시간 형식: YYYY-MM-DD H:MM (초 없음·시 앞자리 0 생략) — file_processor 변환본과 동일
- 구분자: 쉼표(,) — 탭/세미콜론 미사용, encoding utf-8-sig
- VelPeak(Hold)_* 우선, 없으면 PEAKVEL X|Y|Z 백업
- PVS는 XYZ로 √(X²+Y²+Z²) 재계산; __nb_pvs_limit__/__nb_kine_limit__ 초과 시 비율 보정
- 중복 판별·정렬: End_Time 기준
- 출력 인코딩: utf-8-sig (Excel 호환)
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

import pandas as pd

NB_CSV_COLUMNS = [
    "START_TIME",
    "END_TIME",
    "VelPeak_X",
    "VelPeak_Y",
    "VelPeak_Z",
    "PVS_Peak",
    "Kine",
]

NB_SOURCE_EXTENSIONS = (".blast", ".txt")
NB_PVS_TO_KINE = 0.1
NB_CSV_SEP = ","

_RE_START = re.compile(
    r"START\s+(\d{4}-\d{2}-\d{2}\s+(?:AM|PM)\s+\d{1,2}:\d{2}:\d{2})",
    re.IGNORECASE,
)
_RE_END = re.compile(
    r"END\s+(\d{4}-\d{2}-\d{2}\s+(?:AM|PM)\s+\d{1,2}:\d{2}:\d{2})",
    re.IGNORECASE,
)
_RE_VH_X = re.compile(r"VelPeak\(Hold\)_X\s+([\d.]+)", re.IGNORECASE)
_RE_VH_Y = re.compile(r"VelPeak\(Hold\)_Y\s+([\d.]+)", re.IGNORECASE)
_RE_VH_Z = re.compile(r"VelPeak\(Hold\)_Z\s+([\d.]+)", re.IGNORECASE)
_RE_PEAKVEL = re.compile(
    r"PEAKVEL\s+([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)",
    re.IGNORECASE,
)
_RE_PEAKVECT = re.compile(r"PEAKVECT\s+([\d.]+)", re.IGNORECASE)


def nb_master_filename(folder_name: str) -> str:
    """NB 로거 마스터 CSV 파일명."""
    base = (folder_name or "neo_blast").strip() or "neo_blast"
    return f"{base}_nb.csv"


def normalize_nb_time(value: str | None) -> str:
    """시각 → 24시간 비교·정렬 키 (YYYY-MM-DD HH:MM:SS). Excel 축약 형식도 통일."""
    if value is None:
        return ""
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return ""
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    raw = str(value).strip()
    if not raw or raw.lower() in ("nan", "nat", "none"):
        return ""

    cleaned = re.sub(r"\s+", " ", raw)
    for fmt in (
        "%Y-%m-%d %p %I:%M:%S",
        "%Y-%m-%d %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    m = re.match(
        r"(\d{4}-\d{2}-\d{2})\s+(AM|PM)\s+(\d{1,2}):(\d{2}):(\d{2})",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        try:
            dt = datetime.strptime(
                f"{m.group(1)} {m.group(3)}:{m.group(4)}:{m.group(5)} {m.group(2).upper()}",
                "%Y-%m-%d %I:%M:%S %p",
            )
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    # Excel 등으로 초가 빠지거나 시가 한 자리인 경우: 2026-06-11 4:56 / 4:56:47
    m = re.match(
        r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$",
        cleaned,
    )
    if m:
        hour, minute, second = int(m.group(2)), m.group(3), m.group(4) or "00"
        return f"{m.group(1)} {hour:02d}:{minute}:{second}"

    return raw


def format_convert_timestamp(value: str | None) -> str:
    """
    기존 변환본 timestamp 열과 동일 형식.
    예) 2026-01-22 0:00, 2026-06-11 4:56 — YYYY-MM-DD H:MM (초 없음, 시 앞자리 0 생략)
    """
    full = normalize_nb_time(value)
    if not full:
        return ""
    try:
        dt = datetime.strptime(full, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return full
    return f"{dt.strftime('%Y-%m-%d')} {dt.hour}:{dt.minute:02d}"


def nb_dedup_key(value: str | None) -> str:
    """END_TIME 중복 판별 키 (분 단위, 변환본 timestamp 형식)."""
    return format_convert_timestamp(value)


def _nb_sort_timestamp(value: str | None) -> pd.Timestamp:
    """정렬용 END_TIME → Timestamp."""
    full = normalize_nb_time(value)
    if not full:
        return pd.Timestamp.max
    try:
        return pd.Timestamp(datetime.strptime(full, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return pd.Timestamp.max


def format_kine_from_pvs(pvs_str: str | None) -> str:
    """PVS(mm/s) × 0.1 → Kine."""
    if pvs_str is None or str(pvs_str).strip() == "":
        return ""
    try:
        v = float(pvs_str) * NB_PVS_TO_KINE
    except (TypeError, ValueError):
        return ""
    return _fmt_nb_number(v)


def _fmt_nb_number(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def compute_pvs_from_xyz(vx: float, vy: float, vz: float) -> float:
    """√(X²+Y²+Z²)."""
    return (vx * vx + vy * vy + vz * vz) ** 0.5


def resolve_nb_pvs_limit(
    pvs_limit: float | None = None,
    kine_limit: float | None = None,
) -> float | None:
    """
    한도(PVS mm/s). __nb_pvs_limit__ 우선, 없으면 __nb_kine_limit__ / 0.1.
    예: Kine 0.20 → PVS 2.0, Kine 0.25 → PVS 2.5.
    """
    try:
        if pvs_limit is not None and float(pvs_limit) > 0:
            return float(pvs_limit)
    except (TypeError, ValueError):
        pass
    try:
        if kine_limit is not None and float(kine_limit) > 0:
            return float(kine_limit) / NB_PVS_TO_KINE
    except (TypeError, ValueError):
        pass
    return None


def apply_pvs_ratio_cap(
    vx: float,
    vy: float,
    vz: float,
    pvs: float,
    limit: float,
) -> tuple[float, float, float, float, bool]:
    """PVS가 limit 초과 시 세 축을 limit/PVS 비율로 축소. (x,y,z,pvs,scaled)."""
    if limit <= 0 or pvs <= 0 or pvs <= limit:
        return vx, vy, vz, pvs, False
    scale = limit / pvs
    return vx * scale, vy * scale, vz * scale, limit, True


def _last_data_section(text: str) -> str:
    marker = "The Last Data"
    idx = text.find(marker)
    if idx >= 0:
        return text[idx:]
    return text


def _parse_vel_peaks(text: str) -> tuple[str, str, str]:
    section = _last_data_section(text)
    hx = _RE_VH_X.search(section)
    hy = _RE_VH_Y.search(section)
    hz = _RE_VH_Z.search(section)
    if hx and hy and hz:
        return hx.group(1), hy.group(1), hz.group(1)
    backup = _RE_PEAKVEL.search(text)
    if backup:
        return backup.group(1), backup.group(2), backup.group(3)
    return "", "", ""


def parse_neo_blast_file(file_path: str) -> dict[str, str] | None:
    """단일 .blast / .txt 파싱. 실패 시 None."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return None

    if not text.strip():
        return None

    start_m = _RE_START.search(text)
    end_m = _RE_END.search(text)
    if not end_m:
        return None

    vx, vy, vz = _parse_vel_peaks(text)
    pvs_m = _RE_PEAKVECT.search(text)
    pvs = pvs_m.group(1) if pvs_m else ""

    return {
        "Start_Time": start_m.group(1).strip() if start_m else "",
        "End_Time": end_m.group(1).strip(),
        "VelPeak_X": vx,
        "VelPeak_Y": vy,
        "VelPeak_Z": vz,
        "PVS_Peak": pvs,
    }


def blast_to_csv_row(
    parsed: dict[str, str],
    *,
    pvs_limit: float | None = None,
) -> dict[str, str] | None:
    """
    파싱 결과 → CSV 7열 (START_TIME·END_TIME 24h).
    XYZ가 있으면 PVS=√(X²+Y²+Z²)로 재계산하고, pvs_limit 초과 시 비율 보정.
    """
    end_24 = normalize_nb_time(parsed.get("End_Time"))
    if not end_24:
        return None

    sx = (parsed.get("VelPeak_X") or "").strip()
    sy = (parsed.get("VelPeak_Y") or "").strip()
    sz = (parsed.get("VelPeak_Z") or "").strip()
    pvs_raw = (parsed.get("PVS_Peak") or "").strip()

    fx = fy = fz = None
    try:
        if sx and sy and sz:
            fx, fy, fz = float(sx), float(sy), float(sz)
    except (TypeError, ValueError):
        fx = fy = fz = None

    if fx is not None:
        pvs = compute_pvs_from_xyz(fx, fy, fz)
        if pvs_limit is not None:
            fx, fy, fz, pvs, _ = apply_pvs_ratio_cap(fx, fy, fz, pvs, float(pvs_limit))
        pvs_out = _fmt_nb_number(pvs)
        return {
            "START_TIME": format_convert_timestamp(parsed.get("Start_Time")),
            "END_TIME": format_convert_timestamp(parsed.get("End_Time")),
            "VelPeak_X": _fmt_nb_number(fx),
            "VelPeak_Y": _fmt_nb_number(fy),
            "VelPeak_Z": _fmt_nb_number(fz),
            "PVS_Peak": pvs_out,
            "Kine": format_kine_from_pvs(pvs_out),
        }

    pvs_out = pvs_raw
    if pvs_out and pvs_limit is not None:
        try:
            pvs_v = float(pvs_out)
            if pvs_v > float(pvs_limit) > 0:
                pvs_out = _fmt_nb_number(float(pvs_limit))
        except (TypeError, ValueError):
            pass

    return {
        "START_TIME": format_convert_timestamp(parsed.get("Start_Time")),
        "END_TIME": format_convert_timestamp(parsed.get("End_Time")),
        "VelPeak_X": sx,
        "VelPeak_Y": sy,
        "VelPeak_Z": sz,
        "PVS_Peak": pvs_out,
        "Kine": format_kine_from_pvs(pvs_out),
    }


def list_neo_blast_source_files(source_dir: str) -> list[str]:
    if not source_dir or not os.path.isdir(source_dir):
        return []
    out: list[str] = []
    for name in sorted(os.listdir(source_dir)):
        low = name.lower()
        if low.endswith(NB_SOURCE_EXTENSIONS):
            out.append(os.path.join(source_dir, name))
    return out


def _end_time_series_from_df(df: pd.DataFrame) -> pd.Series | None:
    """중복·정렬 키용 END_TIME 열."""
    for col in ("END_TIME", "End_Time", "timestamp", "Time"):
        if col in df.columns:
            return df[col]
    if "Start_Time" in df.columns:
        return df["Start_Time"]
    return None


def _start_time_series_from_df(df: pd.DataFrame) -> pd.Series:
    for col in ("START_TIME", "Start_Time"):
        if col in df.columns:
            return df[col]
    return pd.Series([""] * len(df), index=df.index)


def load_existing_times(csv_path: str) -> set[str]:
    """기존 CSV의 END_TIME 중복 키 집합 (분 단위)."""
    df = _finalize_nb_dataframe(_read_existing_csv(csv_path))
    return set(df["END_TIME"].map(nb_dedup_key).tolist())


def _read_existing_csv(csv_path: str) -> pd.DataFrame:
    if not csv_path or not os.path.isfile(csv_path):
        return pd.DataFrame(columns=NB_CSV_COLUMNS)
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
    except Exception:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
        except Exception:
            return pd.DataFrame(columns=NB_CSV_COLUMNS)

    end_series = _end_time_series_from_df(df)
    if end_series is None:
        return pd.DataFrame(columns=NB_CSV_COLUMNS)

    out = pd.DataFrame(
        {
            "START_TIME": _start_time_series_from_df(df).map(
                lambda v: normalize_nb_time(str(v)) if str(v).strip() else ""
            ),
            "END_TIME": end_series.map(lambda v: normalize_nb_time(str(v))),
            "VelPeak_X": df.get("VelPeak_X", df.get("X", "")),
            "VelPeak_Y": df.get("VelPeak_Y", df.get("Y", "")),
            "VelPeak_Z": df.get("VelPeak_Z", df.get("Z", "")),
            "PVS_Peak": df.get("PVS_Peak", df.get("PVS", "")),
            "Kine": df.get("Kine", ""),
        }
    )
    if out["Kine"].astype(str).str.strip().eq("").any():
        mask = out["Kine"].astype(str).str.strip() == ""
        out.loc[mask, "Kine"] = out.loc[mask, "PVS_Peak"].map(format_kine_from_pvs)

    for col in NB_CSV_COLUMNS:
        if col not in out.columns:
            out[col] = ""

    return out[NB_CSV_COLUMNS]


def _finalize_nb_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """END_TIME 정규화 → 시간순 정렬 → 동일 END_TIME 중복 제거(먼저 들어간 행 유지)."""
    if df.empty:
        return pd.DataFrame(columns=NB_CSV_COLUMNS)

    out = df.copy()
    out["_sort_end"] = out["END_TIME"].map(_nb_sort_timestamp)
    out = out[out["END_TIME"].astype(str).str.strip() != ""]
    out = out[out["_sort_end"] != pd.Timestamp.max]
    if out.empty:
        return pd.DataFrame(columns=NB_CSV_COLUMNS)

    out = out.sort_values("_sort_end", kind="mergesort")
    out = out.drop_duplicates(subset=["_sort_end"], keep="last")
    out["START_TIME"] = out["START_TIME"].map(format_convert_timestamp)
    out["END_TIME"] = out["END_TIME"].map(format_convert_timestamp)
    return out.drop(columns=["_sort_end"])[NB_CSV_COLUMNS].reset_index(drop=True)


def sync_neo_blast_folder(
    source_dir: str,
    out_csv_path: str,
    logger=None,
    *,
    pvs_limit: float | None = None,
    kine_limit: float | None = None,
) -> dict[str, Any]:
    """
    source_dir 의 .blast/.txt 를 스캔해 out_csv_path 에 누적 저장.
    pvs_limit / kine_limit: 한도 초과 시 XYZ 비율 보정 (추출 시점).
    Returns: {parsed, appended, skipped_dup, failed, total_rows, scaled, pvs_limit}
    """
    limit = resolve_nb_pvs_limit(pvs_limit, kine_limit)
    os.makedirs(os.path.dirname(out_csv_path) or ".", exist_ok=True)
    old_df = _finalize_nb_dataframe(_read_existing_csv(out_csv_path))
    rows_by_key: dict[str, dict[str, str]] = {
        nb_dedup_key(r["END_TIME"]): {col: str(r[col]) for col in NB_CSV_COLUMNS}
        for _, r in old_df.iterrows()
    }
    initial_keys = set(rows_by_key.keys())
    parsed = appended = skipped_dup = failed = scaled = 0

    for fp in list_neo_blast_source_files(source_dir):
        try:
            raw = parse_neo_blast_file(fp)
            if not raw:
                failed += 1
                if logger:
                    logger.log(f"[NB] 파싱 실패(필수 항목 없음): {fp}", level="WARN")
                continue
            row = blast_to_csv_row(raw, pvs_limit=limit)
            if not row:
                failed += 1
                continue
            if limit is not None:
                try:
                    raw_xyz = (
                        float(raw.get("VelPeak_X") or 0),
                        float(raw.get("VelPeak_Y") or 0),
                        float(raw.get("VelPeak_Z") or 0),
                    )
                    raw_pvs = compute_pvs_from_xyz(*raw_xyz)
                    if raw_pvs > limit:
                        scaled += 1
                except (TypeError, ValueError):
                    pass
            parsed += 1
            key = nb_dedup_key(row["END_TIME"])
            if key in initial_keys:
                skipped_dup += 1
            else:
                appended += 1
                initial_keys.add(key)
            rows_by_key[key] = row
        except Exception as e:
            failed += 1
            if logger:
                logger.log(f"[NB] 파일 처리 오류 {fp}: {e}", level="ERROR")

    merged = _finalize_nb_dataframe(pd.DataFrame(list(rows_by_key.values())))

    merged = merged[NB_CSV_COLUMNS]
    merged.to_csv(
        out_csv_path,
        index=False,
        encoding="utf-8-sig",
        sep=NB_CSV_SEP,
        lineterminator="\n",
    )

    total_rows = len(merged)
    if logger:
        lim_txt = f", PVS한도 {limit:g} (비율보정 {scaled})" if limit is not None else ""
        logger.log(
            f"[NB] 통합 완료: 파싱 {parsed}, 추가 {appended}, 중복스킵 {skipped_dup}, "
            f"실패 {failed}, CSV 총 {total_rows}행{lim_txt} → {out_csv_path}",
            level="INFO",
        )

    return {
        "parsed": parsed,
        "appended": appended,
        "skipped_dup": skipped_dup,
        "failed": failed,
        "total_rows": total_rows,
        "scaled": scaled,
        "pvs_limit": limit,
    }
