# utils/memory_tracker.py

import os
import json
from datetime import datetime

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


class MemoryTracker:
    """
    Convert Pro 3 - Runtime Memory Tracker (Prototype)

    - 현재 프로세스 메모리(RSS) 측정
    - 실행 단계별 메모리 사용량을 JSON으로 기록
    - psutil 미설치 시 자동 비활성화 (프로그램 영향 없음)
    """

    def __init__(self, base_dir: str, filename: str = "runtime_memory.json"):
        """
        base_dir : 프로그램(EXE)이 있는 기준 디렉터리
        filename : 생성될 JSON 파일명
        """
        self.enabled = _PSUTIL_AVAILABLE

        # ✅ 항상 프로그램 위치 기준으로 파일 생성
        self.path = os.path.join(base_dir, filename)

        if self.enabled:
            try:
                self.process = psutil.Process(os.getpid())
            except Exception:
                # psutil은 있으나 프로세스 접근 실패 시도 대비
                self.enabled = False

    # --------------------------------------------------
    # 내부 유틸
    # --------------------------------------------------
    def _get_memory_mb(self) -> float:
        """현재 프로세스 RSS 메모리를 MB 단위로 반환"""
        mem_bytes = self.process.memory_info().rss
        return round(mem_bytes / (1024 * 1024), 2)

    # --------------------------------------------------
    # 외부 호출 API
    # --------------------------------------------------
    def log(self, stage: str, extra: dict | None = None):
        """
        stage : 실행 단계 이름 (예: app_start, convert_all_start 등)
        extra : 부가 정보(dict, 선택)
        """
        if not self.enabled:
            return

        record = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stage": stage,
            "memory_mb": self._get_memory_mb(),
        }

        if extra:
            record["extra"] = extra

        try:
            # 기존 파일이 있으면 이어서 기록
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {
                    "start_time": record["ts"],
                    "records": []
                }

            data["records"].append(record)

            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception:
            # ⚠️ 메모리 로깅 실패로 프로그램이 멈추면 안 됨
            pass
