"""
monitoring/data_cache.py

변환 완료 시 file_processor가 호출 → monitoring_cache.json 에 캐시 저장
서버(server.py)는 CSV 직접 읽지 않고 이 캐시만 읽음

캐시 구조:
{
  "company|folder|filename": {
    "latest_values": {"CH0": 1.23, ...},
    "chart": {
      "labels": ["04/05 10:00", ...],   // 최근 48개
      "values": {"CH0": [...], ...}
    },
    "updated_at": "2026-04-06 13:05"
  }
}
"""
import json
import sys
import threading
from datetime import datetime
from pathlib import Path

# 앱 루트 기준으로 캐시 파일 위치 결정 (빌드/개발 모두 대응)
if getattr(sys, "frozen", False):
    _APP_ROOT = Path(sys.executable).parent
else:
    _APP_ROOT = Path(__file__).parent.parent

CACHE_PATH = _APP_ROOT / "monitoring_cache.json"

N_CHART = 48          # 차트에 보여줄 최대 데이터 포인트 수
CH_COL_START = 16     # CSV 컬럼 인덱스: CH0=16, CH1=17 ... CH7=23

_lock = threading.Lock()

# ─────────────────────────────────────────
#  인메모리 캐시 (파일 반복 읽기 방지)
# ─────────────────────────────────────────
_mem_cache: dict = {}          # {key: entry}
_mem_cache_mtime: float = 0.0  # 마지막으로 파일을 읽었을 때의 mtime


def _load_cache_from_disk() -> dict:
    """디스크에서 전체 캐시 읽기. 실패 시 빈 dict 반환."""
    global _mem_cache, _mem_cache_mtime
    try:
        mtime = CACHE_PATH.stat().st_mtime
        if mtime != _mem_cache_mtime:
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            _mem_cache = data
            _mem_cache_mtime = mtime
    except Exception:
        pass
    return _mem_cache


# ─────────────────────────────────────────
#  캐시 읽기
# ─────────────────────────────────────────

def get_file_cache(company: str, folder: str, filename: str) -> dict | None:
    """저장된 캐시 반환. 없으면 None. 파일 변경 시에만 디스크 재읽기."""
    key = f"{company}|{folder}|{filename}"
    try:
        if not CACHE_PATH.exists():
            return None
        data = _load_cache_from_disk()
        return data.get(key)
    except Exception:
        return None


# ─────────────────────────────────────────
#  캐시 쓰기 (file_processor에서 호출)
# ─────────────────────────────────────────

def update_file_cache(company: str, folder: str, filename: str, df) -> None:
    """
    변환 완료 직후 DataFrame(df)에서 캐시를 업데이트.
    df: 변환 완료된 전체 DataFrame (컬럼은 정수 인덱스 0~23)
    """
    try:
        import pandas as pd

        # 마지막 N행만 사용
        tail = df.tail(N_CHART).copy()
        if tail.empty:
            return

        labels = []
        ch_values = {f"CH{i}": [] for i in range(8)}

        for _, row in tail.iterrows():
            # 타임스탬프 레이블
            ts = str(row.iloc[0]) if len(row) > 0 else ""
            try:
                dt = datetime.fromisoformat(ts)
                labels.append(dt.strftime("%m/%d %H:%M"))
            except Exception:
                labels.append(ts[-5:] if len(ts) >= 5 else ts)

            # CH0~CH7 값 추출
            for i in range(8):
                idx = CH_COL_START + i
                try:
                    v = row.iloc[idx] if idx < len(row) else None
                    # NaN 처리
                    import math
                    if v is None or (isinstance(v, float) and math.isnan(v)):
                        v = None
                    else:
                        v = float(v)
                except Exception:
                    v = None
                ch_values[f"CH{i}"].append(v)

        # 최신값 (마지막 유효값)
        latest_values = {}
        for i in range(8):
            vals = [v for v in ch_values[f"CH{i}"] if v is not None]
            latest_values[f"CH{i}"] = vals[-1] if vals else None

        entry = {
            "latest_values": latest_values,
            "chart": {
                "labels": labels,
                "values": ch_values,
            },
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        key = f"{company}|{folder}|{filename}"
        with _lock:
            # 인메모리 캐시 기반으로 읽기 (파일 재읽기 최소화)
            cache = _load_cache_from_disk()
            cache[key] = entry
            raw = json.dumps(cache, ensure_ascii=False, separators=(",", ":"))
            CACHE_PATH.write_text(raw, encoding="utf-8")
            # 인메모리 캐시 mtime 동기화
            global _mem_cache, _mem_cache_mtime
            _mem_cache = cache
            try:
                _mem_cache_mtime = CACHE_PATH.stat().st_mtime
            except Exception:
                _mem_cache_mtime = 0.0

    except Exception as e:
        # 캐시 실패는 변환 파이프라인에 영향 없음
        import sys
        print(f"[MonitoringCache] update 실패: {e}", file=sys.stderr)
