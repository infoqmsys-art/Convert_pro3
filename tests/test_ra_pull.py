# -*- coding: utf-8 -*-
"""RA: 초기치에 머물고, 1차 관리기준 근처는 초기치 쪽으로 접는지."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.sensor_processor import SensorProcessor  # noqa: E402

L_MM = 1000.0
LEVEL1_MM = 4.0
LEVEL1_DEG = LEVEL1_MM * 180.0 / (L_MM * math.pi)


def _mm(deg: float) -> float:
    return L_MM * math.sin(math.radians(deg))


def _frame(n: int) -> pd.DataFrame:
    df = pd.DataFrame({i: [0.0] * n for i in range(24)})
    df[0] = pd.date_range("2026-03-08", periods=n, freq="h").strftime("%Y-%m-%d %H:%M:%S")
    return df


def _cfg(**extra) -> dict:
    cfg = {
        "mode": "RA",
        "col_idx": 16,
        "slot": "CH0",
        "base": 0.0,
        "scale": 0.015,
    }
    cfg.update(extra)
    return cfg


def test_stays_near_initial() -> None:
    out = SensorProcessor().generate_RA(_frame(4000), _cfg())
    dev = np.abs(out.to_numpy() - 0.0)
    assert float(dev.max()) < 0.05
    assert _mm(float(dev.max())) < 1.0


def test_near_level1_is_pulled() -> None:
    """차트에 보이던 0.2562°(약 4.47mm)는 1차(4mm) 아래로 내려온다."""
    carry_deg = 0.2562
    cfg = _cfg(
        ra_carry_keep=1.0,
        __last_converted_row__={"AmountCH0": carry_deg},
    )
    out = SensorProcessor().generate_RA(_frame(1), cfg)
    got = float(out.iloc[0])
    assert abs(got) < abs(carry_deg)
    assert abs(got) < LEVEL1_DEG
    assert _mm(abs(got)) < LEVEL1_MM


def test_carry_returns_toward_initial() -> None:
    cfg = _cfg(__last_converted_row__={"AmountCH0": 0.2562})
    out = SensorProcessor().generate_RA(_frame(40), cfg)
    assert abs(float(out.iloc[0])) < 0.12
    assert abs(float(out.iloc[-1])) < abs(float(out.iloc[0]))
    assert abs(float(out.iloc[-1])) < 0.03


def test_large_scale_stays_under_level1() -> None:
    out = SensorProcessor().generate_RA(_frame(5000), _cfg(scale=0.5, ra_spike_prob=0.05))
    dev = np.abs(out.to_numpy())
    assert float(dev.max()) < LEVEL1_DEG * 0.7
    assert _mm(float(dev.max())) < 3.0


if __name__ == "__main__":
    test_stays_near_initial()
    test_near_level1_is_pulled()
    test_carry_returns_toward_initial()
    test_large_scale_stays_under_level1()
    print("ok")
