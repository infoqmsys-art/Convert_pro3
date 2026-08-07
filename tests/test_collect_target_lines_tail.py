"""
원본 _collect_target_lines: base_time 있을 때 tail 창 수집 회귀.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.file_processor import FileProcessor


class _Log:
    def log(self, msg, level="INFO"):
        pass


def _fp():
    return FileProcessor(
        config=None, tree=None, sensor=None, fill_interval=None, logger=_Log()
    )


def _write_logger_csv(path, start, minutes, step_min=1, prefix_junk_bytes=0):
    """append-only 로거 스타일 CSV (헤더 없음)."""
    with open(path, "wb") as f:
        if prefix_junk_bytes:
            f.write(b"x" * prefix_junk_bytes + b"\n")
        t = start
        for _ in range(minutes):
            line = f"{t.strftime('%Y-%m-%d %H:%M:%S')},1.0,2.0\n".encode("utf-8")
            f.write(line)
            t += timedelta(minutes=step_min)


def test_peek_skip_when_last_before_base():
    fp = _fp()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        path = tf.name
    try:
        _write_logger_csv(path, datetime(2026, 7, 13, 8, 0), 10)
        lines = fp._collect_target_lines(path, pd.Timestamp("2026-07-13 10:00:00"))
        assert lines == []
    finally:
        os.unlink(path)


def test_tail_matches_full_scan():
    fp = _fp()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        path = tf.name
    try:
        # ~6000행: tail 창이 커지며 base 이전까지 내려감
        _write_logger_csv(path, datetime(2026, 7, 13, 0, 0), 6000, step_min=1)
        base = pd.Timestamp("2026-07-13 09:00:00")
        tail = fp._collect_target_lines(path, base)
        full = fp._collect_target_lines_full(path, base, max_year=2027)
        assert len(tail) == len(full)
        assert tail[0].startswith("2026-07-13 09:00:00")
        assert [ln.split(",")[0] for ln in tail] == [ln.split(",")[0] for ln in full]
    finally:
        os.unlink(path)


def test_first_convert_uses_full_file():
    fp = _fp()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        path = tf.name
    try:
        _write_logger_csv(path, datetime(2026, 7, 13, 8, 0), 5)
        lines = fp._collect_target_lines(path, None)
        assert len(lines) == 5
        assert lines[0].startswith("2026-07-13 08:00:00")
    finally:
        os.unlink(path)


def test_tail_window_stops_before_reading_whole_file():
    """큰 파일에서 window < file_size 로 끝나도 결과가 올바른지."""
    fp = _fp()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        path = tf.name
    try:
        # 행당 ~30B * 20000 ≈ 600KB → 첫 256KB만으론 부족, 1MB 창에서 충분
        _write_logger_csv(path, datetime(2026, 1, 1, 0, 0), 20000, step_min=1)
        # 끝에서 100분 전을 base로
        base = pd.Timestamp("2026-01-01 00:00:00") + timedelta(minutes=19900)
        lines = fp._collect_target_lines_tail_window(path, base, max_year=2027)
        assert lines is not None
        assert len(lines) == 100  # 19900..19999
        assert lines[0].startswith(base.strftime("%Y-%m-%d %H:%M:%S"))
        full = fp._collect_target_lines_full(path, base, max_year=2027)
        assert lines == full
        assert os.path.getsize(path) > 256 * 1024
    finally:
        os.unlink(path)
