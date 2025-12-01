import threading
import time
import datetime

class SchedulerManager:
    def __init__(self, controller, logger):
        self.controller = controller
        self.logger = logger
        self.thread = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.logger.log("스케줄러 시작됨.")

    def _run(self):
        while self.running:
            now = datetime.datetime.now()
            if now.minute == 1:
                self.logger.log("자동 변환 시간 도달 → convert_now 호출 예정")
                # self.controller.convert_now()
            time.sleep(1)

    def stop(self):
        self.running = False
        self.logger.log("스케줄러 종료됨.")
