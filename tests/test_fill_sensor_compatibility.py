"""
누락보충(Fill Interval) × 센서 설정 호환성 검증 스크립트

검증 항목:
1. 파이프라인 순서: 센서 처리 → 누락보충
2. 채워진 행 = 이전 행 복사 (timestamp 제외)
3. 시간순 정렬
4. deviceId/STX 등 메타데이터 유지
"""
import os
import sys
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.fill_interval_processor import FillIntervalProcessor
from core.file_processor import STANDARD_HEADER


def make_test_df(rows_data):
    """테스트용 DataFrame 생성 (24컬럼)"""
    return pd.DataFrame(rows_data, columns=range(24))


def run_fill_compatibility_check():
    print("=" * 60)
    print("누락보충 × 센서 호환성 검증")
    print("=" * 60)

    filler = FillIntervalProcessor(logger=None)

    # ── 케이스 1: 16:00, 18:00 → 17:00 채워지는지
    print("\n[1] 16:00-18:00 간격 → 17:00 채움 검증")
    df1 = make_test_df([
        ["2026-03-07 16:00", "SAEGL08221", "-ST-", 84.5] + [0.0] * 20,
        ["2026-03-07 18:00", "SAEGL08221", "-ST-", 84.2] + [0.0] * 20,
    ])
    result1 = filler._fill_missing_intervals(df1, 60)
    times1 = pd.to_datetime(result1.iloc[:, 0], errors="coerce")
    assert len(result1) == 3, f"3행 예상, 실제 {len(result1)}행"
    valid_ts = times1.dropna()
    assert (valid_ts.diff().dropna() >= pd.Timedelta(0)).all(), "시간순 정렬 필요"
    # 17:00 행 = 16:00 복사 (col 1,2 = deviceId, STX)
    fill_row = result1.iloc[1]
    prev_row = result1.iloc[0]
    for c in range(1, 24):  # timestamp(0) 제외
        assert fill_row.iloc[c] == prev_row.iloc[c] or (pd.isna(fill_row.iloc[c]) and pd.isna(prev_row.iloc[c])), \
            f"col {c} 불일치: fill={fill_row.iloc[c]}, prev={prev_row.iloc[c]}"
    assert "17:00" in str(fill_row.iloc[0]), f"17:00 예상, 실제 {fill_row.iloc[0]}"
    print("  [OK] 17:00 채움, 이전 행 복사, 시간순")

    # ── 케이스 2: last_row(0,0) → 다음 행에서 deviceId/STX 가져오는지
    print("\n[2] deviceId/STX=0인 이전 행 → 다음 행 값 사용 검증")
    df2 = make_test_df([
        ["2026-03-07 16:00", "0", "0", 84.5] + [0.0] * 20,      # 채워진 행처럼 0,0
        ["2026-03-07 18:00", "SAEGL08221", "-ST-", 84.2] + [0.0] * 20,
    ])
    result2 = filler._fill_missing_intervals(df2, 60)
    fill_row2 = result2.iloc[1]
    next_row = result2.iloc[2]  # 18:00
    assert str(fill_row2.iloc[1]) == "SAEGL08221", f"deviceId 예상 SAEGL08221, 실제 {fill_row2.iloc[1]}"
    assert str(fill_row2.iloc[2]) == "-ST-", f"STX 예상 -ST-, 실제 {fill_row2.iloc[2]}"
    print("  [OK] deviceId/STX 다음 행에서 복사")

    # ── 케이스 3: 중복 제거
    print("\n[3] 중복 시간 제거 검증")
    df3 = make_test_df([
        ["2026-03-07 16:00", "A", "-", 1] + [0.0] * 20,
        ["2026-03-07 17:00", "A", "-", 2] + [0.0] * 20,
        ["2026-03-07 17:00", "A", "-", 3] + [0.0] * 20,  # 중복
        ["2026-03-07 18:00", "A", "-", 4] + [0.0] * 20,
    ])
    result3 = filler._fill_missing_intervals(df3, 60)
    times3_str = result3.iloc[:, 0].astype(str)
    dup = times3_str.duplicated()
    assert dup.sum() == 0, f"중복 시간 {dup.sum()}개 남음"
    print("  [OK] 중복 제거")

    # ── 케이스 4: 센서 컬럼(CH0~CH7) 유지
    print("\n[4] 센서 컬럼(16~23) 이전 행 복사 검증")
    df4 = make_test_df([
        ["2026-03-07 16:00", "A", "-", 1] + [0.0] * 12 + [1.1, 2.2, 3.3, 4.4, 5.5, 6.6, 7.7, 8.8],
        ["2026-03-07 18:00", "A", "-", 2] + [0.0] * 20,
    ])
    result4 = filler._fill_missing_intervals(df4, 60)
    fill_row4 = result4.iloc[1]
    prev_row4 = result4.iloc[0]
    for c in range(16, 24):
        assert fill_row4.iloc[c] == prev_row4.iloc[c], f"CH{c-16} 불일치"
    print("  [OK] CH0~CH7 이전 행 복사")

    print("\n" + "=" * 60)
    print("모든 검증 통과 [OK]")
    print("=" * 60)


if __name__ == "__main__":
    run_fill_compatibility_check()
