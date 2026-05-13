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
from ui.context_menu import FolderContextMenu
from ui.company_management_ui import CompanyManagementUI
from ui.unregistered_files_ui import UnregisteredFilesUI


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
    ALL_COMPANIES_OPTION = "전체 업체"

    def __init__(self, root, app):
        self.root = root
        self.app = app               # controller → app (핵심 변경)
        self.logger = app.logger
        self.current_company = ""

        self._build_ui()

        # Logger가 UI로 로그를 전달하기 위한 callback 등록
        self.logger.set_ui_callback(self.append_log)

        # 우클릭 메뉴 초기화
        self.context_menu = FolderContextMenu(self.root, self.app, self.tree)

        self.refresh_company_list()
        # 초기 로드 시 Ghost 체크 포함
        self._refresh_with_ghost_check()

    # ======================================================
    # UI 구성
    # ======================================================
    def _build_ui(self):
        # 메인 프레임 배경색 설정
        main = tk.Frame(self.root, bg="#F5F5F5")
        main.pack(fill="both", expand=True)

        # ======================================================
        #  스타일 설정
        # ======================================================
        style = ttk.Style()
        style.theme_use("default")
        
        # ProgressBar 스타일
        style.configure(
            "ThinProgress.Horizontal.TProgressbar",
            troughcolor="#ECF0F1",
            bordercolor="#ECF0F1",
            background="#3498DB",
            lightcolor="#3498DB",
            darkcolor="#3498DB",
            thickness=6,
            borderwidth=0,
            relief="flat"
        )

        # ------------------------------ 상단: 헤더 영역 ------------------------------
        header = tk.Frame(main, bg="#2C3E50", height=60)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        
        # 왼쪽: 제목
        title_frame = tk.Frame(header, bg="#2C3E50")
        title_frame.pack(side="left", fill="y", padx=15)
        tk.Label(
            title_frame, 
            text="Convert Pro 3", 
            font=("맑은 고딕", 14, "bold"),
            bg="#2C3E50",
            fg="white"
        ).pack(anchor="w", pady=(8, 0))
        tk.Label(
            title_frame,
            text="데이터 변환 관리 시스템",
            font=("맑은 고딕", 9),
            bg="#2C3E50",
            fg="#BDC3C7"
        ).pack(anchor="w")
        
        # 오른쪽: 업체 선택 및 새로고침
        top_controls = tk.Frame(header, bg="#2C3E50")
        top_controls.pack(side="right", fill="y", padx=15, pady=10)
        
        tk.Label(
            top_controls, 
            text="업체:", 
            font=("맑은 고딕", 9, "bold"),
            bg="#2C3E50",
            fg="white"
        ).pack(side="left", padx=(0, 5))

        self.company_var = tk.StringVar()
        self.company_combo = ttk.Combobox(
            top_controls, 
            textvariable=self.company_var, 
            state="readonly",
            width=15,
            font=("맑은 고딕", 9)
        )
        self.company_combo.pack(side="left", padx=5)
        self.company_combo.bind("<<ComboboxSelected>>", self._on_company_change)

        ttk.Button(
            top_controls, 
            text="새로고침", 
            command=self._refresh_with_ghost_check,
            width=12
        ).pack(side="left", padx=5)

        # ------------------------------ 중앙: TreeView ------------------------------
        center = tk.Frame(main, bg="white")
        center.pack(fill="both", expand=True, padx=10, pady=10)

        # TreeView 프레임 (스크롤바 포함)
        tree_frame = tk.Frame(center, bg="white")
        tree_frame.pack(fill="both", expand=True)
        
        # 스크롤바
        tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scrollbar.pack(side="right", fill="y")

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("note", "battery", "type", "company", "site", "folder", "filename", "is_ghost"),
            show="tree headings",
            yscrollcommand=tree_scrollbar.set,
            selectmode="extended"
        )
        tree_scrollbar.config(command=self.tree.yview)

        # 헤더 스타일
        style = ttk.Style()
        style.configure("Treeview.Heading", font=("맑은 고딕", 9, "bold"), background="#ECF0F1")
        style.map("Treeview", 
                  background=[("selected", "#3498DB")],
                  foreground=[("selected", "white")])
        
        # 트리뷰 배경색 설정
        style.configure("Treeview", background="white", fieldbackground="white", rowheight=22)

        self.tree.heading("#0", text="파일 / 폴더 / 현장")
        self.tree.heading("note", text="비고")
        self.tree.heading("battery", text="배터리 (%)")

        # 숨길 internal metadata
        for col in ("type", "company", "site", "folder", "filename", "is_ghost"):
            self.tree.heading(col, text="")
            self.tree.column(col, width=0, stretch=False)

        self.tree.column("#0", width=300, minwidth=200)
        self.tree.column("note", width=180, anchor="center", minwidth=100)
        self.tree.column("battery", width=120, anchor="center", minwidth=80)

        self.tree.pack(side="left", fill="both", expand=True)

        # 이벤트
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)

        # ------------------------------ Progress Bar 및 상태 ------------------------------
        status_frame = tk.Frame(center, bg="white")
        status_frame.pack(fill="x", pady=(10, 0))
        
        self.status_label = tk.Label(
            status_frame, 
            text="준비 완료", 
            font=("맑은 고딕", 9),
            fg="#7F8C8D",
            bg="white",
            anchor="w"
        )
        self.status_label.pack(fill="x", padx=(0, 5))
        
        self.progress = ttk.Progressbar(
            status_frame,
            orient="horizontal",
            mode="determinate",
            style="ThinProgress.Horizontal.TProgressbar",
            maximum=100,
            value=0,
        )
        self.progress.pack(fill="x", pady=(5, 0))
        
        # ------------------------------ 버튼 영역 (상태 메시지 아래) ------------------------------
        button_frame = tk.Frame(status_frame, bg="white")
        button_frame.pack(fill="x", pady=(10, 0))
        
        # 왼쪽: 빈 공간
        tk.Frame(button_frame, bg="white").pack(side="left", fill="x", expand=True)

        # 오른쪽: 버튼들 (크기 통일)
        right_buttons = tk.Frame(button_frame, bg="white")
        right_buttons.pack(side="right")

        # 버튼들을 리스트로 관리 (활성화/비활성화를 위해)
        self.buttons = []
        
        # 변환 실행 버튼 (강조)
        convert_btn = tk.Button(
            right_buttons,
            text="변환 실행",
            command=self.app.convert_now,
            font=("맑은 고딕", 8, "bold"),
            bg="#3498DB",
            fg="white",
            activebackground="#2980B9",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=8,
            pady=4,
            cursor="hand2"
        )
        convert_btn.pack(side="left", padx=(0, 5))
        self.buttons.append(convert_btn)

        schedule_btn = tk.Button(
            right_buttons,
            text="자동변환 시각",
            command=self._open_auto_convert_schedule_dialog,
            font=("맑은 고딕", 8),
            bg="#16A085",
            fg="white",
            activebackground="#138D75",
            activeforeground="white",
            relief="flat",
            width=11,
            height=1,
            padx=8,
            pady=4,
            cursor="hand2",
        )
        schedule_btn.pack(side="left", padx=(0, 5))
        self.buttons.append(schedule_btn)

        # 변환 중지 버튼 (변환 중일 때만 표시)
        self.stop_convert_btn = tk.Button(
            right_buttons,
            text="⏹ 변환 중지",
            command=self.app.convert_stop,
            font=("맑은 고딕", 8, "bold"),
            bg="#E74C3C",
            fg="white",
            activebackground="#C0392B",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=8,
            pady=4,
            cursor="hand2",
            state="disabled"  # 기본 비활성화
        )
        self.stop_convert_btn.pack(side="left", padx=(0, 5))
        
        # 업체 관리 버튼
        manage_company_btn = tk.Button(
            right_buttons,
            text="업체 관리",
            command=self._manage_companies,
            font=("맑은 고딕", 8),
            bg="#27AE60",
            fg="white",
            activebackground="#229954",
            activeforeground="white",
            relief="flat",
            width=8,
            height=1,
            padx=8,
            pady=4,
            cursor="hand2"
        )
        manage_company_btn.pack(side="left", padx=3)
        self.buttons.append(manage_company_btn)
        
        add_site_btn = tk.Button(
            right_buttons,
            text="현장 추가",
            command=self._add_site,
            font=("맑은 고딕", 8),
            bg="#95A5A6",
            fg="white",
            activebackground="#7F8C8D",
            activeforeground="white",
            relief="flat",
            width=8,
            height=1,
            padx=8,
            pady=4,
            cursor="hand2"
        )
        add_site_btn.pack(side="left", padx=3)
        self.buttons.append(add_site_btn)
        
        # 업데이트 확인 버튼
        update_btn = tk.Button(
            right_buttons,
            text="업데이트",
            command=self._check_update,
            font=("맑은 고딕", 8),
            bg="#9B59B6",
            fg="white",
            activebackground="#8E44AD",
            activeforeground="white",
            relief="flat",
            width=8,
            height=1,
            padx=8,
            pady=4,
            cursor="hand2"
        )
        update_btn.pack(side="left", padx=3)
        # 업데이트 버튼은 buttons 리스트에 추가하지 않음 (항상 활성화)
        
        add_folder_btn = tk.Button(
            right_buttons,
            text="로거파일 등록",
            command=self._register_logger_files,
            font=("맑은 고딕", 8),
            bg="#95A5A6",
            fg="white",
            activebackground="#7F8C8D",
            activeforeground="white",
            relief="flat",
            width=11,
            height=1,
            padx=8,
            pady=4,
            cursor="hand2"
        )
        add_folder_btn.pack(side="left", padx=3)
        self.buttons.append(add_folder_btn)
        
        # 미등록 파일 관리 버튼
        unreg_files_btn = tk.Button(
            right_buttons,
            text="미등록 파일",
            command=self._open_unregistered_files,
            font=("맑은 고딕", 8),
            bg="#E67E22",
            fg="white",
            activebackground="#D35400",
            activeforeground="white",
            relief="flat",
            width=9,
            height=1,
            padx=8,
            pady=4,
            cursor="hand2"
        )
        unreg_files_btn.pack(side="left", padx=3)
        self.buttons.append(unreg_files_btn)
        
        # ------------------------------ 웹 재시작 배너 (평소 숨김) -------------------------
        self._web_restart_banner = tk.Frame(main, bg="#E67E22")
        # pack하지 않음 — show_web_restart_banner()에서 동적으로 표시

        tk.Label(
            self._web_restart_banner,
            text="📦 monitoring/server.py 변경 감지됨",
            font=("맑은 고딕", 9, "bold"),
            bg="#E67E22",
            fg="white"
        ).pack(side="left", padx=12, pady=4)

        tk.Button(
            self._web_restart_banner,
            text="웹 재시작",
            command=self._do_web_restart,
            font=("맑은 고딕", 9, "bold"),
            bg="white",
            fg="#E67E22",
            relief="flat",
            padx=10,
            pady=2,
            cursor="hand2"
        ).pack(side="left", padx=4)

        tk.Button(
            self._web_restart_banner,
            text="✕",
            command=self.hide_web_restart_banner,
            font=("맑은 고딕", 9),
            bg="#E67E22",
            fg="white",
            relief="flat",
            padx=6,
            cursor="hand2"
        ).pack(side="right", padx=6)

        # ------------------------------ 상태창 (크기 축소) ------------------------------
        log_frame = tk.LabelFrame(
            main, 
            text="상태", 
            font=("맑은 고딕", 9, "bold"),
            bg="white",
            fg="#2C3E50",
            padx=10,
            pady=5
        )
        log_frame.pack(fill="x", expand=False, padx=10, pady=(0, 10))  # expand=False로 변경하여 트리뷰 공간 확보
        
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical")
        log_scrollbar.pack(side="right", fill="y")
        
        self.log_box = tk.Text(
            log_frame, 
            height=6,  # 높이 축소하여 트리뷰 공간 확보
            font=("맑은 고딕", 8),
            bg="#F8F9FA",
            fg="#2C3E50",
            wrap="word",
            yscrollcommand=log_scrollbar.set,
            relief="flat",
            padx=5,
            pady=5
        )
        self.log_box.pack(side="left", fill="both", expand=True)
        log_scrollbar.config(command=self.log_box.yview)
        
        # ------------------------------ 상태바 (하단 고정) ------------------------------
        self.statusbar = tk.Frame(main, bg="#34495E", height=25)
        self.statusbar.pack(side="bottom", fill="x")
        self.statusbar.pack_propagate(False)
        
        self.statusbar_label = tk.Label(
            self.statusbar, 
            text="준비 완료", 
            anchor="w",
            font=("맑은 고딕", 8),
            bg="#34495E",
            fg="#ECF0F1"
        )
        self.statusbar_label.pack(side="left", padx=10, pady=4)

    # ======================================================
    # ======================================================
    # 웹 서버 재시작 배너
    # ======================================================
    def show_web_restart_banner(self):
        """server.py 변경 감지 시 주황색 배너 표시"""
        try:
            self._web_restart_banner.pack(fill="x", padx=10, pady=(0, 4))
        except Exception:
            pass

    def hide_web_restart_banner(self):
        try:
            self._web_restart_banner.pack_forget()
        except Exception:
            pass

    def _do_web_restart(self):
        """[웹 재시작] 버튼 → 프로그램 전체 재시작"""
        from tkinter import messagebox
        ok = messagebox.askokcancel(
            "웹 서버 재시작",
            "프로그램을 재시작해서 변경된 server.py를 반영합니다.\n\n"
            "진행하시겠습니까?\n"
            "(config·설정 데이터는 그대로 유지됩니다)",
            parent=self.root
        )
        if ok:
            self.hide_web_restart_banner()
            self.app.restart_web_server()

    # ======================================================
    # 로그 출력
    # ======================================================
    def append_log(self, text):
        """상태 메시지 추가 (사용자 친화적 변환)"""
        from datetime import datetime
        try:
            # 개발자용 로그를 사용자 친화적 메시지로 변환
            user_message = self._convert_to_user_message(text)
            if not user_message:
                return  # 표시할 필요 없는 메시지는 스킵
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_box.insert("end", f"[{timestamp}] {user_message}\n")
            self.log_box.see("end")
            
            # 최대 50줄만 유지 (메모리 절약)
            lines = self.log_box.get("1.0", "end").split("\n")
            if len(lines) > 50:
                self.log_box.delete("1.0", f"{len(lines) - 50}.0")
        except:
            pass
    
    def _convert_to_user_message(self, log_text):
        """개발자용 로그를 사용자 친화적 메시지로 변환"""
        # 기술적인 태그 제거
        text = log_text
        
        # 레벨 정보 제거
        text = text.replace("[INFO]", "").replace("[WARN]", "").replace("[ERROR]", "").replace("[DEBUG]", "")
        
        # 기술적인 태그 제거
        text = text.replace("[UI]", "").replace("[Tree]", "").replace("[FP]", "").replace("[Scanner]", "")
        text = text.replace("[BatteryReader]", "").replace("[ConfigManager]", "").replace("[Controller]", "")
        
        # 타임스탬프 제거 (이미 UI에서 추가함)
        import re
        text = re.sub(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]', '', text)
        
        # 메시지 정리
        text = text.strip()
        
        # 사용자 친화적으로 변환
        if "초기화 완료" in text or "초기화" in text:
            return "프로그램이 준비되었습니다."
        
        if "변환 시작" in text or "변환 작업이 진행 중" in text:
            return "변환 작업을 시작합니다..."
        
        if "변환 완료" in text or "변환 종료" in text:
            return "변환 작업이 완료되었습니다."
        
        if "업체 추가" in text:
            match = re.search(r'→\s*(\w+)', text)
            if match:
                return f"업체 '{match.group(1)}'가 추가되었습니다."
            return "업체가 추가되었습니다."
        
        if "업체 삭제" in text:
            match = re.search(r'업체 삭제:\s*(\w+)', text)
            if match:
                return f"업체 '{match.group(1)}'가 삭제되었습니다."
            return "업체가 삭제되었습니다."
        
        if "현장 추가" in text:
            match = re.search(r'→\s*(\w+)/(\w+)', text)
            if match:
                return f"현장 '{match.group(2)}'가 추가되었습니다."
            return "현장이 추가되었습니다."
        
        if "현장 삭제" in text:
            match = re.search(r'현장 삭제:\s*(\w+)/(\w+)', text)
            if match:
                return f"현장 '{match.group(2)}'가 삭제되었습니다."
            return "현장이 삭제되었습니다."
        
        if "폴더 삭제" in text:
            return "폴더가 삭제되었습니다."
        
        if "파일 삭제" in text:
            return "파일이 삭제되었습니다."
        
        if "파일 등록" in text or "등록 완료" in text:
            match = re.search(r'(\d+)개', text)
            if match:
                return f"{match.group(1)}개의 파일이 등록되었습니다."
            return "파일이 등록되었습니다."
        
        if "스캔 완료" in text or "새 파일 스캔" in text:
            match = re.search(r'(\d+)개', text)
            if match:
                return f"새 파일 {match.group(1)}개를 찾았습니다."
            return "새 파일을 찾았습니다."
        
        if "오류" in text or "실패" in text or "ERROR" in text:
            # 요약 통계의 오류 개수 (- 오류: 0) - 정상이므로 표시하지 않음
            if re.search(r'-\s*오류:\s*\d+', text) and any(
                x in text for x in ["대상 파일", "전체 처리", "폴더 변환 완료", "실제 변환"]
            ):
                return None
            # 정보성 메시지 (오류 아님): 최초 변환/스킵 안내
            if "변환본 마지막 값 없음" in text or (
                "누락보충 스킵" in text and "읽기 실패" in text
            ) or "누락 보충 스킵" in text:
                return None
            # 변환본 읽기 실패 - 실제 오류
            if "변환본 읽기 실패" in text:
                match = re.search(r'변환본 읽기 실패:?\s*(.+)', text)
                if match:
                    err = match.group(1).strip()
                    if len(err) > 50:
                        err = err[:47] + "..."
                    return f"변환본 읽기 실패: {err}"
                return "변환본 읽기 실패"
            # 변환 오류인 경우 파일명과 오류 내용 추출
            if "변환 오류:" in text:
                # 예: "변환 오류: DooYoung_Safe/안암역/DYANJ-0805/1237366102.csv - Permission denied"
                match = re.search(r'변환 오류:\s*([^/]+/[^/]+/[^/]+/[^\s]+)\s*-\s*(.+)', text)
                if match:
                    filename = match.group(1).split('/')[-1]  # 파일명만 추출
                    error_msg = match.group(2).strip()
                    # 오류 메시지가 너무 길면 자름
                    if len(error_msg) > 50:
                        error_msg = error_msg[:47] + "..."
                    return f"변환 오류: {filename} - {error_msg}"
                # 파일명만 추출
                match = re.search(r'변환 오류:\s*([^/]+/[^/]+/[^/]+/[^\s]+)', text)
                if match:
                    filename = match.group(1).split('/')[-1]
                    return f"변환 오류: {filename}"
            # 전체/폴더/파일 변환 중 오류
            for prefix in ["전체 변환", "폴더 변환", "파일 변환"]:
                if f"{prefix} 중 오류 발생:" in text:
                    match = re.search(rf'{re.escape(prefix)} 중 오류 발생:\s*(.+)', text)
                    if match:
                        error_msg = match.group(1).strip()
                        if len(error_msg) > 60:
                            error_msg = error_msg[:57] + "..."
                        return f"변환 오류: {error_msg}"
                    break
            # 파일 변환 실패
            if "파일 변환 실패" in text:
                match = re.search(r'파일 변환 실패\s+([^/]+/[^/]+/[^/]+/[^\s:]+)', text)
                if match:
                    filename = match.group(1).split('/')[-1]
                    return f"변환 실패: {filename}"
            # 일반 오류
            # UI 오탐 방지: 실제 ERROR 레벨이 없는 문장은 오류로 띄우지 않음
            # (예: 정상 로그 중 '오류:' 문자열이 포함되거나, 다른 메시지에서 단어만 포함되는 케이스)
            is_real_error = ("[ERROR]" in text) or (" ERROR" in text) or ("ERROR]" in text)
            if ("오류가 발생" in text or "오류:" in text) and not is_real_error:
                return None

            if "오류가 발생" in text or "오류:" in text:
                # 오류 내용이 있으면 표시 (단, "오류: 0"은 오류 개수 0건 = 정상)
                match = re.search(r'오류[:\s]+(.+)', text)
                if match:
                    error_msg = match.group(1).strip()
                    if error_msg.isdigit() and int(error_msg) == 0:
                        return None  # 오류 0건 = 정상, 표시하지 않음
                    if len(error_msg) > 60:
                        error_msg = error_msg[:57] + "..."
                    return f"오류: {error_msg}"
                return "작업 중 오류가 발생했습니다. (로그: logs/app.log)"
            return "오류가 발생했습니다. (로그: logs/app.log)"
        
        if "경고" in text or "WARN" in text:
            return None  # 경고는 표시하지 않음
        
        # DEBUG 레벨은 표시하지 않음
        if "DEBUG" in text or "debug" in text.lower():
            return None
        
        # 나머지는 너무 기술적인 내용이면 스킵
        if any(tag in text for tag in ["[", "]", "→", "FP", "Tree", "Scanner"]):
            return None
        
        # 간단한 메시지만 표시
        if len(text) > 100:
            return None
        
        return text if text else None

    # ======================================================
    # 업체 목록 갱신
    # ======================================================
    def refresh_company_list(self):
        tree_data = self.app.tree.get_tree()
        dynamic = [k for k in tree_data.keys() if not k.startswith("__")]
        
        # 기본 업체와 동적 업체 합치기 (순서 유지)
        merged = []
        for comp in self.DEFAULT_COMPANIES:
            if comp in dynamic:
                merged.append(comp)
        for comp in dynamic:
            if comp not in merged:
                merged.append(comp)
        
        # "전체 업체" 옵션 추가
        company_list = [self.ALL_COMPANIES_OPTION] + merged
        self.company_combo["values"] = company_list

        if not self.current_company:
            self.current_company = self.ALL_COMPANIES_OPTION

        self.company_var.set(self.current_company)

    # ======================================================
    # 업데이트 배터리
    # ======================================================
    def update_battery(self, company, site, folder, filename, value):
        """배터리 값 업데이트 (Site 레벨 포함)"""
        # 모든 현장 노드 탐색
        for site_id in self.tree.get_children():
            if self.tree.set(site_id, "company") != company:
                continue
            if self.tree.set(site_id, "site") != site:
                continue
            
            # 현장 안에서 폴더 찾기
            for folder_id in self.tree.get_children(site_id):
                if self.tree.set(folder_id, "folder") != folder:
                    continue

            # 해당 폴더 안에서 파일 찾기
            for file_id in self.tree.get_children(folder_id):
                if self.tree.set(file_id, "filename") == filename:
                    # 배터리 값 갱신
                    self.tree.set(file_id, "battery", str(value))
                    return

    # ======================================================
    # 트리뷰 갱신 (Ghost 체크 포함)
    # ======================================================
    def _refresh_with_ghost_check(self):
        """경로 유효성 검사 후 트리뷰 새로고침"""
        result = self.app.config.check_path_validity()
        ghost_count = result.get("ghost_count", 0)
        
        if ghost_count > 0:
            self.app.logger.log(
                f"[UI] 경로 유효성 검사 완료: {ghost_count}개 폴더 경로 유실",
                level="WARN"
            )
        
        self.refresh_tree()
    
    # ======================================================
    # 트리뷰 갱신 (4단계 구조: 업체 → 현장 → 폴더 → 파일)
    # ======================================================
    def refresh_tree(self):
        # 웹 모니터링 등 외부에서 config.json을 수정한 경우 메모리와 동기화
        try:
            self.app.config.load(quiet=True)
        except Exception:
            pass

        self.tree.delete(*self.tree.get_children())

        self.refresh_company_list()
        if not self.current_company:
            return

        # "전체 업체" 선택 시 모든 업체 표시
        if self.current_company == self.ALL_COMPANIES_OPTION:
            self._refresh_all_companies()
            return

        company = self.current_company
        company_dict = self.app.tree.get_company_data(company)

        # company_dict가 dict가 아니면 스킵
        if not isinstance(company_dict, dict):
            return

        # 업체 → 현장 → 폴더 → 파일 순회
        self._refresh_single_company(company, company_dict)
    
    def _refresh_all_companies(self):
        """전체 업체 표시"""
        tree_data = self.app.tree.get_tree()
        
        # 업체 목록 가져오기 (콤보박스 순서대로)
        dynamic = [k for k in tree_data.keys() if not k.startswith("__")]
        merged = []
        for comp in self.DEFAULT_COMPANIES:
            if comp in dynamic:
                merged.append(comp)
        for comp in dynamic:
            if comp not in merged:
                merged.append(comp)
        
        # 각 업체별로 표시
        for company in merged:
            company_dict = self.app.tree.get_company_data(company)
            if not isinstance(company_dict, dict):
                continue
            
            # 업체 노드 추가 (bold 스타일)
            company_id = self.tree.insert(
                "",
                "end",
                text=company,
                values=("", "", "company", company, "", "", "", ""),
                tags=("company_bold",)
            )
            
            # 해당 업체의 현장/폴더/파일 표시
            self._refresh_company_content(company_id, company, company_dict)
    
    def _refresh_single_company(self, company, company_dict):
        """단일 업체 표시"""
        # 업체 → 현장 → 폴더 → 파일 순회
        self._refresh_company_content(None, company, company_dict)
    
    def _refresh_company_content(self, parent_id, company, company_dict):
        """업체 내용 표시 (현장 → 폴더 → 파일)"""
        for site_name, site_data in company_dict.items():
            if site_name.startswith("__") or not isinstance(site_data, dict):
                continue

            site_note = site_data.get("__note__", "")
            is_ghost_site = site_data.get("__is_ghost__", False)

            # ------------------------------ 현장 노드 ------------------------------
            site_text = f"[Ghost] {site_name}" if is_ghost_site else site_name
            # 현장은 진하게 표시
            site_tags = ["site_bold"]
            if is_ghost_site:
                site_tags.append("ghost")
            
            if parent_id:
                site_id = self.tree.insert(
                    parent_id,
                    "end",
                    text=site_text,
                    values=(site_note, "", "site", company, site_name, "", "", ""),
                    tags=tuple(site_tags)
                )
            else:
                site_id = self.tree.insert(
                    "",
                    "end",
                    text=site_text,
                    values=(site_note, "", "site", company, site_name, "", "", ""),
                    tags=tuple(site_tags)
                )

            # management.json 현장 카테고리 데이터
            site_mgmt = {}
            if hasattr(self.app, "mgmt") and self.app.mgmt:
                site_mgmt = self.app.mgmt.get_site(company, site_name) or {}
            has_categories = bool(
                [s for s in site_mgmt.get("stations", []) if isinstance(s, dict)]
            ) or bool(
                [g for g in site_mgmt.get("station_groups", []) if isinstance(g, dict)]
            )

            if has_categories:
                # ── 카테고리 있음: 폴더 레벨 없이 현장 바로 아래 ──
                all_files = []  # (folder_name, sort_key, filename, file_cfg)
                for folder_name, folder_data in site_data.items():
                    if folder_name.startswith("__") or not isinstance(folder_data, dict):
                        continue
                    for sort_key, filename, file_cfg in self._build_files_list(folder_data):
                        all_files.append((folder_name, sort_key, filename, file_cfg))
                all_files.sort(key=lambda x: (x[1], x[0], x[2]))
                self._insert_files_by_category(site_id, company, site_name, site_mgmt, all_files)
            else:
                # ── 카테고리 없음: 기존 폴더 구조 유지 ──
                for folder_name, folder_data in site_data.items():
                    if folder_name.startswith("__") or not isinstance(folder_data, dict):
                        continue

                    folder_note = folder_data.get("__note__", "")
                    is_ghost_folder = folder_data.get("__is_ghost__", False)

                    folder_text = f"[Ghost] {folder_name}" if is_ghost_folder else folder_name
                    folder_tags = ["folder_normal"]
                    if is_ghost_folder:
                        folder_tags.append("ghost")

                    folder_id = self.tree.insert(
                        site_id, "end",
                        text=folder_text,
                        values=(folder_note, "", "folder", company, site_name, folder_name, "", str(is_ghost_folder)),
                        tags=tuple(folder_tags)
                    )

                    files_list = self._build_files_list(folder_data)
                    self._insert_folder_files(
                        folder_id, company, site_name, site_mgmt, folder_name, files_list
                    )

        # 기본 태그 스타일
        self.tree.tag_configure("ghost",        foreground="#999999")
        self.tree.tag_configure("company_bold", font=("맑은 고딕", 10, "bold"))
        self.tree.tag_configure("site_bold",    font=("맑은 고딕", 10, "bold"), foreground="#2C3E50")
        self.tree.tag_configure("folder_normal",font=("맑은 고딕", 9))
        self.tree.tag_configure("file_normal",  font=("맑은 고딕", 9))
        # 카테고리 태그 스타일
        self.tree.tag_configure("cat_group",      font=("맑은 고딕", 9, "bold"), foreground="#1a56db")
        self.tree.tag_configure("cat_station",    font=("맑은 고딕", 9),         foreground="#374151")
        self.tree.tag_configure("cat_unassigned", font=("맑은 고딕", 9, "italic"),foreground="#9ca3af")
        self.tree.tag_configure("file_unassigned",foreground="#9ca3af")

        # 자동 확장 (재귀: 카테고리 계층 포함 모든 레벨 확장)
        def _expand(item, depth=0):
            if depth > 10:
                return
            self.tree.item(item, open=True)
            for child in self.tree.get_children(item):
                _expand(child, depth + 1)

        for item in self.tree.get_children():
            _expand(item)

    # ======================================================
    # 트리 파일 목록 헬퍼 (카테고리 그룹화)
    # ======================================================

    def _build_files_list(self, folder_data):
        """폴더 데이터에서 (정렬키, filename, file_cfg) 리스트 생성 (로거번호/__order__ 기준)"""
        files_list = []
        for filename, file_cfg in folder_data.items():
            if filename.startswith("__") or not filename.lower().endswith(".csv"):
                continue
            logger_num = file_cfg.get("__logger_number__", "")
            if logger_num in ("", None):
                order = file_cfg.get("__order__", 9999)
                files_list.append((order, filename, file_cfg))
            else:
                try:
                    files_list.append((int(logger_num), filename, file_cfg))
                except (ValueError, TypeError):
                    files_list.append((file_cfg.get("__order__", 9999), filename, file_cfg))
        files_list.sort(key=lambda x: (x[0], x[1]))
        return files_list

    def _seed_by_cat_from_mgmt(self, by_cat, station_groups, stations):
        """management.json 에만 있고 배정 로거가 없는 대·소분류도 트리에 표시되도록 빈 슬롯을 채운다."""
        grp_map = {
            g.get("id"): g
            for g in station_groups
            if isinstance(g, dict) and g.get("id")
        }
        group_ids = set(grp_map.keys())
        sorted_groups = sorted(
            [g for g in station_groups if isinstance(g, dict)],
            key=lambda g: (
                g.get("order") if g.get("order") is not None else 999,
                str(g.get("id") or ""),
            ),
        )
        for g in sorted_groups:
            gid = g.get("id") or ""
            go = g.get("order") if g.get("order") is not None else 999
            gname = (g.get("name") or "").strip()
            grp_key = (go, gid, gname)
            if grp_key not in by_cat:
                by_cat[grp_key] = {}
            subs = sorted(
                [s for s in stations if isinstance(s, dict) and (s.get("group_id") or "") == gid],
                key=lambda s: (
                    s.get("order") if s.get("order") is not None else 999,
                    str(s.get("id") or ""),
                ),
            )
            for s in subs:
                sid = s.get("id") or ""
                so = s.get("order") if s.get("order") is not None else 999
                sname = (s.get("name") or "").strip() or str(sid)
                st_key = (so, sid, sname)
                if st_key not in by_cat[grp_key]:
                    by_cat[grp_key][st_key] = []

        ungrouped = sorted(
            [
                s
                for s in stations
                if isinstance(s, dict) and (s.get("group_id") or "") not in group_ids
            ],
            key=lambda s: (
                s.get("order") if s.get("order") is not None else 999,
                str(s.get("id") or ""),
            ),
        )
        if ungrouped:
            grp_key = (999, "", "")
            if grp_key not in by_cat:
                by_cat[grp_key] = {}
            for s in ungrouped:
                sid = s.get("id") or ""
                so = s.get("order") if s.get("order") is not None else 999
                sname = (s.get("name") or "").strip() or str(sid)
                st_key = (so, sid, sname)
                if st_key not in by_cat[grp_key]:
                    by_cat[grp_key][st_key] = []

    def _insert_files_by_category(self, parent_id, company, site_name, site_mgmt, all_files):
        """카테고리가 설정된 현장: 폴더 레벨 없이 parent_id 바로 아래에
        대분류 → 소분류 → 파일 구조로 삽입.
        all_files: [(folder_name, sort_key, filename, file_cfg), ...]
        """
        station_groups = [g for g in site_mgmt.get("station_groups", []) if isinstance(g, dict)]
        stations       = [s for s in site_mgmt.get("stations",       []) if isinstance(s, dict)]
        grp_map        = {g["id"]: g for g in station_groups}
        st_map         = {s["id"]: s for s in stations}
        assignments    = site_mgmt.get("assignments", {})

        by_cat    = {}
        unassigned = []

        for folder_name, sort_key, filename, file_cfg in all_files:
            sid = assignments.get(f"{folder_name}/{filename}", "")
            if sid and sid in st_map:
                st    = st_map[sid]
                gid   = st.get("group_id", "")
                grp   = grp_map.get(gid, {}) if gid else {}
                go    = grp.get("order", 999) if grp else 999
                gname = grp.get("name",  "")  if grp else ""
                so    = st.get("order", 999)
                sname = st.get("name",  "")
                grp_key = (go, gid or "", gname)
                st_key  = (so, sid, sname)
                by_cat.setdefault(grp_key, {}).setdefault(st_key, []).append(
                    (sort_key, folder_name, filename, file_cfg)
                )
            else:
                unassigned.append((sort_key, folder_name, filename, file_cfg))

        self._seed_by_cat_from_mgmt(by_cat, station_groups, stations)

        for grp_key in sorted(by_cat.keys()):
            go, gid, gname = grp_key
            st_dict = by_cat[grp_key]
            grp_cnt = sum(len(v) for v in st_dict.values())

            if gname:
                grp_node = self.tree.insert(
                    parent_id, "end",
                    text=f"{gname}  ({grp_cnt})",
                    values=("", "", "cat_group", company, site_name, "", "", ""),
                    tags=("cat_group",)
                )
            else:
                grp_node = parent_id

            for st_key in sorted(st_dict.keys()):
                so, st_id, st_name = st_key
                files = st_dict[st_key]
                st_node = self.tree.insert(
                    grp_node, "end",
                    text=f"{st_name}  ({len(files)})",
                    values=("", "", "cat_station", company, site_name, "", "", ""),
                    tags=("cat_station",)
                )
                for _sk, folder_name, filename, file_cfg in files:
                    self._insert_file_node(
                        st_node, company, site_name, folder_name, filename, file_cfg, registered=True
                    )

        if unassigned:
            ung_node = self.tree.insert(
                parent_id, "end",
                text=f"미배정  ({len(unassigned)})",
                values=("", "", "cat_unassigned", company, site_name, "", "", ""),
                tags=("cat_unassigned",)
            )
            for _sk, folder_name, filename, file_cfg in unassigned:
                self._insert_file_node(
                    ung_node, company, site_name, folder_name, filename, file_cfg, registered=False
                )

    def _insert_folder_files(self, folder_id, company, site_name, site_mgmt, folder_name, files_list):
        """
        파일을 카테고리(대분류→소분류) 기준으로 그룹화하여 트리에 삽입.
        현장에 소분류(station)가 없으면 기존 flat 방식으로 표시.

        site_mgmt: management.json의 현장 관리 데이터 dict (없으면 빈 dict)
        """
        stations = [s for s in site_mgmt.get("stations", []) if isinstance(s, dict)]
        if not stations:
            # 소분류 없음 → 기존 flat 방식
            for _k, filename, file_cfg in files_list:
                self._insert_file_node(folder_id, company, site_name, folder_name, filename, file_cfg)
            return

        station_groups = [g for g in site_mgmt.get("station_groups", []) if isinstance(g, dict)]
        grp_map     = {g["id"]: g for g in station_groups}
        st_map      = {s["id"]: s for s in stations}
        assignments = site_mgmt.get("assignments", {})

        # 파일을 카테고리별로 분류
        # by_cat: (grp_order, grp_id, grp_name) → {(st_order, st_id, st_name): [files]}
        by_cat = {}
        unassigned = []

        for sort_key, filename, file_cfg in files_list:
            sid = assignments.get(f"{folder_name}/{filename}", "")
            if sid and sid in st_map:
                st = st_map[sid]
                gid   = st.get("group_id", "")
                grp   = grp_map.get(gid, {}) if gid else {}
                go    = grp.get("order", 999) if grp else 999
                gname = grp.get("name", "")   if grp else ""
                so    = st.get("order", 999)
                sname = st.get("name", "")
                grp_key = (go, gid or "", gname)
                st_key  = (so, sid, sname)
                by_cat.setdefault(grp_key, {}).setdefault(st_key, []).append(
                    (sort_key, filename, file_cfg)
                )
            else:
                unassigned.append((sort_key, filename, file_cfg))

        self._seed_by_cat_from_mgmt(by_cat, station_groups, stations)

        # 대분류 기준 정렬 출력
        for grp_key in sorted(by_cat.keys()):
            go, gid, gname = grp_key
            st_dict = by_cat[grp_key]
            grp_cnt = sum(len(v) for v in st_dict.values())

            if gname:
                grp_node = self.tree.insert(
                    folder_id, "end",
                    text=f"{gname}  ({grp_cnt})",
                    values=("", "", "cat_group", company, site_name, folder_name, "", ""),
                    tags=("cat_group",)
                )
            else:
                # 대분류 없는 소분류 → 폴더 직접 아래
                grp_node = folder_id

            for st_key in sorted(st_dict.keys()):
                so, st_id, st_name = st_key
                files = st_dict[st_key]
                st_node = self.tree.insert(
                    grp_node, "end",
                    text=f"{st_name}  ({len(files)})",
                    values=("", "", "cat_station", company, site_name, folder_name, "", ""),
                    tags=("cat_station",)
                )
                for _k, filename, file_cfg in files:
                    self._insert_file_node(
                        st_node, company, site_name, folder_name, filename, file_cfg, registered=True
                    )

        # 미배정 섹션
        if unassigned:
            ung_node = self.tree.insert(
                folder_id, "end",
                text=f"미배정  ({len(unassigned)})",
                values=("", "", "cat_unassigned", company, site_name, folder_name, "", ""),
                tags=("cat_unassigned",)
            )
            for _k, filename, file_cfg in unassigned:
                self._insert_file_node(
                    ung_node, company, site_name, folder_name, filename, file_cfg, registered=False
                )

    def _insert_file_node(self, parent_id, company, site_name, folder_name, filename, file_cfg,
                          registered=None):
        """단일 파일 노드를 트리에 삽입 (채널 summary 포함)"""
        label_summary  = self.app.tree.get_file_label_summary(company, site_name, folder_name, filename)
        battery_value  = self.app.battery_cache.get((company, site_name, folder_name, filename), "")
        file_note      = file_cfg.get("__note__", "")
        is_ghost_file  = file_cfg.get("__is_ghost__", False)

        file_text = f"[Ghost] {filename}" if is_ghost_file else filename
        file_tags = ["file_normal"]
        if is_ghost_file:
            file_tags.append("ghost")
        if registered is False:
            file_tags.append("file_unassigned")

        file_id = self.tree.insert(
            parent_id, "end",
            text=file_text,
            values=(file_note, battery_value, "file", company, site_name, folder_name, filename, str(is_ghost_file)),
            tags=tuple(file_tags)
        )
        if label_summary:
            self.tree.insert(
                file_id, "end",
                text="  " + label_summary,
                values=("", "", "summary", "", "", "", ""),
            )

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
        self.status_label.config(text=message, fg="#2C3E50")
        self.statusbar_label.config(text=message, fg="#ECF0F1")
        if progress is not None:
            self.update_progress(progress)
        self.root.update_idletasks()
    
    def set_buttons_enabled(self, enabled):
        """모든 버튼 활성화/비활성화 (변환 중일 때 중지 버튼 활성화)"""
        state = "normal" if enabled else "disabled"
        for btn in self.buttons:
            if isinstance(btn, tk.Button):
                if enabled:
                    # 원래 색상으로 복원
                    if btn.cget("text") == "변환 실행":
                        btn.config(bg="#3498DB", state=state)
                    else:
                        btn.config(bg="#95A5A6", state=state)
                else:
                    # 비활성화 시 회색
                    btn.config(bg="#BDC3C7", state=state, cursor="arrow")
            else:
                btn.config(state=state)

        # 변환 중지 버튼: 변환 중일 때만 활성화
        if hasattr(self, "stop_convert_btn"):
            self.stop_convert_btn.config(
                state="normal" if not enabled else "disabled",
                cursor="hand2" if not enabled else "arrow"
            )

        self.company_combo.config(state="readonly" if enabled else "disabled")

        if enabled:
            self.status_label.config(text="준비 완료", fg="#27AE60")
            self.statusbar_label.config(text="준비 완료", fg="#ECF0F1")
            self.reset_progress()
        else:
            self.status_label.config(text="변환 중...", fg="#3498DB")
            self.statusbar_label.config(text="변환 작업 진행 중...", fg="#ECF0F1")

    # ======================================================
    # 트리뷰 이벤트
    # ======================================================
    def _on_company_change(self, event=None):
        self.current_company = self.company_var.get()
        self.app.logger.log(f"[UI] 업체 변경: {self.current_company}")
        self.refresh_tree()

    def _on_tree_double_click(self, event=None):
        item = self.tree.focus()
        if not item:
            return

        node_type = self.tree.set(item, "type")
        company = self.tree.set(item, "company")
        site = self.tree.set(item, "site")
        folder = self.tree.set(item, "folder")
        filename = self.tree.set(item, "filename")

        if node_type == "summary":
            return

        if node_type == "file":
            self.app.logger.log(
                f"[UI] 파일 더블클릭: {company}/{site}/{folder}/{filename}"
            )
            self.app.open_channel_settings(company, site, folder, filename)

    def _on_right_click(self, event):
        # 우클릭 메뉴 표시
        self.context_menu.popup(event)
    
    # ======================================================
    # 파일 순서 변경 (위/아래로 이동)
    # ======================================================
    def _move_file_up(self):
        """파일을 위로 이동"""
        item = self.tree.focus()
        if not item:
            return
        
        node_type = self.tree.set(item, "type")
        if node_type != "file":
            return
        
        company = self.tree.set(item, "company")
        site = self.tree.set(item, "site")
        folder = self.tree.set(item, "folder")
        filename = self.tree.set(item, "filename")
        
        # 폴더 ID 찾기
        folder_id = self.tree.parent(item)
        if not folder_id:
            return
        
        # 폴더 내 모든 파일 노드 가져오기
        file_items = []
        for child in self.tree.get_children(folder_id):
            child_type = self.tree.set(child, "type")
            if child_type == "file":
                child_filename = self.tree.set(child, "filename")
                file_items.append(child_filename)
        
        # 현재 파일의 인덱스 찾기
        try:
            current_index = file_items.index(filename)
        except ValueError:
            return
        
        # 이미 맨 위면 이동 불가
        if current_index == 0:
            messagebox.showinfo("안내", "이미 맨 위에 있습니다.")
            return
        
        # 위로 이동 (인덱스 교환)
        file_items[current_index], file_items[current_index - 1] = \
            file_items[current_index - 1], file_items[current_index]
        
        # __order__ 값 재조정
        file_order_list = [(name, idx) for idx, name in enumerate(file_items)]
        
        try:
            success = self.app.tree.reorder_files(company, site, folder, file_order_list)
            if success:
                self.refresh_tree()
                # 이동한 파일 다시 선택
                for child in self.tree.get_children(folder_id):
                    if self.tree.set(child, "filename") == filename:
                        self.tree.selection_set(child)
                        self.tree.focus(child)
                        self.tree.see(child)
                        break
                self.app.logger.log(f"[UI] 파일 위로 이동: {company}/{site}/{folder}/{filename}")
        except Exception as e:
            self.app.logger.log(f"[UI] 파일 순서 변경 실패: {e}", level="ERROR")
            messagebox.showerror("순서 변경 실패", f"파일 순서 변경 중 문제가 발생했습니다.\n\n오류 내용: {e}")
    
    def _move_file_down(self):
        """파일을 아래로 이동"""
        item = self.tree.focus()
        if not item:
            return
        
        node_type = self.tree.set(item, "type")
        if node_type != "file":
            return
        
        company = self.tree.set(item, "company")
        site = self.tree.set(item, "site")
        folder = self.tree.set(item, "folder")
        filename = self.tree.set(item, "filename")
        
        # 폴더 ID 찾기
        folder_id = self.tree.parent(item)
        if not folder_id:
            return
        
        # 폴더 내 모든 파일 노드 가져오기
        file_items = []
        for child in self.tree.get_children(folder_id):
            child_type = self.tree.set(child, "type")
            if child_type == "file":
                child_filename = self.tree.set(child, "filename")
                file_items.append(child_filename)
        
        # 현재 파일의 인덱스 찾기
        try:
            current_index = file_items.index(filename)
        except ValueError:
            return
        
        # 이미 맨 아래면 이동 불가
        if current_index == len(file_items) - 1:
            messagebox.showinfo("안내", "이미 맨 아래에 있습니다.")
            return
        
        # 아래로 이동 (인덱스 교환)
        file_items[current_index], file_items[current_index + 1] = \
            file_items[current_index + 1], file_items[current_index]
        
        # __order__ 값 재조정
        file_order_list = [(name, idx) for idx, name in enumerate(file_items)]
        
        try:
            success = self.app.tree.reorder_files(company, site, folder, file_order_list)
            if success:
                self.refresh_tree()
                # 이동한 파일 다시 선택
                for child in self.tree.get_children(folder_id):
                    if self.tree.set(child, "filename") == filename:
                        self.tree.selection_set(child)
                        self.tree.focus(child)
                        self.tree.see(child)
                        break
                self.app.logger.log(f"[UI] 파일 아래로 이동: {company}/{site}/{folder}/{filename}")
        except Exception as e:
            self.app.logger.log(f"[UI] 파일 순서 변경 실패: {e}", level="ERROR")
            messagebox.showerror("순서 변경 실패", f"파일 순서 변경 중 문제가 발생했습니다.\n\n오류 내용: {e}")

    # ======================================================
    # 삭제 기능 (Site 레벨 포함)
    # ======================================================
    def _delete_selected(self):
        """선택된 항목 삭제 (현장, 폴더 또는 파일)"""
        item = self.tree.focus()
        if not item:
            messagebox.showwarning("안내", "삭제할 항목을 먼저 선택해주세요.")
            return
        
        node_type = self.tree.set(item, "type")
        company = self.tree.set(item, "company")
        site = self.tree.set(item, "site")
        folder = self.tree.set(item, "folder")
        filename = self.tree.set(item, "filename")
        
        if node_type == "summary":
            messagebox.showwarning("안내", "요약 정보는 삭제할 수 없습니다.")
            return
        
        # 확인 메시지
        if node_type == "site":
            confirm_msg = f"현장 '{site}'를 삭제하시겠습니까?\n\n주의: 이 현장의 모든 폴더와 파일 설정이 함께 삭제됩니다.\n이 작업은 되돌릴 수 없습니다."
            if not messagebox.askyesno("삭제 확인", confirm_msg):
                return
            
            try:
                self.app.tree.delete_site(company, site)
                self.app.logger.log(f"[UI] 현장 삭제: {company}/{site}")
                self.refresh_tree()
                messagebox.showinfo("삭제 완료", f"현장 '{site}'가 성공적으로 삭제되었습니다.")
            except Exception as e:
                self.app.logger.log(f"[UI] 현장 삭제 실패: {e}", level="ERROR")
                messagebox.showerror("삭제 실패", f"현장 삭제 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.")
        
        elif node_type == "folder":
            confirm_msg = f"폴더 '{folder}'를 삭제하시겠습니까?\n\n주의: 이 폴더의 모든 파일 설정이 함께 삭제됩니다.\n이 작업은 되돌릴 수 없습니다."
            if not messagebox.askyesno("삭제 확인", confirm_msg):
                return
            
            try:
                self.app.tree.delete_folder(company, site, folder)
                self.app.logger.log(f"[UI] 폴더 삭제: {company}/{site}/{folder}")
                self.refresh_tree()
                messagebox.showinfo("삭제 완료", f"폴더 '{folder}'가 성공적으로 삭제되었습니다.")
            except Exception as e:
                self.app.logger.log(f"[UI] 폴더 삭제 실패: {e}", level="ERROR")
                messagebox.showerror("삭제 실패", f"폴더 삭제 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.")
        
        elif node_type == "file":
            confirm_msg = f"파일 '{filename}'을(를) 삭제하시겠습니까?\n\n주의: 이 파일의 모든 설정이 삭제됩니다.\n이 작업은 되돌릴 수 없습니다."
            if not messagebox.askyesno("삭제 확인", confirm_msg):
                return
            
            try:
                self.app.tree.delete_file(company, site, folder, filename)
                self.app.logger.log(f"[UI] 파일 삭제: {company}/{site}/{folder}/{filename}")
                self.refresh_tree()
                messagebox.showinfo("삭제 완료", f"파일 '{filename}'이(가) 성공적으로 삭제되었습니다.")
            except Exception as e:
                self.app.logger.log(f"[UI] 파일 삭제 실패: {e}", level="ERROR")
                messagebox.showerror("삭제 실패", f"파일 삭제 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.")

    # ======================================================
    # 비고 편집
    # ======================================================
    def _edit_note(self):
        """비고 편집 다이얼로그"""
        item = self.tree.focus()
        if not item:
            messagebox.showwarning("안내", "편집할 항목을 먼저 선택해주세요.")
            return
        
        node_type = self.tree.set(item, "type")
        company = self.tree.set(item, "company")
        site = self.tree.set(item, "site")
        folder = self.tree.set(item, "folder")
        filename = self.tree.set(item, "filename")
        
        if node_type == "summary":
            messagebox.showwarning("안내", "요약 정보는 편집할 수 없습니다.")
            return
        
        # 현재 비고 가져오기
        current_note = self.tree.set(item, "note") or ""
        
        # 비고 편집 다이얼로그
        new_note = simpledialog.askstring(
            "비고 편집",
            f"{node_type}의 비고를 입력하세요:",
            initialvalue=current_note,
            parent=self.root
        )
        
        if new_note is None:  # 취소
            return
        
        new_note = new_note.strip()
        
        try:
            if node_type == "site":
                self.app.tree.set_site_note(company, site, new_note)
                self.app.logger.log(f"[UI] 현장 비고 수정: {company}/{site}")
            elif node_type == "folder":
                self.app.tree.set_folder_note(company, site, folder, new_note)
                self.app.logger.log(f"[UI] 폴더 비고 수정: {company}/{site}/{folder}")
            elif node_type == "file":
                self.app.tree.set_file_note(company, site, folder, filename, new_note)
                self.app.logger.log(f"[UI] 파일 비고 수정: {company}/{site}/{folder}/{filename}")
            
            self.refresh_tree()
            messagebox.showinfo("수정 완료", "비고가 성공적으로 수정되었습니다.")
        except Exception as e:
            self.app.logger.log(f"[UI] 비고 수정 실패: {e}", level="ERROR")
            messagebox.showerror("수정 실패", f"비고 수정 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.")

    # ======================================================
    # 자동 변환 시각 (스케줄러)
    # ======================================================
    def _open_auto_convert_schedule_dialog(self):
        """config.json __scheduler__.auto_convert_minutes 편집."""
        mins = self.app.config.get_auto_convert_minutes()
        initial = ", ".join(str(m) for m in mins) if mins else ""

        dlg = tk.Toplevel(self.root)
        dlg.title("자동 변환 시각 설정")
        dlg.geometry("480x270")
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg="white")
        try:
            self._center_popup_on_parent(dlg)
        except Exception:
            pass

        tk.Label(
            dlg,
            text=(
                "매 시간 자동 변환(convert_now)이 실행될 '분'을 설정합니다 (0~59).\n"
                "예: 5, 25, 45 → 각 시각 05분·25분·45분에 실행됩니다."
            ),
            justify="left",
            bg="white",
            wraplength=440,
            font=("맑은 고딕", 9),
        ).pack(anchor="w", padx=14, pady=(14, 8))

        var = tk.StringVar(value=initial)
        tk.Label(dlg, text="분 목록 (쉼표로 구분)", bg="white", font=("맑은 고딕", 9)).pack(
            anchor="w", padx=14
        )
        entry = tk.Entry(dlg, textvariable=var, font=("맑은 고딕", 10), width=52)
        entry.pack(fill="x", padx=14, pady=(4, 6))

        tk.Label(
            dlg,
            text="비워 두고 확인하면 자동 변환이 꺼집니다 (수동 「변환 실행」만 동작).",
            fg="#7F8C8D",
            bg="white",
            font=("맑은 고딕", 8),
        ).pack(anchor="w", padx=14, pady=(0, 8))

        btn_bar = tk.Frame(dlg, bg="white")
        btn_bar.pack(fill="x", padx=14, pady=(6, 14))

        def _parse_minutes(text: str) -> tuple[list[int] | None, str]:
            t = (text or "").strip().replace("，", ",")
            if not t:
                return [], ""
            parts = [p.strip() for p in t.split(",") if p.strip()]
            out: list[int] = []
            for p in parts:
                try:
                    v = int(p)
                except ValueError:
                    return None, f"정수가 아닙니다: {p!r}"
                if v < 0 or v > 59:
                    return None, f"분은 0~59만 가능합니다 ({v})."
                out.append(v)
            return sorted(set(out)), ""

        def save():
            parsed, err = _parse_minutes(var.get())
            if parsed is None:
                messagebox.showerror("입력 오류", err, parent=dlg)
                return
            ok, msg = self.app.config.set_auto_convert_minutes(parsed)
            if not ok:
                messagebox.showerror("저장 실패", msg or "알 수 없는 오류", parent=dlg)
                return
            self.app.logger.log(
                f"[UI] 자동변환 시각 저장: {parsed if parsed else '없음 (자동변환 끔)'}"
            )
            if parsed:
                tip = f"매 시각 {', '.join(map(str, parsed))} 분에 자동 변환합니다."
            else:
                tip = "자동 변환이 꺼졌습니다 (분 목록 없음)."
            messagebox.showinfo(
                "저장됨",
                tip + "\nconfig.json에 저장되었습니다.",
                parent=dlg,
            )
            dlg.destroy()

        tk.Button(
            btn_bar,
            text="기본값 (5, 25, 45)",
            command=lambda: var.set("5, 25, 45"),
            font=("맑은 고딕", 8),
            bg="#ECF0F1",
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btn_bar,
            text="확인",
            command=save,
            font=("맑은 고딕", 9, "bold"),
            bg="#3498DB",
            fg="white",
            width=10,
        ).pack(side="right", padx=(6, 0))

        tk.Button(btn_bar, text="취소", command=dlg.destroy, width=8).pack(side="right")

    # ======================================================
    # 업체 관리
    # ======================================================
    def _manage_companies(self):
        """업체 관리 팝업 열기"""
        CompanyManagementUI(self.root, self.app)
    
    # ======================================================
    # 로거파일 등록 (미등록 파일 UI로 이동)
    # ======================================================
    def _register_logger_files(self):
        """로거파일 등록 - 폴더 선택 후 미등록 파일 UI로 이동"""
        folder_path = filedialog.askdirectory(title="로거파일이 있는 폴더 선택")
        if not folder_path:
            return
        
        # 미등록 파일 UI 열기 (선택한 폴더 경로 전달)
        unreg_ui = UnregisteredFilesUI(self.root, self.app, target_folder_path=folder_path)
        
        self.app.logger.log(f"[UI] 로거파일 등록 시작: {folder_path}")

    # ======================================================
    # 현장 추가
    # ======================================================
    def _add_site(self):
        """현장 추가 다이얼로그"""
        company = self._popup_select_company()
        if not company:
            return
        
        # 커스텀 현장 추가 팝업
        popup = tk.Toplevel(self.root)
        popup.title("현장 추가")
        popup.geometry("450x200")
        popup.grab_set()
        popup.resizable(False, False)
        
        # 메인 창 위치 기준으로 팝업 위치 설정
        self._center_popup_on_parent(popup)
        
        # 배경색 설정
        popup.configure(bg="white")
        
        # 헤더
        header = tk.Frame(popup, bg="#2C3E50", height=40)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="현장 추가",
            font=("맑은 고딕", 11, "bold"),
            bg="#2C3E50",
            fg="white"
        ).pack(side="left", padx=15, pady=8)
        
        # 메인 영역
        main = tk.Frame(popup, bg="white")
        main.pack(fill="both", expand=True, padx=20, pady=20)
        
        tk.Label(
            main,
            text=f"업체: {company}",
            font=("맑은 고딕", 9),
            bg="white",
            fg="#2C3E50"
        ).pack(anchor="w", pady=(0, 10))
        
        tk.Label(
            main,
            text="현장 이름:",
            font=("맑은 고딕", 9, "bold"),
            bg="white",
            fg="#2C3E50"
        ).pack(anchor="w", pady=(0, 5))
        
        site_var = tk.StringVar()
        entry = tk.Entry(
            main,
            textvariable=site_var,
            font=("맑은 고딕", 10),
            width=30,
            relief="solid",
            borderwidth=1
        )
        entry.pack(fill="x", pady=(0, 15))
        entry.focus()
        
        # Enter 키로 확인
        def on_enter(event):
            confirm()
        entry.bind("<Return>", on_enter)
        
        selected = {"value": None}
        
        def confirm():
            site_name = site_var.get().strip()
            if not site_name:
                messagebox.showwarning("안내", "현장 이름을 입력해주세요.", parent=popup)
                return
            
            selected["value"] = site_name
            popup.destroy()
        
        # 버튼 영역
        button_frame = tk.Frame(main, bg="white")
        button_frame.pack(fill="x", pady=(10, 0))
        
        confirm_btn = tk.Button(
            button_frame,
            text="확인",
            command=confirm,
            font=("맑은 고딕", 9),
            bg="#27AE60",
            fg="white",
            activebackground="#229954",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=10,
            pady=5,
            cursor="hand2"
        )
        confirm_btn.pack(side="right", padx=(5, 0))
        
        cancel_btn = tk.Button(
            button_frame,
            text="취소",
            command=popup.destroy,
            font=("맑은 고딕", 9),
            bg="#95A5A6",
            fg="white",
            activebackground="#7F8C8D",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=10,
            pady=5,
            cursor="hand2"
        )
        cancel_btn.pack(side="right")
        
        popup.wait_window()
        site_name = selected["value"]
        
        if not site_name:
            return
        
        try:
            self.app.tree.add_site(company, site_name)
            self.app.logger.log(f"[UI] 현장 추가 완료 → {company}/{site_name}")
            self.refresh_tree()
            messagebox.showinfo("추가 완료", f"현장 '{site_name}'가 성공적으로 추가되었습니다.")
        except Exception as e:
            self.app.logger.log(f"[UI] 현장 추가 실패: {e}", level="ERROR")
            messagebox.showerror("추가 실패", f"현장 추가 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.")
    
    def _check_update(self):
        """업데이트 선택 → EXE 업데이트 또는 웹 패치"""
        dlg = tk.Toplevel(self.root)
        dlg.title("업데이트")
        dlg.geometry("360x180")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center_popup_on_parent(dlg)

        tk.Label(
            dlg,
            text="어떤 업데이트를 진행할까요?",
            font=("맑은 고딕", 11, "bold"),
            fg="#2C3E50"
        ).pack(pady=(20, 6))

        tk.Label(
            dlg,
            text="프로그램 업데이트: GitHub에서 새 EXE 버전 확인\n"
                 "웹 패치: server.py · 화면(HTML) 소스 최신화",
            font=("맑은 고딕", 9),
            fg="#666",
            justify="center"
        ).pack(pady=(0, 16))

        btn_frame = tk.Frame(dlg)
        btn_frame.pack()

        def on_exe():
            dlg.destroy()
            self._start_exe_update_check()

        def on_web():
            dlg.destroy()
            self._start_web_patch()

        tk.Button(
            btn_frame,
            text="프로그램 업데이트",
            command=on_exe,
            font=("맑은 고딕", 10, "bold"),
            bg="#9B59B6", fg="white",
            activebackground="#8E44AD", activeforeground="white",
            relief="flat", padx=14, pady=8, cursor="hand2"
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame,
            text="웹 패치",
            command=on_web,
            font=("맑은 고딕", 10, "bold"),
            bg="#2980B9", fg="white",
            activebackground="#2471A3", activeforeground="white",
            relief="flat", padx=14, pady=8, cursor="hand2"
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame,
            text="취소",
            command=dlg.destroy,
            font=("맑은 고딕", 10),
            bg="#ECF0F1", fg="#555",
            relief="flat", padx=14, pady=8, cursor="hand2"
        ).pack(side="left", padx=6)

    def _start_exe_update_check(self):
        """기존 EXE 업데이트 확인 흐름"""
        import threading

        progress_dialog = tk.Toplevel(self.root)
        progress_dialog.title("업데이트 확인")
        progress_dialog.geometry("300x100")
        progress_dialog.resizable(False, False)
        progress_dialog.transient(self.root)
        progress_dialog.grab_set()
        self._center_popup_on_parent(progress_dialog)

        tk.Label(
            progress_dialog,
            text="업데이트를 확인하는 중...",
            font=("맑은 고딕", 10)
        ).pack(pady=20)

        from tkinter import ttk
        progress = ttk.Progressbar(progress_dialog, mode='indeterminate', length=200)
        progress.pack(pady=10)
        progress.start(10)

        def check_thread():
            try:
                from utils.update_manager import UpdateManager
                update_manager = UpdateManager(self.logger)
                update_info = update_manager.check_for_updates()
                self.root.after(0, lambda: self._handle_update_result(
                    progress_dialog, update_manager, update_info
                ))
            except Exception as exc:
                self.logger.log(f"업데이트 확인 실패: {exc}", level="ERROR")
                error_msg = str(exc)
                self.root.after(0, lambda msg=error_msg: self._show_update_error(progress_dialog, msg))

        threading.Thread(target=check_thread, daemon=True).start()

    def _start_web_patch(self):
        """웹 패치 방식 선택 — git 또는 GitHub ZIP"""
        import threading, shutil, subprocess
        from pathlib import Path

        # git 설치 여부 자동 확인
        git_available = False
        try:
            r = subprocess.run(['git', '--version'], capture_output=True, timeout=5)
            git_available = (r.returncode == 0)
        except Exception:
            pass

        if git_available:
            self._start_web_patch_git()
        else:
            self._start_web_patch_zip()

    def _start_web_patch_git(self):
        """웹 패치 — git pull + monitoring/ 복사"""
        import threading

        # 저장소 경로 확인
        repo_path = self.app.config.get_web_patch_repo_path()
        if not repo_path:
            repo_path = filedialog.askdirectory(
                title="git 저장소 폴더 선택 (Convert_pro3 소스 루트)",
                parent=self.root
            )
            if not repo_path:
                return
            self.app.config.set_web_patch_repo_path(repo_path)

        # 진행 다이얼로그
        dlg = tk.Toplevel(self.root)
        dlg.title("웹 패치")
        dlg.geometry("380x160")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center_popup_on_parent(dlg)

        header = tk.Frame(dlg, bg="#2980B9", height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="웹 파일 최신화 중...",
                 font=("맑은 고딕", 11, "bold"), bg="#2980B9", fg="white").pack(pady=12)

        status_var = tk.StringVar(value="git pull 실행 중...")
        tk.Label(dlg, textvariable=status_var,
                 font=("맑은 고딕", 9), fg="#444").pack(pady=10)

        from tkinter import ttk
        prog = ttk.Progressbar(dlg, mode='indeterminate', length=320)
        prog.pack(pady=4)
        prog.start(10)

        def patch_thread():
            try:
                result = self.app.do_web_patch(
                    repo_path,
                    status_cb=lambda msg: dlg.after(0, lambda m=msg: status_var.set(m))
                )
                dlg.after(0, lambda: _finish(result))
            except Exception as e:
                dlg.after(0, lambda err=str(e): _error(err))

        def _finish(result):
            prog.stop()
            dlg.destroy()
            if result.get('server_changed'):
                self.show_web_restart_banner()
                messagebox.showinfo(
                    "웹 패치 완료",
                    "패치 완료!\n\n"
                    "server.py 가 변경되었습니다.\n"
                    "[웹 재시작] 버튼을 눌러 반영하세요.\n\n"
                    "templates/ 변경은 브라우저 새로고침으로 즉시 반영됩니다.",
                    parent=self.root
                )
            elif result.get('template_changed'):
                messagebox.showinfo(
                    "웹 패치 완료",
                    "패치 완료!\n\n"
                    "templates/ 가 변경되었습니다.\n"
                    "브라우저를 새로고침하면 즉시 반영됩니다.",
                    parent=self.root
                )
            elif result.get('no_change'):
                messagebox.showinfo("웹 패치", "이미 최신 상태입니다.", parent=self.root)
            else:
                messagebox.showinfo("웹 패치 완료", "패치가 완료되었습니다.", parent=self.root)

        def _error(err):
            prog.stop()
            dlg.destroy()
            messagebox.showerror(
                "웹 패치 실패",
                f"오류가 발생했습니다.\n\n{err}\n\n"
                "git 설치 여부와 저장소 경로를 확인하세요.",
                parent=self.root
            )

        threading.Thread(target=patch_thread, daemon=True).start()

    def _start_web_patch_zip(self):
        """웹 패치 — git 없이 GitHub ZIP 다운로드로 monitoring/ 최신화"""
        import threading

        dlg = tk.Toplevel(self.root)
        dlg.title("웹 패치 (ZIP)")
        dlg.geometry("400x180")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        self._center_popup_on_parent(dlg)

        header = tk.Frame(dlg, bg="#27AE60", height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="웹 파일 최신화 중... (ZIP)",
                 font=("맑은 고딕", 11, "bold"), bg="#27AE60", fg="white").pack(pady=12)

        status_var = tk.StringVar(value="GitHub에서 최신 파일 다운로드 중...")
        tk.Label(dlg, textvariable=status_var,
                 font=("맑은 고딕", 9), fg="#444").pack(pady=10)

        from tkinter import ttk
        prog = ttk.Progressbar(dlg, mode='indeterminate', length=340)
        prog.pack(pady=4)
        prog.start(10)

        def patch_thread():
            try:
                result = self.app.do_web_patch_zip(
                    status_cb=lambda msg: dlg.after(0, lambda m=msg: status_var.set(m))
                )
                dlg.after(0, lambda: _finish(result))
            except Exception as e:
                dlg.after(0, lambda err=str(e): _error(err))

        def _finish(result):
            prog.stop()
            dlg.destroy()
            if result.get('server_changed'):
                self.show_web_restart_banner()
                messagebox.showinfo("웹 패치 완료",
                    "패치 완료!\n\nserver.py가 변경되었습니다.\n"
                    "[웹 재시작] 버튼을 눌러 반영하세요.", parent=self.root)
            elif result.get('template_changed'):
                messagebox.showinfo("웹 패치 완료",
                    "패치 완료!\n\ntemplates/가 변경되었습니다.\n"
                    "브라우저를 새로고침하면 즉시 반영됩니다.", parent=self.root)
            elif result.get('no_change'):
                messagebox.showinfo("웹 패치", "이미 최신 상태입니다.", parent=self.root)
            else:
                messagebox.showinfo("웹 패치 완료", "패치가 완료되었습니다.", parent=self.root)

        def _error(err):
            prog.stop()
            dlg.destroy()
            messagebox.showerror("웹 패치 실패",
                f"오류가 발생했습니다.\n\n{err}", parent=self.root)

        threading.Thread(target=patch_thread, daemon=True).start()

    def _handle_update_result(self, progress_dialog, update_manager, update_info):
        """업데이트 확인 결과 처리 - 완전 자동 모드"""
        progress_dialog.destroy()
        
        if update_info.get('error'):
            messagebox.showwarning(
                "업데이트 확인 실패",
                f"업데이트를 확인할 수 없습니다.\n\n오류: {update_info.get('error')}",
                parent=self.root
            )
            return
        
        if not update_info.get('available'):
            messagebox.showinfo(
                "업데이트 없음",
                f"현재 최신 버전입니다.\n\n버전: {update_manager.current_version}",
                parent=self.root
            )
            return
        
        # 새 버전 발견 시 바로 자동 업데이트 시작
        new_version = update_info['version']
        
        # 간단한 확인 메시지만 표시
        response = messagebox.askyesno(
            "업데이트 발견",
            f"새 버전이 있습니다!\n\n"
            f"현재: {update_manager.current_version}\n"
            f"최신: {new_version}\n\n"
            f"지금 자동으로 업데이트하시겠습니까?\n"
            f"(프로그램이 자동으로 재시작됩니다)",
            parent=self.root
        )
        
        if not response:
            return
        
        # 자동 다운로드 시작
        self._start_auto_update(update_manager, update_info)
    
    def _start_auto_update(self, update_manager, update_info):
        """자동 업데이트 시작"""
        import threading
        import tempfile
        from pathlib import Path
        
        # 다운로드 진행 창
        download_dialog = tk.Toplevel(self.root)
        download_dialog.title("자동 업데이트")
        download_dialog.geometry("400x180")
        download_dialog.resizable(False, False)
        download_dialog.transient(self.root)
        download_dialog.grab_set()
        
        # 중앙 배치
        self._center_popup_on_parent(download_dialog)
        
        # 헤더
        header_frame = tk.Frame(download_dialog, bg="#3498DB", height=60)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="자동 업데이트 중...",
            font=("맑은 고딕", 12, "bold"),
            bg="#3498DB",
            fg="white"
        ).pack(pady=18)
        
        # 내용
        content_frame = tk.Frame(download_dialog, bg="white")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        status_label = tk.Label(
            content_frame,
            text="업데이트 파일을 다운로드하는 중...",
            font=("맑은 고딕", 10),
            bg="white"
        )
        status_label.pack(pady=(0, 10))
        
        from tkinter import ttk
        progress = ttk.Progressbar(
            content_frame,
            mode='determinate',
            length=340
        )
        progress.pack(pady=5)
        
        percent_label = tk.Label(
            content_frame,
            text="0%",
            font=("맑은 고딕", 9),
            fg="gray",
            bg="white"
        )
        percent_label.pack(pady=5)
        
        def update_progress(percent):
            """진행률 업데이트"""
            download_dialog.after(0, lambda: progress.config(value=percent))
            download_dialog.after(0, lambda: percent_label.config(text=f"{percent}%"))
        
        def download_thread():
            """다운로드 스레드"""
            try:
                # 임시 파일 경로
                is_zip = update_info.get('is_zip', False)
                file_extension = '.zip' if is_zip else '.exe'
                temp_file = Path(tempfile.gettempdir()) / f"ConvertPro3_update{file_extension}"
                
                # 다운로드
                success = update_manager.download_update(
                    update_info['download_url'],
                    temp_file,
                    progress_callback=update_progress
                )
                
                if not success:
                    download_dialog.after(0, lambda: self._show_download_error(download_dialog))
                    return
                
                # 다운로드 완료
                download_dialog.after(0, lambda: status_label.config(text="업데이트 적용 중..."))
                download_dialog.after(0, lambda: percent_label.config(text="완료"))
                
                # 업데이터 시작
                if update_manager.start_updater(temp_file, is_zip=is_zip):
                    # 성공 - 프로그램 종료
                    download_dialog.after(0, lambda: self._complete_update(download_dialog))
                else:
                    download_dialog.after(0, lambda: self._show_download_error(download_dialog))
                    
            except Exception as e:
                self.logger.log(f"자동 업데이트 실패: {e}", level="ERROR")
                error_msg = str(e)
                download_dialog.after(0, lambda msg=error_msg: self._show_download_error(download_dialog, msg))
        
        # 다운로드 시작
        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()
    
    def _complete_update(self, dialog):
        """업데이트 완료 - 창 없이 즉시 종료, updater가 재시작"""
        dialog.destroy()
        self.root.quit()  # 즉시 종료 (updater가 교체 후 새 버전으로 재시작)
    
    def _show_download_error(self, dialog, error_msg=""):
        """다운로드 오류 표시"""
        dialog.destroy()
        msg = "업데이트 다운로드에 실패했습니다."
        if error_msg:
            msg += f"\n\n오류: {error_msg}"
        messagebox.showerror("업데이트 실패", msg, parent=self.root)
    
    def _show_update_error(self, progress_dialog, error_msg):
        """업데이트 확인 오류 표시"""
        progress_dialog.destroy()
        messagebox.showerror(
            "오류",
            f"업데이트 확인 중 오류가 발생했습니다.\n\n{error_msg}",
            parent=self.root
        )

    # ======================================================
    # 폴더 추가 (Site 레벨 포함)
    # ======================================================
    def _add_folder(self):
        """폴더 추가 다이얼로그"""
        folder_path = filedialog.askdirectory(title="원본 폴더 선택")
        if not folder_path:
            return

        folder_name = os.path.basename(folder_path.rstrip("/\\"))

        company = self._popup_select_company()
        if not company:
            return

        # 현장 선택
        site = self._popup_select_site(company)
        if not site:
            return

        self.app.tree.add_folder(company, site, folder_name, folder_path)

        csv_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".csv")]
        for csv in csv_files:
            self.app.tree.add_file(company, site, folder_name, csv)

        self.app.logger.log(f"[UI] 폴더 등록 완료 → {company}/{site}/{folder_name}")
        self.app.logger.log(f"[UI] CSV 자동 스캔: {len(csv_files)}개 파일")

        self.refresh_tree()

    def _popup_select_site(self, company):
        """현장 선택 팝업"""
        popup = tk.Toplevel(self.root)
        popup.title("현장 선택")
        popup.geometry("450x250")
        popup.grab_set()
        popup.resizable(False, False)
        
        # 메인 창 위치 기준으로 팝업 위치 설정
        self._center_popup_on_parent(popup)
        
        # 배경색 설정
        popup.configure(bg="white")
        
        # 헤더
        header = tk.Frame(popup, bg="#2C3E50", height=40)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="현장 선택",
            font=("맑은 고딕", 11, "bold"),
            bg="#2C3E50",
            fg="white"
        ).pack(side="left", padx=15, pady=8)
        
        # 메인 영역
        main = tk.Frame(popup, bg="white")
        main.pack(fill="both", expand=True, padx=20, pady=20)

        company_data = self.app.tree.get_company_data(company)
        sites = [k for k in company_data.keys() if not k.startswith("__")]
        
        if not sites:
            # 현장이 없으면 새로 만들기 옵션
            tk.Label(
                main,
                text="등록된 현장이 없습니다.",
                font=("맑은 고딕", 9),
                fg="#E74C3C",
                bg="white"
            ).pack(pady=20)
            
            close_btn = tk.Button(
                main,
                text="닫기",
                command=popup.destroy,
                font=("맑은 고딕", 9),
                bg="#95A5A6",
                fg="white",
                activebackground="#7F8C8D",
                activeforeground="white",
                relief="flat",
                width=10,
                height=1,
                padx=10,
                pady=5,
                cursor="hand2"
            )
            close_btn.pack(pady=10)
            popup.wait_window()
            return None
        
        tk.Label(
            main,
            text=f"업체: {company}",
            font=("맑은 고딕", 9),
            bg="white",
            fg="#2C3E50"
        ).pack(anchor="w", pady=(0, 10))
        
        tk.Label(
            main,
            text="현장 선택:",
            font=("맑은 고딕", 9, "bold"),
            bg="white",
            fg="#2C3E50"
        ).pack(anchor="w", pady=(0, 5))
        
        site_var = tk.StringVar(value=sites[0])
        combo = ttk.Combobox(
            main,
            textvariable=site_var,
            values=sites,
            state="readonly",
            font=("맑은 고딕", 10),
            width=35
        )
        combo.pack(fill="x", pady=(0, 20))

        selected = {"value": None}

        def confirm():
            selected["value"] = site_var.get()
            popup.destroy()

        # 버튼 영역
        button_frame = tk.Frame(main, bg="white")
        button_frame.pack(fill="x")
        
        confirm_btn = tk.Button(
            button_frame,
            text="확인",
            command=confirm,
            font=("맑은 고딕", 9),
            bg="#27AE60",
            fg="white",
            activebackground="#229954",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=10,
            pady=5,
            cursor="hand2"
        )
        confirm_btn.pack(side="right", padx=(5, 0))
        
        cancel_btn = tk.Button(
            button_frame,
            text="취소",
            command=popup.destroy,
            font=("맑은 고딕", 9),
            bg="#95A5A6",
            fg="white",
            activebackground="#7F8C8D",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=10,
            pady=5,
            cursor="hand2"
        )
        cancel_btn.pack(side="right")

        popup.wait_window()
        return selected["value"]
    
    def _open_unregistered_files(self):
        """미등록 파일 관리 UI 열기"""
        UnregisteredFilesUI(self.root, self.app)

    # ======================================================
    # 파일 추가
    # ======================================================


    # ======================================================
    # 유틸리티 함수
    # ======================================================
    def _center_popup_on_parent(self, popup):
        """메인 창 위치 기준으로 팝업 중앙 배치"""
        popup.update_idletasks()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        
        popup_width = popup.winfo_width()
        popup_height = popup.winfo_height()
        
        # 메인 창 중앙에 배치
        x = parent_x + (parent_width - popup_width) // 2
        y = parent_y + (parent_height - popup_height) // 2
        
        popup.geometry(f"+{x}+{y}")

    # ======================================================
    # 업체 선택 팝업
    #  - 업체 관리 UI와 동일한 순서/목록 사용
    # ======================================================
    def _popup_select_company(self):
        popup = tk.Toplevel(self.root)
        popup.title("업체 선택")
        popup.geometry("450x250")
        popup.grab_set()
        popup.resizable(False, False)
        
        # 메인 창 위치 기준으로 팝업 위치 설정
        self._center_popup_on_parent(popup)
        
        # 배경색 설정
        popup.configure(bg="white")
        
        # 헤더
        header = tk.Frame(popup, bg="#2C3E50", height=40)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="업체 선택",
            font=("맑은 고딕", 11, "bold"),
            bg="#2C3E50",
            fg="white"
        ).pack(side="left", padx=15, pady=8)
        
        # 메인 영역
        main = tk.Frame(popup, bg="white")
        main.pack(fill="both", expand=True, padx=20, pady=20)

        # 최신 업체 목록/순서를 MainUI 콤보박스 기준으로 사용
        self.refresh_company_list()
        combo_values = list(self.company_combo["values"])
        # "전체 업체" 옵션 제거
        companies = [c for c in combo_values if c != self.ALL_COMPANIES_OPTION]

        if not companies:
            messagebox.showwarning("안내", "등록된 업체가 없습니다.\n\n먼저 '업체 관리' 버튼을 클릭하여 업체를 추가해주세요.", parent=popup)
            popup.destroy()
            return None

        tk.Label(
            main,
            text="업체 선택:",
            font=("맑은 고딕", 9, "bold"),
            bg="white",
            fg="#2C3E50"
        ).pack(anchor="w", pady=(0, 5))

        company_var = tk.StringVar(value=companies[0])
        combo = ttk.Combobox(
            main,
            textvariable=company_var,
            values=companies,
            state="readonly",
            font=("맑은 고딕", 10),
            width=35
        )
        combo.pack(fill="x", pady=(0, 20))

        selected = {"value": None}

        def confirm():
            selected["value"] = company_var.get()
            popup.destroy()

        # 버튼 영역
        button_frame = tk.Frame(main, bg="white")
        button_frame.pack(fill="x")
        
        confirm_btn = tk.Button(
            button_frame,
            text="확인",
            command=confirm,
            font=("맑은 고딕", 9),
            bg="#27AE60",
            fg="white",
            activebackground="#229954",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=10,
            pady=5,
            cursor="hand2"
        )
        confirm_btn.pack(side="right", padx=(5, 0))
        
        cancel_btn = tk.Button(
            button_frame,
            text="취소",
            command=popup.destroy,
            font=("맑은 고딕", 9),
            bg="#95A5A6",
            fg="white",
            activebackground="#7F8C8D",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=10,
            pady=5,
            cursor="hand2"
        )
        cancel_btn.pack(side="right")

        popup.wait_window()
        return selected["value"]

