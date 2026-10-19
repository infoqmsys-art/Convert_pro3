"""관수구: 설치일 기준 주간 원본 정리 + SET 초기치.

8월 설치 → 2026-09-01 00:00
그다음 주 설치(09/01~07) → 2026-09-08 00:00
이후도 화요일 00:00 단위로 동일.

기본은 이번 배치(8월)만 처리. 나머지 파일은 zip에서 복구하고 SET을 뺀다.
SN 공란·중복은 제외.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.file_processor import FileProcessor
from core.presets import _slot, apply_preset_to_file_cfg

ZIP_PATH = Path(r"c:\Users\qm202\Downloads\SAEGL-2026 (1).zip")
DEST = Path(r"c:\Users\qm202\Downloads\SAEGL-2026")
CONFIG_PATH = ROOT / "config.json"
XLSX = Path(r"c:\Users\qm202\Downloads\종로관수8지구_설치관리표 (1).xlsx")
COMPANY = "KD_ENG"
SITE = "관수구"
FOLDER = "SAEGL-2026"
PRESET = "관수구_경사균열"
SLOT_COLS = (("degreeX", 13), ("degreeY", 14), ("CH0", 16))
NAME_RE = re.compile(r"^121234(\d+)\.csv$", re.I)
MAX_YEAR = 2027
WEEK0 = datetime(2026, 9, 1, 0, 0)


def logger_num(name: str) -> int | None:
    m = NAME_RE.match(name)
    return int(m.group(1)) if m else None


def parse_install(raw) -> datetime | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, datetime):
        return datetime(raw.year, raw.month, raw.day)
    if isinstance(raw, pd.Timestamp):
        if pd.isna(raw):
            return None
        return datetime(raw.year, raw.month, raw.day)
    s = str(raw).strip()
    if not s or s in ("미설치", "협의중", "공문요청", "공문필요", "협의불가", "철거예정", "설치거부", "건물없음"):
        return None
    for fmt in ("%Y.%m.%d", "%y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", s)
    if m:
        year = 2026
        ym = re.search(r"(20\d{2})", s)
        if ym:
            year = int(ym.group(1))
        return datetime(year, int(m.group(1)), int(m.group(2)))
    return None


def weekly_cutoff(install: datetime) -> datetime:
    """설치일이 속한 주간 보고서의 끊는 시각(화요일 00:00)."""
    if install < WEEK0:
        return WEEK0
    days = (install.date() - WEEK0.date()).days
    week = days // 7 + 1
    return WEEK0 + timedelta(days=7 * week)


def valid_ts(ts) -> bool:
    return ts is not None and 2000 <= ts.year <= MAX_YEAR


def first_valid_values(path: Path) -> tuple[datetime | None, dict[str, str]]:
    vals: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            ts = FileProcessor._parse_source_line_ts(line)
            if not valid_ts(ts):
                continue
            parts = [p.strip() for p in line.strip().split(",")]
            for key, idx in SLOT_COLS:
                if idx < len(parts) and parts[idx] not in ("", "nan"):
                    vals[key] = parts[idx]
            return ts, vals
    return None, vals


def drop_bad_years(path: Path) -> int:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    lines = text.splitlines(keepends=True)
    if not lines:
        return 0
    kept: list[str] = []
    start = 0
    if FileProcessor._parse_source_line_ts(lines[0]) is None:
        kept.append(lines[0])
        start = 1
    dropped = 0
    for line in lines[start:]:
        ts = FileProcessor._parse_source_line_ts(line)
        if ts is not None and not valid_ts(ts):
            dropped += 1
            continue
        kept.append(line)
    path.write_text("".join(kept), encoding="utf-8-sig")
    return dropped


def logger_from_sn(raw) -> int | None:
    """설치표 SN(260806083)의 끝 3자리 = 1212340NNN 로거번호."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        digits = re.sub(r"\D", "", s)
        if not digits:
            return None
        n = int(digits)
    if n <= 0:
        return None
    return n % 1000


def load_unique_installs() -> tuple[dict[int, datetime], list[int], list[int]]:
    """고유 SN → 설치일. 공란·중복 SN은 제외."""
    empty: list[int] = []
    if not XLSX.exists():
        raise FileNotFoundError(XLSX)
    df = pd.read_excel(XLSX)
    sn_col = "SN" if "SN" in df.columns else df.columns[2]
    date_col = "설치" if "설치" in df.columns else df.columns[3]
    sn_rows: list[tuple[int, datetime | None]] = []
    for _, row in df.iterrows():
        sn = logger_from_sn(row[sn_col])
        if sn is None:
            continue
        inst = parse_install(row[date_col])
        sn_rows.append((sn, inst))
    counts = Counter(sn for sn, _ in sn_rows)
    dupes = sorted(sn for sn, n in counts.items() if n > 1)
    unique: dict[int, datetime] = {}
    for sn, inst in sn_rows:
        if counts[sn] != 1:
            continue
        if inst is None:
            empty.append(sn)
            continue
        unique[sn] = inst
    return unique, dupes, empty


def blank_pass_file(existing: dict | None, n: int, order: int) -> dict:
    cfg = {
        "__order__": order,
        "__fill_interval__": 0,
        "__gen_interval__": 0,
        "__align_60__": False,
        "__is_ghost__": False,
        "__logger_number__": n,
    }
    if isinstance(existing, dict):
        for key in (
            "__order__",
            "__fill_interval__",
            "__gen_interval__",
            "__align_60__",
            "__is_ghost__",
            "__logger_number__",
        ):
            if key in existing:
                cfg[key] = existing[key]
        cfg["__logger_number__"] = n
        cfg["__order__"] = existing.get("__order__", order)
    for ch in range(8):
        cfg[f"CH{ch}"] = _slot("PASS")
    cfg["degreeX"] = _slot("PASS")
    cfg["degreeY"] = _slot("PASS")
    return cfg


def extract_zip(zip_path: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = Path(info.filename).name
            if not name.lower().endswith(".csv") or info.is_dir():
                continue
            target = dest / name
            with zf.open(info) as src, target.open("wb") as dst:
                dst.write(src.read())
    return sorted(
        [p for p in dest.glob("*.csv") if logger_num(p.name) is not None],
        key=lambda p: logger_num(p.name) or 0,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--cutoff",
        default="2026-09-01",
        help="이번에 처리할 주간 끊는 시각 (기본 2026-09-01 = 8월 설치분)",
    )
    ap.add_argument("--zip", dest="zip_path", default=str(ZIP_PATH))
    ap.add_argument("--dest", default=str(DEST))
    ap.add_argument(
        "--write-config",
        action="store_true",
        help="이 PC의 config.json도 같이 수정. 기본은 끄고, 준 파일만 고친다.",
    )
    args = ap.parse_args()
    target_cutoff = datetime.strptime(args.cutoff, "%Y-%m-%d")
    zip_path = Path(args.zip_path)
    dest = Path(args.dest)

    print("extract", zip_path, "->", dest)
    files = extract_zip(zip_path, dest)
    installs, dupes, empty_sn = load_unique_installs()
    print(f"table unique_sn={len(installs)} dupes={dupes} empty_install={len(empty_sn)}")

    batch: list[tuple[int, Path, datetime, datetime]] = []
    later: list[tuple[int, Path, datetime, datetime]] = []
    no_table: list[int] = []
    for p in files:
        n = logger_num(p.name)
        if n is None:
            continue
        inst = installs.get(n)
        if inst is None:
            no_table.append(n)
            continue
        cut = weekly_cutoff(inst)
        if cut == target_cutoff:
            batch.append((n, p, inst, cut))
        else:
            later.append((n, p, inst, cut))

    print(f"files {len(files)}  this_week {len(batch)}  other_weeks {len(later)}  no_table {len(no_table)}")
    print("THIS WEEK:")
    for n, p, inst, cut in batch:
        print(f"  {n:3d} {p.name} install={inst:%Y-%m-%d} cutoff={cut:%Y-%m-%d %H:%M}")

    fp = FileProcessor(None, None, None, None, type("L", (), {"log": lambda *a, **k: None})())
    trimmed = 0
    deleted_total = 0
    empty_after: list[str] = []
    applied = 0

    patch: dict[str, dict] = {}
    folder: dict = {}
    if args.write_config:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cfg.setdefault(COMPANY, {})
        site = cfg[COMPANY].setdefault(SITE, {"__note__": ""})
        site["__require_sensor_config__"] = True
        folder = site.setdefault(
            FOLDER,
            {"__note__": "", "__absolute_path__": str(dest).replace("\\", "/"), "__is_ghost__": False},
        )
        folder["__absolute_path__"] = str(dest).replace("\\", "/")
        folder["__is_ghost__"] = False
        order = 0
        for p in files:
            n = logger_num(p.name)
            name = p.name
            prev = folder.get(name) if isinstance(folder.get(name), dict) else None
            order += 1
            folder[name] = blank_pass_file(prev, n, prev.get("__order__", order) if prev else order)

    for n, p, inst, cut in batch:
        ok, deleted = fp.trim_source_before_time(str(p), cut)
        bad = drop_bad_years(p)
        ts0, vals = first_valid_values(p)
        print(f"  trim {p.name} ok={ok} deleted={deleted} bad_year={bad} first={ts0}")
        if ok:
            trimmed += 1
            deleted_total += deleted
        if ts0 is None:
            empty_after.append(p.name)
            continue
        file_cfg = apply_preset_to_file_cfg(
            blank_pass_file(None, n, n), PRESET, keep_base=False
        )
        for key, _idx in SLOT_COLS:
            file_cfg[key]["base"] = vals.get(key, "")
        patch[p.name] = file_cfg
        if args.write_config:
            folder[p.name] = file_cfg
        applied += 1
        print(f"  preset {p.name} base={ {k: file_cfg[k].get('base') for k, _ in SLOT_COLS} }")

    patch_path = dest.parent / "SAEGL-2026_8월_설정.json"
    patch_path.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.write_config:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding="utf-8")
        print("wrote", CONFIG_PATH)
    print(
        f"done trim_files={trimmed} deleted_rows={deleted_total} "
        f"preset={applied} empty={empty_after} files={dest} patch={patch_path}"
    )


if __name__ == "__main__":
    main()
