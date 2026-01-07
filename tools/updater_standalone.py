r"""
===============================================================
Convert Pro 3 - Standalone Updater
===============================================================
독립 실행형 업데이터 프로그램

사용법:
    update.exe <current_exe_path> <update_file_path>
    
예:
    update.exe "C:\Program Files\ConvertPro3.exe" "C:\Temp\update.exe"

프로세스:
    1. 메인 프로그램 종료 대기 (3초)
    2. 기존 파일 백업
    3. 새 파일로 교체
    4. 메인 프로그램 재시작
    5. 백업 파일 삭제
    6. 자동 종료

이 파일을 PyInstaller로 별도 빌드:
    pyinstaller --onefile --noconsole --name update updater_standalone.py
===============================================================
"""

import os
import sys
import time
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk
import threading


class UpdaterGUI:
    """업데이트 진행 상황을 표시하는 간단한 GUI"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Convert Pro 3 업데이트")
        self.root.geometry("400x150")
        self.root.resizable(False, False)
        
        # 중앙 정렬
        self.root.eval('tk::PlaceWindow . center')
        
        # 아이콘 설정 (메인 앱과 동일한 아이콘 사용 가능)
        try:
            # PyInstaller로 빌드 시 아이콘 포함
            pass
        except:
            pass
        
        # UI 구성
        frame = tk.Frame(self.root, padx=20, pady=20)
        frame.pack(fill="both", expand=True)
        
        # 제목
        title = tk.Label(
            frame, 
            text="Convert Pro 3 업데이트 중...",
            font=("맑은 고딕", 12, "bold")
        )
        title.pack(pady=(0, 10))
        
        # 상태 메시지
        self.status_label = tk.Label(
            frame,
            text="준비 중...",
            font=("맑은 고딕", 9)
        )
        self.status_label.pack(pady=(0, 10))
        
        # 진행률 표시
        self.progress = ttk.Progressbar(
            frame,
            mode='indeterminate',
            length=300
        )
        self.progress.pack(pady=(0, 10))
        self.progress.start(10)
        
        # 닫기 방지
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        
    def update_status(self, message):
        """상태 메시지 업데이트"""
        self.status_label.config(text=message)
        self.root.update()
    
    def close(self):
        """창 닫기"""
        self.root.destroy()


class StandaloneUpdater:
    """독립 실행형 업데이터"""
    
    def __init__(self, target_exe, update_file, gui=None):
        self.target_exe = target_exe
        self.update_file = update_file
        self.gui = gui
        self.backup_file = target_exe + ".backup"
        
    def log(self, message):
        """로그 출력"""
        print(f"[Updater] {message}")
        if self.gui:
            self.gui.update_status(message)
    
    def run(self):
        """업데이트 실행"""
        try:
            # 1. 프로그램 종료 대기
            self.log("프로그램 종료 대기 중... (3초)")
            time.sleep(3)
            
            # 2. 파일 존재 확인
            if not os.path.exists(self.update_file):
                self.log(f"업데이트 파일을 찾을 수 없습니다: {self.update_file}")
                return False
            
            # 3. 기존 파일 백업
            if os.path.exists(self.target_exe):
                self.log("기존 버전 백업 중...")
                try:
                    if os.path.exists(self.backup_file):
                        os.remove(self.backup_file)
                    shutil.copy2(self.target_exe, self.backup_file)
                    self.log("백업 완료")
                except Exception as e:
                    self.log(f"백업 실패: {e}")
                    return False
            
            # 4. 기존 파일 삭제
            if os.path.exists(self.target_exe):
                self.log("기존 파일 삭제 중...")
                try:
                    os.remove(self.target_exe)
                except Exception as e:
                    self.log(f"기존 파일 삭제 실패: {e}")
                    # 백업 복구
                    if os.path.exists(self.backup_file):
                        shutil.copy2(self.backup_file, self.target_exe)
                    return False
            
            # 5. 새 파일 복사
            self.log("새 버전 설치 중...")
            try:
                shutil.copy2(self.update_file, self.target_exe)
                self.log("설치 완료!")
            except Exception as e:
                self.log(f"설치 실패: {e}")
                # 백업 복구
                if os.path.exists(self.backup_file):
                    self.log("백업에서 복구 중...")
                    shutil.copy2(self.backup_file, self.target_exe)
                return False
            
            # 6. 업데이트 파일 삭제
            try:
                if os.path.exists(self.update_file):
                    os.remove(self.update_file)
            except:
                pass
            
            # 7. 프로그램 재시작
            self.log("프로그램 재시작 중...")
            time.sleep(1)
            
            try:
                subprocess.Popen([self.target_exe], shell=True)
            except Exception as e:
                self.log(f"재시작 실패: {e}")
                return False
            
            # 8. 백업 파일 삭제
            time.sleep(2)
            try:
                if os.path.exists(self.backup_file):
                    os.remove(self.backup_file)
            except:
                pass
            
            self.log("업데이트 완료!")
            time.sleep(1)
            return True
            
        except Exception as e:
            self.log(f"업데이트 중 오류 발생: {e}")
            return False


def run_updater_with_gui(target_exe, update_file):
    """GUI와 함께 업데이터 실행"""
    gui = UpdaterGUI()
    updater = StandaloneUpdater(target_exe, update_file, gui)
    
    def update_thread():
        success = updater.run()
        if success:
            gui.update_status("업데이트 완료! 종료 중...")
        else:
            gui.update_status("업데이트 실패")
        time.sleep(2)
        gui.close()
    
    # 별도 스레드에서 업데이트 실행
    thread = threading.Thread(target=update_thread, daemon=True)
    thread.start()
    
    gui.root.mainloop()


def main():
    """메인 함수"""
    if len(sys.argv) < 3:
        print("사용법: update.exe <target_exe> <update_file>")
        print("예: update.exe \"C:\\Program Files\\ConvertPro3.exe\" \"C:\\Temp\\update.exe\"")
        sys.exit(1)
    
    target_exe = sys.argv[1]
    update_file = sys.argv[2]
    
    print(f"대상 파일: {target_exe}")
    print(f"업데이트 파일: {update_file}")
    
    # GUI 모드로 실행
    run_updater_with_gui(target_exe, update_file)


if __name__ == "__main__":
    main()
