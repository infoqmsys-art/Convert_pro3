import os
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import filedialog, simpledialog, messagebox

class MainUI:

    def __init__(self, root, controller, logger):
        self.root = root
        self.controller = controller
        self.logger = logger

        # 👉 반드시 가장 먼저 선언해야 함
        self.default_companies = [
            "SAEGIL",
            "KD_ENG",
            "TAEAM",
            "DooYoung_Safe",
            "KIC"
        ]

        self.company_list = []   # 콤보박스용
        self.current_company = ""

        self._build_ui()
        self.refresh_company_list()
        self.refresh_tree()

    def _build_ui(self):
        main = tk.Frame(self.root)
        main.pack(fill="both", expand=True)

        # ------------------------------
        # 상단: 회사 선택 & 새로고침 버튼
        # ------------------------------
        top = tk.Frame(main)
        top.pack(fill="x")

        tk.Label(top, text="업체 선택:", font=("맑은 고딕", 10, "bold")).pack(side="left", padx=5)

        self.company_var = tk.StringVar()
        self.company_combo = ttk.Combobox(top, textvariable=self.company_var, state="readonly")
        self.company_combo.pack(side="left", padx=5)
        self.company_combo.bind("<<ComboboxSelected>>", self._on_company_change)

        ttk.Button(top, text="새로고침", command=self.refresh_tree).pack(side="left", padx=5)

        # ------------------------------
        # 중앙: TreeView
        # ------------------------------
        center = tk.Frame(main)
        center.pack(fill="both", expand=True, pady=5)

        columns = ("note", "label")
        self.tree = ttk.Treeview(center, columns=columns)
        self.tree.heading("#0", text="파일 / 폴더")
        self.tree.heading("note", text="비고")
        self.tree.heading("label", text="채널 설정")

        self.tree.column("#0", width=250)
        self.tree.column("note", width=120, anchor="center")
        self.tree.column("label", width=160, anchor="center")

        self.tree.pack(fill="both", expand=True)

        # 더블클릭
        self.tree.bind("<Double-Button-1>", self._on_tree_double_click)
        # 우클릭 메뉴
        self.tree.bind("<Button-3>", self._on_right_click)

        # ------------------------------
        # 하단 버튼들
        # ------------------------------
        bottom = tk.Frame(main)
        bottom.pack(fill="x", pady=5)

        ttk.Button(bottom, text="변환 실행", command=self.controller.convert_now).pack(side="left", padx=5)
        ttk.Button(bottom, text="CSV 생성", command=self.controller.create_csv).pack(side="left", padx=5)
        ttk.Button(bottom, text="폴더 추가", command=self._add_folder).pack(side="left", padx=5)
        ttk.Button(bottom, text="파일 추가", command=self._add_file).pack(side="left", padx=5)
        ttk.Button(bottom, text="회사 삭제", command=self._delete_company).pack(side="left", padx=5)
        ttk.Button(bottom, text="선택 삭제", command=self._delete_selected).pack(side="left", padx=5)

        # ------------------------------
        # 로그창
        # ------------------------------
        self.log_box = tk.Text(main, height=10)
        self.log_box.pack(fill="x")

    # ======================================================
    # 로그 출력
    # ======================================================
    def append_log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def refresh_company_list(self):
        # 트리 기반 회사 목록 + 기본 회사 목록 결합
        data = self.controller.tree.get_tree()
        dynamic_list = list(data.keys())

        # 기본 회사 목록 + 동적 목록 합치기 (중복 제거)
        merged = list(dict.fromkeys(self.default_companies + dynamic_list))

        self.company_list = merged
        self.company_combo["values"] = merged

        # 디폴트 선택
        if not self.current_company:
            self.current_company = merged[0]

        self.company_var.set(self.current_company)

    # ======================================================
    # 트리뷰 갱신
    # ======================================================
    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())

        self.refresh_company_list()
        if not self.current_company:
            return

        company = self.current_company
        company_dict = self.controller.tree.get_company_data(company)

        for folder, folder_data in company_dict.items():
            if not isinstance(folder_data, dict):
                continue

            note = folder_data.get("__note__", "")
            abs_path = folder_data.get("__absolute_path__", "")

            folder_id = self.tree.insert("", "end", text=folder, values=(note, ""))

            # 파일 표시
            for filename, file_cfg in folder_data.items():
                if filename.startswith("__"):
                    continue

                label_summary = self.controller.tree.get_file_label_summary(company, folder, filename)

                self.tree.insert(
                    folder_id,
                    "end",
                    text=filename,
                    values=("", label_summary)
                )

    # ======================================================
    # 이벤트 핸들러
    # ======================================================
    def _on_company_change(self, event=None):
        self.current_company = self.company_var.get()
        self.controller.logger.log(f"[UI] 회사 변경: {self.current_company}")
        self.refresh_tree()

    def _on_tree_double_click(self, event=None):
        item = self.tree.focus()
        if not item:
            return

        parent = self.tree.parent(item)
        text = self.tree.item(item, "text")

        if parent == "":  # 회사 아래 → 폴더
            # 폴더 메모 수정 팝업 (다음 단계에서 Controller 통해 팝업 띄우기)
            msg = f"폴더 '{text}' 메모 수정 (구현 예정)"
            self.logger.log(msg)
            messagebox.showinfo("Folder Note", msg)
            return

        folder_name = self.tree.item(parent, "text")
        filename = text

        # 파일 더블클릭 → 채널 설정 UI 열기
        self.logger.log(f"[UI] 파일 더블클릭: {folder_name}/{filename}")
        self.controller.open_channel_settings(self.current_company, folder_name, filename)

    # 우클릭 메뉴
    def _on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return

        self.tree.selection_set(iid)
        self.tree.focus(iid)

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="선택 삭제", command=self._delete_selected)
        menu.tk_popup(event.x_root, event.y_root)

    def _add_folder(self):

        folder_path = filedialog.askdirectory(title="원본 폴더 선택")
        if not folder_path:
            return

        import os
        folder_name = os.path.basename(folder_path.rstrip("/\\"))

        company = self._popup_select_company()
        if not company:
            return

        self.controller.tree.add_folder(company, folder_name, folder_path)

        csv_files = [f for f in os.listdir(folder_path)
                    if f.lower().endswith(".csv")]

        for csv in csv_files:
            self.controller.tree.add_file(company, folder_name, csv)

        self.logger.log(f"[UI] 폴더 등록 완료 → {company}/{folder_name}")
        self.logger.log(f"[UI] CSV 자동 스캔: {len(csv_files)}개 파일 등록됨.")

        self.refresh_company_list()
        self.refresh_tree()

    def _add_file(self):
        if not self.current_company:
            messagebox.showwarning("경고", "회사를 먼저 선택하세요.")
            return

        folder = tk.simpledialog.askstring("파일 추가", "폴더명 입력:")
        if not folder:
            return

        filename = tk.simpledialog.askstring("파일 추가", "파일명 입력:")
        if not filename:
            return

        self.controller.tree.add_file(self.current_company, folder, filename)
        self.refresh_tree()

    def _delete_company(self):
        company = self.current_company
        if not company:
            return

        if messagebox.askyesno("삭제 확인", f"회사 '{company}' 삭제?"):
            self.controller.tree.delete_company(company)
            self.refresh_tree()

    def _delete_selected(self):
        item = self.tree.focus()
        if not item:
            return

        parent = self.tree.parent(item)
        text = self.tree.item(item, "text")

        if parent == "":
            # 폴더 삭제
            if messagebox.askyesno("삭제 확인", f"폴더 '{text}' 삭제?"):
                self.controller.tree.delete_folder(self.current_company, text)
        else:
            # 파일 삭제
            folder = self.tree.item(parent, "text")
            if messagebox.askyesno("삭제 확인", f"파일 '{text}' 삭제?"):
                self.controller.tree.delete_file(self.current_company, folder, text)

        self.refresh_tree()

    def _popup_select_company(self):
        """콤보박스로 회사 선택 팝업을 띄우고 선택된 값을 반환한다."""
        popup = tk.Toplevel(self.root)
        popup.title("회사 선택")
        popup.geometry("300x150")
        popup.grab_set()  # 모달처럼 작동하게

        tk.Label(popup, text="회사 선택:", font=("맑은 고딕", 10, "bold")).pack(pady=10)

        # 기본 회사 목록 + Tree 내 회사 목록 합치기
        tree_companies = list(self.controller.tree.get_tree().keys())
        merged = list(dict.fromkeys(self.default_companies + tree_companies))

        company_var = tk.StringVar(value=merged[0])
        combo = ttk.Combobox(popup, textvariable=company_var, values=merged, state="readonly")
        combo.pack(pady=5)

        selected = {"value": None}

        def confirm():
            selected["value"] = company_var.get()
            popup.destroy()

        def cancel():
            popup.destroy()

        ttk.Button(popup, text="확인", command=confirm).pack(side="left", padx=20, pady=15)
        ttk.Button(popup, text="취소", command=cancel).pack(side="right", padx=20, pady=15)

        popup.wait_window()  # 창 닫힐 때까지 대기
        return selected["value"]