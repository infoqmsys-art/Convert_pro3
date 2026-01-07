import os
import tkinter as tk
from tkinter import ttk, messagebox
from copy import deepcopy
from core.sensor_processor import MODE_META
from core.sensor_processor import SensorProcessor


# ======================================================
#  CH 기본 템플릿 (UI 로드 시 사용)
# ======================================================
def default_channel_config():
    return {
        "mode": "PASS",
        "base": "",
        "scale": "",
        "decimal": "",
        "label": "",
        "initial": ""
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

    def __init__(self, root, controller, company, folder, filename):
        self.root = root
        self.controller = controller
        self.company = company
        self.folder = folder
        self.filename = filename

        self.config = controller.config
        self.tree = controller.tree
        self.logger = getattr(controller, "logger", None)
        self.file_processor = controller.file_processor

        # 센서 모드 목록
        self.mode_list = list(MODE_META.keys())

        self.ch_vars = {}

        # Toplevel UI
        self.win = tk.Toplevel(self.root)
        self.win.title(f"채널 설정 - {company}/{folder}/{filename}")
        self.win.grab_set()

        # 파일 설정 로딩
        self._load_file_config()

        # UI 생성
        self._build_ui()

    # ======================================================
    # 파일 설정 로딩
    # ======================================================
    def _load_file_config(self):
        try:
            file_cfg = self.tree.get_file_config(
                self.company, self.folder, self.filename
            )
        except:
            file_cfg = None

        if file_cfg is None:
            file_cfg = self.config.data.get(self.company, {}).get(
                self.folder, {}).get(self.filename, {})

        if not isinstance(file_cfg, dict):
            file_cfg = {}

        # 전역 옵션 기본값
        file_cfg.setdefault("__fill_interval__", 0)
        file_cfg.setdefault("__gen_interval__", 0)

        final_cfg = deepcopy(file_cfg)

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
            merged.setdefault("decimal", "")
            merged.setdefault("label", "")
            merged.setdefault("initial", "")

            # offset 키는 더 이상 사용하지 않음 (정리)
            merged.pop("offset", None)

            final_cfg[key] = merged
            
        self.file_cfg = final_cfg


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
        frame = ttk.Frame(self.win)
        frame.pack(padx=16, pady=16, fill="both", expand=True)

        # 제목
        title = f"{self.company} / {self.folder} / {self.filename}"
        ttk.Label(
            frame, text=title, font=("맑은 고딕", 11, "bold")
        ).grid(row=0, column=0, columnspan=7, pady=(0, 12), sticky="w")

        # ---------------- 전역 옵션 ----------------
        file_opt = ttk.Frame(frame)
        file_opt.grid(row=1, column=0, columnspan=7, pady=(0, 15), sticky="w")

        # 누락 보충
        ttk.Label(file_opt, text="누락 보충:").grid(row=0, column=0, padx=5)

        self.fill_interval_var = tk.IntVar(
            value=self.file_cfg.get("__fill_interval__", 0)
        )

        combo = ttk.Combobox(
            file_opt,
            textvariable=self.fill_interval_var,
            values=[0, 10, 60],
            width=12,
            state="readonly",
        )
        combo.grid(row=0, column=1, padx=5)
        
        # 설명 라벨
        desc_text = {
            0: "비활성화",
            10: "10분 간격",
            60: "60분 간격"
        }.get(self.fill_interval_var.get(), "비활성화")
        
        desc_label = ttk.Label(file_opt, text=f"({desc_text})", foreground="gray")
        desc_label.grid(row=0, column=2, padx=5)
        
        def update_desc(*args):
            val = self.fill_interval_var.get()
            new_text = {0: "비활성화", 10: "10분 간격", 60: "60분 간격"}.get(val, "비활성화")
            desc_label.config(text=f"({new_text})")
        
        self.fill_interval_var.trace_add("write", update_desc)

        # 주기 생성
        ttk.Label(file_opt, text="주기 생성(분):").grid(row=1, column=0, padx=5)

        self.gen_interval_var = tk.IntVar(
            value=self.file_cfg.get("__gen_interval__", 0)
        )

        ttk.Combobox(
            file_opt,
            textvariable=self.gen_interval_var,
            values=[0, 10, 60],
            width=6,
            state="readonly",
        ).grid(row=1, column=1)

        # ---------------- CH header ----------------
        headers = ["채널", "모드", "base", "scale", "소수점", "센서명(label)", "초기치"]
        for i, h in enumerate(headers):
            ttk.Label(frame, text=h).grid(row=2, column=i, padx=4, pady=4)

        # ---------------- 채널 설정 ----------------
        for ch in range(8):
            row = 3 + ch
            key = f"CH{ch}"
            cfg = self.file_cfg[key]

            # 채널명
            ttk.Label(frame, text=key).grid(row=row, column=0)
            
            base_var = tk.StringVar(value=str(cfg["base"]))
            scale_var = tk.StringVar(value=str(cfg["scale"]))
            
            decimal_var = tk.StringVar(value=str(cfg.get("decimal", "")))

            # ===============================
            # 채널 UI 생성 (CH loop 내부)
            # ===============================

            mode_var = tk.StringVar(value=cfg["mode"])
            mode_cb = ttk.Combobox(
                frame,
                textvariable=mode_var,
                values=self.mode_list,
                width=10,
                state="readonly",
            )
            mode_cb.grid(row=row, column=1)

            tooltip = ToolTip(
                mode_cb,
                MODE_META.get(mode_var.get(), MODE_META["PASS"])["desc"]
            )

            base_var = tk.StringVar(value="" if cfg.get("base") is None else str(cfg["base"]))
            base_entry = ttk.Entry(frame, textvariable=base_var, width=10)
            base_entry.grid(row=row, column=2)

            scale_var = tk.StringVar(value="" if cfg.get("scale") is None else str(cfg["scale"]))
            scale_entry = ttk.Entry(frame, textvariable=scale_var, width=10)
            scale_entry.grid(row=row, column=3)

            on_mode_change = self._make_mode_change_handler(
                mode_var,
                base_entry,
                scale_entry,
                tooltip
            )

            mode_cb.bind("<<ComboboxSelected>>", on_mode_change)
            mode_var.trace_add("write", on_mode_change)

            # 초기 상태
            on_mode_change()

            # ===============================
            # ⭐ 초기 상태 반영
            # ===============================
            on_mode_change()
                
            decimal_entry = ttk.Entry(frame, textvariable=decimal_var, width=6)
            decimal_entry.grid(row=row, column=4)

            # label
            label_var = tk.StringVar(value=str(cfg["label"]))
            ttk.Entry(frame, textvariable=label_var, width=18).grid(
                row=row, column=5
            )

            # ⭐ 초기치(initial) 표시 (READ ONLY)
            init_val = cfg.get("initial", "")
            ttk.Label(frame, text=str(init_val), foreground="#666").grid(
                row=row, column=6
            )

            # UI 변수 저장
            self.ch_vars[key] = {
                "mode": mode_var,
                "base": base_var,
                "scale": scale_var,
                "decimal": decimal_var,
                "label": label_var,
            }

        # ---------------- 버튼들 ----------------
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(pady=(10, 8))

        ttk.Button(btn_frame, text="저장", command=self._on_save).pack(
            side="left", padx=5
        )
        ttk.Button(btn_frame, text="닫기", command=self.win.destroy).pack(
            side="left", padx=5
        )

    def _make_mode_change_handler(self, mode_var, base_entry, scale_entry, tooltip):
        def _handler(*args):
            mode = mode_var.get()
            self.update_param_state(mode, base_entry, scale_entry)
            tooltip.text = MODE_META.get(mode, MODE_META["PASS"])["desc"]
        return _handler

    # ======================================================
    # 저장 버튼 클릭
    # ======================================================
    def _on_save(self):
        new_cfg = dict(self.file_cfg)

        new_cfg["__fill_interval__"] = int(self.fill_interval_var.get())
        new_cfg["__gen_interval__"] = int(self.gen_interval_var.get())

        # ---------------- CH 저장 ----------------
        for ch in range(8):
            key = f"CH{ch}"
            ui = self.ch_vars[key]

            # ⭐ initial 값은 절대 덮어쓰면 안됨 → 기존 값 유지
            new_cfg[key] = {
                "mode": ui["mode"].get().strip(),
                "base": ui["base"].get().strip(),
                "scale": ui["scale"].get().strip(),
                "decimal": ui["decimal"].get().strip(),
                "label": ui["label"].get().strip(),
                "initial": self.file_cfg[key].get("initial", "")
            }

        try:
            self.controller.tree.set_file_config(
                self.company, self.folder, self.filename, new_cfg
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
