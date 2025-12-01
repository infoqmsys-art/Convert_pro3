import tkinter as tk

from ui.main_ui import MainUI
from utils.logger import Logger
from core.config_manager import ConfigManager
from core.tree_manager import TreeManager
from core.sensor_processor import SensorProcessor
from core.file_processor import FileProcessor
from core.scheduler_manager import SchedulerManager


class AppController:
    def __init__(self, root):
        self.root = root
        self.root.title("Analog Sensor Manager")

        # Utils
        self.logger = Logger()

        # Core modules
        self.config = ConfigManager(self.logger)
        self.tree = TreeManager(self.config, self.logger)
        self.sensor = SensorProcessor(self.logger)
        self.file_processor = FileProcessor(
            config=self.config,
            tree=self.tree,
            sensor=self.sensor,
            logger=self.logger
        )
        self.scheduler = SchedulerManager(self, self.logger)

        # UI
        self.ui = MainUI(self.root, self, self.logger)

        # UI 로그 연결
        self.logger.set_ui_callback(self.ui.append_log)

        self.logger.log("AppController 초기화 완료.")

    def convert_now(self):
        self.logger.log("변환 실행 요청 (convert_now).")
        # 여기서 file_processor.run_all() 같은 함수 호출 예정
        pass

    def refresh_tree(self):
        self.logger.log("트리뷰 갱신 요청 (refresh_tree).")
        pass

    def open_channel_settings(self, company, folder, filename):
        self.logger.log(f"채널 설정창 요청: {company}/{folder}/{filename}")
        from ui.channel_settings_ui import ChannelSettingsUI
        ChannelSettingsUI(self.root, self, company, folder, filename)

    def create_csv(self):
        self.logger.log("CSV 생성 팝업 요청.")
        pass

def main():
    root = tk.Tk()
    app = AppController(root)
    root.mainloop()


if __name__ == "__main__":
    main()
