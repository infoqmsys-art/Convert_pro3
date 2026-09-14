# utils/battery.py
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

# 변환본: STANDARD_HEADER[3] == "battery"
OUT_BATTERY_COL = 3
# CP3 관례: 원본 batLevel 0-based 인덱스
SOURCE_BATTERY_INDEX = 56

# 이름 우선순위 (높을수록 선호). 변환본 헤더 "battery"는 재처리 시에만 쓰이므로 낮게.
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
    """
    (유효개수, 0~105% 범위 개수, 최근값또는 nan).
    헤더 문자열·빈 열은 유효 0.
    """
    series = pd.to_numeric(raw, errors="coerce")
    valid = series.dropna()
    n = int(len(valid))
    if n == 0:
        return 0, 0, float("nan")
    in_pct = int(((valid >= 0) & (valid <= 105)).sum())
    last = float(valid.iloc[-1])
    return n, in_pct, last


def find_battery_source_col(df: pd.DataFrame) -> tuple[int | None, str]:
    """
    배터리 원본 열 인덱스와 출처 설명.
    후보: 컬럼명 / 0행 헤더명 / 고정 인덱스 56.
    이름만 맞고 숫자가 없으면 다른 후보(특히 56)로 폴백.
    """
    if df is None or df.empty:
        return None, "empty"

    ncols = int(df.shape[1])
    candidates: list[tuple[int, int, str]] = []  # (priority, col, tag)

    for i, c in enumerate(df.columns):
        key = _norm_name(c)
        if key in _NAME_PRIORITY:
            # 변환본 재처리: 이미 battery(3)만 있는 경우는 허용
            # 원본(열 많음)에서 범용명 "battery"만 매칭되면 점수 낮음 → 품질 비교에서 밀릴 수 있음
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

    # 중복 col은 최고 우선순위 태그만 유지
    best_by_col: dict[int, tuple[int, str]] = {}
    for pri, col, tag in candidates:
        prev = best_by_col.get(col)
        if prev is None or pri > prev[0]:
            best_by_col[col] = (pri, tag)

    scored: list[tuple[tuple, int, str]] = []
    for col, (pri, tag) in best_by_col.items():
        n_valid, n_pct, _last = _series_quality(df.iloc[:, col])
        # 정렬키: 범위 내 개수 → 이름우선 → 전체유효 → 낮은 col
        scored.append(((n_pct, pri, n_valid, -col), col, tag))

    scored.sort(key=lambda x: x[0], reverse=True)
    _key, col, tag = scored[0]
    n_pct = _key[0]
    if n_pct == 0 and len(scored) > 1:
        # 1등이 전부 비숫자면 차선 (로그용 태그에 fallback 표기)
        _k2, col2, tag2 = scored[1]
        if _k2[0] > 0:
            return col2, f"{tag2}(fallback_from:{tag})"
    return col, tag


def extract_battery_series(df: pd.DataFrame, logger=None) -> tuple[pd.Series, str]:
    """
    원본 df에서 배터리 Series 추출. 파싱 실패·헤더 문자열은 NaN.
    반환: (series, source_tag)  — tag는 디버그용, 변환 로그에는 찍지 않음.
    """
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
    """
    batLevel → 3열(battery) 기록 후 앞 24열만 유지.
    유효값이 있으면 ffill/bfill로 빈 칸을 메우고, 그래도 없으면 0.
    """
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
    """변환본 한 칸 → float. 없거나 파싱 실패면 None (0과 구분)."""
    if raw is None:
        return None
    s = str(raw).strip().strip('"')
    if not s or s.lower() in ("nan", "none", "null", "-"):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None
