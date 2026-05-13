# core/cumulative_drift.py
"""
누적(drift) 공통 로직 — 스텝 배열 → cumsum, 선형 침하, 증분 변환 시 이어짐.

파이프라인과의 관계 (FileProcessor)
------------------------------------
1) 센서 처리(process) → 2) 소수점 → 3) 누락 보충(fill_missing_by_step 등)

- 동일 배치 안에서 누적은 **행 순서대로** 스텝을 합한 값으로 정의한다.
- 누락 보충은 **센서 처리 이후**에 이루어지며, 빈 시간은 **이전 행 전체 복사**다.
  → 그 시각에는 측정이 없었으므로 값이 그대로인 것이 맞고, 누적값도 복사본이
    자연스럽게 유지된다.
- 경계 연결(last_row prepend)으로 앞에 붙은 행은 이미 변환된 값이므로,
  그 다음 원본 행부터의 스텝 누적은 **배치 내 cumsum**으로 이어진다.

증분 변환(append)
-----------------
- 배치가 “파일 전체”가 아니라 “새 구간만”일 때, 단순 config base로 다시 시작하면
  단절된다.
- `cfg["__last_converted_row__"]`에 있는 해당 채널 헤더 값이 있으면,
  **스칼라 시작값**은 그 값을 우선한다(read_carry_float / resolve_start_scalar).
- Series base(행마다 다른 기준)인 CR_TAEAM 등은 **첫 행 기준 레벨만** carry로 맞춘다.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

import numpy as np


def cumsum_drift(steps: np.ndarray) -> np.ndarray:
    """스텝 배열의 누적합 (항상 float64)."""
    a = np.asarray(steps, dtype=float)
    if a.size == 0:
        return a.copy()
    return np.cumsum(a)


def accumulate_from_increments(start: float, increments: np.ndarray) -> np.ndarray:
    """
    시작값 + 증가분 누적 결과를 반환.
    out[0] = start, out[i] = start + sum(increments[1..i])
    """
    inc = np.asarray(increments, dtype=float)
    n = inc.size
    if n == 0:
        return inc.copy()
    out = np.empty(n, dtype=float)
    out[0] = float(start)
    if n > 1:
        out[1:] = float(start) + np.cumsum(inc[1:])
    return out


def linear_drift_first_row_zero(n: int, step_per_row: float) -> np.ndarray:
    """
    매 행 동일 스텝의 누적. 0행은 0, 1행부터 step, 2행 2*step, ...
    (RA 침하 등)
    """
    if n <= 0:
        return np.array([], dtype=float)
    out = np.zeros(n, dtype=float)
    if n > 1:
        out[1:] = np.cumsum(np.full(n - 1, float(step_per_row), dtype=float))
    return out


def bernoulli_signed_steps(
    n: int,
    rng: np.random.Generator,
    prob: float,
    choices: Sequence[float],
    *,
    skip_first_row: bool = False,
) -> np.ndarray:
    """
    각 행에 prob 확률로 choices 중 하나를 스텝으로 두는 배열.
    skip_first_row=True면 0행 스텝은 항상 0 (CR 스파이크 등).
    """
    steps = np.zeros(max(0, n), dtype=float)
    if n <= 0:
        return steps
    start = 1 if skip_first_row else 0
    if start >= n:
        return steps
    m = rng.random(n - start) < float(prob)
    if m.any():
        ch = np.asarray(choices, dtype=float)
        steps[start:][m] = rng.choice(ch, size=int(m.sum()))
    return steps


def read_carry_float(cfg: Mapping[str, Any], header_key: Optional[str]) -> Optional[float]:
    """변환본 마지막 행에서 해당 컬럼 값을 읽는다. 없거나 파싱 실패 시 None."""
    if not header_key:
        return None
    last = cfg.get("__last_converted_row__") if isinstance(cfg, Mapping) else None
    if not isinstance(last, dict) or header_key not in last:
        return None
    v = last.get(header_key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def resolve_start_scalar(carry: Optional[float], fallback: float) -> float:
    """증분 이어짐이 있으면 carry, 없으면 fallback(config base 등)."""
    return float(carry) if carry is not None else float(fallback)


def incremental_output_offset(
    cfg: Mapping[str, Any],
    header_key: Optional[str],
    first_row_output: float,
) -> float:
    """
    증분 변환 시 첫 행의 '센서 출력(누적·잡음 반영 후)'이 변환본 마지막값과 맞도록
    전 행에 더할 오프셋. carry 없으면 0.
    """
    carry = read_carry_float(cfg, header_key)
    if carry is None:
        return 0.0
    return float(carry) - float(first_row_output)


def header_key_for_col(col_idx: int) -> Optional[str]:
    """STANDARD_HEADER 상의 컬럼명 (file_processor와 동일 순서)."""
    from core.file_processor import STANDARD_HEADER

    if col_idx < 0 or col_idx >= len(STANDARD_HEADER):
        return None
    return STANDARD_HEADER[col_idx]
