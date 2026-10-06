"""관수구 1차(EL_GWAN 설정 파일) 원본을 2026-09-01 00:00 기준으로 맞춘다.

    python tools\\gwan_prepare_raw.py            (미리보기)
    python tools\\gwan_prepare_raw.py --apply    (바꿀 파일은 먼저 백업 폴더로 복사)
    python tools\\gwan_prepare_raw.py --move-converted C:\\DATA\\Convertfile --apply

- 09-01 00:00 이전 행은 지운다.
- 첫 행이 09-01 00:00 보다 늦으면, 첫 행을 본떠 09-01 00:00 부터 매시간 행을 앞에 넣는다.
  EL_GWAN·CR_GWAN 은 원값을 안 보므로 시각만 있으면 된다.
- 시각을 읽을 수 없는 줄(통신 오류로 앞부분이 잘린 조각 등)은 지운다. 헤더 첫 줄은 남긴다.
- 시각은 그 시간 정각으로 맞춘다(02:01 → 02:00). 같은 시간에 둘 이상이면 정각에 가까운 줄만 남긴다.
- --move-converted: 대상 변환본(및 _60 사본)을 같은 폴더 옆 백업 폴더로 옮겨 처음부터 다시 변환되게 한다.
대상: config 의 SAEGIL / 관수구 / SAEGL-2026 에서 degreeX 가 EL_GWAN 인 파일. Convert Pro 는 닫고 돌린다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.file_processor import FileProcessor  # noqa: E402

COMPANY = "SAEGIL"
SITE = "서울시 종로구 관수동 129-1번지 일원 업무시설"
FOLDER = "SAEGL-2026"
CUTOFF = datetime(2026, 9, 1)


def gwan_targets(config_data: dict) -> list[str]:
    files = config_data[COMPANY][SITE][FOLDER]
    return sorted(
        fn for fn, fc in files.items()
        if isinstance(fc, dict) and (fc.get("degreeX") or {}).get("mode") == "EL_GWAN"
    )


def plan_file(path: str, cutoff: datetime = CUTOFF) -> tuple[list[str], dict]:
    """(새 줄 목록, 건수). 건수: dropped(09-01 이전) added(앞에 넣음) broken(시각 없음)
    aligned(정시로 맞춤) dup(같은 시간 중복 삭제). 모두 0 이면 바꿀 게 없다."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        lines = f.read().splitlines()
    head: list[str] = []
    body = lines
    if lines and FileProcessor._parse_source_line_ts(lines[0]) is None:
        head, body = lines[:1], lines[1:]

    n = {"dropped": 0, "added": 0, "broken": 0, "aligned": 0, "dup": 0}
    slots: dict[datetime, tuple[timedelta, str]] = {}
    for line in body:
        if not line.strip():
            continue
        ts = FileProcessor._parse_source_line_ts(line)
        if ts is None:
            n["broken"] += 1
            continue
        slot = ts.replace(minute=0, second=0, microsecond=0)
        if slot < cutoff:
            n["dropped"] += 1
            continue
        ts_text, rest = line.split(",", 1)
        if ts != slot:
            fmt = "%Y-%m-%d %H:%M:%S" if ts_text.strip().count(":") == 2 else "%Y-%m-%d %H:%M"
            line = f"{slot.strftime(fmt)},{rest}"
        dist = ts - slot
        prev = slots.get(slot)
        if prev is not None:
            n["dup"] += 1
            if prev[0] <= dist:
                continue
        slots[slot] = (dist, line)
    n["aligned"] = sum(1 for d, _l in slots.values() if d)
    kept = [slots[s][1] for s in sorted(slots)]

    added: list[str] = []
    if kept:
        first_ts = min(slots)
        ts_text, rest = kept[0].split(",", 1)
        fmt = "%Y-%m-%d %H:%M:%S" if ts_text.strip().count(":") == 2 else "%Y-%m-%d %H:%M"
        t = cutoff
        while t < first_ts:
            added.append(f"{t.strftime(fmt)},{rest}")
            t += timedelta(hours=1)
    n["added"] = len(added)
    return head + added + kept, n


def describe(n: dict) -> str:
    return (
        f"09-01 이전 {n['dropped']}행 삭제, 앞에 {n['added']}행 추가, 깨진 줄 {n['broken']}개 삭제, "
        f"정시 맞춤 {n['aligned']}행, 같은 시간 중복 {n['dup']}행 삭제"
    )


def move_converted(convert_root: str, targets: list[str], apply: bool) -> int:
    from utils.convert_paths import align60_filename, convert_out_path, site_layout_out_path

    found = []
    for fn in targets:
        for name in (fn, align60_filename(fn)):
            for p in (
                convert_out_path(convert_root, COMPANY, FOLDER, name),
                site_layout_out_path(convert_root, COMPANY, SITE, FOLDER, name),
            ):
                if os.path.exists(p) and p not in found:
                    found.append(p)
    print(f"변환본 루트 {convert_root}, 대상 {len(targets)}개, 찾은 변환본 {len(found)}개")
    for p in found[:4]:
        print(f"  {p}")
    if len(found) > 4:
        print("  ...")
    if not found or not apply:
        if found:
            print("미리보기. 옮기려면 --apply")
        return 0
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    for p in found:
        bak = os.path.join(os.path.dirname(os.path.dirname(p)), f"{FOLDER}_bak-{stamp}")
        os.makedirs(bak, exist_ok=True)
        shutil.move(p, os.path.join(bak, os.path.basename(p)))
    print(f"옮김 {len(found)}개 → {FOLDER}_bak-{stamp}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--raw", default="", help="원본 폴더 (비우면 config 의 __absolute_path__)")
    ap.add_argument("--move-converted", default="", metavar="CONVERT_ROOT", help="변환본 루트 (예 C:\\DATA\\Convertfile)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with open(args.config, encoding="utf-8") as f:
        data = json.load(f)
    targets = gwan_targets(data)
    if args.move_converted:
        return move_converted(args.move_converted, targets, args.apply)
    raw_dir = args.raw or data[COMPANY][SITE][FOLDER]["__absolute_path__"]
    print(f"원본 {raw_dir}, 대상 {len(targets)}개")

    plans = {}
    for fn in targets:
        p = os.path.join(raw_dir, fn)
        if not os.path.exists(p):
            print(f"  없음 {fn}")
            continue
        new_lines, n = plan_file(p)
        if any(n.values()):
            plans[fn] = new_lines
            print(f"  {fn}: {describe(n)}")
    if not plans:
        print("바꿀 파일 없음")
        return 0
    if not args.apply:
        print("미리보기. 적용하려면 --apply")
        return 0

    bak = os.path.join(os.path.dirname(raw_dir.rstrip("\\/")), f"{FOLDER}_bak-{datetime.now():%Y%m%d-%H%M%S}")
    os.makedirs(bak)
    for fn, new_lines in plans.items():
        p = os.path.join(raw_dir, fn)
        shutil.copy2(p, os.path.join(bak, fn))
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(new_lines) + "\n")
        os.replace(tmp, p)
    print(f"적용 {len(plans)}개, 백업 {bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
