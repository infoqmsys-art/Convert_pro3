"""원본 중간부터 행이 넓어진 파일(로거 펌웨어 변경)을 버리지 않고 읽는지. `python tests\\test_wide_rows.py`"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.file_processor import FileProcessor  # noqa: E402

NARROW = "2026-10-02 15:00:00,D,-ST-,100.0,1.02,1,60,0,0,0,100,100,100,0.3086,88.5152,0.0,1.0781,0,0,0,0,0,0,0"
WIDE = (
    "2026-10-02 16:00:00,D,-ST-,220,1.02,1,60,0,0,0,100,100,100,0.276,88.64,0.0,1.0816"
    + ",0.0" * 18 + ",22.1,44.1,20.909,50.0,          ,"
)


def _fp() -> FileProcessor:
    return FileProcessor(None, None, None, None, None)


def test_read_source_keeps_wide_rows() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.csv")
        with open(p, "w", encoding="utf-8") as f:
            f.write("timestamp,deviceId\n" + NARROW + "\n" + WIDE + "\n" + WIDE.replace("16:00", "17:00") + "\n")
        df = _fp()._read_source_csv(p)
    assert len(df) == 4, len(df)
    assert list(df.iloc[1:, 0]) == ["2026-10-02 15:00:00", "2026-10-02 16:00:00", "2026-10-02 17:00:00"]
    assert float(df.iloc[3, 13]) == 0.276


def test_lines_keep_wide_rows() -> None:
    df = _fp()._dataframe_from_lines([NARROW, WIDE])
    assert len(df) == 2, len(df)
    assert float(df.iloc[1, 16]) == 1.0816


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
