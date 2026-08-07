"""60분 정렬(__align_60__) 유틸·map_slots 회귀."""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fill_interval_processor import FillIntervalProcessor
from utils.convert_paths import align60_filename


def test_align60_filename():
    assert align60_filename("1227998430.csv") == "1227998430_60.csv"
    assert align60_filename("1227998430_60.csv") == "1227998430_60.csv"


def test_map_slots_60_picks_nearest_to_hour():
    filler = FillIntervalProcessor()
    rows = [
        ["2026-07-27 10:03:00"] + [0.0] * 23,
        ["2026-07-27 10:55:00"] + [0.0] * 23,
        ["2026-07-27 11:02:00"] + [0.0] * 23,
    ]
    df = pd.DataFrame(rows, columns=range(24))
    out = filler.map_slots(df, 60)
    assert len(out) == 2
    ts = out.iloc[:, 0].astype(str).tolist()
    assert "2026-07-27 10:03:00" in ts
    assert "2026-07-27 11:02:00" in ts
