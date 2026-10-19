# -*- coding: utf-8 -*-
"""RA: 벌어진 값은 시간에 걸쳐 초기치로 돌아오고, 스파이크는 떨림 안에 있는다."""
from __future__ import annotations

import math
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.sensor_processor import SensorProcessor  # noqa: E402

L_MM = 1000.0


def _mm(deg: float) -> float:
    return L_MM * math.sin(math.radians(abs(deg)))


def _frame(start: str, n: int, freq: str = "h") -> pd.DataFrame:
    df = pd.DataFrame({i: [0.0] * n for i in range(24)})
    df[0] = pd.date_range(start, periods=n, freq=freq).strftime("%Y-%m-%d %H:%M:%S")
    return df


def _cfg(**extra) -> dict:
    cfg = {
        "mode": "RA",
        "col_idx": 16,
        "slot": "CH0",
        "base": 0.0,
        "scale": 0.015,
        "ra_spike_prob": 0.0,
        "ra_up_prob": 0.0,
        "ra_down_prob": 0.0,
    }
    cfg.update(extra)
    return cfg


def test_stays_near_initial_without_carry() -> None:
    out = SensorProcessor().generate_RA(_frame("2026-03-08", 500), _cfg())
    dev = (out - 0.0).abs()
    assert float(dev.max()) <= 0.015 + 1e-9
    assert _mm(float(dev.max())) < 0.4


def test_drift_pulls_slowly() -> None:
    """0.2562°(약 4.47mm)는 한 시간에 꺾이지 않고, 나흘이면 약 37%만 남는다."""
    carry = 0.2562
    cfg = _cfg(
        scale=0.0,
        __last_converted_row__={"timestamp": "2026-10-19 11:00:00", "AmountCH0": carry},
    )
    out = SensorProcessor().generate_RA(_frame("2026-10-19 12:00:00", 192), cfg)
    one_h = float(out.iloc[0])
    one_day = float(out.iloc[23])
    four_days = float(out.iloc[95])
    assert one_h > carry * 0.97
    assert one_h < carry
    assert _mm(one_h) > 4.0
    assert one_day < one_h
    assert abs(four_days - carry / math.e) < 0.01
    assert abs(float(out.iloc[-1])) < abs(four_days)


def test_spikes_stay_inside_noise_band() -> None:
    """스파이크가 노이즈 상한(scale) 밖으로 나가지 않는다. 예전은 scale의 1.2배였다."""
    scale = 0.015
    out = SensorProcessor().generate_RA(
        _frame("2026-03-08", 2000),
        _cfg(scale=scale, ra_spike_prob=0.05),
    )
    dev = (out - 0.0).abs()
    assert float(dev.max()) <= scale + 1e-9


if __name__ == "__main__":
    test_stays_near_initial_without_carry()
    test_drift_pulls_slowly()
    test_spikes_stay_inside_noise_band()
    print("ok")
