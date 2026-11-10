"""EL_ST10: 10분 정거장 경사는 초기치 근처만. `python tests/test_el_st10.py`"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.file_processor import STANDARD_HEADER  # noqa: E402
from core.sensor_processor import SensorProcessor  # noqa: E402

TILT_L_MM = 1000.0
MGMT_1ST_MM = 0.5
BASE = -0.2146
CAP = 0.0003


def _frame(start: str, periods: int, freq: str, raw: float = 3.7) -> pd.DataFrame:
    ts = pd.date_range(start, periods=periods, freq=freq)
    df = pd.DataFrame({i: [0.0] * periods for i in range(24)})
    df[0] = ts.strftime("%Y-%m-%d %H:%M:%S")
    df[13] = raw
    df[14] = raw * -2
    return df


def _cfg(file_key: str, slot: str = "degreeX", base: float = BASE, scale=1.0) -> dict:
    return {
        "mode": "EL_ST10",
        "col_idx": 13 if slot == "degreeX" else 14,
        "slot": slot,
        "base": base,
        "scale": scale,
        "__file_key__": file_key,
        "__logger_number__": "",
    }


def _gen(df: pd.DataFrame, cfg: dict) -> np.ndarray:
    return SensorProcessor(logger=None).generate_EL_ST10(df, cfg).to_numpy()


def test_deterministic_batch_and_raw() -> None:
    df = _frame("2026-11-01", 144 * 20, "10min")
    cfg = _cfg("QM/정거장/A/0000000001.csv")
    a = _gen(df, cfg)
    assert np.array_equal(a, _gen(df, cfg))
    parts = [_gen(df.iloc[i : i + 100].reset_index(drop=True), cfg) for i in range(0, len(df), 100)]
    assert np.array_equal(a, np.concatenate(parts))
    spiky = df.copy()
    spiky.loc[::3, 13] = 99.0
    assert np.array_equal(a, _gen(spiky, cfg))


def test_scale_zero_and_cap() -> None:
    df = _frame("2026-11-01", 144 * 90, "10min")
    assert np.all(_gen(df, _cfg("x", scale=0.0)) == BASE)
    out = _gen(df, _cfg("QM/정거장/A/0000000008.csv"))
    delta = out - BASE
    assert np.max(np.abs(delta)) <= CAP + 1e-15
    mm = TILT_L_MM * np.deg2rad(np.abs(delta))
    assert mm.max() < MGMT_1ST_MM * 0.02, mm.max()
    day = delta.reshape(-1, 144).mean(axis=1)
    assert np.max(np.abs(day)) < 0.00008, np.max(np.abs(day))
    print(f"  90일 10분 |Δ|° max {np.abs(delta).max():.5f} (mm {mm.max():.4f}), 하루평균 max {np.abs(day).max():.6f}")


def test_ten_min_matches_hourly_clock() -> None:
    """같은 시각은 10분이든 1시간이든 같은 값. 행 수가 폭을 키우지 않는다."""
    df10 = _frame("2026-11-01", 144 * 3, "10min")
    df60 = _frame("2026-11-01", 24 * 3, "h")
    cfg = _cfg("QM/정거장/A/0000000002.csv")
    assert np.allclose(_gen(df10, cfg)[::6], _gen(df60, cfg))


def test_sensors_differ_and_carry_ignored() -> None:
    df = _frame("2026-11-01", 144 * 2, "10min")
    x = _gen(df, _cfg("QM/정거장/A/0000000003.csv", "degreeX"))
    y = _gen(df, _cfg("QM/정거장/A/0000000003.csv", "degreeY", base=0.1))
    other = _gen(df, _cfg("QM/정거장/A/0000000099.csv", "degreeX"))
    assert not np.array_equal(x - x[0], other - other[0])
    assert not np.allclose(x - BASE, y - 0.1)

    file_cfg = {
        "__file_key__": "QM/정거장/A/0000000003.csv",
        "__last_converted_row__": {STANDARD_HEADER[13]: BASE - 0.05},
        "degreeX": {"mode": "EL_ST10", "base": BASE, "scale": "1", "decimal": "4"},
        "degreeY": {"mode": "PASS"},
    }
    sp = SensorProcessor(logger=None)
    got = sp.process(df.copy(), file_cfg).iloc[:, 13].to_numpy()
    assert np.allclose(got, x)
    assert np.max(np.abs(got - BASE)) <= CAP + 1e-15


def test_noise_mix_and_regen() -> None:
    df = _frame("2026-11-01", 144 * 30, "10min", raw=0.0)
    cfg = _cfg("QM/정거장/A/0000000004.csv")
    delta = _gen(df, cfg) - BASE
    zero = np.mean(np.abs(delta) < 1e-15)
    big = np.mean(np.abs(delta) > 0.0001 + 1e-15)
    assert 0.25 < zero < 0.40, zero
    assert 0.01 < big < 0.08, big

    sp = SensorProcessor(logger=None)
    file_cfg = {
        "__file_key__": cfg["__file_key__"],
        "degreeX": {"mode": "EL_ST10", "base": BASE, "scale": 1, "decimal": "4", "label": "ELX"},
        "degreeY": {"mode": "EL", "base": 1.5},
    }
    filled = df.copy()
    filled.iloc[:, 13] = 0.0
    filled.iloc[:, 14] = 8.0
    out = sp.regen_time_only(filled, file_cfg)
    assert np.allclose(out.iloc[:, 13].to_numpy(), _gen(df, cfg))
    assert np.allclose(out.iloc[:, 14].to_numpy(), 8.0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
