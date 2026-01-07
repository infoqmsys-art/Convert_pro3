"""
===============================================================
Convert Pro 3 - Main UI
===============================================================
이 파일은 Convert Pro 3 의 사용자 인터페이스(UI)를 담당한다.
UI는 화면 그리기, 버튼 이벤트 처리, 트리뷰 렌더링 등
오직 "표현 + 사용자 입력" 만 담당한다.

핵심 규칙:
    - UI는 데이터 처리나 변환을 직접 수행하지 않는다.
    - 항상 self.app 을 통해 ConvertPro3App 엔진에 요청한다.
    - CORE(FileProcessor, TreeManager 등)에는 직접 접근하지 않는다.

구조:
    self.app.tree               → TreeManager
    self.app.config             → ConfigManager
    self.app.file_processor     → FileProcessor
    self.app.logger             → Logger
===============================================================
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog


class MainUI:
    """
    ===========================================================
    Convert Pro 3 - Main User Interface
    ===========================================================
    화면 구성 요소 (TreeView, 버튼, ProgressBar 등)을 관리한다.
    모든 동작은 self.app (ConvertPro3App)에 명령을 보내 수행된다.
    ===========================================================
    """

    DEFAULT_COMPANIES = ["SAEGIL", "KD_ENG", "TAEAM", "DooYoung_Safe", "KIC"]

    def __init__(self, root, app):
        self.root = root
        self.app = app               # controller → app (핵심 변경)
        self.logger = app.logger
        self.current_company = ""

        self._build_ui()

        # Logger가 UI로 로그를 전달하기 위한 callback 등록
        self.logger.set_ui_callback(self.append_log)

        self.refresh_company_list()
        self.refresh_tree()

    # ======================================================
    # UI 구성
    # ======================================================
    def _build_ui(self):
        main = tk.Frame(self.root)
        main.pack(fill="both", expand=True)

        # ======================================================
        #  ProgressBar Style (얇은 파란색)
        # ======================================================
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "ThinProgress.Horizontal.TProgressbar",
            troughcolor="#E6E6E6",
            bordercolor="#E6E6E6",
            background="#4A90E2",
            lightcolor="#4A90E2",
            darkcolor="#4A90E2",
            thickness=5
        )

        # ------------------------------ 상단: 회사 선택 ------------------------------
        top = tk.Frame(main)
        top.pack(fill="x")

        tk.Label(top, text="업체 선택:", font=("맑은 고딕", 10, "bold")).pack(side="left", padx=5)

        self.company_var = tk.StringVar()
        self.company_combo = ttk.Combobox(top, textvariable=self.company_var, state="readonly")
        self.company_combo.pack(side="left", padx=5)
        self.company_combo.bind("<<ComboboxSelected>>", self._on_company_change)

        ttk.Button(top, text="새로고침", command=self.refresh_tree).pack(side="left", padx=5)

        # ------------------------------ 중앙: TreeView ------------------------------
        center = tk.Frame(main)
        center.pack(fill="both", expand=True, pady=5)

        self.tree = ttk.Treeview(
            center,
            columns=("note", "battery", "type", "company", "folder", "filename"),
            show="tree headings",
        )

        self.tree.heading("#0", text="파일 / 폴더")
        self.tree.heading("note", text="비고")
        self.tree.heading("battery", text="배터리 (%)")

        # 숨길 internal metadata
        for col in ("type", "company", "folder", "filename"):
            self.tree.heading(col, text="")
            self.tree.column(col, width=0, stretch=False)

        self.tree.column("#0", width=260)
        self.tree.column("note", width=150, anchor="center")
        self.tree.column("battery", width=100, anchor="center")

        self.tree.pack(fill="both", expand=True)

        # 이벤트
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)

        # ------------------------------ Progress Bar ------------------------------
        self.progress = ttk.Progressbar(
            center,
            orient="horizontal",
            mode="determinate",
            style="ThinProgress.Horizontal.TProgressbar",
            maximum=100,
            value=0,
        )
        self.progress.pack(fill="x", padx=5, pady=(2, 4))
        
        # ------------------------------ 상태 표시 레이블 ------------------------------
        self.status_label = tk.Label(center, text="대기 중", font=("맑은 고딕", 9), fg="#666666")
        self.status_label.pack(fill="x", padx=5, pady=(0, 2))

        # ------------------------------ 하단 버튼들 ------------------------------
        bottom = tk.Frame(main)
        bottom.pack(fill="x", pady=5)

        # 버튼들을 리스트로 관리 (활성화/비활성화를 위해)
        self.buttons = []
        self.buttons.append(ttk.Button(bottom, text="변환 실행", command=self.app.convert_now))
        self.buttons.append(ttk.Button(bottom, text="CSV 생성", command=self.app.create_csv))
        self.buttons.append(ttk.Button(bottom, text="폴더 추가", command=self._add_folder))
        self.buttons.append(ttk.Button(bottom, text="파일 추가", command=self._add_file))
        self.buttons.append(ttk.Button(bottom, text="회사 삭제", command=self._delete_company))
        self.buttons.append(ttk.Button(bottom, text="선택 삭제", command=self._delete_selected))
        
        # 업데이트 버튼 (초기에는 숨김)
        self.update_button = ttk.Button(bottom, text="⬇ 업데이트 있음", command=self._on_update_click)
        self.update_button_visible = False
        
        for btn in self.buttons:
            btn.pack(side="left", padx=5)

        # ------------------------------ 로그창 ------------------------------
        self.log_box = tk.Text(main, height=10)
        self.log_box.pack(fill="x")
        
        # ------------------------------ 상태바 (하단 고정) ------------------------------
        self.statusbar = tk.Frame(main, relief=tk.SUNKEN, bd=1)
        self.statusbar.pack(side="bottom", fill="x")
        
        self.statusbar_label = tk.Label(
            self.statusbar, 
            text="준비 완료", 
            anchor="w",
            font=("맑은 고딕", 9)
        )
        self.statusbar_label.pack(side="left", padx=5, pady=2)

    # ======================================================
    # 로그 출력
    # ======================================================
    def append_log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    # ======================================================
    # 회사 목록 갱신
    # ======================================================
    def refresh_company_list(self):
        tree_data = self.app.tree.get_tree()
        dynamic = list(tree_data.keys())
        merged = list(dict.fromkeys(self.DEFAULT_COMPANIES + dynamic))

        self.company_combo["values"] = merged

        if not self.current_company:
            self.current_company = merged[0]

        self.company_var.set(self.current_company)

    # ======================================================
    # 업데이트 배터리
    # ======================================================
    def update_battery(self, company, folder, filename, value):

        # 모든 폴더 노드 탐색
        for folder_id in self.tree.get_children():
            if self.tree.set(folder_id, "company") != company:
                continue
            if self.tree.set(folder_id, "folder") != folder:
                continue

            # 해당 폴더 안에서 파일 찾기
            for file_id in self.tree.get_children(folder_id):
                if self.tree.set(file_id, "filename") == filename:
                    # ⭐ 배터리 값 갱신
                    self.tree.set(file_id, "battery", str(value))
                    return

    # ======================================================
    # 트리뷰 갱신
    # ======================================================
    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())

        self.refresh_company_list()
        if not self.current_company:
            return

        company = self.current_company
        company_dict = self.app.tree.get_company_data(company)

        for folder, folder_data in company_dict.items():

            if not isinstance(folder_data, dict):
                continue

            folder_note = folder_data.get("__note__", "")

            # ------------------------------ 📁 폴더 노드 ------------------------------
            folder_id = self.tree.insert(
                "",
                "end",
                text=folder,
                values=(folder_note, "", "folder", company, folder, ""),
            )

            # ------------------------------ 📄 파일 노드 ------------------------------
            for filename, file_cfg in folder_data.items():
                if filename.startswith("__"):
                    continue

                # 채널 summary 문자열 생성
                label_summary = self.app.tree.get_file_label_summary(company, folder, filename)

                # battery 캐시에서 가져오기
                key = (company, folder, filename)
                battery_value = self.app.battery_cache.get(key, "")

                file_id = self.tree.insert(
                    folder_id,
                    "end",
                    text=filename,
                    values=("", battery_value, "file", company, folder, filename),
                )

                # ------------------------------ Summary Node ------------------------------
                if label_summary:
                    self.tree.insert(
                        file_id,
                        "end",
                        text="  " + label_summary,
                        values=("", "", "summary", "", "", ""),
                    )

        # 자동 확장
        for item in self.tree.get_children():
            self.tree.item(item, open=True)
            for child in self.tree.get_children(item):
                self.tree.item(child, open=True)

    # ======================================================
    # 진행률 바 및 상태
    # ======================================================
    def update_progress(self, pct):
        self.progress["value"] = pct * 100
        self.root.update_idletasks()

    def reset_progress(self):
        self.progress["value"] = 0
        self.root.update_idletasks()
    
    def update_status(self, message, progress=None):
        """상태 메시지 및 진행률 업데이트"""
        self.status_label.config(text=message)
        self.statusbar_label.config(text=message)  # 하단 상태바도 업데이트
        if progress is not None:
            self.update_progress(progress)
        self.root.update_idletasks()
    
    def set_buttons_enabled(self, enabled):
        """모든 버튼 활성화/비활성화"""
        state = "normal" if enabled else "disabled"
        for btn in self.buttons:
            btn.config(state=state)
        self.company_combo.config(state="readonly" if enabled else "disabled")
        
        if enabled:
            self.status_label.config(text="대기 중", fg="#666666")
            self.statusbar_label.config(text="준비 완료", fg="#000000")
        else:
            self.status_label.config(text="변환 중...", fg="#4A90E2")
            self.statusbar_label.config(text="변환 작업 진행 중...", fg="#4A90E2")

    # ======================================================
    # 트리뷰 이벤트
    # ======================================================
    def _on_company_change(self, event=None):
        self.current_company = self.company_var.get()
        self.app.logger.log(f"[UI] 회사 변경: {self.current_company}")
        self.refresh_tree()

    def _on_tree_double_click(self, event=None):
        item = self.tree.focus()
        if not item:
            return

        node_type = self.tree.set(item, "type")
        company = self.tree.set(item, "company")
        folder = self.tree.set(item, "folder")
        filename = self.tree.set(item, "filename")

        if node_type == "summary":
            return

        if node_type == "file":
            self.app.logger.log(
                f"[UI] 파일 더블클릭: {company}/{folder}/{filename}"
            )
            self.app.open_channel_settings(company, folder, filename)

    def _on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return

        self.tree.selection_set(iid)
        self.tree.focus(iid)

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="선택 삭제", command=self._delete_selected)
        menu.tk_popup(event.x_root, event.y_root)

    # ======================================================
    # 폴더 추가
    # ======================================================
    def _add_folder(self):
        folder_path = filedialog.askdirectory(title="원본 폴더 선택")
        if not folder_path:
            return

        folder_name = os.path.basename(folder_path.rstrip("/\\"))

        company = self._popup_select_company()
        if not company:
            return

        self.app.tree.add_folder(company, folder_name, folder_path)

        csv_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".csv")]
        for csv in csv_files:
            self.app.tree.add_file(company, folder_name, csv)

        self.app.logger.log(f"[UI] 폴더 등록 완료 → {company}/{folder_name}")
        self.app.logger.log(f"[UI] CSV 자동 스캔: {len(csv_files)}개 파일")

        self.refresh_tree()

    # ======================================================
    # 파일 추가
    # ======================================================
    def _add_file(self):
        if not self.current_company:
            messagebox.showwarning("경고", "회사를 먼저 선택하세요.")
            return

        folder = simpledialog.askstring("파일 추가", "폴더명 입력:")
        if not folder:
            return

        filename = simpledialog.askstring("파일 추가", "파일명 입력:")
        if not filename:
            return

        self.app.tree.add_file(self.current_company, folder, filename)
        self.refresh_tree()

    # ======================================================
    # 삭제 기능
    # ======================================================
    def _delete_company(self):
        company = self.current_company
        if not company:
            return

        if messagebox.askyesno("삭제 확인", f"회사 '{company}' 삭제?"):
            self.app.tree.delete_company(company)
            self.refresh_tree()

    def _delete_selected(self):
        item = self.tree.focus()
        if not item:
            return

        node_type = self.tree.set(item, "type")
        company = self.tree.set(item, "company")
        folder = self.tree.set(item, "folder")
        filename = self.tree.set(item, "filename")

        if node_type == "folder":
            if messagebox.askyesno("삭제 확인", f"폴더 '{folder}' 삭제?"):
                self.app.tree.delete_folder(company, folder)

        elif node_type == "file":
            if messagebox.askyesno("삭제 확인", f"파일 '{filename}' 삭제?"):
                self.app.tree.delete_file(company, folder, filename)

        self.refresh_tree()

    # ======================================================
    # 회사 선택 팝업
    # ======================================================
    def _popup_select_company(self):
        popup = tk.Toplevel(self.root)
        popup.title("회사 선택")
        popup.geometry("300x150")
        popup.grab_set()

        tk.Label(popup, text="회사 선택:", font=("맑은 고딕", 10, "bold")).pack(pady=10)

        tree_companies = list(self.app.tree.get_tree().keys())
        merged = list(dict.fromkeys(self.DEFAULT_COMPANIES + tree_companies))

        company_var = tk.StringVar(value=merged[0])
        combo = ttk.Combobox(popup, textvariable=company_var, values=merged, state="readonly")
        combo.pack(pady=5)

        selected = {"value": None}

        def confirm():
            selected["value"] = company_var.get()
            popup.destroy()

        tk.Button(popup, text="확인", command=confirm).pack(side="left", padx=20, pady=15)
        tk.Button(popup, text="취소", command=popup.destroy).pack(side="right", padx=20, pady=15)

        popup.wait_window()
        return selected["value"]

    # ======================================================
    # 업데이트 기능
    # ======================================================
    def show_update_notification(self, update_info):
        """업데이트 알림 표시"""
        if not self.update_button_visible:
            self.update_button.pack(side="right", padx=10)
            self.update_button_visible = True
            
        version = update_info.get("version", "")
        self.update_button.config(text=f"⬇ 업데이트 {version} 사용 가능")
        
        # 상태바에도 표시
        self.statusbar_label.config(
            text=f"새 버전 {version} 발견! 업데이트 버튼을 클릭하세요.",
            fg="#0066CC"
        )
        
        # 로그에도 기록
        self.logger.log(f"[업데이트] 새 버전 {version} 발견", level="INFO")
    
    def _on_update_click(self):
        """업데이트 버튼 클릭 시"""
        if not self.app.update_info:
            return
        
        version = self.app.update_info.get("version", "")
        release_notes = self.app.update_info.get("release_notes", "업데이트 내용 없음")
        release_date = self.app.update_info.get("release_date", "")
        mandatory = self.app.update_info.get("mandatory", False)
        
        # 팝업 메시지
        msg = f"""새로운 버전이 있습니다!

버전: {version}
발표일: {release_date}

변경 내용:
{release_notes}

지금 업데이트하시겠습니까?
(프로그램이 재시작됩니다)"""
        
        if messagebox.askyesno("업데이트 가능", msg):
            # 업데이트 시작
            self.app.install_update()
