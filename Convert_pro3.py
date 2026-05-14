"""
================================================================================
컨버트 프로그램 (Convert Pro 3)
================================================================================
QM 계측 로거의 원본 CSV 파일을 읽어 표준 형식으로 변환·저장하는 데스크톱 앱.

주요 기능
---------
- 원본 CSV 자동 감지 및 주기 변환 (스케줄러)
- 센서 타입별 공학 단위 환산 (SensorProcessor)
- 누락 구간 자동 보충 (FillIntervalProcessor)
- 채널·파일 설정 GUI (Tkinter)
- 모니터링 웹 대시보드 연동 (monitoring/server.py)
- 계측관리 통합시스템 연동 (measurement_portal/)

프로젝트 구성
-------------
  Convert_pro3.py          ← 이 파일 (진입점·앱 초기화)
  core/                    핵심 로직 (변환·스케줄링·설정)
  ui/                      Tkinter 화면
  utils/                   공통 유틸
  monitoring/server.py     QM 자동화 관제시스템 (Flask 웹)
  measurement_portal/      계측관리 통합시스템 (Flask 웹)
================================================================================
"""
import os
import sys
import time
import tkinter as tk
import threading
from tkinter import messagebox
from concurrent.futures import ThreadPoolExecutor, as_completed
from version import VERSION, APP_NAME, APP_FULL_NAME

APP_VERSION = VERSION  # 버전은 version.py에서 관리

ENABLE_MEMORY_TRACKING = False  # 프로덕션 24시간 운용 시 비활성화 (런타임_memory.json 누적 방지)

from core.config_manager import ConfigManager
from core.management_manager import ManagementManager
from core.tree_manager import TreeManager
from core.file_processor import FileProcessor
from core.sensor_processor import SensorProcessor
from core.scheduler_manager import SchedulerManager
from core.fill_interval_processor import FillIntervalProcessor
from ui.main_ui import MainUI
from ui.channel_settings_ui import ChannelSettingsUI
from utils.logger import Logger
from datetime import datetime
import pandas as pd
from utils.battery_reader import BatteryReader
from utils.memory_tracker import MemoryTracker
from utils.path_utils import PathUtils

try:
    from utils.update_manager import UpdateManager
except ImportError:
    UpdateManager = None  # 업데이트 매니저 import 실패 시 None

_MONITORING_FAIL_MSG = ""
_start_monitoring_server = None
_monitoring_server_mod   = None   # 콜백 등록에 사용


def _load_monitoring_server():
    """
    외부 monitoring/server.py 우선 동적 로드.
    dist 폴더 옆에 monitoring/server.py 가 있으면 그것을 사용하고,
    없으면 PyInstaller 번들 내 내장 모듈을 사용한다.
    (모듈 객체를 반환하여 set_category_saved_callback 등 접근 가능)
    """
    import importlib.util
    from pathlib import Path

    if getattr(sys, "frozen", False):
        _app_dir = Path(sys.executable).parent
    else:
        _app_dir = Path(__file__).parent

    external = _app_dir / "monitoring" / "server.py"

    if external.exists():
        _parent = str(_app_dir)
        if _parent not in sys.path:
            sys.path.insert(0, _parent)
        spec = importlib.util.spec_from_file_location("monitoring.server", external)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["monitoring.server"] = mod
        spec.loader.exec_module(mod)
        return mod
    else:
        import monitoring.server as mod
        return mod


_MONITORING_AVAILABLE = False
try:
    _monitoring_server_mod   = _load_monitoring_server()
    _start_monitoring_server = _monitoring_server_mod.start_server
    _MONITORING_AVAILABLE = True
except Exception as e:
    _MONITORING_FAIL_MSG = str(e)

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
        self.battery_cache = {}   # (company, site, folder, filename) → float | None
        self.is_converting = False  # 변환 중 상태 플래그
        self.convert_stop_requested = False  # 변환 중지 요청 플래그
        self.convert_lock = threading.Lock()  # 로그 출력용 락
        self.max_workers = 4  # 동시 변환 스레드 수
        self.open_settings_windows = {}  # 열린 센서 설정 창 추적 {파일키: 창}
        self._last_trim_cutoff = self._load_last_trim_cutoff()  # 변환본 시간 이후 삭제 마지막 사용값

        # =========================
        # Config / Tree
        # =========================
        config_path = os.path.join(self.base_dir, "config.json")
        self.config = ConfigManager(config_path, self.logger)
        self.tree = TreeManager(self.config, self.logger)

        # =========================
        # ManagementManager (관리 데이터 분리)
        # management.json 없으면 config.json에서 자동 마이그레이션
        # =========================
        self.mgmt = ManagementManager(self.base_dir, logger=self.logger)
        self.mgmt.migrate_from_config(config_path)

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
        
        # =========================
        # UpdateManager (optional)
        # =========================
        self.update_manager = None
        if UpdateManager:
            try:
                self.update_manager = UpdateManager(self.logger)
            except Exception as e:
                self.logger.log(f"UpdateManager 초기화 실패: {e}", level="WARNING")

        # UI
        self.root = tk.Tk()
        self.root.title(APP_FULL_NAME)
        self.ui = MainUI(self.root, self)
        
        # UI 로드 후 크기 조정 (이미지 기준 적절한 크기)
        self.root.update_idletasks()  # 창 크기 계산을 위해 업데이트
        # UI가 완전히 로드된 후 실제 필요한 너비 사용
        self.root.after(100, lambda: self._adjust_window_size())  # 약간의 지연 후 크기 조정
    
    def _adjust_window_size(self):
        """창 크기 조정 (UI 로드 완료 후)"""
        self.root.update_idletasks()
        current_width = self.root.winfo_width()
        # 실제 필요한 너비 사용 (UI가 계산한 크기 그대로 사용)
        # 세로만 800으로 고정
        self.root.geometry(f"{current_width}x800")

        # Scheduler  ← UI 생성 이후
        self.scheduler = SchedulerManager(self, self.logger)
        self.scheduler.start()

        # 모니터링 웹 서버 (daemon 스레드 -> 앱 종료 시 자동 종료)
        self._mon_thread = None
        if _MONITORING_AVAILABLE:
            self._start_web_server_thread()

            # 웹에서 카테고리 「저장」(save_all 등 일괄 반영) 시에만 콜백 → mgmt 재로드 + 트리 1회 갱신
            if _monitoring_server_mod and hasattr(_monitoring_server_mod, 'set_category_saved_callback'):
                def _on_cat_saved():
                    try:
                        if hasattr(self, 'mgmt') and self.mgmt:
                            self.mgmt.reload()
                        self.root.after(0, self.ui.refresh_tree)
                    except Exception:
                        pass
                _monitoring_server_mod.set_category_saved_callback(_on_cat_saved)

            # monitoring/ 파일 변경 감시 → 자동 알림
            self._start_monitoring_watcher()

        elif _MONITORING_FAIL_MSG:
            self.logger.log(
                f'모니터링 웹 비활성화 (Flask 등 미설치): {_MONITORING_FAIL_MSG} → '
                f'프로그램과 동일한 Python으로: python -m pip install flask',
                level='WARN',
            )

        # 초기 1회 배터리 로드
        self.root.after(200, self.refresh_all_battery_cache)

        self.logger.log(f"[{APP_VERSION}] 초기화 완료")

    # ======================================================
    # 웹 서버 관리
    # ======================================================
    def _start_web_server_thread(self):
        """모니터링 웹 서버 데몬 스레드 시작"""
        _mon = threading.Thread(
            target=_start_monitoring_server,
            kwargs={'open_browser': False},
            daemon=True,
            name='MonitoringServer'
        )
        _mon.start()
        self._mon_thread = _mon
        self.logger.log('모니터링 서버: http://localhost:5050', level='INFO')

    def do_web_patch(self, repo_path: str, status_cb=None) -> dict:
        """
        git pull + 필요 시 monitoring/ 실행 폴더 동기화.
        git 이 최신이라도 실행 폴더 monitoring 과 저장소 내용이 다르면 복사합니다.

        repo_path : Convert_pro3 소스 저장소 루트 경로 (git clone 위치)
        status_cb : 진행 상황 문자열 콜백 (선택)
        반환값    : {'server_changed': bool, 'template_changed': bool, 'no_change': bool}
        """
        import subprocess
        import shutil
        from pathlib import Path

        def _status(msg):
            self.logger.log(f'[WebPatch] {msg}', level='INFO')
            if status_cb:
                status_cb(msg)

        def _files_differ(sa: Path, sb: Path) -> bool:
            if not sa.exists() or not sa.is_file():
                return False
            if not sb.exists():
                return True
            try:
                return sa.read_bytes() != sb.read_bytes()
            except Exception:
                return True

        def _monitoring_differs(src_root: Path, dst_root: Path):
            srv = tpl = False
            need = False
            for py_name in ('server.py', 'data_cache.py', '__init__.py'):
                a = src_root / py_name
                if not a.exists():
                    continue
                if _files_differ(a, dst_root / py_name):
                    need = True
                    if py_name in ('server.py', 'data_cache.py'):
                        srv = True
            tsrc = src_root / 'templates'
            if tsrc.exists():
                for fpath in tsrc.rglob('*'):
                    if not fpath.is_file():
                        continue
                    rel = fpath.relative_to(tsrc)
                    if _files_differ(fpath, dst_root / 'templates' / rel):
                        need = True
                        tpl = True
            return need, srv, tpl

        repo = Path(repo_path)
        src_monitoring = repo / 'monitoring'
        dst_monitoring = Path(self.base_dir) / 'monitoring'

        if not src_monitoring.exists():
            raise FileNotFoundError(
                f"저장소에서 monitoring/ 폴더를 찾을 수 없습니다: {src_monitoring}\n"
                "올바른 Convert_pro3 저장소 폴더를 선택하세요."
            )

        # ① git pull — 브랜치 명시 (upstream 미설정된 클론에서도 동작)
        br_cmd = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='replace',
        )
        branch = (br_cmd.stdout or '').strip()
        if not branch or branch == 'HEAD':
            branch = 'main'

        _status(f'git pull 실행 중... (origin {branch})')
        result = subprocess.run(
            ['git', 'pull', 'origin', branch],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode != 0 and branch == 'main':
            _status('origin main 실패 — origin master 재시도...')
            result = subprocess.run(
                ['git', 'pull', 'origin', 'master'],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=120,
                encoding='utf-8',
                errors='replace'
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"git pull 실패:\n{result.stderr.strip() or result.stdout.strip()}"
            )

        pull_output = result.stdout.strip()
        _status(f'git pull 완료: {pull_output[:120]}')

        need_sync, server_changed, template_changed = _monitoring_differs(
            src_monitoring, dst_monitoring
        )

        if not need_sync:
            lo = pull_output.lower()
            if 'already up to date' in lo or 'already up-to-date' in lo:
                _status('저장소 최신 · 실행 폴더 monitoring 과 동일')
            else:
                _status('이번 pull 에 monitoring 변경 없음 · 실행 폴더 동일')
            return {'no_change': True, 'server_changed': False, 'template_changed': False}

        # ② monitoring/ 복사
        _status('monitoring/ 실행 폴더로 복사 중...')
        dst_monitoring.mkdir(parents=True, exist_ok=True)
        (dst_monitoring / 'templates').mkdir(parents=True, exist_ok=True)

        for py_name in ('server.py', 'data_cache.py', '__init__.py'):
            src = src_monitoring / py_name
            if src.exists():
                shutil.copy2(src, dst_monitoring / py_name)

        templates_src = src_monitoring / 'templates'
        if templates_src.exists():
            shutil.copytree(
                str(templates_src),
                str(dst_monitoring / 'templates'),
                dirs_exist_ok=True
            )

        _status(f'복사 완료 (server.py변경={server_changed}, templates변경={template_changed})')
        return {
            'no_change': False,
            'server_changed': server_changed,
            'template_changed': template_changed
        }

    def do_web_patch_zip(self, status_cb=None) -> dict:
        """
        git 없이 GitHub ZIP으로 monitoring/ 최신화.
        서버 PC에 git 미설치 시 사용.
        """
        import shutil
        import tempfile
        import zipfile
        import requests
        from pathlib import Path

        GITHUB_ZIP_URL = "https://github.com/infoqmsys-art/Convert_pro3/archive/refs/heads/main.zip"
        dst_monitoring = Path(self.base_dir) / 'monitoring'

        def _status(msg):
            self.logger.log(f'[WebPatchZIP] {msg}', level='INFO')
            if status_cb:
                status_cb(msg)

        _status('GitHub에서 최신 소스 다운로드 중...')

        with tempfile.TemporaryDirectory(prefix='qm_webpatch_') as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / 'source.zip'

            # 다운로드
            resp = requests.get(GITHUB_ZIP_URL, stream=True, timeout=60)
            resp.raise_for_status()
            with open(zip_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

            _status('압축 해제 중...')
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(tmp_path)

            # 압축 해제 후 최상위 폴더 찾기 (Convert_pro3-main/)
            extracted_dirs = [d for d in tmp_path.iterdir()
                              if d.is_dir() and d.name != '__MACOSX']
            if not extracted_dirs:
                raise RuntimeError("압축 해제 실패: 폴더를 찾을 수 없습니다.")
            repo_root = extracted_dirs[0]
            src_monitoring = repo_root / 'monitoring'

            if not src_monitoring.exists():
                raise RuntimeError("다운로드된 소스에 monitoring/ 폴더가 없습니다.")

            # 변경 여부 확인 (mtime 비교 대신 파일 내용 비교)
            _status('변경 사항 확인 중...')
            server_changed = False
            template_changed = False

            def _files_differ(a: Path, b: Path) -> bool:
                if not b.exists():
                    return True
                try:
                    return a.read_bytes() != b.read_bytes()
                except Exception:
                    return True

            for py_name in ('server.py', 'data_cache.py'):
                src = src_monitoring / py_name
                dst = dst_monitoring / py_name
                if src.exists() and _files_differ(src, dst):
                    server_changed = True

            templates_src = src_monitoring / 'templates'
            if templates_src.exists():
                for f in templates_src.rglob('*'):
                    if f.is_file():
                        rel = f.relative_to(templates_src)
                        if _files_differ(f, dst_monitoring / 'templates' / rel):
                            template_changed = True
                            break

            if not server_changed and not template_changed:
                return {'no_change': True, 'server_changed': False, 'template_changed': False}

            # 복사
            _status('파일 복사 중...')
            dst_monitoring.mkdir(parents=True, exist_ok=True)
            (dst_monitoring / 'templates').mkdir(parents=True, exist_ok=True)

            for py_name in ('server.py', 'data_cache.py', '__init__.py'):
                src = src_monitoring / py_name
                if src.exists():
                    shutil.copy2(src, dst_monitoring / py_name)

            if templates_src.exists():
                shutil.copytree(
                    str(templates_src),
                    str(dst_monitoring / 'templates'),
                    dirs_exist_ok=True
                )

        _status(f'완료 (server.py={server_changed}, templates={template_changed})')
        return {
            'no_change': False,
            'server_changed': server_changed,
            'template_changed': template_changed
        }

    def restart_web_server(self):
        """
        웹 서버(Flask) 재시작 — server.py 패치 후 사용.
        프로그램 전체를 새 프로세스로 교체(os.execv 방식).
        config/management 등 모든 파일 기반 상태는 그대로 유지됨.
        """
        import subprocess
        self.logger.log('[WebRestart] 프로그램을 재시작합니다...', level='INFO')
        try:
            # 새 프로세스 먼저 띄우고 현재 프로세스 종료
            subprocess.Popen(
                [sys.executable] + sys.argv,
                cwd=os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                    else os.path.dirname(os.path.abspath(__file__))
            )
        except Exception as e:
            self.logger.log(f'[WebRestart] 재시작 실패: {e}', level='ERROR')
            return
        self.root.after(500, lambda: sys.exit(0))

    def _start_monitoring_watcher(self):
        """
        monitoring/ 폴더 파일 변경 감시 스레드.
        server.py 가 변경되면 UI에 [웹 재시작] 알림을 표시한다.
        templates/ 변경은 Flask TEMPLATES_AUTO_RELOAD 로 자동 반영되므로 알림만.
        """
        from pathlib import Path

        def _watch():
            monitoring_dir = Path(self.base_dir) / 'monitoring'
            if not monitoring_dir.exists():
                return

            # 초기 mtime 기록
            mtimes = {}
            for f in monitoring_dir.rglob('*'):
                if f.is_file() and f.suffix in ('.py', '.html', '.js', '.css'):
                    try:
                        mtimes[str(f)] = f.stat().st_mtime
                    except Exception:
                        pass

            while True:
                time.sleep(4)
                try:
                    server_changed = False
                    template_changed = False
                    for f in monitoring_dir.rglob('*'):
                        if not f.is_file() or f.suffix not in ('.py', '.html', '.js', '.css'):
                            continue
                        try:
                            mtime = f.stat().st_mtime
                        except Exception:
                            continue
                        key = str(f)
                        if key in mtimes and mtimes[key] != mtime:
                            mtimes[key] = mtime
                            if f.suffix == '.py':
                                server_changed = True
                            else:
                                template_changed = True
                        elif key not in mtimes:
                            mtimes[key] = mtime

                    if server_changed:
                        self.logger.log(
                            '[패치] server.py 변경 감지 — [웹 재시작] 버튼을 눌러 반영하세요', level='INFO'
                        )
                        self.root.after(0, lambda: self.ui.show_web_restart_banner())
                    elif template_changed:
                        self.logger.log(
                            '[패치] templates 변경 감지 — 브라우저 새로고침으로 즉시 반영됩니다', level='INFO'
                        )
                except Exception:
                    pass

        watcher = threading.Thread(target=_watch, daemon=True, name='MonitoringWatcher')
        watcher.start()

    # ======================================================
    # 공용 유틸
    # ======================================================
    def _ui_call(self, func, *args):
        try:
            self.root.after(0, lambda: func(*args))
        except:
            pass

    def iter_config_files(self):
        """모든 파일 순회 (Site 레벨 포함)"""
        # 딕셔너리 순회 중 변경 방지를 위해 복사본 사용
        for company, sites in list(self.config.data.items()):
            if company.startswith("__"):
                continue
            for site_name, site_data in list(sites.items()):
                if site_name.startswith("__") or not isinstance(site_data, dict):
                    continue
                for folder, folder_dict in list(site_data.items()):
                    if folder.startswith("__") or not isinstance(folder_dict, dict):
                        continue
                    for filename in list(folder_dict.keys()):
                        if not filename.startswith("__") and filename.lower().endswith(".csv"):
                            yield company, site_name, folder, filename

    def get_convert_path(self, company, site, folder, filename):
        """
        변환본 경로 반환
        경로: C:\\data\\Convertfile\\{company}\\{folder}\\{filename}
        - 폴더명(로거 식별자)으로 매핑, 현장은 트리용 논리 레벨
        """
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
        targets: iterable of (company, site, folder, filename)
        """
        for company, site, folder, filename in targets:
            path = self.get_convert_path(company, site, folder, filename)
            batt = self.battery_reader.read_last_battery(path)

            key = (company, site, folder, filename)
            self.battery_cache[key] = batt

            self._ui_call(
                self.ui.update_battery,
                company, site, folder, filename,
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
        self.convert_stop_requested = False
        import threading
        t = threading.Thread(target=self._thread_convert, daemon=True)
        t.start()

    def convert_stop(self):
        """변환 중지 요청 (진행 중인 작업은 완료 후, 대기 중인 작업은 취소)"""
        if self.is_converting:
            self.convert_stop_requested = True
            self.logger.log("변환 중지 요청됨", level="INFO")

    def _thread_convert(self):
        """멀티스레딩 변환 (ThreadPoolExecutor 사용)"""
        try:
            self.is_converting = True
            self._ui_call(self.ui.set_buttons_enabled, False)
            
            start = datetime.now()

            self._thread_safe_log(
                f"{APP_FULL_NAME} 전체 변환 시작 (멀티스레딩: {self.max_workers} workers)",
                level="INFO"
            )
            self._log_memory("convert_all_start")

            # 전체 파일 수 계산
            all_files = list(self.iter_config_files())
            total = len(all_files)
            
            if total == 0:
                self._thread_safe_log("변환할 파일이 없습니다.", level="INFO")
                self._ui_call(self.ui.update_status, "변환할 파일 없음", 1.0)
                return

            converted = 0
            skipped = 0
            fill_applied = 0
            errors = []
            completed_count = 0

            # ThreadPoolExecutor로 병렬 처리
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 모든 파일 변환 작업 제출
                future_to_file = {
                    executor.submit(
                        self._convert_single_file_safe,
                        company, site, folder, filename
                    ): (company, site, folder, filename)
                    for company, site, folder, filename in all_files
                }

                # 완료된 작업 처리 (중지 요청 시 루프 탈출)
                for future in as_completed(future_to_file):
                    company, site, folder, filename = future_to_file[future]
                    completed_count += 1

                    try:
                        result = future.result()
                        if result == "converted":
                            converted += 1
                        elif result == "fill":
                            converted += 1
                            fill_applied += 1
                        elif result == "error":
                            errors.append((company, site, folder, filename))
                        else:
                            skipped += 1

                        # 진행률 업데이트
                        progress = completed_count / total
                        status_msg = f"변환 중... {completed_count}/{total} 파일 처리 완료"
                        self._ui_call(self.ui.update_status, status_msg, progress)

                    except Exception as e:
                        errors.append((company, site, folder, filename))
                        self._thread_safe_log(
                            f"변환 오류: {company}/{site}/{folder}/{filename} - {e}",
                            level="ERROR"
                        )

                    if self.convert_stop_requested:
                        cancelled = sum(1 for f in future_to_file if not f.done() and f.cancel())
                        if cancelled:
                            self._thread_safe_log(
                                f"변환 중지: 대기 중인 {cancelled}개 작업 취소됨",
                                level="INFO"
                            )
                        break

            elapsed = (datetime.now() - start).seconds
            stop_msg = " (중지 요청으로 일부만 처리)" if self.convert_stop_requested else ""

            self._thread_safe_log(
                f"전체 처리 완료{stop_msg}\n"
                f"- 대상 파일: {total}\n"
                f"- 실제 변환: {converted}\n"
                f"- 누락 보정 적용: {fill_applied}\n"
                f"- 스킵: {skipped}\n"
                f"- 오류: {len(errors)}\n"
                f"- 소요 시간: {elapsed}s",
                level="INFO"
            )

            if errors:
                self._thread_safe_log(
                    f"오류 발생 파일 ({len(errors)}개):\n" + 
                    "\n".join([f"  - {c}/{s}/{f}/{n}" for c, s, f, n in errors[:10]]),
                    level="ERROR"
                )

            status_end = "변환 중지됨" if self.convert_stop_requested else "변환 완료"
            self._ui_call(self.ui.update_status, status_end, 1.0)
            
            # 변환 완료 후 배터리 갱신
            self.refresh_battery_for_files(all_files)
            
            self._ui_call(self.ui.refresh_tree)
            self._log_memory("convert_all_end")

        except Exception as e:
            import traceback
            error_detail = f"{type(e).__name__}: {str(e)}"
            self._thread_safe_log(
                f"전체 변환 중 오류 발생: {error_detail}",
                level="ERROR"
            )
            # 상세 오류 정보를 로그에 기록 (디버깅용)
            self._thread_safe_log(
                f"오류 상세 정보:\n{traceback.format_exc()}",
                level="ERROR"
            )
            self._ui_call(self.ui.update_status, f"변환 오류: {error_detail[:50]}", 0)
        finally:
            self.is_converting = False
            self._ui_call(self.ui.set_buttons_enabled, True)
    
    def _convert_single_file_safe(self, company, site, folder, filename):
        """스레드 안전한 단일 파일 변환"""
        try:
            return self.file_processor.convert_file(company, site, folder, filename)
        except Exception as e:
            self._thread_safe_log(
                f"파일 변환 실패 {company}/{site}/{folder}/{filename}: {e}",
                level="ERROR"
            )
            return "error"
    
    def _thread_safe_log(self, message, level="INFO"):
        """스레드 안전한 로그 출력"""
        with self.convert_lock:
            self.logger.log(message, level=level)
            # UI 로그창에도 출력
            self._ui_call(self.ui.append_log, f"[{level}] {message}")

    # ======================================================
    # 폴더 단위 변환
    # ======================================================
    def convert_folder(self, company, site, folder):
        """폴더 전체 변환 (Site 레벨 포함)"""
        if self.is_converting:
            self.logger.log("이미 변환 작업이 진행 중입니다.", level="WARNING")
            return
        self.convert_stop_requested = False
        import threading
        t = threading.Thread(target=self._thread_convert_folder, args=(company, site, folder), daemon=True)
        t.start()

    def _thread_convert_folder(self, company, site, folder):
        """폴더 전체 변환 스레드 (Site 레벨 포함)"""
        try:
            self.is_converting = True
            self._ui_call(self.ui.set_buttons_enabled, False)
            
            start = datetime.now()

            self.logger.log(
                f"폴더 변환 시작: {company}/{site}/{folder}",
                level="INFO"
            )

            # 폴더 내 파일 목록 가져오기
            folder_dict = self.config.data.get(company, {}).get(site, {}).get(folder, {})
            files = [f for f in folder_dict.keys() if f.lower().endswith(".csv") and not f.startswith("__")]
            
            total = len(files)
            converted = 0
            skipped = 0
            fill_applied = 0

            for idx, filename in enumerate(files, 1):
                if self.convert_stop_requested:
                    self.logger.log("변환 중지 요청으로 폴더 변환 중단", level="INFO")
                    break

                # 진행 상태 업데이트
                progress = idx / total if total > 0 else 0
                status_msg = f"폴더 변환 중... {idx}/{total} 파일 처리 중 ({filename})"
                self._ui_call(self.ui.update_status, status_msg, progress)

                result = self.file_processor.convert_file(company, site, folder, filename)

                if result == "converted":
                    converted += 1
                elif result == "fill":
                    converted += 1
                    fill_applied += 1
                else:
                    skipped += 1

            elapsed = (datetime.now() - start).seconds
            stop_msg = " (중지 요청)" if self.convert_stop_requested else ""

            self.logger.log(
                f"폴더 변환 완료{stop_msg}: {company}/{site}/{folder}\n"
                f"- 대상 파일: {total}\n"
                f"- 실제 변환: {converted}\n"
                f"- 누락 보정 적용: {fill_applied}\n"
                f"- 스킵: {skipped}\n"
                f"- 소요 시간: {elapsed}s",
                level="INFO"
            )

            status_end = "폴더 변환 중지됨" if self.convert_stop_requested else f"폴더 변환 완료: {folder}"
            self._ui_call(self.ui.update_status, status_end, 1.0)
            
            # 변환 완료 후 배터리 갱신
            converted_files = [(company, site, folder, f) for f in files]
            self.refresh_battery_for_files(converted_files)
            
            self._ui_call(self.ui.refresh_tree)

        except Exception as e:
            self.logger.log(
                f"폴더 변환 중 오류 발생: {e}",
                level="ERROR"
            )
            self._ui_call(self.ui.update_status, "변환 오류 발생", 0)
        finally:
            self.is_converting = False
            self._ui_call(self.ui.set_buttons_enabled, True)

    # ======================================================
    # 카테고리(대분류/소분류) 단위 일괄 변환
    # ======================================================

    def convert_files_batch(self, files_list, label="일괄"):
        """[(company, site, folder, filename), ...] 리스트를 일괄 변환.
        우클릭 메뉴의 '대분류 업로드' / '소분류 업로드'에서 호출.
        """
        if self.is_converting:
            self.logger.log("이미 변환 작업이 진행 중입니다.", level="WARNING")
            return
        if not files_list:
            return
        self.convert_stop_requested = False
        import threading
        t = threading.Thread(
            target=self._thread_convert_batch,
            args=(files_list, label),
            daemon=True
        )
        t.start()

    def _thread_convert_batch(self, files_list, label="일괄"):
        try:
            self.is_converting = True
            self._ui_call(self.ui.set_buttons_enabled, False)
            start = datetime.now()
            total = len(files_list)
            converted = skipped = fill_applied = 0

            self.logger.log(f"{label} 변환 시작: {total}개 파일", level="INFO")

            for idx, (company, site, folder, filename) in enumerate(files_list, 1):
                if self.convert_stop_requested:
                    self.logger.log("변환 중지 요청으로 일괄 변환 중단", level="INFO")
                    break
                progress = idx / total if total > 0 else 0
                self._ui_call(self.ui.update_status,
                              f"{label} 변환 중... {idx}/{total} ({filename})", progress)
                result = self.file_processor.convert_file(company, site, folder, filename)
                if result == "converted":
                    converted += 1
                elif result == "fill":
                    converted += 1
                    fill_applied += 1
                else:
                    skipped += 1

            elapsed = (datetime.now() - start).total_seconds()
            fill_info = f", 채움 적용 {fill_applied}건" if fill_applied else ""
            msg = (f"{label} 변환 완료: {converted}건 변환, "
                   f"{skipped}건 건너뜀{fill_info} ({elapsed:.1f}초)")
            self.logger.log(msg, level="INFO")
            self._ui_call(self.ui.update_status, msg, 1.0)
            self._ui_call(self.ui.refresh_tree)

        except Exception as e:
            self.logger.log(f"{label} 변환 오류: {e}", level="ERROR")
            self._ui_call(self.ui.update_status, "변환 오류 발생", 0)
        finally:
            self.is_converting = False
            self._ui_call(self.ui.set_buttons_enabled, True)

    # ======================================================
    # 파일 단위 변환
    # ======================================================
    def convert_single_file(self, company, site, folder, filename):
        """단일 파일 변환 (Site 레벨 포함)"""
        if self.is_converting:
            self.logger.log("이미 변환 작업이 진행 중입니다.", level="WARNING")
            return
        
        import threading
        t = threading.Thread(target=self._thread_convert_file, args=(company, site, folder, filename), daemon=True)
        t.start()

    def _thread_convert_file(self, company, site, folder, filename):
        """단일 파일 변환 스레드 (Site 레벨 포함)"""
        try:
            self.is_converting = True
            self._ui_call(self.ui.set_buttons_enabled, False)
            
            start = datetime.now()

            self.logger.log(
                f"파일 변환 시작: {company}/{site}/{folder}/{filename}",
                level="INFO"
            )

            self._ui_call(self.ui.update_status, f"파일 변환 중... {filename}", 0.5)
            
            result = self.file_processor.convert_file(company, site, folder, filename)

            elapsed = (datetime.now() - start).seconds

            if result in ("converted", "fill"):
                fill_text = " (누락 보정 적용)" if result == "fill" else ""
                self.logger.log(
                    f"파일 변환 완료: {company}/{site}/{folder}/{filename}{fill_text}\n"
                    f"- 소요 시간: {elapsed}s",
                    level="INFO"
                )
                self._ui_call(self.ui.update_status, f"파일 변환 완료: {filename}", 1.0)
                
                # 변환 완료 후 배터리 갱신
                self.refresh_battery_for_files([(company, site, folder, filename)])
            else:
                self.logger.log(
                    f"파일 변환 스킵: {company}/{site}/{folder}/{filename}",
                    level="INFO"
                )
                self._ui_call(self.ui.update_status, f"파일 변환 스킵: {filename}", 1.0)

            self._ui_call(self.ui.refresh_tree)

        except Exception as e:
            self.logger.log(
                f"파일 변환 중 오류 발생: {e}",
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
    # 변환본 시간 이후 삭제
    # ======================================================
    def _load_last_trim_cutoff(self):
        """마지막 사용한 삭제 시작 시간 로드 (프로그램 재실행 후에도 유지)"""
        prefs_path = os.path.join(self.base_dir, "convert_pro3_prefs.json")
        try:
            if os.path.exists(prefs_path):
                import json
                with open(prefs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("last_trim_cutoff", "")
        except Exception:
            pass
        return ""

    def _save_last_trim_cutoff(self, value):
        """마지막 사용한 삭제 시작 시간 저장"""
        prefs_path = os.path.join(self.base_dir, "convert_pro3_prefs.json")
        try:
            import json
            data = {}
            if os.path.exists(prefs_path):
                with open(prefs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["last_trim_cutoff"] = value
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            if self.logger:
                self.logger.log(f"prefs 저장 실패: {e}", level="WARN")

    def trim_converted_file(self, company, site, folder, filename):
        """변환본에서 지정 시간 이후(~끝) 데이터 삭제 (우클릭 메뉴용)"""
        from ui.trim_time_dialog import show_trim_time_dialog, parse_datetime_safe
        out_path = self.get_convert_path(company, site, folder, filename)
        if not os.path.exists(out_path):
            messagebox.showwarning(
                "안내",
                f"변환본이 없습니다.\n{out_path}",
                parent=self.root
            )
            return

        # 기본값: 이전 사용값 → 없으면 현재 날짜 00:00 (YYYY-MM-DD HH:MM 고정 형식)
        initial = (self._last_trim_cutoff if self._last_trim_cutoff
                   else datetime.now().strftime("%Y-%m-%d 00:00"))
        value = show_trim_time_dialog(self.root, initial)
        if value is None or not value.strip():
            return

        cutoff = parse_datetime_safe(value)
        if cutoff is None:
            messagebox.showerror(
                "입력 오류",
                "시간 형식을 확인해주세요. (YYYY-MM-DD HH:MM)",
                parent=self.root
            )
            return

        if not messagebox.askyesno(
            "삭제 확인",
            f"'{cutoff.strftime('%Y-%m-%d %H:%M')}'부터 끝까지 삭제합니다.\n"
            f"이 작업은 되돌릴 수 없습니다.\n\n계속하시겠습니까?",
            parent=self.root
        ):
            return

        ok, deleted_count = self.file_processor.trim_converted_from_time(out_path, cutoff)
        if ok:
            self._last_trim_cutoff = value  # YYYY-MM-DD HH:MM 형식 그대로 저장
            self._save_last_trim_cutoff(self._last_trim_cutoff)
            messagebox.showinfo(
                "완료",
                f"{deleted_count}행이 삭제되었습니다.",
                parent=self.root
            )
            self.refresh_battery_for_files([(company, site, folder, filename)])
            self.ui.refresh_tree()
        else:
            messagebox.showerror(
                "오류",
                "변환본 삭제 중 오류가 발생했습니다.",
                parent=self.root
            )

    def trim_converted_files_multi(self, file_infos: list):
        """
        다중 파일 일괄 변환본 시간 이후 삭제.
        - 다이얼로그는 딱 1번만 띄운다.
        - 확인 후 file_infos 순서대로 처리.
        """
        from ui.trim_time_dialog import show_trim_time_dialog, parse_datetime_safe

        if not file_infos:
            return

        # 1) 시간 선택 (1회)
        initial = (self._last_trim_cutoff if self._last_trim_cutoff
                   else datetime.now().strftime("%Y-%m-%d 00:00"))
        value = show_trim_time_dialog(self.root, initial)
        if value is None or not value.strip():
            return

        cutoff = parse_datetime_safe(value)
        if cutoff is None:
            messagebox.showerror(
                "입력 오류",
                "시간 형식을 확인해주세요. (YYYY-MM-DD HH:MM)",
                parent=self.root,
            )
            return

        # 2) 한 번에 확인
        names = "\n".join(f"  - {fi['filename']}" for fi in file_infos)
        if not messagebox.askyesno(
            "삭제 확인",
            f"'{cutoff.strftime('%Y-%m-%d %H:%M')}'부터 끝까지 삭제합니다.\n"
            f"이 작업은 되돌릴 수 없습니다.\n\n대상 파일 ({len(file_infos)}개):\n{names}\n\n계속하시겠습니까?",
            parent=self.root,
        ):
            return

        # 3) 순차 처리
        success, fail, total_deleted = 0, 0, 0
        refresh_targets = []
        for fi in file_infos:
            company, site, folder, filename = fi["company"], fi["site"], fi["folder"], fi["filename"]
            out_path = self.get_convert_path(company, site, folder, filename)
            if not os.path.exists(out_path):
                fail += 1
                self.logger.log(f"[Trim] 변환본 없음: {filename}", level="WARN")
                continue
            ok, deleted_count = self.file_processor.trim_converted_from_time(out_path, cutoff)
            if ok:
                success += 1
                total_deleted += deleted_count
                refresh_targets.append((company, site, folder, filename))
            else:
                fail += 1
                self.logger.log(f"[Trim] 처리 오류: {filename}", level="ERROR")

        self._last_trim_cutoff = value
        self._save_last_trim_cutoff(self._last_trim_cutoff)

        msg = f"완료: {success}개 파일, 총 {total_deleted}행 삭제."
        if fail:
            msg += f"\n실패/건너뜀: {fail}개"
        messagebox.showinfo("완료", msg, parent=self.root)

        if refresh_targets:
            self.refresh_battery_for_files(refresh_targets)
            self.ui.refresh_tree()

    # ======================================================
    # 기타 UI 연동
    # ======================================================
    def create_csv(self):
        self.logger.log("[Controller] CSV 생성 기능 준비 중")

    def open_channel_settings(self, company, site, folder, filename):
        """채널 설정 UI 열기 (Site 레벨 포함) - 중복 방지"""
        # 파일 고유 키 생성
        file_key = f"{company}/{site}/{folder}/{filename}"
        
        # 이미 열린 창이 있는지 확인
        if file_key in self.open_settings_windows:
            existing_window = self.open_settings_windows[file_key]
            try:
                # 창이 아직 존재하면 포커스
                existing_window.win.lift()
                existing_window.win.focus_force()
                self.logger.log(f"센서 설정 창이 이미 열려있습니다: {file_key}", level="INFO")
                return
            except:
                # 창이 닫혔으면 딕셔너리에서 제거
                del self.open_settings_windows[file_key]
        
        # 새 창 열기
        settings_window = ChannelSettingsUI(self.ui.root, self, company, site, folder, filename)
        self.open_settings_windows[file_key] = settings_window
        
        # 창이 닫힐 때 딕셔너리에서 제거하는 콜백 등록
        def on_close():
            if file_key in self.open_settings_windows:
                del self.open_settings_windows[file_key]
            try:
                settings_window.win.destroy()
            except:
                pass
        
        settings_window.win.protocol("WM_DELETE_WINDOW", on_close)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    # ============================================
    # 단일 인스턴스 체크 (중복 실행 방지)
    # ============================================
    import tempfile
    
    lock_file_path = os.path.join(tempfile.gettempdir(), 'ConvertPro3.lock')
    lock_file = None
    
    try:
        if sys.platform == 'win32':
            # Windows: 파일 잠금 사용
            import msvcrt
            try:
                lock_file = open(lock_file_path, 'w')
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except (IOError, OSError):
                # 이미 실행 중
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror(
                    APP_NAME,
                    f"{APP_NAME}이(가) 이미 실행 중입니다.\n\n"
                    "작업 표시줄에서 실행 중인 프로그램을 확인하세요."
                )
                sys.exit(1)
        else:
            # Linux/Mac: fcntl 사용
            import fcntl
            lock_file = open(lock_file_path, 'w')
            fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        # 정상 실행
        ConvertPro3App().run()
        
    except BlockingIOError:
        # 이미 실행 중
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            APP_NAME,
            f"{APP_NAME}이(가) 이미 실행 중입니다."
        )
        sys.exit(1)
    finally:
        # 프로그램 종료 시 잠금 해제
        if lock_file:
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                lock_file.close()
                os.remove(lock_file_path)
            except:
                pass
