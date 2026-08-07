"""
누락보충 파이프라인 파츠 회귀 테스트.

계약:
- map_slots: 랜덤 시각 → 슬롯당 1행 (원본 timestamp 유지)
- fill_gaps: 사이 빈 슬롯을 정각(N분 경계)으로 채움
- fill_from_last_to_now: 마지막 슬롯 다음 ~ 현재 슬롯까지 채움 (실측+N분 금지)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fill_interval_processor import FillIntervalProcessor, _slot_key


def _df(times):
    rows = [[t, "D", "S", 1.0] + [0.0] * 20 for t in times]
    return pd.DataFrame(rows, columns=range(24))


def _run_step5(src_times, base_time, interval, now):
    """file_processor STEP5 상당: map → prepend → fill_gaps → fill_to_now"""
    filler = FillIntervalProcessor()
    df = filler.map_slots(_df(src_times), interval)
    if base_time is not None and len(df) > 0:
        last_df = _df([base_time])
        first_ts = pd.to_datetime(df.iloc[0, 0])
        if pd.Timestamp(base_time) < first_ts:
            df = pd.concat([last_df, df], ignore_index=True)
    df = filler.fill_gaps(df, interval)
    last_ts = pd.to_datetime(df.iloc[-1, 0])
    tail = filler.fill_from_last_to_now(
        df.iloc[[-1]].copy(), last_ts, interval, current_time_limit=now, max_rows=168
    )
    if not tail.empty:
        df = pd.concat([df, tail], ignore_index=True)
    slots = sorted({_slot_key(pd.to_datetime(t), interval) for t in df.iloc[:, 0]})
    return list(df.iloc[:, 0].astype(str)), slots


def test_A_random_source_fill_to_current_hour():
    times, slots = _run_step5(
        ["2026-07-13 07:03:00", "2026-07-13 07:18:00", "2026-07-13 08:41:00"],
        None,
        60,
        datetime(2026, 7, 13, 9, 50),
    )
    assert slots == [
        "2026-07-13 07:00:00",
        "2026-07-13 08:00:00",
        "2026-07-13 09:00:00",
    ], slots


def test_B_no_source_fill_slot_aligned():
    filler = FillIntervalProcessor()
    tail = filler.fill_from_last_to_now(
        _df(["2026-07-13 07:05:00"]),
        pd.Timestamp("2026-07-13 07:05:00"),
        60,
        current_time_limit=datetime(2026, 7, 13, 9, 50),
        max_rows=168,
    )
    assert list(tail.iloc[:, 0].astype(str)) == [
        "2026-07-13 08:00:00",
        "2026-07-13 09:00:00",
    ]


def test_F_gate_case_0850_at_0930():
    _, slots = _run_step5(
        ["2026-07-13 08:50:00"], None, 60, datetime(2026, 7, 13, 9, 30)
    )
    assert slots == ["2026-07-13 08:00:00", "2026-07-13 09:00:00"], slots


def test_D_middle_gap():
    _, slots = _run_step5(
        ["2026-07-13 07:10:00", "2026-07-13 10:05:00"],
        None,
        60,
        datetime(2026, 7, 13, 10, 50),
    )
    assert slots == [
        "2026-07-13 07:00:00",
        "2026-07-13 08:00:00",
        "2026-07-13 09:00:00",
        "2026-07-13 10:00:00",
    ], slots


def test_E_ten_minute_continuous():
    import random

    random.seed(1)
    now = datetime(2026, 7, 13, 9, 37)
    src = []
    t = datetime(2026, 7, 13, 9, 0)
    while t < now:
        src.append(t.strftime("%Y-%m-%d %H:%M:%S"))
        t += timedelta(minutes=random.choice([5, 7, 11, 3, 9]))
    _, slots = _run_step5(src, None, 10, now)
    assert slots[-1] == "2026-07-13 09:30:00", slots
    for i in range(1, len(slots)):
        gap = (pd.to_datetime(slots[i]) - pd.to_datetime(slots[i - 1])).total_seconds()
        assert gap == 600, (slots[i - 1], slots[i])


def test_H_no_duplicate_when_already_current_slot():
    _, slots = _run_step5(
        ["2026-07-13 09:02:00"],
        "2026-07-13 09:00:00",
        60,
        datetime(2026, 7, 13, 9, 50),
    )
    assert slots == ["2026-07-13 09:00:00"], slots


def test_map_slots_picks_nearest_in_hour():
    filler = FillIntervalProcessor()
    df = _df(
        [
            "2026-07-13 10:50:00",
            "2026-07-13 10:05:00",
            "2026-07-13 10:30:00",
        ]
    )
    out = filler.map_slots(df, 60)
    assert len(out) == 1
    assert str(out.iloc[0, 0]).startswith("2026-07-13 10:05")


if __name__ == "__main__":
    test_A_random_source_fill_to_current_hour()
    test_B_no_source_fill_slot_aligned()
    test_F_gate_case_0850_at_0930()
    test_D_middle_gap()
    test_E_ten_minute_continuous()
    test_H_no_duplicate_when_already_current_slot()
    test_map_slots_picks_nearest_in_hour()
    print("ALL PASS")
