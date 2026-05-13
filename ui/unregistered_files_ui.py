"""
===============================================================
Convert Pro 3 - UnregisteredFilesUI
===============================================================
미등록 파일 관리 UI

기능:
    - 등록된 폴더 내 미등록 CSV 파일 목록 표시
    - 파일 정보 표시 (파일명, 폴더, 수정일시, 크기)
    - 다중 선택 (체크박스)
    - 특정 현장에 일괄 등록
===============================================================
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from core.scanner_manager import ScannerManager


class UnregisteredFilesUI:
    """미등록 파일 관리 UI"""

    def __init__(self, root, app, target_folder_path=None):
        """
        Args:
            root: 부모 윈도우
            app: ConvertPro3App 인스턴스
            target_folder_path: 특정 폴더 경로 (선택적, 로거파일 등록에서 호출 시)
        """
        self.root = root
        self.app = app
        self.scanner = ScannerManager(app.config, app.tree, app.logger)
        self.target_folder_path = target_folder_path  # 로거파일 등록에서 전달된 폴더 경로
        self.current_files = []  # 현재 표시된 파일 목록 저장
        
        self.win = tk.Toplevel(root)
        self.win.title("로거 파일 관리")
        self.win.geometry("900x600")
        
        # 메인 창 위치 기준으로 팝업 위치 설정
        self._center_on_parent()
        
        self.win.grab_set()
        
        self.check_vars = {}  # 파일 경로 → 체크박스 변수
        
        self._build_ui()
        self.refresh_list()
    
    def _center_on_parent(self):
        """메인 창 위치 기준으로 팝업 중앙 배치"""
        self.win.update_idletasks()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        
        popup_width = self.win.winfo_width()
        popup_height = self.win.winfo_height()
        
        # 메인 창 중앙에 배치
        x = parent_x + (parent_width - popup_width) // 2
        y = parent_y + (parent_height - popup_height) // 2
        
        self.win.geometry(f"+{x}+{y}")

    def _build_ui(self):
        """UI 구성"""
        # 헤더
        header = tk.Frame(self.win, bg="#2C3E50", height=50)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="로거 파일 관리",
            font=("맑은 고딕", 12, "bold"),
            bg="#2C3E50",
            fg="white"
        ).pack(side="left", padx=15, pady=10)
        
        # 오른쪽 버튼 영역
        right_header_buttons = tk.Frame(header, bg="#2C3E50")
        right_header_buttons.pack(side="right", padx=15, pady=10)
        
        # 로거파일 추가 버튼
        add_btn = tk.Button(
            right_header_buttons,
            text="로거파일 추가",
            command=self._on_add_logger_files,
            font=("맑은 고딕", 9),
            bg="#27AE60",
            fg="white",
            activebackground="#229954",
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2"
        )
        add_btn.pack(side="right", padx=(0, 8))
        
        # 새로고침 버튼
        ttk.Button(
            right_header_buttons,
            text="새로고침",
            command=self.refresh_list
        ).pack(side="right")
        
        # 메인 영역
        main = tk.Frame(self.win, bg="white")
        main.pack(fill="both", expand=True, padx=10, pady=10)
        
        # TreeView 프레임
        tree_frame = tk.Frame(main, bg="white")
        tree_frame.pack(fill="both", expand=True)
        
        # 스크롤바
        tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scrollbar.pack(side="right", fill="y")
        
        # TreeView
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("selected", "filename", "folder", "mtime", "size"),
            show="tree headings",
            yscrollcommand=tree_scrollbar.set,
            selectmode="extended"
        )
        tree_scrollbar.config(command=self.tree.yview)
        
        # 헤더 설정
        self.tree.heading("#0", text="선택")
        self.tree.heading("selected", text="")
        self.tree.heading("filename", text="파일명")
        self.tree.heading("folder", text="폴더")
        self.tree.heading("mtime", text="수정일시")
        self.tree.heading("size", text="크기")
        
        # 컬럼 너비
        self.tree.column("#0", width=50, stretch=False)
        self.tree.column("selected", width=0, stretch=False)
        self.tree.column("filename", width=250)
        self.tree.column("folder", width=200)
        self.tree.column("mtime", width=180)
        self.tree.column("size", width=100, anchor="e")
        
        self.tree.pack(side="left", fill="both", expand=True)
        
        # 클릭/더블클릭으로 체크박스 토글 (체크박스 영역만)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-1>", self._on_click)
        # Space 키로 선택/해제
        self.tree.bind("<space>", self._on_space_key)
        self.tree.bind("<Key-space>", self._on_space_key)
        
        # 버튼 영역
        button_frame = tk.Frame(main, bg="white")
        button_frame.pack(fill="x", pady=(10, 0))
        
        # 왼쪽: 선택 관련 버튼
        left_buttons = tk.Frame(button_frame, bg="white")
        left_buttons.pack(side="left")
        
        ttk.Button(
            left_buttons,
            text="전체 선택",
            command=self._select_all
        ).pack(side="left", padx=5)
        
        ttk.Button(
            left_buttons,
            text="전체 해제",
            command=self._deselect_all
        ).pack(side="left", padx=5)

        ttk.Button(
            left_buttons,
            text="선택 토글",
            command=self._toggle_selected
        ).pack(side="left", padx=5)
        
        # 오른쪽: 등록 / 제외 버튼
        right_buttons = tk.Frame(button_frame, bg="white")
        right_buttons.pack(side="right")
        
        self.register_btn = tk.Button(
            right_buttons,
            text="로거파일 등록",
            command=self._on_register_selected,
            font=("맑은 고딕", 9, "bold"),
            bg="#3498DB",
            fg="white",
            activebackground="#2980B9",
            activeforeground="white",
            relief="flat",
            width=16,
            height=1,
            padx=12,
            pady=6,
            cursor="hand2"
        )
        self.register_btn.pack(side="left", padx=5)

        # 삭제 버튼 추가
        self.delete_btn = tk.Button(
            right_buttons,
            text="파일삭제",
            command=self._on_delete_selected,
            font=("맑은 고딕", 9),
            bg="#E74C3C",
            fg="white",
            activebackground="#C0392B",
            activeforeground="white",
            relief="flat",
            width=12,
            height=1,
            padx=12,
            pady=6,
            cursor="hand2"
        )
        self.delete_btn.pack(side="left", padx=5)
        
        # 상태 라벨
        self.status_label = tk.Label(
            main,
            text="미등록 파일을 스캔 중...",
            font=("맑은 고딕", 9),
            fg="#7F8C8D",
            bg="white",
            anchor="w"
        )
        self.status_label.pack(fill="x", pady=(10, 0))

    def refresh_list(self):
        """미등록 파일 목록 새로고침"""
        self.status_label.config(text="스캔 중...", fg="#7F8C8D")
        self.win.update()
        
        # 특정 폴더가 지정된 경우 해당 폴더만 스캔하여 미등록 목록에 추가
        if self.target_folder_path:
            files = self._scan_single_folder(self.target_folder_path)
            # 추가 후 전체 목록 다시 읽기
            files = self.scanner.scan_all_folders()
        else:
            # config.json의 __unregistered_files__에서 읽기
            files = self.scanner.scan_all_folders()
        
        # 현재 파일 목록 저장 (등록 시 사용)
        self.current_files = files
        
        # TreeView 초기화
        self.tree.delete(*self.tree.get_children())
        self.check_vars = {}
        
        if not files:
            self.status_label.config(
                text="미등록 파일이 없습니다.",
                fg="#27AE60"
            )
            return
        
        # 파일 목록 추가
        for file_info in files:
            file_key = file_info["path"]
            check_var = tk.BooleanVar(value=False)
            self.check_vars[file_key] = check_var
            
            # 파일 크기 포맷팅
            size_str = self._format_size(file_info["size"])
            
            # 수정일시 포맷팅
            mtime_str = file_info["mtime"].strftime("%Y-%m-%d %H:%M:%S")
            
            # 폴더 경로 표시 (company/site가 None인 경우)
            if file_info["company"] and file_info["site"]:
                folder_display = f"{file_info['company']}/{file_info['site']}/{file_info['folder']}"
            else:
                folder_display = file_info["folder"]
            
            # TreeView에 추가
            item_id = self.tree.insert(
                "",
                "end",
                text="[ ]",
                values=(
                    "",
                    file_info["filename"],
                    folder_display,
                    mtime_str,
                    size_str
                ),
                tags=(file_key,)
            )
            
            # 체크박스 상태 변경 시 텍스트 업데이트
            check_var.trace_add("write", lambda *args, key=file_key: self._update_checkbox(key))
        
        if len(files) > 0:
            self.status_label.config(
                text=f"총 {len(files)}개의 미등록 파일이 발견되었습니다.",
                fg="#2C3E50"
            )
        else:
            self.status_label.config(
                text="미등록 파일이 없습니다.",
                fg="#27AE60"
            )
    
    def _scan_single_folder(self, folder_path):
        """특정 폴더만 스캔하여 미등록 파일 목록에 추가 (로거파일 등록용)"""
        if not os.path.exists(folder_path):
            return []
        
        folder_name = os.path.basename(folder_path.rstrip("/\\"))
        files = []
        
        try:
            # 폴더 내 CSV 파일 찾기
            csv_files = [
                f for f in os.listdir(folder_path) 
                if f.lower().endswith(".csv")
            ]
            
            added_count = 0
            skipped_count = 0
            for filename in csv_files:
                file_path = os.path.join(folder_path, filename)
                try:
                    stat = os.stat(file_path)
                    
                    result = self.app.config.add_unregistered_file(
                        folder_path, filename, stat.st_size,
                        datetime.fromtimestamp(stat.st_mtime)
                    )
                    if result:
                        added_count += 1
                        self.app.logger.log(
                            f"[UI] 미등록 파일 추가: {folder_path}/{filename}",
                            level="INFO"
                        )
                        # UI 표시용 정보 (미등록 목록에 추가된 것만)
                        files.append({
                            "company": None,
                            "site": None,
                            "folder": folder_name,
                            "folder_path": folder_path,
                            "filename": filename,
                            "path": file_path,
                            "size": stat.st_size,
                            "mtime": datetime.fromtimestamp(stat.st_mtime)
                        })
                    else:
                        skipped_count += 1
                        self.app.logger.log(
                            f"[UI] 미등록 추가 스킵 (이미 등록/중복): {folder_path}/{filename}",
                            level="INFO"
                        )
                except Exception as e:
                    self.app.logger.log(
                        f"파일 정보 읽기 실패 {file_path}: {e}",
                        level="ERROR"
                    )
            
            # 메시지박스 대신 상태 라벨로 결과 표시 (호출부에서 처리)
            self.app.logger.log(
                f"[UI] 폴더 스캔 완료: {folder_path} — 추가 {added_count}개, 스킵 {skipped_count}개",
                level="INFO"
            )
        except Exception as e:
            self.app.logger.log(
                f"폴더 스캔 오류 {folder_path}: {e}",
                level="ERROR"
            )
        
        return files

    def _format_size(self, size_bytes):
        """파일 크기 포맷팅"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _on_double_click(self, event):
        """더블클릭으로 체크박스 토글 (체크박스 영역만)"""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        # 체크박스 영역에서만 토글
        region = self.tree.identify_region(event.x, event.y)
        column = self.tree.identify_column(event.x)
        
        if region == "cell" and column == "#0":
            tags = self.tree.item(item, "tags")
            if not tags:
                return
            
            file_key = tags[0]
            if file_key in self.check_vars:
                check_var = self.check_vars[file_key]
                check_var.set(not check_var.get())
    
    def _on_space_key(self, event):
        """Space 키로 선택된 항목들의 체크 상태 토글"""
        selected_items = self.tree.selection()
        if not selected_items:
            return
        
        for item in selected_items:
            tags = self.tree.item(item, "tags")
            if not tags:
                continue
            
            file_key = tags[0]
            if file_key in self.check_vars:
                check_var = self.check_vars[file_key]
                check_var.set(not check_var.get())
        
        return "break"  # 기본 동작 방지

    def _on_click(self, event):
        """행 아무 곳이나 클릭해도 체크박스 토글"""
        item = self.tree.identify_row(event.y)
        if not item:
            return

        region = self.tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return

        tags = self.tree.item(item, "tags")
        if not tags:
            return

        file_key = tags[0]
        if file_key in self.check_vars:
            self.check_vars[file_key].set(not self.check_vars[file_key].get())

    def _update_checkbox(self, file_key):
        """체크박스 상태에 따라 텍스트 업데이트"""
        if file_key not in self.check_vars:
            return
        
        check_var = self.check_vars[file_key]
        checked = check_var.get()
        
        # 해당 파일의 모든 항목 찾기
        for item in self.tree.get_children():
            tags = self.tree.item(item, "tags")
            if tags and tags[0] == file_key:
                self.tree.item(item, text="[x]" if checked else "[ ]")
                break

    def _select_all(self):
        """전체 선택"""
        for check_var in self.check_vars.values():
            check_var.set(True)

    def _deselect_all(self):
        """전체 해제"""
        for check_var in self.check_vars.values():
            check_var.set(False)

    def _toggle_selected(self):
        """현재 선택된 항목들의 체크 상태 토글"""
        for item in self.tree.selection():
            tags = self.tree.item(item, "tags")
            if not tags:
                continue
            file_key = tags[0]
            if file_key in self.check_vars:
                check_var = self.check_vars[file_key]
                check_var.set(not check_var.get())

    def _on_register_selected(self):
        """선택된 파일들을 현장에 등록"""
        selected_files = []
        
        for file_key, check_var in self.check_vars.items():
            if check_var.get():
                # 파일 정보 찾기 (현재 표시된 파일 목록에서)
                for file_info in self.current_files:
                    if file_info["path"] == file_key:
                        selected_files.append(file_info)
                        break
        
        if not selected_files:
            messagebox.showwarning("안내", "등록할 파일을 먼저 선택해주세요.")
            return
        
        # 업체 및 현장 선택 다이얼로그
        company, site = self._select_company_and_site()
        
        if not company or not site:
            return
        
        # 확인 메시지
        confirm_msg = (
            f"선택한 {len(selected_files)}개의 파일을\n"
            f"'{company}/{site}' 현장에 등록하시겠습니까?"
        )
        
        if not messagebox.askyesno("등록 확인", confirm_msg):
            return
        
        # 선택한 파일들의 company/site 업데이트
        for file_info in selected_files:
            file_info["company"] = company
            file_info["site"] = site
        
        # 일괄 등록
        try:
            added_count = self.scanner.add_files_to_site(company, site, selected_files)
            
            messagebox.showinfo(
                "등록 완료",
                f"{added_count}개의 파일이 성공적으로 등록되었습니다.\n\n"
                f"등록된 파일은 트리뷰에서 확인할 수 있습니다."
            )
            
            # 트리뷰 새로고침
            self.app.ui.refresh_tree()
            
            # 목록 새로고침
            self.refresh_list()
            
        except Exception as e:
            self.app.logger.log(f"[UI] 파일 등록 실패: {e}", level="ERROR")
            messagebox.showerror("등록 실패", f"파일 등록 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.")
    
    def _on_delete_selected(self):
        """선택된 파일들을 미등록 목록에서 삭제"""
        selected_files = []
        
        for file_key, check_var in self.check_vars.items():
            if check_var.get():
                # 파일 정보 찾기 (현재 표시된 파일 목록에서)
                for file_info in self.current_files:
                    if file_info["path"] == file_key:
                        selected_files.append(file_info)
                        break
        
        if not selected_files:
            messagebox.showwarning("안내", "삭제할 파일을 먼저 선택해주세요.")
            return
        
        # 확인 메시지
        confirm_msg = (
            f"선택한 {len(selected_files)}개의 파일을\n"
            f"미등록 목록에서 삭제하시겠습니까?\n\n"
            f"(파일 자체는 삭제되지 않으며, 미등록 목록에서만 제거됩니다.)"
        )
        
        if not messagebox.askyesno("삭제 확인", confirm_msg):
            return
        
        # 선택한 파일들을 미등록 목록에서 제거
        deleted_count = 0
        for file_info in selected_files:
            # folder_path 우선 사용, 없으면 path에서 추출
            folder_path = file_info.get("folder_path")
            if not folder_path:
                full_path = file_info["path"]
                folder_path = os.path.dirname(full_path)
            
            filename = file_info["filename"]
            
            if self.app.config.remove_unregistered_file(folder_path, filename):
                deleted_count += 1
                self.app.logger.log(
                    f"[UI] 미등록 파일 삭제: {folder_path}/{filename}",
                    level="INFO"
                )
        
        if deleted_count > 0:
            messagebox.showinfo(
                "삭제 완료",
                f"{deleted_count}개의 파일이 미등록 목록에서 제거되었습니다."
            )
            
            # 목록 새로고침
            self.refresh_list()
        else:
            messagebox.showwarning(
                "삭제 실패",
                "선택한 파일을 미등록 목록에서 찾을 수 없습니다."
            )


    def _select_company_and_site(self):
        """업체 및 현장 선택 팝업 (한 번에 선택)"""
        popup = tk.Toplevel(self.win)
        popup.title("업체 및 현장 선택")
        popup.geometry("350x220")
        popup.grab_set()
        
        tk.Label(
            popup,
            text="등록할 업체와 현장을 선택하세요:",
            font=("맑은 고딕", 10, "bold")
        ).pack(pady=10)
        
        # 업체 목록
        all_companies = list(self.app.tree.get_tree().keys())
        companies = [c for c in all_companies if not c.startswith("__")]
        
        if not companies:
            tk.Label(
                popup,
                text="등록된 업체가 없습니다.\n먼저 업체를 추가하세요.",
                fg="red"
            ).pack(pady=5)
            tk.Button(popup, text="닫기", command=popup.destroy).pack(pady=15)
            popup.wait_window()
            return None, None
        
        # 업체 선택
        tk.Label(popup, text="업체:", font=("맑은 고딕", 9)).pack(pady=(5, 0))
        company_var = tk.StringVar(value=companies[0])
        company_combo = ttk.Combobox(
            popup,
            textvariable=company_var,
            values=companies,
            state="readonly",
            width=25
        )
        company_combo.pack(pady=5)
        
        # 현장 선택
        tk.Label(popup, text="현장:", font=("맑은 고딕", 9)).pack(pady=(10, 0))
        site_var = tk.StringVar()
        site_combo = ttk.Combobox(
            popup,
            textvariable=site_var,
            state="readonly",
            width=25
        )
        site_combo.pack(pady=5)
        
        # 업체 변경 시 현장 목록 업데이트
        def update_sites(*args):
            company = company_var.get()
            if company:
                company_data = self.app.tree.get_company_data(company)
                sites = [k for k in company_data.keys() if not k.startswith("__")]
                site_combo["values"] = sites
                if sites:
                    site_var.set(sites[0])
                else:
                    site_var.set("")
        
        company_var.trace_add("write", update_sites)
        update_sites()  # 초기 현장 목록 설정
        
        selected = {"company": None, "site": None}
        
        def confirm():
            selected["company"] = company_var.get()
            selected["site"] = site_var.get()
            if not selected["company"] or not selected["site"]:
                messagebox.showwarning("안내", "업체와 현장을 모두 선택해주세요.")
                return
            popup.destroy()
        
        button_frame = tk.Frame(popup)
        button_frame.pack(pady=15)
        tk.Button(button_frame, text="확인", command=confirm, width=8).pack(side="left", padx=10)
        tk.Button(button_frame, text="취소", command=popup.destroy, width=8).pack(side="left", padx=10)
        
        popup.wait_window()
        return selected["company"], selected["site"]
    
    def _on_add_logger_files(self):
        """로거파일 추가 - 폴더 선택 후 미등록 목록에 추가"""
        folder_path = filedialog.askdirectory(title="로거파일이 있는 폴더 선택")
        if not folder_path:
            return

        self.status_label.config(text="폴더 스캔 중...", fg="#7F8C8D")
        self.win.update()

        self._scan_single_folder(folder_path)
        self.refresh_list()

        self.app.logger.log(f"[UI] 로거파일 추가 완료: {folder_path}")