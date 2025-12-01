import json
import os

class ConfigManager:
    def __init__(self, logger, path="config.json"):
        self.logger = logger
        self.path = path
        self.data = {}

        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.logger.log("config.json 없음 → 새로 생성 예정")
            self.data = {}
            self.save()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            self.logger.log("config 로딩 완료.")
        except Exception as e:
            self.logger.log(f"config 로딩 실패: {e}", level="ERROR")
            self.data = {}

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            self.logger.log("config 저장 완료.")
        except Exception as e:
            self.logger.log(f"config 저장 실패: {e}", level="ERROR")
