"""
변환본 CSV에서 timestamp 최대값 행을 가볍게 읽는다.

- Fast path: 파일 끝 chunk에서 마지막 유효 행과 max timestamp 일치 시 즉시 반환
- Fallback: 전체 파일 1-pass line scan (pandas 전체 read 대체)
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple

import pandas as pd

STRING_COLS = frozenset({"timestamp", "deviceId", "STX"})
TAIL_MAX_BYTES = 256 * 1024
TAIL_MAX_LINES = 2000


def parse_csv_fields(line: str) -> List[str]:
    """쉼표 구분 CSV 한 줄 파싱 (따옴표 안 쉼표 무시)."""
    parts: List[str] = []
    current = ""
    in_quotes = False
    for char in line:
        if char == '"':
            in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def _parse_timestamp(raw: str):
    text = (raw or "").strip().strip('"').strip("'")
    if not text or text.lower() == "timestamp":
        return pd.NaT
    try:
        return pd.to_datetime(text, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(text, errors="coerce")


def fields_to_row_dict(fields: List[str], header: List[str]) -> dict:
    row: dict = {}
    for i, col_name in enumerate(header):
        if i < len(fields):
            raw = fields[i]
            try:
                if col_name in STRING_COLS:
                    row[col_name] = (
                        str(raw).strip()
                        if raw is not None and str(raw).strip() not in ("", "nan")
                        else ("" if col_name != "timestamp" else "2026-01-01 00:00")
                    )
                else:
                    val = pd.to_numeric(raw, errors="coerce")
                    row[col_name] = float(val) if pd.notna(val) else 0.0
            except Exception:
                row[col_name] = (
                    0.0 if col_name not in STRING_COLS
                    else ("" if col_name != "timestamp" else "2026-01-01 00:00")
                )
        else:
            row[col_name] = (
                0.0 if col_name not in STRING_COLS
                else ("" if col_name != "timestamp" else "2026-01-01 00:00")
            )
    return row


def _read_tail_lines(path: str, max_bytes: int = TAIL_MAX_BYTES, max_lines: int = TAIL_MAX_LINES) -> Tuple[List[str], bool]:
    """
    파일 끝에서 최대 max_bytes 만큼 읽어 유효 줄 목록 반환.
    Returns: (lines_in_file_order, truncated_at_start)
    """
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        if pos == 0:
            return [], False

        read_size = min(pos, max_bytes)
        start_pos = pos - read_size
        f.seek(start_pos)
        chunk = f.read(read_size)

    truncated = start_pos > 0
    text = chunk.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    if truncated and lines:
        lines = lines[1:]  # 불완전한 첫 줄 제거
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return [ln.strip() for ln in lines if ln.strip()], truncated


def _max_row_from_lines(lines: List[str]) -> Tuple[Optional[pd.Timestamp], Optional[List[str]]]:
    best_ts = None
    best_fields = None
    last_ts = None
    last_fields = None

    for line in lines:
        if line.lower().startswith("timestamp"):
            continue
        fields = parse_csv_fields(line)
        if not fields:
            continue
        ts = _parse_timestamp(fields[0])
        if pd.isna(ts):
            continue
        last_ts = ts
        last_fields = fields
        if best_ts is None or ts >= best_ts:
            best_ts = ts
            best_fields = fields

    return (best_ts, best_fields), (last_ts, last_fields)


def _stream_max_row(path: str, header: List[str]) -> Tuple[Optional[pd.Timestamp], Optional[dict]]:
    best_ts = None
    best_fields = None

    with open(path, "rb") as f:
        for raw in f:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line or line.lower().startswith("timestamp"):
                continue
            fields = parse_csv_fields(line)
            if not fields:
                continue
            ts = _parse_timestamp(fields[0])
            if pd.isna(ts):
                continue
            if best_ts is None or ts >= best_ts:
                best_ts = ts
                best_fields = fields

    if best_fields is None:
        return None, None
    return best_ts, fields_to_row_dict(best_fields, header)


def _try_tail_max_row(path: str, header: List[str]) -> Tuple[Optional[pd.Timestamp], Optional[dict]]:
    lines, truncated = _read_tail_lines(path)
    if not lines:
        return None, None

    (best_ts, best_fields), (last_ts, _last_fields) = _max_row_from_lines(lines)
    if best_fields is None or best_ts is None:
        return None, None

    # append-only 변환본: 물리적 마지막 행 timestamp == max timestamp 여야 fast path
    if last_ts is None or pd.isna(last_ts) or last_ts < best_ts:
        return None, None

    # chunk 시작이 잘렸고 데이터가 max_lines 꽉 찼으면 max가 chunk 밖일 수 있음
    if truncated and len(lines) >= TAIL_MAX_LINES:
        return None, None

    return best_ts, fields_to_row_dict(best_fields, header)


def read_max_timestamp_row(
    csv_path: str,
    header: List[str],
) -> Tuple[Optional[pd.Timestamp], Optional[dict]]:
    """
    변환본에서 timestamp 최대값 행 반환.
    Returns: (timestamp, last_row_data_dict) 또는 (None, None)
    """
    if not csv_path or not os.path.exists(csv_path):
        return None, None

    tail_ts, tail_row = _try_tail_max_row(csv_path, header)
    if tail_row is not None:
        return tail_ts, tail_row

    return _stream_max_row(csv_path, header)


def peek_last_timestamp(csv_path: str) -> Optional[pd.Timestamp]:
    """
    원본/변환본 끝에서 마지막 유효 timestamp만 빠르게 읽기 (전체 scan 없음).
    구분자 , ; 탭 모두 지원.
    """
    if not csv_path or not os.path.exists(csv_path):
        return None
    lines, _truncated = _read_tail_lines(csv_path, max_bytes=64 * 1024, max_lines=200)
    if not lines:
        return None
    for line in reversed(lines):
        if line.lower().startswith("timestamp"):
            continue
        # 첫 필드만
        first = line
        for sep in (",", ";", "\t"):
            if sep in line:
                first = line.split(sep, 1)[0]
                break
        else:
            first = line.split()[0] if line.split() else ""
        ts = _parse_timestamp(first)
        if pd.notna(ts):
            return ts
    return None
