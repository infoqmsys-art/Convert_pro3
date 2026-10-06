"""관수구 1차(EL_GWAN 설정 파일) 원본을 2026-09-01 00:00 기준으로 맞춘다.

    python tools\\gwan_prepare_raw.py            (미리보기)
    python tools\\gwan_prepare_raw.py --apply    (바꿀 파일은 먼저 백업 폴더로 복사)
    python tools\\gwan_prepare_raw.py --move-converted C:\\DATA\\Convertfile --apply

- 09-01 00:00 이전 행은 지운다.
- 첫 행이 09-01 00:00 보다 늦으면, 첫 행을 본떠 09-01 00:00 부터 매시간 행을 앞에 넣는다.
  EL_GWAN·CR_GWAN 은 원값을 안 보므로 시각만 있으면 된다.
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


def plan_file(path: str, cutoff: datetime = CUTOFF) -> tuple[list[str], int, int]:
    """(새 줄 목록, 지운 행 수, 앞에 넣은 행 수). 바꿀 게 없으면 지운·넣은 행이 0."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        lines = f.read().splitlines()
    head: list[str] = []
    body = lines
    if lines and FileProcessor._parse_source_line_ts(lines[0]) is None:
        head, body = lines[:1], lines[1:]

    kept, dropped = [], 0
    for line in body:
        ts = FileProcessor._parse_source_line_ts(line) if line.strip() else None
        if ts is not None and ts < cutoff:
            dropped += 1
        else:
            kept.append(line)

    first = next((ln for ln in kept if FileProcessor._parse_source_line_ts(ln)), None)
    added: list[str] = []
    if first:
        first_ts = FileProcessor._parse_source_line_ts(first)
        ts_text, rest = first.split(",", 1)
        fmt = "%Y-%m-%d %H:%M:%S" if ts_text.strip().count(":") == 2 else "%Y-%m-%d %H:%M"
        t = cutoff
        while t + timedelta(minutes=30) < first_ts:
            added.append(f"{t.strftime(fmt)},{rest}")
            t += timedelta(hours=1)
    return head + added + kept, dropped, len(added)


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
        new_lines, dropped, added = plan_file(p)
        if dropped or added:
            plans[fn] = (new_lines, dropped, added)
            print(f"  {fn}: 09-01 이전 {dropped}행 삭제, 앞에 {added}행 추가")
    if not plans:
        print("바꿀 파일 없음")
        return 0
    if not args.apply:
        print("미리보기. 적용하려면 --apply")
        return 0

    bak = os.path.join(os.path.dirname(raw_dir.rstrip("\\/")), f"{FOLDER}_bak-{datetime.now():%Y%m%d-%H%M%S}")
    os.makedirs(bak)
    for fn, (new_lines, _d, _a) in plans.items():
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
