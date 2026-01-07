import datetime
import os
from threading import Lock


class Logger:
    """
    Convert Pro 3 공용 Logger

    ✔ 콘솔 출력
    ✔ UI(Text widget) 출력
    ✔ 파일 로그 저장
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

        # DEBUG 등 낮은 레벨 → 파일만 기록
        if self.LEVEL_ORDER[level] < self.LEVEL_ORDER[self.level]:
            self._write_file(msg, level)
            return

        timestamp = self._now()
        text = f"[{timestamp}] [{level}] {msg}"

        with self.lock:
            # 콘솔 출력
            print(text)

            # 파일 기록
            self._write_file(msg, level, timestamp)

            # UI 출력
            if self.ui_callback:
                try:
                    self.ui_callback(text)
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

    def _write_raw(self, text):
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    def _now(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
