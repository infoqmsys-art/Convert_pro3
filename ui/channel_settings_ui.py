import tkinter as tk
from tkinter import ttk, messagebox

class ChannelSettingsUI:
    """파일별 CH0~CH7 설정창"""

    MODES = ["PASS", "SET", "SET_EL", "BASE+RAND"]

    def __init__(self, root, controller, company, folder, filename):
        self.root = root
        self.controller = controller
        self.company = company
        self.folder = folder
        self.filename = filename

        # 기존 설정 읽기
        self.file_cfg = controller.tree.get_file_config(company, folder, filename)

        self.win = tk.Toplevel(root)
        self.win.title(f"채널 설정 - {filename}")
        self.win.geometry("650x350")
        self.win.grab_set()

        self.entries = {}
        self._build_ui()

    def _build_ui(self):
        frame = tk.Frame(self.win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 헤더
        header = ["CH", "Mode", "Base", "Scale", "Label"]
        for col, text in enumerate(header):
            tk.Label(frame, text=text, font=("맑은 고딕", 10, "bold")).grid(row=0, column=col, padx=5, pady=5)

        # 8개 채널 생성
        for ch in range(8):
            row = ch + 1
            ch_name = f"CH{ch}"

            # CH 이름
            tk.Label(frame, text=ch_name).grid(row=row, column=0, padx=5, pady=3)

            # Mode
            mode_var = tk.StringVar()
            mode_combo = ttk.Combobox(frame, textvariable=mode_var, values=self.MODES, state="readonly", width=12)
            mode_combo.grid(row=row, column=1)

            # Base
            base_var = tk.StringVar()
            base_entry = ttk.Entry(frame, textvariable=base_var, width=10)
            base_entry.grid(row=row, column=2)

            # Scale
            scale_var = tk.StringVar()
            scale_entry = ttk.Entry(frame, textvariable=scale_var, width=10)
            scale_entry.grid(row=row, column=3)

            # Label
            label_var = tk.StringVar()
            label_entry = ttk.Entry(frame, textvariable=label_var, width=14)
            label_entry.grid(row=row, column=4)

            # 기존 값 반영
            cfg = self.file_cfg.get(ch_name, {})
            mode_var.set(cfg.get("mode", "PASS"))
            base_var.set(cfg.get("base", ""))
            scale_var.set(cfg.get("scale", ""))
            label_var.set(cfg.get("label", ""))

            # 저장을 위해 dict에 보관
            self.entries[ch_name] = {
                "mode": mode_var,
                "base": base_var,
                "scale": scale_var,
                "label": label_var
            }

        # 저장 버튼
        ttk.Button(self.win, text="저장", command=self._save).pack(pady=10)

    def _save(self):
        """설정 저장 → config.json에 저장"""
        new_cfg = {}

        for ch, data in self.entries.items():
            new_cfg[ch] = {
                "mode": data["mode"].get(),
                "base": data["base"].get(),
                "scale": data["scale"].get(),
                "label": data["label"].get()
            }

        # TreeManager 저장 호출
        self.controller.tree.set_file_config(
            self.company, self.folder, self.filename, new_cfg
        )

        messagebox.showinfo("저장 완료", "채널 설정이 저장되었습니다.")

        # UI 갱신
        self.controller.ui.refresh_tree()

        self.win.destroy()
