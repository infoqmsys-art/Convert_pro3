import datetime
import os
from threading import Lock
import sys

_MAX_LOG_BYTES = 5 * 1024 * 1024   # 5 MB — 초과 시 백업 후 새 파일
_MAX_BACKUP_COUNT = 3               # 유지할 백업 파일 수 (app.log.1 ~ app.log.3)


class Logger:
    """
    Convert Pro 3 공용 Logger

    ✔ 콘솔 출력
    ✔ UI(Text widget) 출력
    ✔ 파일 로그 저장 (5 MB 로테이션, 백업 3개)
    ✔ 로그 레벨 필터링 (DEBUG 숨김 가능)

    기본 정책:
    - UI / 콘솔: INFO 이상
    - 파일 로그: DEBUG 포함 전부 저장
    """

    LEVEL_ORDER = {
        "DEBUG": 10,
        "INFO": 20,
        "WARN": 30,
        "ERROR": 40,
    }

    def __init__(self, base_dir=".", level="INFO", log_name="app.log"):
        self.ui_callback = None
        self.level = level.upper()
        self.lock = Lock()
        # 대량 변환 중 DEBUG 파일 I/O가 병목이 되므로 일시 생략
        self.skip_debug_file = False

        # 로그 디렉토리
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)

        self.log_file = os.path.join(log_dir, log_name)

        # 로그 시작 마커
        self._write_raw(
            f"\n========== LOG START ({self._now()}) ==========\n"
        )

    # ======================================================
    # Public
    # ======================================================
    def set_ui_callback(self, func):
        """
        UI(Text 위젯)에 로그를 표시하기 위한 콜백 연결
        """
        self.ui_callback = func

    def log(self, msg, level="INFO"):
        """
        로그 기록 메인 함수
        """
        level = level.upper()
        if level not in self.LEVEL_ORDER:
            level = "INFO"

        # DEBUG 등 낮은 레벨 → 파일만 기록 (대량 변환 중에는 생략)
        if self.LEVEL_ORDER[level] < self.LEVEL_ORDER[self.level]:
            if not self.skip_debug_file:
                self._write_file(msg, level)
            return

        timestamp = self._now()
        text = f"[{timestamp}] [{level}] {msg}"
        cb = None

        with self.lock:
            try:
                print(text)
            except UnicodeEncodeError:
                safe = text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                    sys.stdout.encoding or "utf-8", errors="replace"
                )
                print(safe)
            self._write_file(msg, level, timestamp)
            cb = self.ui_callback

        # 락 밖에서 호출 — UI 콜백이 Tk를 건드려도 로거 락과 교착하지 않음
        if cb:
            try:
                cb(text)
            except Exception:
                pass

    # ======================================================
    # Internal
    # ======================================================
    def _write_file(self, msg, level, timestamp=None):
        if timestamp is None:
            timestamp = self._now()
        text = f"[{timestamp}] [{level}] {msg}\n"
        self._write_raw(text)

    def _rotate_if_needed(self):
        """로그 파일이 _MAX_LOG_BYTES 초과 시 백업 후 새 파일 시작."""
        try:
            if not os.path.exists(self.log_file):
                return
            if os.path.getsize(self.log_file) < _MAX_LOG_BYTES:
                return
            # 오래된 백업 순서대로 밀어내기
            for i in range(_MAX_BACKUP_COUNT, 0, -1):
                src = f"{self.log_file}.{i}"
                dst = f"{self.log_file}.{i + 1}" if i < _MAX_BACKUP_COUNT else None
                if dst and os.path.exists(src):
                    try:
                        os.replace(src, dst)
                    except Exception:
                        pass
            try:
                os.replace(self.log_file, f"{self.log_file}.1")
            except Exception:
                pass
        except Exception:
            pass

    def _write_raw(self, text):
        try:
            self._rotate_if_needed()
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    def _now(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
