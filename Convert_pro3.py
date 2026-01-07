import os
import tkinter as tk
from version import VERSION_SHORT, APP_NAME, APP_FULL_NAME

APP_VERSION = VERSION_SHORT  # 버전은 version.py에서 관리

ENABLE_MEMORY_TRACKING = True  # ⭐ 프로토타입용 (나중에 False)

from core.config_manager import ConfigManager
from core.tree_manager import TreeManager
from core.file_processor import FileProcessor
from core.sensor_processor import SensorProcessor
from core.scheduler_manager import SchedulerManager
from core.fill_interval_processor import FillIntervalProcessor
from ui.main_ui import MainUI
from utils.logger import Logger
from datetime import datetime
from utils.battery_reader import BatteryReader
from utils.memory_tracker import MemoryTracker
from utils.path_utils import PathUtils
from utils.updater import AutoUpdater

class ConvertPro3App:

    def __init__(self):
        self.base_dir = PathUtils.get_app_dir()

        # =========================
        # Logger
        # =========================
        self.logger = Logger(self.base_dir)

        # =========================
        # Memory Tracker (Prototype)
        # =========================
        self.mem_tracker = None
        if ENABLE_MEMORY_TRACKING:
            self.mem_tracker = MemoryTracker(self.base_dir)
            self.mem_tracker.log("app_start")

        # =========================
        # Runtime state
        # =========================
        self.battery_cache = {}   # (company, folder, filename) → float | None
        self.is_converting = False  # 변환 중 상태 플래그

        # =========================
        # Config / Tree
        # =========================
        config_path = os.path.join(self.base_dir, "config.json")
        self.config = ConfigManager(config_path, self.logger)
        self.tree = TreeManager(self.config, self.logger)

        # =========================
        # Sensor
        # =========================
        self.sensor = SensorProcessor(self.logger)

        # =========================
        # FillIntervalProcessor  ✅ 먼저 생성
        # =========================
        self.fill_interval_processor = FillIntervalProcessor(self.logger)

        # =========================
        # FileProcessor  ✅ 나중에 주입
        # =========================
        self.file_processor = FileProcessor(
            config=self.config,
            tree=self.tree,
            sensor=self.sensor,
            fill_interval=self.fill_interval_processor,
            logger=self.logger,
            convert_root=r"C:\data\Convertfile"
        )
        
        # =========================
        # BatteryReader
        # =========================
        self.battery_reader = BatteryReader(self.logger)

        # UI
        self.root = tk.Tk()
        self.root.title(APP_FULL_NAME)
        self.ui = MainUI(self.root, self)

        # Scheduler  ← UI 생성 이후
        self.scheduler = SchedulerManager(self, self.logger)
        self.scheduler.start()

        # =========================
        # Auto Updater
        # =========================
        self.updater = AutoUpdater(
            current_version=APP_VERSION,
            update_server_url="https://yourserver.com/updates",  # TODO: 실제 서버 URL로 변경
            logger=self.logger
        )
        self.update_info = None  # 업데이트 정보 저장

        # 초기 1회 배터리 로드
        self.root.after(200, self.refresh_all_battery_cache)
        
        # 백그라운드 업데이트 체크 (5초 후)
        self.root.after(5000, self.check_for_updates_background)

        self.logger.log(f"[{APP_VERSION}] 초기화 완료")

    # ======================================================
    # 공용 유틸
    # ======================================================
    def _ui_call(self, func, *args):
        try:
            self.root.after(0, lambda: func(*args))
        except:
            pass

    def iter_config_files(self):
        # 딕셔너리 순회 중 변경 방지를 위해 복사본 사용
        for company, folders in list(self.config.data.items()):
            if company.startswith("__"):
                continue
            for folder, folder_dict in list(folders.items()):
                if folder.startswith("__"):
                    continue
                for filename in list(folder_dict.keys()):
                    if filename.lower().endswith(".csv"):
                        yield company, folder, filename

    def get_convert_path(self, company, folder, filename):
        return os.path.join(
            self.file_processor.convert_root,
            company, folder, filename
        )

    # ======================================================
    # 배터리 포맷 (UI 전용)
    # ======================================================
    def format_battery(self, value):
        if value is None or value == "":
            return ""
        try:
            return f"{float(value):.2f} %"
        except:
            return ""

    # ======================================================
    # 배터리 갱신
    # ======================================================
    def refresh_battery_for_files(self, targets):
        """
        targets: iterable of (company, folder, filename)
        """
        for company, folder, filename in targets:
            path = self.get_convert_path(company, folder, filename)
            batt = self.battery_reader.read_last_battery(path)

            key = (company, folder, filename)
            self.battery_cache[key] = batt

            self._ui_call(
                self.ui.update_battery,
                company, folder, filename,
                self.format_battery(batt)
            )

    def refresh_all_battery_cache(self):
        self.refresh_battery_for_files(self.iter_config_files())

    # ======================================================
    # 변환 요청
    # ======================================================
    def convert_now(self):
        if self.is_converting:
            self.logger.log("이미 변환 작업이 진행 중입니다.", level="WARNING")
            return
        
        import threading
        t = threading.Thread(target=self._thread_convert, daemon=True)
        t.start()

    def _thread_convert(self):
        try:
            self.is_converting = True
            self._ui_call(self.ui.set_buttons_enabled, False)
            
            start = datetime.now()

            self.logger.log(
                f"{APP_FULL_NAME} 전체 변환 시작",
                level="INFO"
            )
            self._log_memory("convert_all_start")

            # 전체 파일 수 계산
            all_files = list(self.iter_config_files())
            total = len(all_files)
            converted = 0
            skipped = 0
            fill_applied = 0

            for idx, (company, folder, filename) in enumerate(all_files, 1):
                # 진행 상태 업데이트
                progress = idx / total
                status_msg = f"변환 중... {idx}/{total} 파일 처리 중 ({filename})"
                self._ui_call(self.ui.update_status, status_msg, progress)
                
                result = self.file_processor.convert_file(company, folder, filename)

                if result == "converted":
                    converted += 1
                elif result == "fill":
                    converted += 1
                    fill_applied += 1
                else:
                    skipped += 1

            elapsed = (datetime.now() - start).seconds

            self.logger.log(
                f"전체 처리 완료\n"
                f"- 대상 파일: {total}\n"
                f"- 실제 변환: {converted}\n"
                f"- 누락 보정 적용: {fill_applied}\n"
                f"- 스킵: {skipped}\n"
                f"- 소요 시간: {elapsed}s",
                level="INFO"
            )

            self._ui_call(self.ui.update_status, "변환 완료", 1.0)
            self._ui_call(self.ui.refresh_tree)
            self._log_memory("convert_all_end")

        except Exception as e:
            self.logger.log(
                f"전체 변환 중 오류 발생: {e}",
                level="ERROR"
            )
            self._ui_call(self.ui.update_status, "변환 오류 발생", 0)
        finally:
            self.is_converting = False
            self._ui_call(self.ui.set_buttons_enabled, True)

    def _log_memory(self, stage, extra=None):
        """
        메모리 로깅 헬퍼
        ENABLE_MEMORY_TRACKING=False면 자동 무시
        """
        if self.mem_tracker:
            self.mem_tracker.log(stage, extra)

    # ======================================================
    # 자동 업데이트
    # ======================================================
    def check_for_updates_background(self):
        """백그라운드에서 업데이트 확인 (UI 블록 없음)"""
        try:
            has_update, update_info = self.updater.check_for_updates(timeout=5)
            if has_update:
                self.update_info = update_info
                # UI에 알림 표시
                self._ui_call(self.ui.show_update_notification, update_info)
        except Exception as e:
            self.logger.log(f"업데이트 확인 중 오류: {e}", level="DEBUG")
    
    def install_update(self):
        """업데이트 다운로드 및 설치"""
        if not self.update_info:
            self.logger.log("설치할 업데이트 정보가 없습니다", level="WARN")
            return
        
        try:
            # UI 상태 업데이트
            self._ui_call(self.ui.update_status, "업데이트 다운로드 중...", 0)
            
            def progress_callback(percent):
                self._ui_call(self.ui.update_status, f"업데이트 다운로드 중... {percent}%", percent / 100.0)
            
            # 업데이트 다운로드 및 설치 (이 메서드는 프로그램을 종료시킴)
            self.updater.download_and_install(self.update_info, progress_callback)
            
        except Exception as e:
            self.logger.log(f"업데이트 설치 실패: {e}", level="ERROR")
            self._ui_call(self.ui.update_status, "업데이트 실패", 0)

    # ======================================================
    # 기타 UI 연동
    # ======================================================
    def create_csv(self):
        self.logger.log("[Controller] CSV 생성 기능 준비 중")

    def open_channel_settings(self, company, folder, filename):
        from ui.channel_settings_ui import ChannelSettingsUI
        ChannelSettingsUI(self.ui.root, self, company, folder, filename)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ConvertPro3App().run()
