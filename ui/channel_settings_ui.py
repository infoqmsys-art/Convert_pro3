import os
import tkinter as tk
from tkinter import ttk, messagebox
from copy import deepcopy
import pandas as pd
from core.sensor_processor import MODE_META
from core.sensor_processor import SensorProcessor
from core.presets import PRESET_NAMES, CHANNEL_PRESETS, apply_preset_to_file_cfg


def index_to_excel_col(idx):
    """컬럼 인덱스를 엑셀 칼럼 문자로 변환 (0=A, 1=B, ..., 16=Q, 17=R, ...)"""
    result = ""
    idx += 1  # 엑셀은 1부터 시작
    while idx > 0:
        idx -= 1
        result = chr(ord('A') + (idx % 26)) + result
        idx //= 26
    return result


# ======================================================
#  CH 기본 템플릿 (UI 로드 시 사용)
# ======================================================
def default_channel_config():
    return {
        "mode": "PASS",
        "base": "",
        "scale": "",
        "post_offset": "",
        "decimal": "",
        "label": "",
        "initial": "",
    }


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None

        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tipwindow or not self.text:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20

        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            tw,
            text=self.text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("맑은 고딕", 9)
        )
        label.pack(ipadx=4, ipady=2)

    def hide(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


class ChannelSettingsUI:
    """
    파일별 전역 옵션 + CH0~CH7 설정창
    baseline(과거 방식)이 제거되고
    초기치(initial)는 각 CH 개별 필드에서만 관리됨.
    """

    def __init__(self, root, controller, company, site, folder, filename):
        self.root = root
        self.controller = controller
        self.company = company
        self.site = site
        self.folder = folder
        self.filename = filename

        self.config = controller.config
        self.tree = controller.tree
        self.logger = getattr(controller, "logger", None)
        self.file_processor = controller.file_processor

        # 센서 모드 목록
        self.mode_list = list(MODE_META.keys())

        self.ch_vars = {}

        # Toplevel UI — grab_set 하지 않음.
        # 변환 스레드의 로그/상태 갱신과 모달이 겹치면 Tk가 먹통이 된다.
        self.win = tk.Toplevel(self.root)

        # 파일 설정 로딩
        self._load_file_config()
        self.is_nb = bool(self.file_cfg.get("__nb_mode__"))
        title_kind = "Neo Blast 로거 설정" if self.is_nb else "채널 설정"
        self.win.title(f"{title_kind} - {company}/{site}/{folder}/{filename}")

        # CSV 파일에서 초기치 읽기 (일반 로거만)
        self.initial_values = {} if self.is_nb else self._read_initial_values()

        # UI 생성
        self._build_ui()

    # ======================================================
    # 파일 설정 로딩
    # ======================================================
    def _load_file_config(self):
        converting = bool(getattr(self.controller, "is_converting", False))
        if not converting:
            try:
                self.config.load(quiet=True)
            except Exception:
                pass
        try:
            file_cfg = self.tree.get_file_config(
                self.company, self.site, self.folder, self.filename
            )
        except:
            file_cfg = None

        if file_cfg is None:
            file_cfg = self.config.data.get(self.company, {}).get(
                self.site, {}).get(self.folder, {}).get(self.filename, {})

        if not isinstance(file_cfg, dict):
            file_cfg = {}

        # 전역 옵션 기본값
        file_cfg.setdefault("__fill_interval__", 0)
        file_cfg.setdefault("__gen_interval__", 0)
        file_cfg.setdefault("__align_60__", False)
        file_cfg.setdefault("__note__", "")  # 파일별 비고
        file_cfg.setdefault("__nb_mode__", False)
        file_cfg.setdefault("__nb_source_dir__", "")
        file_cfg.setdefault("__nb_kine_limit__", "")
        file_cfg.setdefault("__nb_pvs_limit__", "")

        final_cfg = deepcopy(file_cfg)

        for key in ("degreeX", "degreeY"):
            merged = default_channel_config()
            merged.update(final_cfg.get(key, {}) if isinstance(final_cfg.get(key), dict) else {})
            if "mode" not in merged and "offset" in merged:
                merged["mode"] = merged.get("offset", "PASS")
            merged.setdefault("mode", "PASS")
            merged.setdefault("base", "")
            merged.setdefault("scale", "")
            merged.setdefault("post_offset", "")
            merged.setdefault("decimal", "")
            merged.setdefault("label", "")
            merged.setdefault("initial", "")
            merged.pop("offset", None)
            final_cfg[key] = merged

        for ch in range(8):
            key = f"CH{ch}"
            merged = default_channel_config()
            merged.update(final_cfg.get(key, {}))

            # ============================================================
            # channel config 정리 (STEP 2-A 기준)
            # ============================================================

            # (구버전 제거) offset → mode
            if "mode" not in merged and "offset" in merged:
                merged["mode"] = merged.get("offset", "PASS")

            # mode 기본값 보장
            merged.setdefault("mode", "PASS")

            # 나머지 파라미터 기본값
            merged.setdefault("base", "")
            merged.setdefault("scale", "")
            merged.setdefault("post_offset", "")
            merged.setdefault("decimal", "")
            merged.setdefault("label", "")
            merged.setdefault("initial", "")

            # offset 키는 더 이상 사용하지 않음 (정리)
            merged.pop("offset", None)

            final_cfg[key] = merged
            
        self.file_cfg = final_cfg

    # ======================================================
    # CSV 파일에서 초기치 읽기 (UI 열 때마다 실행)
    # ======================================================
    def _read_initial_values(self):
        """
        변환된 파일 또는 원본 파일에서 첫 번째 유효한 데이터 행을 읽어서
        CH0~CH7의 초기치를 반환합니다.
        
        우선순위:
        1. 변환된 파일 ({convert_root}/{company}/{folder}/{filename})
        2. 원본 파일 (__absolute_path__/filename)
        
        초기치는 파일의 첫 번째 데이터 행(헤더 제외)에서 추출됩니다.
        
        Returns:
            dict: {0: "값0", 1: "값1", ... 7: "값7"} 또는 {}
        """
        initial_values = {}
        if getattr(self.controller, "is_converting", False):
            return initial_values
        
        try:
            from utils.convert_paths import resolve_convert_out_path

            convert_path = resolve_convert_out_path(
                self.file_processor.convert_root,
                self.company,
                self.site,
                self.folder,
                self.filename,
            )
            
            csv_path = None
            if os.path.exists(convert_path):
                csv_path = convert_path
            else:
                # 2. 원본 파일 경로 확인 (Site 레벨 포함)
                folder_cfg = self.config.data.get(self.company, {}).get(self.site, {}).get(self.folder, {})
                abs_path = folder_cfg.get("__absolute_path__", "")
                if abs_path:
                    src_path = os.path.join(abs_path, self.filename)
                    if os.path.exists(src_path):
                        csv_path = src_path
            
            if not csv_path:
                return initial_values
            
            # 3. CSV 파일 읽기 (첫 번째 유효한 데이터 행 찾기)
            try:
                # 변환된 파일인지 확인 (변환 파일은 헤더가 있을 수 있음)
                is_converted = (csv_path == convert_path)
                
                if is_converted:
                    # 변환된 파일: 헤더가 있을 수 있으므로 첫 번째 데이터 행 찾기
                    # STANDARD_HEADER가 있으면 첫 번째 행은 헤더
                    try:
                        df_full = pd.read_csv(
                            csv_path,
                            header=0,  # 헤더 있으면 첫 행 스킵
                            nrows=1,   # 첫 번째 데이터 행만
                            engine="python",
                            on_bad_lines="skip",
                            encoding="utf-8-sig"
                        )
                    except:
                        # 헤더가 없는 경우 시도
                        df_full = pd.read_csv(
                            csv_path,
                            header=None,
                            nrows=1,
                            engine="python",
                            on_bad_lines="skip",
                            encoding="utf-8-sig"
                        )
                else:
                    # 원본 파일: 헤더 없이 읽고 타임스탬프로 유효한 행 찾기
                    # 파일을 한 줄씩 읽어서 첫 번째 유효한 데이터 행 찾기
                    first_data_row = None
                    with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            parts = line.split(",")
                            if len(parts) < 17:  # 최소 17개 컬럼 필요 (0~16)
                                continue
                            # 타임스탬프 파싱 시도
                            try:
                                ts = pd.to_datetime(parts[0], errors="coerce")
                                if pd.notna(ts) and ts.year >= 2000:
                                    first_data_row = line
                                    break
                            except:
                                continue
                    
                    if not first_data_row:
                        return initial_values
                    
                    # 첫 번째 유효한 행을 DataFrame으로 변환
                    from io import StringIO
                    df_full = pd.read_csv(
                        StringIO(first_data_row),
                        header=None,
                        engine="python",
                        on_bad_lines="skip"
                    )
                
                if df_full.empty:
                    return initial_values
                
                # 4. 내장 degreeX/Y(13·14) + 외장 CH0~CH7(16~23)
                for key, col_idx in (("degreeX", 13), ("degreeY", 14)):
                    if col_idx < df_full.shape[1]:
                        val = df_full.iloc[0, col_idx]
                        if pd.notna(val) and str(val).strip():
                            initial_values[key] = str(val).strip()
                        else:
                            initial_values[key] = ""
                    else:
                        initial_values[key] = ""

                for ch in range(8):
                    col_idx = 16 + ch
                    if col_idx < df_full.shape[1]:
                        val = df_full.iloc[0, col_idx]
                        # NaN이나 None 처리
                        if pd.notna(val) and str(val).strip():
                            initial_values[ch] = str(val).strip()
                        else:
                            initial_values[ch] = ""
                    else:
                        initial_values[ch] = ""
                        
            except Exception as e:
                if self.logger:
                    self.logger.log(
                        f"[ChannelSettingsUI] 초기치 읽기 실패: {e}",
                        level="DEBUG"
                    )
                return {}
                
        except Exception as e:
            if self.logger:
                self.logger.log(
                    f"[ChannelSettingsUI] 초기치 읽기 오류: {e}",
                    level="DEBUG"
                )
            return {}
        
        return initial_values

    def _initial_for_slot(self, key) -> str:
        """슬롯 키(degreeX/Y, CH0…)에 해당하는 첫 행 초기치."""
        if key in ("degreeX", "degreeY"):
            raw = self.initial_values.get(key, "")
        elif isinstance(key, str) and key.startswith("CH"):
            try:
                raw = self.initial_values.get(int(key[2:]), "")
            except ValueError:
                raw = ""
        else:
            raw = self.initial_values.get(key, "")
        return str(raw or "").strip()

    def _fill_set_base_if_empty(self, key, mode, base_var):
        """SET이고 base가 비었으면 초기치를 한 번 넣는다. 있는 값은 덮지 않음."""
        if (mode or "").strip().upper() != "SET":
            return
        if (base_var.get() or "").strip():
            return
        init_val = self._initial_for_slot(key)
        if init_val:
            base_var.set(init_val)

    def update_param_state(self, mode, base_entry, scale_entry):
        meta = MODE_META.get(mode, MODE_META["PASS"])

        # base
        if meta["use_base"]:
            base_entry.config(state="normal")
        else:
            base_entry.delete(0, "end")
            base_entry.config(state="disabled")

        # scale
        if meta["use_scale"]:
            scale_entry.config(state="normal")
        else:
            scale_entry.delete(0, "end")
            scale_entry.config(state="disabled")

    # ======================================================
    # UI 생성
    # ======================================================
    def _build_ui(self):
        # 메인 컨테이너
        main = tk.Frame(self.win, bg="#F5F5F5")
        main.pack(fill="both", expand=True)

        # ------------------------------ 헤더 영역 ------------------------------
        header = tk.Frame(main, bg="#2C3E50", height=50)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        
        title_text = f"{self.company} / {self.site} / {self.folder} / {self.filename}"
        header_label = "Neo Blast 로거 설정" if self.is_nb else "채널 설정"
        tk.Label(
            header,
            text=header_label,
            font=("맑은 고딕", 12, "bold"),
            bg="#2C3E50",
            fg="white"
        ).pack(side="left", padx=15, pady=(8, 0), anchor="w")
        
        tk.Label(
            header,
            text=title_text,
            font=("맑은 고딕", 9),
            bg="#2C3E50",
            fg="#BDC3C7"
        ).pack(side="left", padx=(10, 0), pady=(0, 8), anchor="w")
        
        # ------------------------------ 컨텐츠 영역 ------------------------------
        content = tk.Frame(main, bg="white")
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        frame = tk.Frame(content, bg="white")
        frame.pack(fill="both", expand=True)

        if self.is_nb:
            self._build_nb_options(frame)
        else:
            self._build_global_options(frame)
            self._build_note_section(frame, row=2)
            self._build_preset_section(frame, row=3)
            self._build_channel_grid(frame)

        if self.is_nb:
            self._build_note_section(frame, row=2)

        # ---------------- 버튼 영역 ----------------
        self._build_footer_buttons(main)

    def _build_nb_options(self, frame):
        """Neo Blast: 원본 경로 + Kine 한도(비율 보정)."""
        info = ttk.LabelFrame(frame, text="Neo Blast", padding=12)
        info.grid(row=0, column=0, columnspan=8, sticky="ew", pady=(0, 12))

        src = str(self.file_cfg.get("__nb_source_dir__", "") or "")
        tk.Label(
            info,
            text="원본 폴더:",
            font=("맑은 고딕", 9),
            bg="white",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        tk.Label(
            info,
            text=src or "(없음)",
            font=("맑은 고딕", 9),
            fg="#2C3E50",
            bg="white",
            wraplength=520,
            justify="left",
        ).grid(row=0, column=1, columnspan=3, sticky="w", pady=4)

        tk.Label(
            info,
            text=".blast/.txt 추출 시 X·Y·Z로 PVS를 계산하고, 한도 초과 시 세 축을 같은 비율로 줄입니다.",
            font=("맑은 고딕", 8),
            fg="#7F8C8D",
            bg="white",
            wraplength=560,
            justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 8))

        # 기존: kine 우선, 없으면 pvs→kine 환산 표시
        kine_val = self.file_cfg.get("__nb_kine_limit__", "")
        pvs_val = self.file_cfg.get("__nb_pvs_limit__", "")
        display_kine = ""
        enabled = False
        try:
            if kine_val not in ("", None):
                display_kine = f"{float(kine_val):g}"
                enabled = float(kine_val) > 0
            elif pvs_val not in ("", None) and float(pvs_val) > 0:
                display_kine = f"{float(pvs_val) * 0.1:g}"
                enabled = True
        except (TypeError, ValueError):
            display_kine = str(kine_val or "")

        self.nb_limit_enabled_var = tk.BooleanVar(value=enabled)
        ttk.Checkbutton(
            info,
            text="한도 비율 보정 사용",
            variable=self.nb_limit_enabled_var,
            command=self._sync_nb_limit_widgets,
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(0, 6))

        tk.Label(
            info,
            text="Kine 한도:",
            font=("맑은 고딕", 9),
            bg="white",
        ).grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)

        self.nb_kine_limit_var = tk.StringVar(value=display_kine or "0.20")
        self.nb_kine_combo = ttk.Combobox(
            info,
            textvariable=self.nb_kine_limit_var,
            values=["0.20", "0.25", "0.30"],
            width=10,
            font=("맑은 고딕", 9),
        )
        self.nb_kine_combo.grid(row=3, column=1, sticky="w", pady=4)

        tk.Label(
            info,
            text="(예: 0.20 / 0.25 · PVS 한도 = Kine ÷ 0.1)",
            font=("맑은 고딕", 8),
            fg="#7F8C8D",
            bg="white",
        ).grid(row=3, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=4)

        # 로거 번호
        tk.Label(
            info,
            text="로거 번호:",
            font=("맑은 고딕", 9),
            bg="white",
        ).grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(10, 4))
        self.logger_number_var = tk.StringVar(
            value=str(self.file_cfg.get("__logger_number__", "") or "")
        )
        tk.Entry(
            info,
            textvariable=self.logger_number_var,
            width=10,
            font=("맑은 고딕", 9),
            bg="white",
        ).grid(row=4, column=1, sticky="w", pady=(10, 4))
        tk.Label(
            info,
            text="(트리뷰 정렬용)",
            font=("맑은 고딕", 8),
            fg="#7F8C8D",
            bg="white",
        ).grid(row=4, column=2, sticky="w", padx=(8, 0), pady=(10, 4))

        self._sync_nb_limit_widgets()

    def _sync_nb_limit_widgets(self):
        if not getattr(self, "nb_kine_combo", None):
            return
        state = "normal" if self.nb_limit_enabled_var.get() else "disabled"
        self.nb_kine_combo.configure(state=state)

    def _build_global_options(self, frame):
        # ---------------- 전역 옵션 ----------------
        opt_frame = ttk.LabelFrame(
            frame, 
            text="전역 옵션", 
            padding=12,
            style="TLabelframe"
        )
        opt_frame.grid(row=1, column=0, columnspan=8, sticky="ew", pady=(0, 15))
        
        file_opt = tk.Frame(opt_frame, bg="white")
        file_opt.pack(fill="x")

        # 누락 보충
        tk.Label(
            file_opt, 
            text="누락 보충:", 
            font=("맑은 고딕", 9),
            bg="white"
        ).grid(row=0, column=0, padx=(0, 8), pady=5, sticky="w")

        self.fill_interval_var = tk.IntVar(
            value=self.file_cfg.get("__fill_interval__", 0)
        )

        combo = ttk.Combobox(
            file_opt,
            textvariable=self.fill_interval_var,
            values=[0, 10, 60],
            width=12,
            state="readonly",
            font=("맑은 고딕", 9)
        )
        combo.grid(row=0, column=1, padx=5, pady=5)
        
        # 설명 라벨
        desc_text = {
            0: "비활성화",
            10: "10분마다 1행 (빈 슬롯·현재까지 채움)",
            60: "1시간마다 1행 (빈 슬롯·현재까지 채움)",
        }.get(self.fill_interval_var.get(), "비활성화")
        
        desc_label = tk.Label(
            file_opt, 
            text=f"({desc_text})", 
            foreground="#7F8C8D",
            font=("맑은 고딕", 8),
            bg="white"
        )
        desc_label.grid(row=0, column=2, padx=(5, 20), pady=5, sticky="w")
        
        def update_desc(*args):
            val = self.fill_interval_var.get()
            new_text = {
                0: "비활성화",
                10: "10분마다 1행 (빈 슬롯·현재까지 채움)",
                60: "1시간마다 1행 (빈 슬롯·현재까지 채움)",
            }.get(val, "비활성화")
            desc_label.config(text=f"({new_text})")
        
        self.fill_interval_var.trace_add("write", update_desc)

        # 60분 정렬 파일 (EL/CR용 — 누락보충과 별개)
        self.align_60_var = tk.BooleanVar(
            value=bool(self.file_cfg.get("__align_60__", False))
        )
        align_row = tk.Frame(opt_frame, bg="white")
        align_row.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(
            align_row,
            text="60분 정렬 파일 생성 (10분 변환본을 시간당 1행으로 정렬 → 파일명_60.csv)",
            variable=self.align_60_var,
        ).pack(anchor="w")
        tk.Label(
            align_row,
            text="센서·누락보충은 10분 파일만. _60은 저장된 10분본과 동일 값, EL·CR 등록용.",
            foreground="#7F8C8D",
            font=("맑은 고딕", 8),
            bg="white",
        ).pack(anchor="w", padx=(22, 0))

        # 주기 생성
        tk.Label(
            file_opt, 
            text="주기 생성(분):", 
            font=("맑은 고딕", 9),
            bg="white"
        ).grid(row=0, column=3, padx=(20, 8), pady=5, sticky="w")

        self.gen_interval_var = tk.IntVar(
            value=self.file_cfg.get("__gen_interval__", 0)
        )

        ttk.Combobox(
            file_opt,
            textvariable=self.gen_interval_var,
            values=[0, 10, 60],
            width=8,
            state="readonly",
            font=("맑은 고딕", 9)
        ).grid(row=0, column=4, padx=5, pady=5)

        # 로거 번호
        tk.Label(
            file_opt, 
            text="로거 번호:", 
            font=("맑은 고딕", 9),
            bg="white"
        ).grid(row=0, column=5, padx=(20, 8), pady=5, sticky="w")

        self.logger_number_var = tk.StringVar(
            value=str(self.file_cfg.get("__logger_number__", ""))
        )

        logger_entry = tk.Entry(
            file_opt,
            textvariable=self.logger_number_var,
            width=8,
            font=("맑은 고딕", 9),
            bg="white"
        )
        logger_entry.grid(row=0, column=6, padx=5, pady=5, sticky="w")
        
        tk.Label(
            file_opt, 
            text="(트리뷰 정렬용)", 
            foreground="#7F8C8D",
            font=("맑은 고딕", 8),
            bg="white"
        ).grid(row=0, column=7, padx=(5, 0), pady=5, sticky="w")

    def _build_note_section(self, frame, row=2):
        # ---------------- 비고 (파일별) ----------------
        note_frame = ttk.LabelFrame(
            frame, 
            text="비고", 
            padding=10
        )
        note_frame.grid(row=row, column=0, columnspan=8, sticky="ew", pady=(0, 15))
        
        file_note = self.file_cfg.get("__note__", "")
        note_entry = tk.Text(
            note_frame,
            height=3,
            wrap="word",
            font=("맑은 고딕", 9),
            relief="solid",
            bd=1,
            bg="#FAFAFA",
            fg="#2C3E50"
        )
        note_entry.pack(fill="both", expand=True, padx=5, pady=5)
        note_entry.insert("1.0", file_note)
        
        # 참조를 저장하기 위해 인스턴스 변수로 저장
        self.note_text_widget = note_entry

    def _build_preset_section(self, frame, row=3):
        box = ttk.LabelFrame(frame, text="센서 프리셋", padding=10)
        box.grid(row=row, column=0, columnspan=8, sticky="ew", pady=(0, 12))

        rowf = tk.Frame(box, bg="white")
        rowf.pack(fill="x")

        tk.Label(
            rowf, text="프리셋:", font=("맑은 고딕", 9), bg="white"
        ).pack(side="left", padx=(0, 8))

        default_name = PRESET_NAMES[0] if PRESET_NAMES else ""
        self.preset_var = tk.StringVar(value=default_name)
        combo = ttk.Combobox(
            rowf,
            textvariable=self.preset_var,
            values=list(PRESET_NAMES),
            width=22,
            state="readonly",
            font=("맑은 고딕", 9),
        )
        combo.pack(side="left", padx=(0, 8))

        tk.Button(
            rowf,
            text="적용",
            command=self._on_apply_preset,
            font=("맑은 고딕", 9),
            bg="#16A085",
            fg="white",
            activebackground="#138D75",
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=2,
            cursor="hand2",
        ).pack(side="left", padx=(0, 12))

        desc0 = CHANNEL_PRESETS.get(default_name, {}).get("desc", "")
        self.preset_desc_label = tk.Label(
            rowf,
            text=desc0,
            font=("맑은 고딕", 8),
            fg="#7F8C8D",
            bg="white",
            wraplength=520,
            justify="left",
            anchor="w",
        )
        self.preset_desc_label.pack(side="left", fill="x", expand=True)

        def _on_preset_selected(*_a):
            name = self.preset_var.get()
            self.preset_desc_label.config(
                text=CHANNEL_PRESETS.get(name, {}).get("desc", "")
            )

        self.preset_var.trace_add("write", _on_preset_selected)

    def _on_apply_preset(self):
        name = (self.preset_var.get() or "").strip()
        if not name:
            return
        try:
            self.file_cfg = apply_preset_to_file_cfg(
                self.file_cfg, name, keep_base=True
            )
        except KeyError:
            messagebox.showerror("프리셋", f"알 수 없는 프리셋: {name}")
            return

        for key, slot in CHANNEL_PRESETS[name]["slots"].items():
            ui = self.ch_vars.get(key)
            if not ui:
                continue
            cfg = self.file_cfg.get(key, slot)
            ui["mode"].set(cfg.get("mode", "PASS"))
            ui["base"].set(str(cfg.get("base", "") or ""))
            ui["scale"].set(str(cfg.get("scale", "") or ""))
            ui["post_offset"].set(str(cfg.get("post_offset", "") or ""))
            ui["decimal"].set(str(cfg.get("decimal", "") or ""))
            ui["label"].set(str(cfg.get("label", "") or ""))
            self.update_param_state(
                ui["mode"].get(), ui["base_entry"], ui["scale_entry"]
            )
            self._fill_set_base_if_empty(key, ui["mode"].get(), ui["base"])

        messagebox.showinfo(
            "프리셋 적용",
            f"「{name}」을(를) 화면에 반영했습니다.\n"
            "SET이고 base가 비어 있으면 초기치를 넣습니다. "
            "저장을 눌러야 config에 반영됩니다.",
        )

    def _build_channel_grid(self, frame):
        headers = ["채널", "모드", "base", "scale", "변환후+", "소수점", "센서명(label)", "초기치"]
        col_widths = [18, 14, 10, 10, 8, 8, 20, 18]

        for i in range(8):
            frame.columnconfigure(i, weight=0)

        # —— 로거 내장 경사 ——
        tk.Label(
            frame,
            text="로거 내장 경사 (degreeX / degreeY · 인덱스 13·14)",
            font=("맑은 고딕", 9, "bold"),
            bg="#1A5276",
            fg="white",
            anchor="w",
        ).grid(row=4, column=0, columnspan=8, sticky="ew", pady=(0, 4), padx=2)

        for i, h in enumerate(headers):
            tk.Label(
                frame,
                text=h,
                font=("맑은 고딕", 9, "bold"),
                bg="#D6EAF8",
                fg="#2C3E50",
                width=col_widths[i],
                relief="flat",
            ).grid(row=5, column=i, padx=2, pady=4, sticky="ew")

        builtin = (
            ("degreeX", 13, "내장 X"),
            ("degreeY", 14, "내장 Y"),
        )
        for bi, (key, col_idx, short) in enumerate(builtin):
            excel_col = index_to_excel_col(col_idx)
            self._add_sensor_row(
                frame,
                row=6 + bi,
                key=key,
                cfg=self.file_cfg[key],
                col_widths=col_widths,
                channel_text=f"{short}\n(칼럼{excel_col}, 인덱스{col_idx})",
                row_bg="#FFFFFF" if bi % 2 == 0 else "#EBF5FB",
                init_key=key,
            )

        # —— 외장 AmountCH ——
        tk.Label(
            frame,
            text="외장 센서 AmountCH0~7 (로거에 연결한 센서 · 인덱스 16~23)",
            font=("맑은 고딕", 9, "bold"),
            bg="#1E8449",
            fg="white",
            anchor="w",
        ).grid(row=8, column=0, columnspan=8, sticky="ew", pady=(12, 4), padx=2)

        for i, h in enumerate(headers):
            tk.Label(
                frame,
                text=h,
                font=("맑은 고딕", 9, "bold"),
                bg="#ECF0F1",
                fg="#2C3E50",
                width=col_widths[i],
                relief="flat",
            ).grid(row=9, column=i, padx=2, pady=4, sticky="ew")

        for ch in range(8):
            key = f"CH{ch}"
            col_idx = 16 + ch
            excel_col = index_to_excel_col(col_idx)
            self._add_sensor_row(
                frame,
                row=10 + ch,
                key=key,
                cfg=self.file_cfg[key],
                col_widths=col_widths,
                channel_text=f"{key}\n(칼럼{excel_col}, 인덱스{col_idx})",
                row_bg="#FFFFFF" if ch % 2 == 0 else "#F8F9FA",
                init_key=ch,
            )

    def _add_sensor_row(self, frame, row, key, cfg, col_widths, channel_text, row_bg, init_key):
        decimal_var = tk.StringVar(value=str(cfg.get("decimal", "")))
        mode_var = tk.StringVar(value=cfg["mode"])
        label_var = tk.StringVar(value=str(cfg["label"]))

        tk.Label(
            frame,
            text=channel_text,
            font=("맑은 고딕", 8),
            bg=row_bg,
            fg="#2C3E50",
            width=col_widths[0],
            justify="center",
            relief="flat",
        ).grid(row=row, column=0, padx=2, pady=2, sticky="nsew")

        mode_frame = tk.Frame(frame, bg=row_bg)
        mode_frame.grid(row=row, column=1, padx=2, pady=2, sticky="ew")
        mode_cb = ttk.Combobox(
            mode_frame,
            textvariable=mode_var,
            values=self.mode_list,
            width=col_widths[1],
            state="readonly",
            font=("맑은 고딕", 9),
        )
        mode_cb.pack(fill="both", expand=True)
        tooltip = ToolTip(
            mode_cb,
            MODE_META.get(mode_var.get(), MODE_META["PASS"])["desc"],
        )

        base_frame = tk.Frame(frame, bg=row_bg)
        base_frame.grid(row=row, column=2, padx=2, pady=2, sticky="ew")
        base_var = tk.StringVar(value="" if cfg.get("base") is None else str(cfg["base"]))
        base_entry = ttk.Entry(
            base_frame,
            textvariable=base_var,
            width=col_widths[2],
            font=("맑은 고딕", 9),
        )
        base_entry.pack(fill="both", expand=True)

        scale_frame = tk.Frame(frame, bg=row_bg)
        scale_frame.grid(row=row, column=3, padx=2, pady=2, sticky="ew")
        scale_var = tk.StringVar(value="" if cfg.get("scale") is None else str(cfg["scale"]))
        scale_entry = ttk.Entry(
            scale_frame,
            textvariable=scale_var,
            width=col_widths[3],
            font=("맑은 고딕", 9),
        )
        scale_entry.pack(fill="both", expand=True)

        po_frame = tk.Frame(frame, bg=row_bg)
        po_frame.grid(row=row, column=4, padx=2, pady=2, sticky="ew")
        post_off_var = tk.StringVar(
            value="" if cfg.get("post_offset") in (None, "") else str(cfg["post_offset"])
        )
        post_off_entry = ttk.Entry(
            po_frame,
            textvariable=post_off_var,
            width=col_widths[4],
            font=("맑은 고딕", 9),
        )
        post_off_entry.pack(fill="both", expand=True)
        ToolTip(
            post_off_entry,
            "모드 계산 결과에 마지막으로 더하는 값(JSON: post_offset).\n비우면 0. PASS 포함 모든 모드에 적용.",
        )

        on_mode_change = self._make_mode_change_handler(
            key, mode_var, base_var, base_entry, scale_entry, tooltip
        )
        mode_cb.bind("<<ComboboxSelected>>", on_mode_change)
        mode_var.trace_add("write", on_mode_change)
        on_mode_change()

        decimal_frame = tk.Frame(frame, bg=row_bg)
        decimal_frame.grid(row=row, column=5, padx=2, pady=2, sticky="ew")
        ttk.Entry(
            decimal_frame,
            textvariable=decimal_var,
            width=col_widths[5],
            font=("맑은 고딕", 9),
        ).pack(fill="both", expand=True)

        label_frame = tk.Frame(frame, bg=row_bg)
        label_frame.grid(row=row, column=6, padx=2, pady=2, sticky="ew")
        ttk.Entry(
            label_frame,
            textvariable=label_var,
            width=col_widths[6],
            font=("맑은 고딕", 9),
        ).pack(fill="both", expand=True)

        init_val = self.initial_values.get(init_key, "")
        if not init_val:
            init_val = cfg.get("initial", "")
        init_text = (
            f"※ 초기치: {str(init_val).strip()}"
            if init_val and str(init_val).strip()
            else ""
        )
        tk.Label(
            frame,
            text=init_text,
            foreground="#999",
            font=("맑은 고딕", 8),
            bg=row_bg,
            anchor="w",
            width=col_widths[7],
        ).grid(row=row, column=7, padx=2, pady=2, sticky="ew")

        self.ch_vars[key] = {
            "mode": mode_var,
            "base": base_var,
            "scale": scale_var,
            "post_offset": post_off_var,
            "decimal": decimal_var,
            "label": label_var,
            "base_entry": base_entry,
            "scale_entry": scale_entry,
        }

    def _build_footer_buttons(self, main):
        # ---------------- 버튼 영역 ----------------
        btn_frame = tk.Frame(main, bg="#ECF0F1", height=60)
        btn_frame.pack(fill="x", side="bottom")
        btn_frame.pack_propagate(False)
        
        btn_container = tk.Frame(btn_frame, bg="#ECF0F1")
        btn_container.pack(fill="both", expand=True, padx=15, pady=10)
        
        # 왼쪽: 메뉴얼 버튼 (일반 채널만)
        left_btns = tk.Frame(btn_container, bg="#ECF0F1")
        left_btns.pack(side="left")

        if not self.is_nb:
            manual_btn = tk.Button(
                left_btns,
                text="📖 메뉴얼",
                command=self.show_manual,
                font=("맑은 고딕", 9),
                bg="#8E44AD",
                fg="white",
                activebackground="#7D3C98",
                activeforeground="white",
                relief="flat",
                width=10,
                height=1,
                padx=15,
                pady=6,
                cursor="hand2"
            )
            manual_btn.pack(side="left")

        tk.Frame(btn_container, bg="#ECF0F1").pack(side="left", fill="x", expand=True)

        # 오른쪽: 버튼들
        right_btns = tk.Frame(btn_container, bg="#ECF0F1")
        right_btns.pack(side="right")

        save_btn = tk.Button(
            right_btns,
            text="저장",
            command=self._on_save,
            font=("맑은 고딕", 9, "bold"),
            bg="#3498DB",
            fg="white",
            activebackground="#2980B9",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=15,
            pady=6,
            cursor="hand2"
        )
        save_btn.pack(side="left", padx=(0, 8))

        close_btn = tk.Button(
            right_btns,
            text="닫기",
            command=self.win.destroy,
            font=("맑은 고딕", 9),
            bg="#95A5A6",
            fg="white",
            activebackground="#7F8C8D",
            activeforeground="white",
            relief="flat",
            width=10,
            height=1,
            padx=15,
            pady=6,
            cursor="hand2"
        )
        close_btn.pack(side="left")

    # ======================================================
    # 메뉴얼 창
    # ======================================================
    def show_manual(self):
        win = tk.Toplevel(self.win)
        win.title("센서 설정 메뉴얼")
        win.geometry("780x680")
        win.resizable(True, True)
        win.grab_set()

        # ── 상단 제목
        header = tk.Frame(win, bg="#2C3E50", height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="📖  센서 모드 설정 메뉴얼",
            font=("맑은 고딕", 13, "bold"),
            bg="#2C3E50", fg="white"
        ).pack(side="left", padx=18, pady=10)

        # ── 스크롤 영역
        frame_outer = tk.Frame(win, bg="#F4F6F7")
        frame_outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(frame_outer, bg="#F4F6F7", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg="#F4F6F7")
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_resize(event):
            canvas.itemconfig(inner_id, width=event.width)
        canvas.bind("<Configure>", _on_resize)

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_frame_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        win.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # ── 공통 파라미터 설명
        MANUAL_SECTIONS = [
            {
                "title": "공통 파라미터",
                "color": "#1A5276",
                "items": [
                    ("mode",    "센서 동작 방식 선택 (아래 모드 목록 참조)"),
                    ("base",    "기준값 또는 참조 컬럼 인덱스 (모드에 따라 다름)"),
                    ("scale",   "랜덤 폭·배율·표준편차 등 (모드에 따라 다름). 일부 모드는 VW 입력 가능"),
                    ("변환후+", "저장 키 post_offset. 모드·SET·PASS 등 계산된 채널 값 맨 마지막에 더할 상수. 레거시 「offset」(모드)과 무관"),
                    ("소수점",  "변환 결과 소수점 자리수 (예: 4 → 소수점 4자리)"),
                    ("센서명",  "출력 파일 헤더에 표시될 이름 (label)"),
                    ("초기치",  "이어쓰기 시 시작 기준값. 비어 있으면 base 또는 0 사용"),
                ]
            },
            {
                "title": "원본 참조 모드 (원본 센서값을 읽어서 변환)",
                "color": "#1F618D",
                "items": [
                    ("PASS",      "원본 그대로 출력. base/scale 불필요"),
                    ("OFFSET",    "원본 + base\n예) 원본=10, base=0.5 → 출력=10.5"),
                    ("EL",        "경사/변위 아날로그 센서용 OFFSET 동일 동작\n원본 + base"),
                    ("SET",       "base 기준으로 변위를 scale 배율 보정\n결과 = base + (원본 - base) × scale"),
                    ("ANSAN_WM",  "지하수위계 전용\n결과 = (원본 × 4) − base + offset\nbase = 파이프 전체 길이(양수), scale = 보정값(선택)"),
                    ("COPY",      "다른 컬럼 복사\nbase = 복사할 열 번호 (0부터 시작)\n예) base=3 → D열 값 그대로 복사"),
                    ("VIBROMETER","진동계 전용. scale 1~9 로 X/Y/Z 최대·최소·평균 중 하나 선택\n  1=X최대, 2=X최소, 3=X평균\n  4=Y최대, 5=Y최소, 6=Y평균\n  7=Z최대, 8=Z최소, 9=Z평균"),
                    ("SM_TAEAM",  "TAEAM 진동계: 원본 그대로, base(리미트) 이상만 (base-5)~base 사이 랜덤으로 낮춤. 비어 두면 75(70~75)"),
                ]
            },
            {
                "title": "원본 미참조 모드 (원본 무시, 자체 생성)",
                "color": "#1E8449",
                "items": [
                    ("V",         "전압형 가라값\n- 90% : base 그대로\n- 7%  : ±0.0001\n- 2.8%: ±0.0002~0.0003\n- 0.2%: +0.0005\nbase = 중심값, scale 미사용, 음수 방지"),
                    ("V_2",       "전압형 가라 V_2 (자글자글)\n- 약 30%: base 그대로\n- 약 45%: ±0.0001 × scale\n- 약 22%: ±0.0002~0.0003 × scale\n- 약 3% : ±0.0005 × scale\nscale 1 → ±0.0001, 10 → ±0.001, 비우면 1\nbase = 중심값, 음수 방지"),
                    ("NM",        "균등 랜덤 노이즈\n결과 = base + uniform(−scale, scale)\n예) base=10, scale=0.5 → 9.5~10.5 랜덤"),
                    ("BASE_RAND", "다른 컬럼값 + 랜덤 노이즈\nbase = 참조 열 번호 (0부터 시작)\nscale = ±폭 (숫자) 또는 VW (전압계 특수 분포)\n예) base=3, scale=0.001 → D열값 ± 0.001"),
                    ("TS",        "TS 센서 가라값 (확률 분포 변동)\n- 70%: ±0.00005 이내\n- 20%: ±0.0002\n- 8% : ±0.0004\n- 2% : ±0.0005~0.0006\nbase = 중심값"),
                    ("EL_LOW",    "저노이즈 경사 가라\n- 98.5%: ±0.0003\n- 1.5% : ±0.001 스파이크\n+ 아주 느린 누적 drift\nbase = 중심값, scale 미사용"),
                    ("EL_NEW",    "경사 가라(매행 미세 뾰족 + 0.0001 drift)\n- 매 행 항상 노이즈 (평탄 없음): 이중곱 → |Δ|≈0.00005~0.0003\n- 드물게 ±0.0001씩 drift (장기≤0.0015)\n- 절대±0.004, scale 비우거나 1, 소수점 4 권장\nbase=중심값"),
                    ("EL_TAEAM",  "TAEAM 경사계 가라 (정규분포)\n결과 = base + 정규분포(0, scale)\nbase = 중심값, scale = 표준편차 (기본 0.001)"),
                    ("EL_STATION","정거장 경사계 가라\n- 60%: ±0.0001 미세 노이즈\n- 30%: 0\n- 10%: ±0.0001~0.0003 스파이크\n+ 드문 누적 drift\nbase = 중심값"),
                    ("EL_TUNNEL", "터널 경사계 가라 (EL_STATION 동일 동작)"),
                    ("CHANG_V",   "9번 열(0-based 인덱스 8, 0=A) 값 × scale\nscale에 배율: 0.2 → 0.2곱, 2 → 2곱, 비어 있으면 1\nbase 미사용"),
                    ("CHANG_V2",  "8번 열(0-based 인덱스 7, 0=A) 값 참조\n|값| ≥ 0.01 이면 × scale, 미만이면 원값 그대로\n원본 0 → 약 90%는 0, 약 10%는 0.001/0.002\nscale에 배율: 0.2 → 0.2곱, 2 → 2곱, 비어 있으면 1\nbase 미사용"),
                    ("DY_V",      "전압형 가라 (0.001 단위 이산)\n0.019~0.022 위주, 가끔 0.016·0.024, 행이 길면 약간 하강\nbase = 시작 중심값 (비우면 0.020)\n예) 0.021, 0.02, 0.022, 0.019 … 랜덤 반복\nscale 미사용"),
                    ("CHANG_SM",  "소음계 가라 (10분 간격 특성)\n평균 55.2 dB, 표준편차 6.1 dB 기반\n시간대별 야간↓ 출근·저녁↑\nbase = 평균값 (권장 55.2), scale = 표준편차 (권장 6.1)"),
                    ("CHANG_SM2", "0-based 8번 행(인덱스 8, 9번째 행)·해당 채널 열 셀값 × base\n→ 그 값을 열 전체에 동일 적용. base=0.98 → 0.98배, 비면 1\n데이터 9행 미만이면 NaN. scale 미사용"),
                    ("CR",        "균열계 가라 (누적 drift)\n5% 확률로 ±0.0001씩 누적 이동\nbase = 시작값"),
                    ("CR_TAEAM",  "TAEAM 균열계 가라\nCR과 동일, 누적 drift 모델\nbase = 시작값"),
                    ("FM",        "유량계 가라 (carry 이어 받기)\n월~토 06~18시 사이에만 증가\nbase = 시작값, scale = 시간당 증가량"),
                    ("RA",        "레일변위계 가라\n행별 미세 떨림 위주(명시적 하락·상승은 매우 희박, 기본 하락 ~행당 0.002%)\n고급: ra_down_prob(0=하락스텝 없음), ra_up_prob, ra_settle(월간 침하, 기본 0)\nbase = 시작값, scale = 행별 노이즈 진폭 (기본 0.015)"),
                    ("L-QM",      "하중계 가라 (점진적 감소 + 소수점 2자리 랜덤)\n결과 = base + 선형감소 + uniform(-scale, scale)\nbase  = 시작 하중값 (예: 2281)\nscale = 노이즈 폭 (기본 1.0 → ±1.0 kg 수준)\n소수점 자리수는 채널설정 소수점 필드에서 2 입력\n고급 옵션:\n  lqm_daily_drift   : 하루 감소량 (기본 -0.5)\n  lqm_rows_per_day  : 하루 행 수 (기본 144 = 10분간격)"),
                    ("ANSAN_WM_GA", "안산 WM 가라 · 전값에 **코드 고정 랜덤**만 더함(시작값 주변 좁은 밴드).\n**scale 비워도 됨**(기본 출렁 폭은 소스 상수). 더 줄이거나 키우려면 scale에 반폭 숫자.\n**base·초기치**로 시작 수준만 맞추면 됨. JSON 불필요."),
                    ("L-KoreaHY", "하중계 가라 KoreaHY형 (미세 감소 추세 + 랜덤 진동)\n예) base=25050, scale=10 → 25040~25060 오르락내리락하며 서서히 감소\n확률 분포:\n  60%: ±scale×0.3 이내 (미세 변화)\n  30%: ±scale×0.7 이내 (중간 변화)\n  10%: ±scale 이내    (큰 변화)\nbase  = 시작 하중값 (예: 25050)\nscale = 최대 진동 폭 (기본 10.0)\n고급 옵션:\n  lqm_daily_drift  : 하루 감소량 (기본 -0.1)\n  lqm_rows_per_day : 하루 행 수 (기본 144 = 10분간격)"),
                    ("ST",        "변형률계 가라 (추세 없이 base 주변 떨림)\n결과 = base + uniform(-scale, scale)\nbase  = 중심값\nscale = 떨림 폭 (기본 1.0)"),
                ]
            },
            {
                "title": "scale 특수값 VW",
                "color": "#784212",
                "items": [
                    ("VW",        "BASE_RAND 모드 전용 특수 분포\n- 85% : 노이즈 0\n- 12% : +0.001\n- 2.5%: +0.002\n- 0.4%: +0.003\n- 0.1%: +0.004\n전압계(V형) 특성 근사 분포"),
                ]
            },
            {
                "title": "TIP",
                "color": "#616A6B",
                "items": [
                    ("모드 변경 시",    "base/scale 입력란이 자동으로 활성/비활성 처리됨"),
                    ("초기치(initial)", "이어쓰기(증분 변환) 시 첫 값의 기준점. 비우면 carry 또는 base 사용"),
                    ("열 인덱스",       "0=A열, 1=B열, …, 16=Q열(CH0), 17=R열(CH1) … 형식\n(COPY / BASE_RAND에서 base에 입력)"),
                ]
            },
        ]

        PAD = 14

        for sec in MANUAL_SECTIONS:
            # 섹션 헤더
            sec_hdr = tk.Frame(inner, bg=sec["color"])
            sec_hdr.pack(fill="x", padx=PAD, pady=(12, 0))
            tk.Label(
                sec_hdr,
                text=f"  {sec['title']}",
                font=("맑은 고딕", 10, "bold"),
                bg=sec["color"], fg="white",
                anchor="w"
            ).pack(fill="x", ipady=5)

            # 항목 행
            for i, (key, desc) in enumerate(sec["items"]):
                row_bg = "#FFFFFF" if i % 2 == 0 else "#EBF5FB"
                row = tk.Frame(inner, bg=row_bg)
                row.pack(fill="x", padx=PAD)

                tk.Label(
                    row,
                    text=key,
                    font=("Consolas", 9, "bold"),
                    bg=row_bg, fg=sec["color"],
                    width=14, anchor="w"
                ).pack(side="left", padx=(8, 4), pady=4)

                tk.Label(
                    row,
                    text=desc,
                    font=("맑은 고딕", 9),
                    bg=row_bg, fg="#2C3E50",
                    anchor="w", justify="left",
                    wraplength=570
                ).pack(side="left", padx=(0, 8), pady=4, fill="x", expand=True)

        # ── 닫기 버튼
        tk.Button(
            win,
            text="닫기",
            command=win.destroy,
            font=("맑은 고딕", 9),
            bg="#95A5A6", fg="white",
            activebackground="#7F8C8D",
            activeforeground="white",
            relief="flat",
            width=12, padx=10, pady=5,
            cursor="hand2"
        ).pack(pady=10)

    def _make_mode_change_handler(self, key, mode_var, base_var, base_entry, scale_entry, tooltip):
        def _handler(*args):
            mode = mode_var.get()
            self.update_param_state(mode, base_entry, scale_entry)
            tooltip.text = MODE_META.get(mode, MODE_META["PASS"])["desc"]
            self._fill_set_base_if_empty(key, mode, base_var)
        return _handler

    # ======================================================
    # 저장 버튼 클릭
    # ======================================================
    def _on_save(self):
        new_cfg = dict(self.file_cfg)

        # 로거 번호 저장
        logger_num_str = self.logger_number_var.get().strip()
        if logger_num_str:
            try:
                new_cfg["__logger_number__"] = int(logger_num_str)
            except ValueError:
                new_cfg["__logger_number__"] = ""
        else:
            new_cfg["__logger_number__"] = ""

        # 비고 저장 (파일별 비고)
        note_text = self.note_text_widget.get("1.0", "end-1c").strip()
        new_cfg["__note__"] = note_text

        if self.is_nb:
            new_cfg["__nb_mode__"] = True
            src = self.file_cfg.get("__nb_source_dir__", "")
            if src:
                new_cfg["__nb_source_dir__"] = src

            if self.nb_limit_enabled_var.get():
                raw = (self.nb_kine_limit_var.get() or "").strip()
                try:
                    kine = float(raw)
                    if kine <= 0:
                        raise ValueError("한도는 0보다 커야 합니다.")
                    new_cfg["__nb_kine_limit__"] = kine
                    new_cfg.pop("__nb_pvs_limit__", None)
                except ValueError:
                    messagebox.showerror(
                        "입력 오류",
                        "Kine 한도를 숫자로 입력하세요.\n예: 0.20 또는 0.25",
                    )
                    return
            else:
                new_cfg.pop("__nb_kine_limit__", None)
                new_cfg.pop("__nb_pvs_limit__", None)
        else:
            # 전역 옵션 저장
            new_cfg["__fill_interval__"] = int(self.fill_interval_var.get())
            new_cfg["__gen_interval__"] = int(self.gen_interval_var.get())
            new_cfg["__align_60__"] = bool(self.align_60_var.get())

            # ---------------- 센서 슬롯 저장 (내장 degreeX/Y + 외장 CH0~7) ----------------
            for key in ("degreeX", "degreeY", *[f"CH{ch}" for ch in range(8)]):
                ui = self.ch_vars[key]
                mode = ui["mode"].get().strip()
                self._fill_set_base_if_empty(key, mode, ui["base"])
                new_cfg[key] = {
                    "mode": mode,
                    "base": ui["base"].get().strip(),
                    "scale": ui["scale"].get().strip(),
                    "post_offset": ui["post_offset"].get().strip(),
                    "decimal": ui["decimal"].get().strip(),
                    "label": ui["label"].get().strip(),
                    "initial": self.file_cfg.get(key, {}).get("initial", ""),
                }

        try:
            self.controller.tree.set_file_config(
                self.company, self.site, self.folder, self.filename, new_cfg
            )
            messagebox.showinfo("저장 완료", "설정이 저장되었습니다.")
            self.controller.ui.refresh_tree()
            self.win.destroy()

        except Exception as e:
            if self.logger:
                self.logger.log(
                    f"[ChannelSettingsUI] 저장 실패: {e}", "ERROR"
                )
            messagebox.showerror("오류", f"저장 중 오류 발생\n{e}")
