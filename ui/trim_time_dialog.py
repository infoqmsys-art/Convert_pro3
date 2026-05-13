"""
변환본 시간 이후 삭제 - 날짜/시간 선택 다이얼로그
화살표로 조정 가능한 Spinbox UI
"""

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from datetime import datetime
from typing import Optional


def parse_datetime_safe(s: str) -> Optional[datetime]:
    """안전한 시간 파싱. 형식: YYYY-MM-DD HH:MM"""
    if not s or not s.strip():
        return None
    s = s.strip()
    try:
        return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        pass
    return None


def show_trim_time_dialog(parent, initial_value: Optional[str] = None) -> Optional[str]:
    """
    삭제 시작 시간 선택 다이얼로그.
    Returns: "YYYY-MM-DD HH:MM" 형식 문자열 또는 None(취소)
    """
    now = datetime.now()
    dt = parse_datetime_safe(initial_value) if initial_value else None
    if dt is None:
        dt = now.replace(minute=0, second=0, microsecond=0)

    result = [None]  # mutable로 결과 전달

    win = tk.Toplevel(parent)
    win.title("변환본 시간 이후 삭제")
    win.geometry("320x160")
    win.resizable(False, False)
    win.transient(parent)
    win.grab_set()
    # 프로그램(부모) 창 위에 띄움
    win.update_idletasks()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    px, py = parent.winfo_x(), parent.winfo_y()
    ww, wh = 320, 160
    x = px + max(0, (pw - ww) // 2)
    y = py + max(0, (ph - wh) // 2)
    win.geometry(f"+{x}+{y}")

    main = ttk.Frame(win, padding=15)
    main.pack(fill="both", expand=True)

    ttk.Label(main, text="삭제할 시작 시간 (해당 시각부터 끝까지 삭제)", font=("맑은 고딕", 9)).pack(anchor="w")

    row = ttk.Frame(main)
    row.pack(fill="x", pady=(10, 5))

    def make_spin(parent_frame, from_, to, initial, width=5, cmd=None):
        var = tk.StringVar(value=str(initial))
        sb = tk.Spinbox(
            parent_frame, from_=from_, to=to,
            textvariable=var, width=width, font=("맑은 고딕", 10),
            command=cmd
        )
        sb.pack(side="left", padx=2)
        return var

    ttk.Label(row, text="년").pack(side="left")
    y_var = make_spin(row, 2000, 2100, dt.year, 5)
    ttk.Label(row, text="월").pack(side="left", padx=(8, 0))
    m_var = make_spin(row, 1, 12, dt.month, 3)
    ttk.Label(row, text="일").pack(side="left", padx=(8, 0))
    d_var = make_spin(row, 1, 31, dt.day, 3)

    row2 = ttk.Frame(main)
    row2.pack(fill="x", pady=5)
    ttk.Label(row2, text="시").pack(side="left")
    h_var = make_spin(row2, 0, 23, dt.hour, 3)
    ttk.Label(row2, text="분").pack(side="left", padx=(8, 0))
    min_var = make_spin(row2, 0, 59, dt.minute, 3)

    def build_result():
        try:
            y, m, d = int(y_var.get()), int(m_var.get()), int(d_var.get())
            h, mi = int(h_var.get()), int(min_var.get())
            # 유효한 날짜인지 검사
            datetime(y, m, d, h, mi)
            return f"{y:04d}-{m:02d}-{d:02d} {h:02d}:{mi:02d}"
        except (ValueError, TypeError):
            return None

    def on_ok():
        s = build_result()
        if s:
            result[0] = s
            win.destroy()
        else:
            messagebox.showwarning("입력 오류", "올바른 날짜/시간을 입력해주세요.", parent=win)

    def on_cancel():
        win.destroy()

    btn_frame = ttk.Frame(main)
    btn_frame.pack(fill="x", pady=(15, 0))
    ttk.Button(btn_frame, text="확인", command=on_ok).pack(side="right", padx=4)
    ttk.Button(btn_frame, text="취소", command=on_cancel).pack(side="right")

    win.protocol("WM_DELETE_WINDOW", on_cancel)
    win.focus_force()

    win.wait_window()
    return result[0]
