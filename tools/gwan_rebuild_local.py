"""관수구 1차 64개: zip 원본을 정리하고 로컬에서 처음부터 변환해 결과를 점검한다.

    python tools\\gwan_rebuild_local.py --zip C:\\Users\\qm202\\Downloads\\SAEGL-2026.zip

- 작업 폴더(--work) 아래 raw/ 에 대상 파일만 풀고 gwan_prepare_raw 와 같이 09-01 00:00 에 맞춘다.
- config 는 포털 사본(data/convert_pro_remote/config.json)을 읽기만 한다.
- convert/ 에 새로 변환하고 파일별 행 수·시간 간격·변동폭을 출력한다.
서버 파일·포털 DB 는 건드리지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.file_processor import FileProcessor  # noqa: E402
from core.fill_interval_processor import FillIntervalProcessor  # noqa: E402
from core.sensor_processor import SensorProcessor  # noqa: E402
from tools.gwan_prepare_raw import COMPANY, CUTOFF, FOLDER, SITE, describe, plan_file  # noqa: E402

PORTAL_CONFIG = r"C:\projects\QMWebportal\data\convert_pro_remote\config.json"


class _Log:
    def __init__(self) -> None:
        self.warn: list[str] = []

    def log(self, msg, level="INFO"):
        if level in ("WARN", "ERROR"):
            self.warn.append(f"[{level}] {msg}")


class _Cfg:
    def __init__(self, data: dict) -> None:
        self.data = data


class _Tree:
    def __init__(self, cfg: _Cfg) -> None:
        self.cfg = cfg

    def get_site_time_block_future(self, company, site):
        return bool(self.cfg.data.get(company, {}).get(site, {}).get("__time_block_future__"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--work", default=os.path.join(os.path.expanduser("~"), "Downloads", "SAEGL-2026_work"))
    ap.add_argument("--config", default=PORTAL_CONFIG)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with open(args.config, encoding="utf-8") as f:
        data = json.load(f)
    files = data[COMPANY][SITE][FOLDER]
    targets = sorted(
        fn for fn, fc in files.items()
        if isinstance(fc, dict) and (fc.get("degreeX") or {}).get("mode") == "EL_GWAN"
    )
    print(f"대상 {len(targets)}개")

    raw_dir = os.path.join(args.work, "raw", FOLDER)
    conv_root = os.path.join(args.work, "convert")
    for d in (raw_dir, conv_root):
        if os.path.isdir(d):
            shutil.rmtree(d)
    os.makedirs(raw_dir)
    os.makedirs(conv_root)

    log = _Log()
    with zipfile.ZipFile(args.zip) as zf:
        for fn in targets:
            with open(os.path.join(raw_dir, fn), "wb") as out:
                out.write(zf.read(f"{FOLDER}/{fn}"))

    data[COMPANY][SITE][FOLDER]["__absolute_path__"] = raw_dir
    cfg = _Cfg(data)
    fp = FileProcessor(cfg, _Tree(cfg), SensorProcessor(logger=None), FillIntervalProcessor(logger=None), log, convert_root=conv_root)
    fp.skip_monitoring_cache = True

    for fn in targets:
        p = os.path.join(raw_dir, fn)
        new_lines, n = plan_file(p, CUTOFF)
        if any(n.values()):
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(new_lines) + "\n")
            print(f"원본 정리 {fn}: {describe(n)}")

    results = {}
    for fn in targets:
        results[fn] = fp.convert_file(COMPANY, SITE, FOLDER, fn)
    print("변환 결과:", {k: list(results.values()).count(k) for k in set(results.values())})

    outs = {}
    for dp, _dn, fns in os.walk(conv_root):
        for fn in fns:
            outs[fn] = os.path.join(dp, fn)

    print("\n파일 행수 첫행 끝행 | 정시아님 간격>1h | ELX Δmax° ELY Δmax° CR Δmax | 끝 같은값 연속")
    for fn in targets:
        p = outs.get(fn)
        if not p:
            print(f"{fn[6:10]} 변환본 없음 ({results[fn]})")
            continue
        df = pd.read_csv(p)
        ts = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed")
        offmin = int(((ts.dt.minute != 0) | (ts.dt.second != 0)).sum())
        gaps = int((ts.diff().dt.total_seconds() > 3600).sum())
        x = df.iloc[:, 13].to_numpy(float)
        y = df.iloc[:, 14].to_numpy(float)
        c = df.iloc[:, 16].to_numpy(float)
        same = 0
        for i in range(len(df) - 1, 0, -1):
            if x[i] == x[i - 1] and y[i] == y[i - 1] and c[i] == c[i - 1]:
                same += 1
            else:
                break
        flag = "  <<" if offmin or gaps or len(df) < 850 or same > 6 else ""
        print(
            f"{fn[6:10]} {len(df):4d} {ts.iloc[0]:%m-%d %H:%M} {ts.iloc[-1]:%m-%d %H:%M} | {offmin:3d} {gaps:3d} | "
            f"{np.abs(x - x[0]).max():.4f} {np.abs(y - y[0]).max():.4f} {np.abs(c - c[0]).max():.4f} | {same}{flag}"
        )
    if log.warn:
        print("\n경고:")
        for w in log.warn[:20]:
            print(" ", w)
    print(f"\n원본 {raw_dir}\n변환본 {conv_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
