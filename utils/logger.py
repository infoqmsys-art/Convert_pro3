import datetime
import os


class Logger:
    """
    UI 로그 / 콘솔 로그 / 파일 로그를 모두 지원하는 로거 클래스.
    UI(Text) 위젯은 set_ui_callback()을 통해 연결한다.
    """

    def __init__(self, log_file="app.log"):
        self.ui_callback = None
        self.log_file = log_file

        # 로그 파일 초기 생성
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"\n========== 로그 시작 ({self._now()}) ==========\n")
        except Exception:
            pass

    def set_ui_callback(self, func):
        """UI용 로그 콜백 설정"""
        self.ui_callback = func

    def log(self, msg, level="INFO"):
        timestamp = self._now()
        text = f"[{timestamp}] [{level}] {msg}"

        print(text)
        self._write_to_file(text)

        if self.ui_callback:
            try:
                self.ui_callback(text)
            except:
                pass

    # 내부 유틸
    def _now(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write_to_file(self, text):
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except:
            pass
