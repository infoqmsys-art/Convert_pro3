"""
웹/DB에 등록된 로거의 folder_path 를 기준으로 폴더·파일을 스캔합니다.

전제 (말씀하신 흐름과 맞춤):
  - 현장·로거·로거종류·로거번호(보통 뒤 4자리)은 웹에서 저장 → DB 반영
  - 레거시 수집 프로그램을 잠시 멈춘 뒤, 해당 로거에 읽을 폴더 경로를 등록하면
    `logger_device.folder_path` 에 저장됨
  - 이 스크립트는 그 경로가 가리키는 위치가 있는지, 안에 어떤 파일이 있는지 확인
  - 「어떤 열을 읽을지」는 센서 설정(sensor_channel) 연동 시 추가 예정

사용 (저장소 루트 또는 measurement_portal/SurveyMgmtPortal 에서):
  python scripts/read_logger_folders.py
  python scripts/read_logger_folders.py --include-inactive
  python scripts/read_logger_folders.py --only-missing-path

DB 경로: 환경변수 SURVEY_PORTAL_DB (미설정 시 data/survey_portal.sqlite3)
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

# measurement_portal/SurveyMgmtPortal 루트의 db 모듈
_PORTAL_ROOT = Path(__file__).resolve().parent.parent
if str(_PORTAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_PORTAL_ROOT))

import db  # noqa: E402


@dataclass
class LoggerRow:
    id: int
    name: str
    logger_kind: str | None
    serial_number: str | None
    is_active: int
    folder_path: str | None
    site_name: str
    site_code: str | None
    org_name: str


def _fetch_loggers(
    conn: sqlite3.Connection,
    *,
    active_only: bool,
    only_missing_path: bool,
) -> list[LoggerRow]:
    cur = conn.execute(
        """
        SELECT ld.id, ld.name, ld.logger_kind, ld.serial_number,
               COALESCE(ld.is_active, 1) AS is_active,
               ld.folder_path,
               s.name AS site_name, s.site_code AS site_code, o.name AS org_name
        FROM logger_device ld
        JOIN site s ON s.id = ld.site_id
        JOIN organization o ON o.id = s.organization_id
        ORDER BY o.name, s.name, ld.name
        """
    )
    out: list[LoggerRow] = []
    for r in cur.fetchall():
        row = LoggerRow(
            id=r["id"],
            name=r["name"],
            logger_kind=r["logger_kind"],
            serial_number=r["serial_number"],
            is_active=int(r["is_active"]),
            folder_path=r["folder_path"],
            site_name=r["site_name"],
            site_code=r["site_code"],
            org_name=r["org_name"],
        )
        if active_only and row.is_active != 1:
            continue
        path_ok = bool(row.folder_path and str(row.folder_path).strip())
        if only_missing_path and path_ok:
            continue
        if only_missing_path and not path_ok:
            out.append(row)
            continue
        if not only_missing_path:
            out.append(row)
    return out


def _resolve_path(raw: str) -> Path:
    s = os.path.expandvars(os.path.expanduser(raw.strip()))
    return Path(s)


def _scan_target(path: Path) -> dict:
    """파일이면 그 파일, 디렉터리면 직접 자식 파일 일부 요약."""
    info: dict = {"exists": path.exists(), "is_file": False, "is_dir": False}
    if not path.exists():
        info["error"] = "경로 없음"
        return info
    if path.is_file():
        info["is_file"] = True
        st = path.stat()
        info["size"] = st.st_size
        info["mtime"] = int(st.st_mtime)
        return info
    if path.is_dir():
        info["is_dir"] = True
        try:
            files = [p for p in path.iterdir() if p.is_file()]
        except OSError as e:
            info["error"] = str(e)
            return info
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        info["file_count"] = len(files)
        info["sample_files"] = [
            {"name": p.name, "size": p.stat().st_size, "mtime": int(p.stat().st_mtime)}
            for p in files[:15]
        ]
        return info
    info["error"] = "파일도 디렉터리도 아님"
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description="DB 로거 folder_path 스캔")
    ap.add_argument(
        "--include-inactive",
        action="store_true",
        help="사용(is_active=0) 로거도 포함",
    )
    ap.add_argument(
        "--only-missing-path",
        action="store_true",
        help="folder_path 가 비어 있는 로거만 목록",
    )
    args = ap.parse_args()

    conn = db.connect()
    try:
        rows = _fetch_loggers(
            conn,
            active_only=not args.include_inactive,
            only_missing_path=args.only_missing_path,
        )
    finally:
        conn.close()

    print(f"DB: {db.get_db_path()}", flush=True)
    print(f"대상 로거: {len(rows)}건\n", flush=True)

    for row in rows:
        kind = row.logger_kind or "manual"
        serial = row.serial_number or "-"
        site_c = row.site_code or "-"
        head = f"[{row.org_name}] {row.site_name} (코드:{site_c}) / {row.name} | {kind} | 로거번호:{serial}"
        print(head, flush=True)

        raw = (row.folder_path or "").strip()
        if not raw:
            print("  → folder_path 미등록 (수집 프로그램에서 경로 저장 후 다시 실행)", flush=True)
            print(flush=True)
            continue

        p = _resolve_path(raw)
        print(f"  → path: {p}", flush=True)
        sc = _scan_target(p)
        if "error" in sc:
            print(f"  → {sc['error']}", flush=True)
        elif sc.get("is_file"):
            print(
                f"  → 파일, size={sc['size']} byte, mtime={sc['mtime']}",
                flush=True,
            )
        elif sc.get("is_dir"):
            print(f"  → 폴더, 파일 수(직접 자식)={sc['file_count']}", flush=True)
            for sf in sc.get("sample_files") or []:
                print(
                    f"     · {sf['name']}  ({sf['size']} byte)",
                    flush=True,
                )
        print(flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
