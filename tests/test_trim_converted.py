"""
변환본 시간 이후 삭제(trim_converted_from_time) 검증 스크립트
"""
import os
import sys
import csv
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.file_processor import FileProcessor, STANDARD_HEADER


def make_test_csv(path, timestamps):
    """테스트용 변환본 CSV 생성 (STANDARD_HEADER 형식)"""
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(STANDARD_HEADER)
        for ts in timestamps:
            row = [ts] + ['0'] * (len(STANDARD_HEADER) - 1)
            w.writerow(row)


def run_test():
    print("=" * 60)
    print("trim_converted_from_time 검증")
    print("=" * 60)

    class DummyLogger:
        def log(self, msg, level="INFO"):
            print(f"  [{level}] {msg}")

    fp = FileProcessor(config=None, tree=None, sensor=None, fill_interval=None, logger=DummyLogger())

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8-sig') as tf:
        test_path = tf.name

    try:
        # 테스트 데이터: 2026-03-01 00:00 ~ 2026-03-05 00:00 (5일, 10분 간격)
        timestamps = []
        from datetime import timedelta
        t = datetime(2026, 3, 1, 0, 0)
        for _ in range(5 * 24 * 6):  # 5일 * 24시간 * 6(10분)
            timestamps.append(t.strftime("%Y-%m-%d %H:%M:%S"))
            t += timedelta(minutes=10)

        make_test_csv(test_path, timestamps)
        total_rows = 1 + len(timestamps)  # 헤더 + 데이터

        print(f"\n1. 테스트 파일 생성: {total_rows-1}개 데이터행")
        print(f"   첫 행: {timestamps[0]}")
        print(f"   끝 행: {timestamps[-1]}")

        # --- 케이스 1: 2026-03-03 00:00 이후 삭제 (3일째 00:00 ~ 끝 삭제)
        cutoff1 = datetime(2026, 3, 3, 0, 0)
        ok, _ = fp.trim_converted_from_time(test_path, cutoff1)
        assert ok, "trim 실패"
        with open(test_path, 'r', encoding='utf-8-sig') as f:
            remaining = list(csv.reader(f))
        kept_count = len(remaining) - 1
        last_kept_ts = remaining[-1][0] if len(remaining) > 1 else None
        print(f"\n2. cutoff=2026-03-03 00:00")
        print(f"   결과: 유지={kept_count}행")
        print(f"   마지막 유지 행 timestamp: {last_kept_ts}")
        assert remaining[-1][0] < "2026-03-03 00:00", f"마지막 유지 행이 cutoff 이상: {last_kept_ts}"
        assert "2026-03-02 23:50" in last_kept_ts or last_kept_ts.startswith("2026-03-02"), f"예상: 2026-03-02 23:50 이전, 실제: {last_kept_ts}"

        # --- 케이스 2: 다시 파일 만들어서 2026-03-01 12:00 이후 삭제
        make_test_csv(test_path, timestamps)
        cutoff2 = datetime(2026, 3, 1, 12, 0)
        ok, _ = fp.trim_converted_from_time(test_path, cutoff2)
        assert ok
        with open(test_path, 'r', encoding='utf-8-sig') as f:
            remaining2 = list(csv.reader(f))
        last_kept_ts2 = remaining2[-1][0] if len(remaining2) > 1 else None
        print(f"\n3. cutoff=2026-03-01 12:00")
        print(f"   결과: 유지={len(remaining2)-1}행")
        print(f"   마지막 유지 행: {last_kept_ts2}")
        assert "2026-03-01 11:50" in last_kept_ts2 or (last_kept_ts2 and last_kept_ts2 < "2026-03-01 12:00:00")

        # --- 케이스 3: cutoff가 모든 데이터보다 과거 → 전부 삭제 (모든 행이 cutoff 이후)
        make_test_csv(test_path, timestamps)
        cutoff3 = datetime(2025, 1, 1, 0, 0)
        ok, _ = fp.trim_converted_from_time(test_path, cutoff3)
        assert ok
        with open(test_path, 'r', encoding='utf-8-sig') as f:
            remaining3 = list(csv.reader(f))
        print(f"\n4. cutoff=2025-01-01 (모든 데이터 >= cutoff → 전부 삭제)")
        print(f"   결과: 유지={len(remaining3)-1}행")
        assert len(remaining3) == 1, "헤더만 남아야 함"

        # --- 케이스 4: cutoff가 마지막 데이터보다 이후 → 전부 유지
        make_test_csv(test_path, timestamps)
        cutoff4 = datetime(2026, 12, 31, 23, 59)
        ok, _ = fp.trim_converted_from_time(test_path, cutoff4)
        assert ok
        with open(test_path, 'r', encoding='utf-8-sig') as f:
            remaining4 = list(csv.reader(f))
        print(f"\n5. cutoff=2026-12-31 (모든 데이터 < cutoff → 전부 유지)")
        print(f"   결과: 유지={len(remaining4)-1}행")
        assert len(remaining4) == total_rows

        print("\n" + "=" * 60)
        print("[OK] 모든 검증 통과")
        print("=" * 60)
        return True

    finally:
        if os.path.exists(test_path):
            os.unlink(test_path)


if __name__ == "__main__":
    run_test()
