"""EL_GWAN: 재현성, 원값 무시, 120센서 분산·상한 확인. `python tests\\test_el_gwan.py`"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.sensor_processor import SensorProcessor  # noqa: E402

TILT_L_MM = 1000.0
MGMT_1ST_MM = 0.5


def _frame(start: str, hours: int, raw_x: float = -8.3629, raw_y: float = 81.4799) -> pd.DataFrame:
    ts = pd.date_range(start, periods=hours, freq="h")
    df = pd.DataFrame({i: [0.0] * hours for i in range(24)})
    df[0] = ts.strftime("%Y-%m-%d %H:%M:%S")
    df[13] = raw_x
    df[14] = raw_y
    return df


def _cfg(file_key: str, slot: str = "degreeX", base: float = -8.3629, scale: float = 1.0) -> dict:
    return {
        "mode": "EL_GWAN",
        "col_idx": 13 if slot == "degreeX" else 14,
        "slot": slot,
        "base": base,
        "scale": scale,
        "__file_key__": file_key,
        "__logger_number__": "",
    }


def _gen(df: pd.DataFrame, cfg: dict) -> np.ndarray:
    return SensorProcessor(logger=None).generate_EL_GWAN(df, cfg).to_numpy()


def test_deterministic_and_batch_split() -> None:
    df = _frame("2026-09-01", 24 * 40)
    cfg = _cfg("QM/관수구/A/0000000001.csv")
    a = _gen(df, cfg)
    b = _gen(df, cfg)
    assert np.array_equal(a, b)
    parts = [_gen(df.iloc[i : i + 97].reset_index(drop=True), cfg) for i in range(0, len(df), 97)]
    assert np.array_equal(a, np.concatenate(parts))


def test_raw_ignored() -> None:
    df = _frame("2026-09-01", 24 * 10)
    cfg = _cfg("QM/관수구/A/0000000002.csv")
    a = _gen(df, cfg)
    spiky = df.copy()
    spiky.loc[::7, 13] = -7.9
    spiky.loc[::11, 13] = -9.4
    assert np.array_equal(a, _gen(spiky, cfg))


def test_scale_zero_is_flat() -> None:
    df = _frame("2026-09-01", 48)
    out = _gen(df, _cfg("x", scale=0.0))
    assert np.all(out == -8.3629)


def test_120_sensors_spread() -> None:
    hours = 24 * 365
    df = _frame("2026-09-01", hours)
    deltas = []
    for n in range(1, 121):
        for slot, base in (("degreeX", -8.3629), ("degreeY", 81.4799)):
            out = np.round(_gen(df, _cfg(f"QM/관수구/A/{n:010d}.csv", slot, base, 1.0 if slot == "degreeX" else 0.7)), 4)
            deltas.append(np.round(out - out[0], 4))
    d = np.array(deltas)

    peak = np.abs(d).max(axis=1)
    peak_mm = TILT_L_MM * np.deg2rad(peak)
    assert peak.max() <= 0.0041, peak.max()
    assert peak_mm.max() < MGMT_1ST_MM * 0.2, peak_mm.max()
    distinct_peaks = len(np.unique(peak))
    assert distinct_peaks >= 8, distinct_peaks
    top_share = np.bincount(np.round(peak * 1e4).astype(int)).max() / len(peak)
    assert top_share < 0.3, top_share

    for a in range(len(d) - 2):
        assert not np.array_equal(d[a], d[a + 2])

    corr = np.corrcoef(d)
    off = np.abs(corr[~np.eye(len(d), dtype=bool)])
    assert np.nanmean(off) < 0.35, np.nanmean(off)

    step = np.abs(np.diff(d, axis=1))
    small = (step <= 0.00021).mean()
    assert small > 0.95, small
    flat = (step < 0.00005).mean()
    assert 0.15 < flat < 0.75, flat

    print(
        f"  peak|Δ|° min {peak.min():.4f} / median {np.median(peak):.4f} / max {peak.max():.4f}"
        f" (mm max {peak_mm.max():.3f}), distinct {distinct_peaks}/240, top share {top_share:.2f}"
    )
    print(f"  |corr| mean {np.nanmean(off):.3f}, step≤0.0002 {small:.3f}, flat {flat:.3f}")


def _cr_cfg(file_key: str, base: float = 1.0778, scale: float = 1.0) -> dict:
    return {
        "mode": "CR_GWAN",
        "col_idx": 16,
        "slot": "CH0",
        "base": base,
        "scale": scale,
        "__file_key__": file_key,
        "__logger_number__": "",
    }


def _gen_cr(df: pd.DataFrame, cfg: dict) -> np.ndarray:
    return SensorProcessor(logger=None).generate_CR_GWAN(df, cfg).to_numpy()


def test_cr_gwan_deterministic_raw_ignored() -> None:
    df = _frame("2026-09-01", 24 * 40)
    df[16] = 1.0778
    cfg = _cr_cfg("QM/관수구/A/0000000003.csv")
    a = _gen_cr(df, cfg)
    assert np.array_equal(a, _gen_cr(df, cfg))
    parts = [_gen_cr(df.iloc[i : i + 113].reset_index(drop=True), cfg) for i in range(0, len(df), 113)]
    assert np.array_equal(a, np.concatenate(parts))
    spiky = df.copy()
    spiky.loc[::5, 16] = 9.9
    assert np.array_equal(a, _gen_cr(spiky, cfg))
    assert np.all(_gen_cr(df, _cr_cfg("x", scale=0.0)) == 1.0778)
    tilt = _gen(df, _cfg("QM/관수구/A/0000000003.csv"))
    assert not np.allclose(a - a[0], tilt - tilt[0])


def test_cr_gwan_vs_cr() -> None:
    hours = 24 * 36
    df = _frame("2026-09-01", hours)
    df[16] = 1.0778
    sp = SensorProcessor(logger=None)
    gw, cr = [], []
    for n in range(1, 121):
        out = np.round(_gen_cr(df, _cr_cfg(f"QM/관수구/A/{n:010d}.csv")), 4)
        gw.append(np.round(out - out[0], 4))
        c = np.round(sp.generate_CR(df, {"mode": "CR", "col_idx": 16, "slot": "CH0", "base": 1.0778}).to_numpy(), 4)
        cr.append(np.round(c - c[0], 4))
    gw, cr = np.array(gw), np.array(cr)

    def stats(d: np.ndarray) -> tuple[float, float, float, float]:
        step = np.abs(np.diff(d, axis=1))
        peak = np.abs(d).max(axis=1)
        return (step > 0).mean(), (step <= 0.00021).mean(), float(np.median(peak)), float(peak.max())

    g_move, g_small, g_med, g_max = stats(gw)
    c_move, c_small, c_med, c_max = stats(cr)
    assert c_move < g_move < 0.05, (c_move, g_move)
    assert g_small > 0.99, g_small
    assert g_max <= 0.0016, g_max
    assert len(np.unique(np.abs(gw).max(axis=1))) >= 5
    def mean_abs_corr(d: np.ndarray) -> float:
        with np.errstate(invalid="ignore", divide="ignore"):
            corr = np.corrcoef(d)
        return float(np.nanmean(np.abs(corr[~np.eye(len(d), dtype=bool)])))

    g_corr, c_corr = mean_abs_corr(gw), mean_abs_corr(cr)
    assert g_corr < c_corr + 0.1, (g_corr, c_corr)
    print(f"  36일 120센서: 바뀐 시간 비율 CR {c_move:.3f} / CR_GWAN {g_move:.3f}")
    print(f"  최대|Δ| 중간값 CR {c_med:.4f} / CR_GWAN {g_med:.4f}, 최대 CR {c_max:.4f} / CR_GWAN {g_max:.4f}")
    print(f"  한 시간 변화 ≤0.0002 CR_GWAN {g_small:.4f}, |corr| CR {c_corr:.3f} / CR_GWAN {g_corr:.3f}")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
