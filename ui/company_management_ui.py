"""
===============================================================
Convert Pro 3 - CompanyManagementUI
===============================================================
업체 관리 UI

기능:
    - 업체 목록 표시
    - 업체 추가 / 삭제 / 순서 변경
    - 선택 업체의 현장 목록
    - 현장별 주소 · 사용 프로그램 (config.json: 회사/현장 노드 __site_address__, __site_program__)
===============================================================
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

_SITE_PROGRAM_NONE = "(선택 안 함)"
SITE_PROGRAM_OPTIONS = (
    _SITE_PROGRAM_NONE,
    "AMS 휴먼 프로그램",
    "새길 자동화계측 통합 프로그램",
    "큐엠 올아이원 프로그램",
)


class CompanyManagementUI:
    """업체 관리 UI"""

    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.tree_manager = app.tree
        self.logger = app.logger

        self.win = tk.Toplevel(root)
        self.win.title("업체 관리")
        self.win.geometry("540x760")

        self._center_on_parent()

        self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.company_list = []
        self._current_company = None
        self._site_names = []

        self._build_ui()
        self.refresh_list()

    def _center_on_parent(self):
        self.win.update_idletasks()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()

        popup_width = self.win.winfo_width()
        popup_height = self.win.winfo_height()

        x = parent_x + (parent_width - popup_width) // 2
        y = parent_y + (parent_height - popup_height) // 2

        self.win.geometry(f"+{x}+{y}")

    def _on_closing(self):
        self.app.ui.refresh_company_list()
        self.app.ui.refresh_tree()
        self.win.destroy()

    def _site_keys_for_company(self, company):
        data = self.app.config.data.get(company, {})
        if not isinstance(data, dict):
            return []
        return sorted(
            k for k, v in data.items()
            if not k.startswith("__") and isinstance(v, dict)
        )

    def _clear_site_form(self):
        self._set_site_form_state(False)

    def _set_site_form_state(self, enabled):
        if enabled:
            self.address_entry.configure(state="normal")
            self.program_combo.configure(state="readonly")
            self._save_info_btn.configure(state="normal")
        else:
            self.address_var.set("")
            self.program_var.set(_SITE_PROGRAM_NONE)
            self.address_entry.configure(state="disabled")
            self.program_combo.configure(state="disabled")
            self._save_info_btn.configure(state="disabled")

    def _refresh_site_listbox(self, company, select_site=None):
        self.site_listbox.delete(0, tk.END)
        self._site_names = self._site_keys_for_company(company)
        self._current_company = company
        for idx, s in enumerate(self._site_names, 1):
            self.site_listbox.insert(tk.END, f"{idx}. {s}")
        if not self._site_names:
            self._clear_site_form()
            return
        if select_site and select_site in self._site_names:
            i = self._site_names.index(select_site)
            self.site_listbox.selection_set(i)
            self.site_listbox.see(i)
            self._load_site_details(company, select_site)
        else:
            self.site_listbox.selection_set(0)
            self.site_listbox.see(0)
            self._load_site_details(company, self._site_names[0])

    def _load_site_details(self, company, site):
        self._set_site_form_state(True)
        comp_data = self.app.config.data.get(company, {})
        if not isinstance(comp_data, dict):
            comp_data = {}
        site_data = comp_data.get(site, {})
        if not isinstance(site_data, dict):
            site_data = {}
        addr = (site_data.get("__site_address__") or "").strip()
        if not addr:
            addr = (comp_data.get("__address__") or "").strip()
        self.address_var.set(addr)
        stored = (site_data.get("__site_program__") or "").strip()
        if not stored:
            stored = (comp_data.get("__program__") or "").strip()
        known = {opt for opt in SITE_PROGRAM_OPTIONS if opt != _SITE_PROGRAM_NONE}
        if stored in known:
            self.program_var.set(stored)
        else:
            self.program_var.set(_SITE_PROGRAM_NONE)

    def _on_company_select(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            self._current_company = None
            self.site_listbox.delete(0, tk.END)
            self._site_names = []
            self._clear_site_form()
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self.company_list):
            self._clear_site_form()
            return
        company = self.company_list[idx]
        self._refresh_site_listbox(company)

    def _on_site_select(self, event=None):
        if not self._current_company:
            return
        sel = self.site_listbox.curselection()
        if not sel or sel[0] >= len(self._site_names):
            self._clear_site_form()
            return
        site = self._site_names[sel[0]]
        self._load_site_details(self._current_company, site)

    def _save_site_info(self):
        if not self._current_company:
            messagebox.showwarning("안내", "업체를 먼저 선택해주세요.")
            return
        sel = self.site_listbox.curselection()
        if not sel or sel[0] >= len(self._site_names):
            messagebox.showwarning("안내", "현장을 먼저 선택해주세요.")
            return
        company = self._current_company
        site = self._site_names[sel[0]]
        self.app.config.ensure_site(company, site)
        site_dict = self.app.config.data[company][site]
        if not isinstance(site_dict, dict):
            messagebox.showerror("오류", "현장 설정을 읽을 수 없습니다.")
            return

        addr = self.address_var.get().strip()
        if addr:
            site_dict["__site_address__"] = addr
        else:
            site_dict.pop("__site_address__", None)

        prog_display = self.program_var.get()
        if prog_display == _SITE_PROGRAM_NONE:
            site_dict.pop("__site_program__", None)
        else:
            site_dict["__site_program__"] = prog_display

        self.app.config.save()
        self.logger.log(f"[UI] 현장 정보 저장: {company}/{site}")
        messagebox.showinfo("저장 완료", f"'{company} / {site}' 현장 정보를 저장했습니다.")

    def _build_ui(self):
        header = tk.Frame(self.win, bg="#2C3E50", height=50)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="업체 관리",
            font=("맑은 고딕", 12, "bold"),
            bg="#2C3E50",
            fg="white",
        ).pack(side="left", padx=15, pady=10)

        main = tk.Frame(self.win, bg="white")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        list_frame = tk.LabelFrame(
            main,
            text="업체 목록",
            font=("맑은 고딕", 9, "bold"),
            bg="white",
            fg="#2C3E50",
            padx=10,
            pady=8,
        )
        list_frame.pack(fill="x", pady=(0, 8))

        sb_c = ttk.Scrollbar(list_frame, orient="vertical")
        sb_c.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            list_frame,
            font=("맑은 고딕", 10),
            yscrollcommand=sb_c.set,
            selectmode="single",
            height=6,
        )
        self.listbox.pack(side="left", fill="x", expand=True)
        sb_c.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self._on_company_select)

        site_frame = tk.LabelFrame(
            main,
            text="현장 목록 (업체 선택 후)",
            font=("맑은 고딕", 9, "bold"),
            bg="white",
            fg="#2C3E50",
            padx=10,
            pady=8,
        )
        site_frame.pack(fill="x", pady=(0, 8))

        sb_s = ttk.Scrollbar(site_frame, orient="vertical")
        sb_s.pack(side="right", fill="y")
        self.site_listbox = tk.Listbox(
            site_frame,
            font=("맑은 고딕", 10),
            yscrollcommand=sb_s.set,
            selectmode="single",
            height=6,
        )
        self.site_listbox.pack(side="left", fill="x", expand=True)
        sb_s.config(command=self.site_listbox.yview)
        self.site_listbox.bind("<<ListboxSelect>>", self._on_site_select)

        detail_frame = tk.LabelFrame(
            main,
            text="선택 현장 정보",
            font=("맑은 고딕", 9, "bold"),
            bg="white",
            fg="#2C3E50",
            padx=10,
            pady=8,
        )
        detail_frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            detail_frame,
            text="주소",
            font=("맑은 고딕", 9),
            bg="white",
            fg="#34495E",
        ).pack(anchor="w")
        self.address_var = tk.StringVar()
        self.address_entry = tk.Entry(
            detail_frame,
            textvariable=self.address_var,
            font=("맑은 고딕", 9),
            state="disabled",
        )
        self.address_entry.pack(fill="x", pady=(2, 8))

        tk.Label(
            detail_frame,
            text="사용 프로그램",
            font=("맑은 고딕", 9),
            bg="white",
            fg="#34495E",
        ).pack(anchor="w")
        self.program_var = tk.StringVar(value=_SITE_PROGRAM_NONE)
        self.program_combo = ttk.Combobox(
            detail_frame,
            textvariable=self.program_var,
            values=SITE_PROGRAM_OPTIONS,
            state="disabled",
            font=("맑은 고딕", 9),
            width=40,
        )
        self.program_combo.pack(anchor="w", pady=(2, 6))

        self._save_info_btn = tk.Button(
            detail_frame,
            text="정보 저장",
            command=self._save_site_info,
            font=("맑은 고딕", 9),
            bg="#16A085",
            fg="white",
            activebackground="#138D75",
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            state="disabled",
        )
        self._save_info_btn.pack(anchor="e")

        button_frame = tk.Frame(main, bg="white")
        button_frame.pack(fill="x", pady=(0, 10))

        left_buttons = tk.Frame(button_frame, bg="white")
        left_buttons.pack(side="left")

        tk.Button(
            left_buttons,
            text="업체 추가",
            command=self._add_company,
            font=("맑은 고딕", 9),
            bg="#27AE60",
            fg="white",
            activebackground="#229954",
            activeforeground="white",
            relief="flat",
            width=12,
            height=1,
            padx=10,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=5)

        tk.Button(
            left_buttons,
            text="업체 삭제",
            command=self._delete_company,
            font=("맑은 고딕", 9),
            bg="#E74C3C",
            fg="white",
            activebackground="#C0392B",
            activeforeground="white",
            relief="flat",
            width=12,
            height=1,
            padx=10,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=5)

        right_buttons = tk.Frame(button_frame, bg="white")
        right_buttons.pack(side="right")

        tk.Button(
            right_buttons,
            text="위로",
            command=self._move_up,
            font=("맑은 고딕", 9),
            bg="#3498DB",
            fg="white",
            activebackground="#2980B9",
            activeforeground="white",
            relief="flat",
            width=8,
            height=1,
            padx=8,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=3)

        tk.Button(
            right_buttons,
            text="아래로",
            command=self._move_down,
            font=("맑은 고딕", 9),
            bg="#3498DB",
            fg="white",
            activebackground="#2980B9",
            activeforeground="white",
            relief="flat",
            width=8,
            height=1,
            padx=8,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=3)

        tk.Button(
            main,
            text="닫기",
            command=self._on_closing,
            font=("맑은 고딕", 9),
            bg="#95A5A6",
            fg="white",
            activebackground="#7F8C8D",
            activeforeground="white",
            relief="flat",
            width=15,
            height=1,
            padx=10,
            pady=5,
            cursor="hand2",
        ).pack(pady=5)

    def refresh_list(self):
        prev_company = None
        prev_site = None
        csel = self.listbox.curselection()
        if csel and self.company_list and csel[0] < len(self.company_list):
            prev_company = self.company_list[csel[0]]
        ssel = self.site_listbox.curselection()
        if prev_company and self._site_names and ssel and ssel[0] < len(self._site_names):
            prev_site = self._site_names[ssel[0]]

        self.listbox.delete(0, tk.END)
        self.company_list = []

        tree_data = self.app.tree.get_tree()
        dynamic = [k for k in tree_data.keys() if not k.startswith("__")]

        merged = []
        for comp in self.app.ui.DEFAULT_COMPANIES:
            if comp in dynamic:
                merged.append(comp)
        for comp in dynamic:
            if comp not in merged:
                merged.append(comp)

        self.company_list = merged

        for idx, company in enumerate(self.company_list, 1):
            self.listbox.insert(tk.END, f"{idx}. {company}")

        if prev_company and prev_company in self.company_list:
            ci = self.company_list.index(prev_company)
            self.listbox.selection_set(ci)
            self.listbox.see(ci)
            self._refresh_site_listbox(prev_company, select_site=prev_site)
        elif self.company_list:
            self.listbox.selection_set(0)
            self.listbox.see(0)
            self._refresh_site_listbox(self.company_list[0])
        else:
            self.site_listbox.delete(0, tk.END)
            self._site_names = []
            self._current_company = None
            self._clear_site_form()

    def _add_company(self):
        company_name = simpledialog.askstring(
            "업체 추가",
            "업체 이름을 입력하세요:",
            parent=self.win,
        )

        if not company_name or not company_name.strip():
            return

        company_name = company_name.strip()

        if company_name in self.company_list:
            messagebox.showwarning("안내", f"'{company_name}' 업체가 이미 등록되어 있습니다.")
            return

        try:
            self.tree_manager.add_company(company_name)
            self.logger.log(f"[UI] 업체 추가 완료 → {company_name}")
            self.refresh_list()
            messagebox.showinfo("추가 완료", f"업체 '{company_name}'가 성공적으로 추가되었습니다.")
        except Exception as e:
            self.logger.log(f"[UI] 업체 추가 실패: {e}", level="ERROR")
            messagebox.showerror(
                "추가 실패",
                f"업체 추가 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.",
            )

    def _delete_company(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("안내", "삭제할 업체를 먼저 선택해주세요.")
            return

        idx = selection[0]
        company = self.company_list[idx]

        confirm_msg = (
            f"업체 '{company}'를 삭제하시겠습니까?\n\n"
            f"주의: 이 업체의 모든 현장, 폴더, 파일 설정이 함께 삭제됩니다.\n"
            f"이 작업은 되돌릴 수 없습니다."
        )

        if not messagebox.askyesno("삭제 확인", confirm_msg):
            return

        try:
            self.tree_manager.delete_company(company)
            self.logger.log(f"[UI] 업체 삭제: {company}")
            self.refresh_list()
            messagebox.showinfo("삭제 완료", f"업체 '{company}'가 성공적으로 삭제되었습니다.")
        except Exception as e:
            self.logger.log(f"[UI] 업체 삭제 실패: {e}", level="ERROR")
            messagebox.showerror(
                "삭제 실패",
                f"업체 삭제 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.",
            )

    def _move_up(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("안내", "위로 이동할 업체를 먼저 선택해주세요.")
            return

        idx = selection[0]
        if idx == 0:
            messagebox.showinfo("안내", "이미 맨 위에 있습니다.")
            return

        self.company_list[idx], self.company_list[idx - 1] = (
            self.company_list[idx - 1],
            self.company_list[idx],
        )

        self._save_order()
        self.refresh_list()
        self.listbox.selection_set(idx - 1)
        self.listbox.see(idx - 1)

    def _move_down(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("안내", "아래로 이동할 업체를 먼저 선택해주세요.")
            return

        idx = selection[0]
        if idx == len(self.company_list) - 1:
            messagebox.showinfo("안내", "이미 맨 아래에 있습니다.")
            return

        self.company_list[idx], self.company_list[idx + 1] = (
            self.company_list[idx + 1],
            self.company_list[idx],
        )

        self._save_order()
        self.refresh_list()
        self.listbox.selection_set(idx + 1)
        self.listbox.see(idx + 1)

    def _save_order(self):
        new_order = []

        for company in self.company_list:
            if company in self.app.ui.DEFAULT_COMPANIES:
                new_order.append(company)

        for company in self.company_list:
            if company not in new_order:
                new_order.append(company)

        self.app.ui.DEFAULT_COMPANIES = new_order
        self.logger.log(f"[UI] 업체 순서 저장: {new_order}")
