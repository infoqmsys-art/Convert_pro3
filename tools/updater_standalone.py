"""
Convert Pro 3 - Updater (독립 실행 프로그램)

역할:
1. 기존 프로그램 종료 대기
2. 새 파일로 교체
3. 프로그램 재시작 (창 없이)

사용법:
    updater.exe [현재_exe] [새_exe] [restart] [--silent]
    --silent: GUI 없이 백그라운드 실행
"""

import sys
import time
import shutil
import subprocess
from pathlib import Path

# Windows: 창 없이 실행
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


class DummyGUI:
    """GUI 없음 (--silent용)"""
    def update_status(self, message, status_text=""):
        pass
    def close(self):
        pass


class UpdaterGUI:
    """업데이트 진행 상황 GUI (--silent 아닐 때)"""
    
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk
        self.root = tk.Tk()
        self.root.title("Convert Pro 3 업데이트")
        self.root.geometry("400x200")
        self.root.resizable(False, False)
        self.root.eval('tk::PlaceWindow . center')
        self.label = tk.Label(self.root, text="업데이트 준비 중...", font=("맑은 고딕", 12))
        self.label.pack(pady=30)
        self.progress = ttk.Progressbar(self.root, mode='indeterminate', length=300)
        self.progress.pack(pady=20)
        self.progress.start(10)
        self.status = tk.Label(self.root, text="", font=("맑은 고딕", 9), fg="gray")
        self.status.pack(pady=10)
    
    def update_status(self, message, status_text=""):
        self.label.config(text=message)
        self.status.config(text=status_text)
        self.root.update()
    
    def close(self):
        self.root.destroy()


def wait_for_process(exe_path, timeout=30):
    """프로세스 종료 대기"""
    import psutil
    
    exe_name = Path(exe_path).name
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        found = False
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] == exe_name:
                    found = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if not found:
            return True
        
        time.sleep(0.5)
    
    return False


def perform_update(current_exe, new_exe, should_restart=True, silent=False):
    """업데이트 실행"""
    
    gui = DummyGUI() if silent else UpdaterGUI()
    
    try:
        current_exe_p = Path(current_exe)
        payload_p = Path(new_exe)

        def _pick_payload_main_exe(payload_dir: Path) -> Path | None:
            candidates = [p for p in payload_dir.glob("*.exe") if "updater" not in p.name.lower()]
            if not candidates:
                return None
            same_name = [p for p in candidates if p.name.lower() == current_exe_p.name.lower()]
            if same_name:
                return same_name[0]
            try:
                candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
            except Exception:
                pass
            return candidates[0]

        def _sync_tree(src: Path, dst: Path) -> None:
            if not src.exists():
                return
            for p in src.rglob("*"):
                rel = p.relative_to(src)
                target = dst / rel
                if p.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, target)

        is_payload_dir = payload_p.exists() and payload_p.is_dir()

        # 1. 프로세스 종료 대기
        gui.update_status(
            "프로그램 종료 대기 중...",
            f"{Path(current_exe).name}"
        )
        
        if not wait_for_process(current_exe, timeout=30):
            gui.update_status(
                "프로그램이 종료되지 않았습니다.",
                "수동으로 종료 후 다시 시도하세요."
            )
            time.sleep(3)
            return False
        
        time.sleep(1)  # 안전을 위한 추가 대기
        
        # 2. 백업 생성
        gui.update_status(
            "기존 파일 백업 중...",
            "안전을 위해 백업을 생성합니다."
        )
        
        backup_path = str(current_exe) + ".backup"
        if current_exe_p.exists():
            shutil.copy2(current_exe, backup_path)
        
        # 3. 파일 교체
        gui.update_status(
            "파일 업데이트 중...",
            "새 버전으로 교체합니다."
        )

        if is_payload_dir:
            payload_dir = payload_p
            payload_exe = _pick_payload_main_exe(payload_dir)
            if not payload_exe or not payload_exe.exists():
                raise RuntimeError(f"업데이트 패키지에 메인 EXE가 없습니다: {payload_dir}")

            shutil.copy2(str(payload_exe), str(current_exe_p))

            app_dir = current_exe_p.parent
            payload_tools_updater = payload_dir / "tools" / "updater.exe"
            if payload_tools_updater.exists():
                dst_tools_dir = app_dir / "tools"
                dst_tools_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(payload_tools_updater), str(dst_tools_dir / "updater.exe"))

            for dname in ("monitoring", "measurement_portal", "survey_mgmt_portal"):
                src_dir = payload_dir / dname
                if src_dir.exists() and src_dir.is_dir():
                    _sync_tree(src_dir, app_dir / dname)

            time.sleep(0.5)
        else:
            shutil.copy2(new_exe, current_exe)
            time.sleep(0.5)

            app_dir = current_exe_p.parent
            payload_root = payload_p.parent
            payload_tools_updater = payload_root / "tools" / "updater.exe"
            if payload_tools_updater.exists():
                dst_tools_dir = app_dir / "tools"
                dst_tools_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(payload_tools_updater), str(dst_tools_dir / "updater.exe"))

            for dname in ("monitoring", "measurement_portal", "survey_mgmt_portal"):
                src_dir = payload_root / dname
                if src_dir.exists() and src_dir.is_dir():
                    _sync_tree(src_dir, app_dir / dname)

            try:
                payload_p.unlink()
            except Exception:
                pass

            try:
                new_exe_parent = payload_p.parent
                import tempfile
                tmp_root = Path(tempfile.gettempdir())
                if new_exe_parent != tmp_root and str(new_exe_parent).startswith(str(tmp_root)):
                    shutil.rmtree(new_exe_parent, ignore_errors=True)
            except Exception:
                pass

        # 5. 프로그램 재시작 (작업 디렉토리=exe 위치, 창 없이)
        if should_restart:
            gui.update_status(
                "프로그램 재시작 중...",
                "잠시 후 자동으로 시작됩니다."
            )
            time.sleep(0.5)
            
            app_dir = str(current_exe_p.parent)
            subprocess.Popen(
                [current_exe],
                cwd=app_dir,
                shell=False,
                creationflags=CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
        
        gui.update_status(
            "업데이트 완료!",
            "프로그램이 재시작됩니다."
        )
        time.sleep(0.5 if silent else 2)
        
        gui.close()
        return True
        
    except Exception as e:
        gui.update_status(
            f"업데이트 실패: {str(e)}",
            "수동으로 업데이트해주세요."
        )
        time.sleep(5)
        gui.close()
        return False


def main():
    """메인 함수"""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    silent = "--silent" in sys.argv
    
    if len(args) < 2:
        print("사용법: updater.exe [현재_exe] [새_exe] [restart] [--silent]")
        sys.exit(1)
    
    current_exe = args[0]
    new_exe = args[1]
    should_restart = len(args) > 2 and args[2].lower() == "restart"
    
    # 파일 존재 확인
    if not Path(new_exe).exists():
        print(f"새 파일을 찾을 수 없습니다: {new_exe}")
        sys.exit(1)
    
    # 업데이트 실행
    success = perform_update(current_exe, new_exe, should_restart, silent=silent)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
