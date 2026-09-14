# convert_engine/battery.py (synced from utils/battery.py)
"""
배터리(batLevel) 추출·이동.

원본 CSV는 보통 인덱스 56에 batLevel이 있으나,
컬럼 수·헤더·펌웨어 버전에 따라 달라질 수 있다.
실패와 '실제 0%'를 구분할 수 있게 추출 단계는 NaN을 유지하고,
변환본 기록 시에만 ffill/bfill 후 필요 최소로 0을 채운다.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

OUT_BATTERY_COL = 3
SOURCE_BATTERY_INDEX = 56

_NAME_PRIORITY: dict[str, int] = {
    "batlevel": 100,
    "bat_level": 100,
    "batterylevel": 90,
    "battery_level": 90,
    "bat": 70,
    "battery": 40,
}


def _norm_name(v: Any) -> str:
    return str(v).strip().lower().replace(" ", "").replace("-", "_")


def _series_quality(raw: pd.Series) -> tuple[int, int, float]:
    series = pd.to_numeric(raw, errors="coerce")
    valid = series.dropna()
    n = int(len(valid))
    if n == 0:
        return 0, 0, float("nan")
    in_pct = int(((valid >= 0) & (valid <= 105)).sum())
    last = float(valid.iloc[-1])
    return n, in_pct, last


def find_battery_source_col(df: pd.DataFrame) -> tuple[int | None, str]:
    if df is None or df.empty:
        return None, "empty"

    ncols = int(df.shape[1])
    candidates: list[tuple[int, int, str]] = []

    for i, c in enumerate(df.columns):
        key = _norm_name(c)
        if key in _NAME_PRIORITY:
            candidates.append((_NAME_PRIORITY[key], int(i), f"column_name:{c}"))

    if ncols > 0:
        for i in range(min(ncols, 96)):
            key = _norm_name(df.iloc[0, i])
            if key in _NAME_PRIORITY:
                candidates.append((_NAME_PRIORITY[key], int(i), f"row0_header:{i}"))

    if ncols > SOURCE_BATTERY_INDEX:
        candidates.append((50, SOURCE_BATTERY_INDEX, f"index:{SOURCE_BATTERY_INDEX}"))

    if not candidates:
        return None, f"not_found(ncols={ncols})"

    best_by_col: dict[int, tuple[int, str]] = {}
    for pri, col, tag in candidates:
        prev = best_by_col.get(col)
        if prev is None or pri > prev[0]:
            best_by_col[col] = (pri, tag)

    scored: list[tuple[tuple, int, str]] = []
    for col, (pri, tag) in best_by_col.items():
        n_valid, n_pct, _last = _series_quality(df.iloc[:, col])
        scored.append(((n_pct, pri, n_valid, -col), col, tag))

    scored.sort(key=lambda x: x[0], reverse=True)
    _key, col, tag = scored[0]
    if _key[0] == 0 and len(scored) > 1:
        _k2, col2, tag2 = scored[1]
        if _k2[0] > 0:
            return col2, f"{tag2}(fallback_from:{tag})"
    return col, tag


def extract_battery_series(df: pd.DataFrame, logger=None) -> tuple[pd.Series, str]:
    empty = pd.Series(np.nan, index=df.index if df is not None else None, dtype="float64")
    col, tag = find_battery_source_col(df)
    if col is None:
        return empty, tag
    try:
        series = pd.to_numeric(df.iloc[:, col], errors="coerce").astype("float64")
    except Exception:
        return empty, f"{tag}:error"
    return series, tag


def move_battery_and_trim(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    out = df.copy()
    batt, _tag = extract_battery_series(out, logger=logger)
    filled = batt.ffill().bfill().fillna(0.0)
    if out.shape[1] <= OUT_BATTERY_COL:
        return out
    col_name = out.columns[OUT_BATTERY_COL]
    out[col_name] = filled.astype("float64")
    if out.shape[1] > 24:
        out = out.iloc[:, :24].copy()
    return out


def parse_battery_cell(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().strip('"')
    if not s or s.lower() in ("nan", "none", "null", "-"):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None
