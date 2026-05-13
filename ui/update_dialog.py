"""
Convert Pro 3 - 업데이트 UI 다이얼로그
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import tempfile
from pathlib import Path


class UpdateDialog:
    """업데이트 확인 및 다운로드 다이얼로그"""
    
    def __init__(self, parent, update_manager, update_info):
        self.parent = parent
        self.update_manager = update_manager
        self.update_info = update_info
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("업데이트 가능")
        self.dialog.geometry("450x300")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # 중앙 배치
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (450 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (300 // 2)
        self.dialog.geometry(f"+{x}+{y}")
        
        self._build_ui()
    
    def _build_ui(self):
        """UI 구성"""
        # 헤더
        header_frame = tk.Frame(self.dialog, bg="#4CAF50", height=60)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="새로운 버전이 있습니다",
            font=("맑은 고딕", 14, "bold"),
            bg="#4CAF50",
            fg="white"
        ).pack(pady=15)
        
        # 내용
        content_frame = tk.Frame(self.dialog, bg="white")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 버전 정보
        version_text = f"현재 버전: {self.update_manager.current_version}\n새 버전: {self.update_info['version']}"
        tk.Label(
            content_frame,
            text=version_text,
            font=("맑은 고딕", 10),
            bg="white",
            fg="#333"
        ).pack(anchor="w", pady=(0, 10))
        
        # 변경사항
        tk.Label(
            content_frame,
            text="변경사항:",
            font=("맑은 고딕", 9, "bold"),
            bg="white",
            fg="#666"
        ).pack(anchor="w")
        
        notes_text = tk.Text(
            content_frame,
            height=6,
            wrap="word",
            font=("맑은 고딕", 9),
            bg="#f5f5f5",
            relief="flat",
            padx=10,
            pady=10
        )
        notes_text.pack(fill="both", expand=True, pady=(5, 15))
        notes_text.insert("1.0", self.update_info.get('release_notes', '변경사항 없음'))
        notes_text.config(state="disabled")
        
        # 버튼
        btn_frame = tk.Frame(content_frame, bg="white")
        btn_frame.pack(fill="x")
        
        update_btn = tk.Button(
            btn_frame,
            text="업데이트",
            command=self._start_update,
            bg="#4CAF50",
            fg="white",
            font=("맑은 고딕", 10, "bold"),
            relief="flat",
            padx=30,
            pady=10,
            cursor="hand2"
        )
        update_btn.pack(side="left", padx=(0, 10))
        
        later_btn = tk.Button(
            btn_frame,
            text="나중에",
            command=self.dialog.destroy,
            bg="#e0e0e0",
            fg="#333",
            font=("맑은 고딕", 10),
            relief="flat",
            padx=30,
            pady=10,
            cursor="hand2"
        )
        later_btn.pack(side="left")
    
    def _start_update(self):
        """업데이트 시작"""
        # 다운로드 진행 창으로 변경
        for widget in self.dialog.winfo_children():
            widget.destroy()
        
        self.dialog.geometry("400x150")
        
        # 진행 상황
        tk.Label(
            self.dialog,
            text="업데이트 다운로드 중...",
            font=("맑은 고딕", 12)
        ).pack(pady=20)
        
        self.progress = ttk.Progressbar(
            self.dialog,
            mode='determinate',
            length=300
        )
        self.progress.pack(pady=10)
        
        self.status_label = tk.Label(
            self.dialog,
            text="0%",
            font=("맑은 고딕", 9),
            fg="gray"
        )
        self.status_label.pack(pady=5)
        
        # 다운로드 시작 (별도 스레드)
        thread = threading.Thread(target=self._download_and_apply, daemon=True)
        thread.start()
    
    def _download_and_apply(self):
        """다운로드 및 적용"""
        try:
            # 임시 파일 경로
            is_zip = self.update_info.get('is_zip', False)
            file_extension = '.zip' if is_zip else '.exe'
            temp_file = Path(tempfile.gettempdir()) / f"ConvertPro3_update{file_extension}"
            
            # 다운로드
            success = self.update_manager.download_update(
                self.update_info['download_url'],
                temp_file,
                progress_callback=self._update_progress
            )
            
            if not success:
                self.dialog.after(0, lambda: messagebox.showerror(
                    "다운로드 실패",
                    "업데이트 다운로드에 실패했습니다.",
                    parent=self.dialog
                ))
                self.dialog.after(0, self.dialog.destroy)
                return
            
            # 업데이터 시작
            self.dialog.after(0, lambda: self.status_label.config(text="업데이트 적용 중..."))
            
            if self.update_manager.start_updater(temp_file, is_zip=is_zip):
                # 성공 - 프로그램 종료
                self.dialog.after(0, self._close_program)
            else:
                self.dialog.after(0, lambda: messagebox.showerror(
                    "업데이트 실패",
                    "업데이트 적용에 실패했습니다.\n\n"
                    "수동으로 업데이트하려면:\n"
                    f"GitHub에서 _full.zip 파일을 다운로드하세요.",
                    parent=self.dialog
                ))
                self.dialog.after(0, self.dialog.destroy)
                
        except Exception as e:
            self.dialog.after(0, lambda: messagebox.showerror(
                "오류",
                f"업데이트 중 오류가 발생했습니다:\n{e}",
                parent=self.dialog
            ))
            self.dialog.after(0, self.dialog.destroy)
    
    def _update_progress(self, percent):
        """진행률 업데이트"""
        self.dialog.after(0, lambda: self.progress.config(value=percent))
        self.dialog.after(0, lambda: self.status_label.config(text=f"{percent}%"))
    
    def _close_program(self):
        """프로그램 종료 — updater가 파일을 교체할 수 있도록 프로세스까지 완전 종료"""
        import sys
        try:
            self.parent.quit()
            self.parent.destroy()
        except Exception:
            pass
        sys.exit(0)
