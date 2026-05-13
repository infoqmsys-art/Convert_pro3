import os
import sys
import time
import threading
import datetime
import json
import requests
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, simpledialog

_SCRIPT_DIR = Path(__file__).resolve().parent
_DESKTOP_API_JSON = _SCRIPT_DIR / "qm_desktop_api.json"


def _load_desktop_api_cfg():
    """모니터링 서버(Convert Pro 웹) QM API + 로컬 SQLite."""
    if not _DESKTOP_API_JSON.exists():
        return None
    try:
        with open(_DESKTOP_API_JSON, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return None
        base = str(d.get("api_base") or "").strip().rstrip("/")
        token = str(d.get("api_token") or "").strip()
        if not base:
            return None
        return {"api_base": base, "api_token": token}
    except Exception:
        return None


DESKTOP_API = _load_desktop_api_cfg()
if DESKTOP_API is None:
    print(
        "[큐엠원격] qm_desktop_api.json 이 없습니다. qm_desktop_api.json.example 을 복사해 api_base·api_token 을 채우세요.",
        flush=True,
    )
    sys.exit(1)

# ==========================
# 관리자 비밀번호 — monitoring/server.py 의 QM_REMOTE_DEFAULT_SESSION_ADMIN_PW(1524)와 같게 유지
ADMIN_PASSWORD = "1524"


DEFAULT_SERVER_LIST = [
    "큐엠메인서버1",
    "큐엠메인서버2",
    "큐엠메인서버3",
    "큐엠메인서버5",
]

PC_ID = os.environ.get("COMPUTERNAME", "UNKNOWN_PC")


def _api_headers():
    h = {"X-QM-Client-PC-ID": PC_ID}
    if DESKTOP_API.get("api_token"):
        h["X-QM-Remote-Token"] = DESKTOP_API["api_token"]
    return h


def _fetch_api_server_list():
    try:
        r = requests.get(
            f"{DESKTOP_API['api_base']}/api/qm-remote/config",
            headers=_api_headers(),
            timeout=8,
        )
        if r.status_code != 200:
            return None
        d = r.json()
        if not d.get("ok"):
            return None
        raw = d.get("servers")
        if not isinstance(raw, list):
            return None
        out = [str(x).strip() for x in raw if str(x).strip()]
        return out if out else None
    except Exception:
        return None


def _resolve_server_list():
    remote = _fetch_api_server_list()
    if remote:
        return list(remote)
    print("[큐엠원격] API에서 메인서버 목록을 가져오지 못했습니다. 기본 목록을 사용합니다.", flush=True)
    return list(DEFAULT_SERVER_LIST)


SERVER_LIST = _resolve_server_list()

current_user_name = ""

server_states = {
    name: {"status": "OFF", "user": "", "timestamp": ""}
    for name in SERVER_LIST
}

server_notes = {name: "" for name in SERVER_LIST}

server_widgets = {}


def get_servers_state():
    try:
        r = requests.get(
            f"{DESKTOP_API['api_base']}/api/qm-remote/status",
            headers=_api_headers(),
            timeout=5,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        if not data.get("ok"):
            return {}
        out = {}
        for row in data.get("rows") or []:
            name = row.get("server_name")
            if not name:
                continue
            out[name] = {
                "status": row.get("status") or "OFF",
                "user": row.get("user") or "",
                "timestamp": row.get("timestamp") or "",
            }
            if name in SERVER_LIST:
                server_notes[name] = str(row.get("note") or "")
        return out
    except Exception:
        return {}


def put_server_state(server_name: str, state: dict):
    """사용 시작: 성공 시 (True, ''), 실패 시 (False, 에러문구). 사용 종료: (True, '') best-effort."""
    b = DESKTOP_API["api_base"]
    on = str((state or {}).get("status") or "OFF").upper() == "ON"
    if on:
        try:
            r = requests.post(
                f"{b}/api/qm-remote/session/start",
                json={"server_name": server_name},
                headers=_api_headers(),
                timeout=5,
            )
            if r.status_code == 200:
                d = r.json()
                if d.get("ok"):
                    return True, ""
            try:
                d = r.json()
                msg = str(d.get("error") or "").strip()
            except Exception:
                msg = ""
            if not msg:
                msg = f"HTTP {r.status_code}"
            return False, msg
        except Exception as e:
            return False, str(e) or "네트워크 오류"
    try:
        prev_user = (server_states.get(server_name) or {}).get("user") or ""
        me = get_effective_username()
        body = {"server_name": server_name}
        if prev_user and prev_user != me:
            body["admin_password"] = ADMIN_PASSWORD
        requests.post(
            f"{b}/api/qm-remote/session/stop",
            json=body,
            headers=_api_headers(),
            timeout=5,
        )
    except Exception:
        pass
    return True, ""


def get_pc_config():
    try:
        r = requests.get(
            f"{DESKTOP_API['api_base']}/api/qm-remote/config",
            headers=_api_headers(),
            timeout=5,
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("ok"):
                name = str(d.get("my_pc_display_name") or "").strip()
                return {"name": name}
    except Exception:
        pass
    return {}


def put_pc_config(name: str):
    try:
        requests.post(
            f"{DESKTOP_API['api_base']}/api/qm-remote/my-pc",
            json={"display_name": name},
            headers=_api_headers(),
            timeout=5,
        )
    except Exception:
        pass


def save_server_note(server_name: str, note: str):
    try:
        requests.post(
            f"{DESKTOP_API['api_base']}/api/qm-remote/note",
            json={"server_name": server_name, "note": note},
            headers=_api_headers(),
            timeout=5,
        )
    except Exception:
        pass


def load_server_notes():
    global server_notes
    data = get_servers_state()
    if isinstance(data, dict):
        for name in SERVER_LIST:
            if name in data:
                server_states[name] = data[name]


# ==========================
# 유틸
# ==========================

def get_effective_username():
    return current_user_name.strip() if current_user_name.strip() else PC_ID


def is_this_pc_in_use():
    me = get_effective_username()
    for name, state in server_states.items():
        if state["status"] == "ON" and state["user"] == me:
            return True
    return False


# ==========================
# 관리자 비밀번호 팝업
# ==========================

def ask_admin_password():
    pw = simpledialog.askstring(
        "관리자 인증",
        "관리자 비밀번호를 입력하세요:",
        show="*"
    )
    if pw is None:
        return False
    return pw == ADMIN_PASSWORD


# ==========================
# 강제 종료 처리
# ==========================

def force_stop(server_name: str):
    """관리자 강제 종료"""
    if not ask_admin_password():
        messagebox.showerror("오류", "비밀번호가 올바르지 않습니다.")
        return

    new_state = {"status": "OFF", "user": "", "timestamp": ""}
    put_server_state(server_name, new_state)  # 종료는 API best-effort
    server_states[server_name] = new_state
    update_single_server_ui(server_name)
    messagebox.showinfo("완료", f"{server_name} 강제 종료되었습니다.")


# ==========================
# 정상 종료 처리
# ==========================

def normal_stop(server_name: str):
    new_state = {"status": "OFF", "user": "", "timestamp": ""}
    put_server_state(server_name, new_state)
    server_states[server_name] = new_state
    update_single_server_ui(server_name)


# ==========================
# 버튼 동작
# ==========================

def on_start(server_name: str):
    state = server_states.get(server_name, {})
    me = get_effective_username()

    if state.get("status") == "ON":
        if state.get("user") == me:
            messagebox.showinfo("안내", f"이미 「{server_name}」에서 사용 중입니다.")
        else:
            messagebox.showwarning(
                "사용 중",
                f"{server_name}은(는) 현재 {state.get('user','')} 님이 사용 중입니다.",
            )
        return

    for name, st in server_states.items():
        if name == server_name:
            continue
        if st.get("status") == "ON" and st.get("user") == me:
            messagebox.showwarning(
                "다른 방 사용 중",
                f"이미 「{name}」에서 원격을 사용 중입니다.\n먼저 그쪽에서 사용 종료한 뒤 시작하세요.",
            )
            return

    new_state = {
        "status": "ON",
        "user": me,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    ok, err = put_server_state(server_name, new_state)
    if not ok:
        messagebox.showerror("사용 시작 실패", err or "서버와 통신하지 못했습니다.")
        return
    server_states[server_name] = new_state
    update_single_server_ui(server_name)


def on_stop(server_name: str):
    state = server_states.get(server_name, {})

    if state.get("status") != "ON":
        messagebox.showinfo("정보", "현재 사용 중이 아닙니다.")
        return

    my_name = get_effective_username()

    if state.get("user") == my_name:
        normal_stop(server_name)
    else:
        # 관리자 비밀번호 필요
        force_stop(server_name)


# ==========================
# 설정창
# ==========================

def open_settings_window():
    if is_this_pc_in_use():
        messagebox.showwarning("변경 불가", "현재 사용 중일 때는 이름을 변경할 수 없습니다.")
        return

    win = tk.Toplevel(root)
    win.title("설정")
    win.configure(bg="white")

    tk.Label(win, text="PC ID: " + PC_ID, bg="white").pack(pady=5)

    tk.Label(win, text="PC 표시 이름:", bg="white").pack()

    var = tk.StringVar()
    var.set(current_user_name)
    entry = tk.Entry(win, textvariable=var)
    entry.pack(pady=5)

    def save():
        global current_user_name
        current_user_name = var.get().strip()
        put_pc_config(current_user_name)
        root.title(f"큐엠 원격 모니터링 — API - {get_effective_username()}")
        win.destroy()

    tk.Button(win, text="저장", command=save).pack(pady=10)
    win.grab_set()


def load_initial_pc_name():
    global current_user_name
    cfg = get_pc_config()
    current_user_name = cfg.get("name", "").strip()
    suffix = " — API"
    root.title(f"큐엠 원격 모니터링{suffix} - {get_effective_username()}")


# ==========================
# UI 업데이트
# ==========================

def update_single_server_ui(server_name: str):
    state = server_states.get(server_name, {})
    widgets = server_widgets.get(server_name)
    if not widgets:
        return

    status = state.get("status", "OFF")
    user = state.get("user", "")
    timestamp = state.get("timestamp", "")
    status_label = widgets["status_label"]
    note_label = widgets["note_label"]

    if status == "ON":
        try:
            start_dt = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            diff = datetime.datetime.now() - start_dt
            mins = diff.seconds // 60
            time_str = f"{mins}분 경과"
        except:
            time_str = ""

        status_label.config(
            text=f"🟢 사용 중 ({user}) - {time_str}",
            bg="#E1F8E8",
            fg="#006622",
        )

        note_label.config(
            text=server_notes.get(server_name, "(없음)").strip() or "(없음)"
        )

    else:
        status_label.config(
            text="⚪ 사용 가능",
            bg="#F0F0F0",
            fg="#333333",
        )
        note_label.config(
            text=server_notes.get(server_name, "(없음)").strip() or "(없음)"
        )


def update_all_servers_ui():
    for name in SERVER_LIST:
        update_single_server_ui(name)

    if is_this_pc_in_use():
        settings_btn.config(state="disabled")
    else:
        settings_btn.config(state="normal")


# ==========================
# Polling 스레드
# ==========================

def polling_thread():
    global server_states

    while True:
        data = get_servers_state()
        if isinstance(data, dict):
            updated = False

            for name in SERVER_LIST:
                new = data.get(name, {"status": "OFF", "user": "", "timestamp": ""})
                if server_states[name] != new:
                    server_states[name] = new
                    updated = True

            if updated:
                root.after(0, update_all_servers_ui)

        time.sleep(1)


# ==========================
# UI 구성
# ==========================

root = tk.Tk()
root.title("큐엠 원격 모니터링")
root.configure(bg="#F2F2F7")

header = tk.Label(
    root,
    text="큐엠 원격 모니터링",
    font=("맑은 고딕", 16, "bold"),
    bg="#F2F2F7",
    fg="#333"
)
header.pack(pady=(15, 5))

main = tk.Frame(root, bg="#F2F2F7")
main.pack(fill="both", expand=True, padx=15, pady=10)


def create_card(parent, name, r, c):
    frame = tk.Frame(parent, bg="white", bd=1, relief="solid")
    frame.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")

    parent.grid_rowconfigure(r, weight=1)
    parent.grid_columnconfigure(c, weight=1)

    tk.Label(
        frame,
        text=name,
        font=("맑은 고딕", 12, "bold"),
        bg="white",
        fg="#333"
    ).pack(anchor="w", padx=15, pady=(12, 3))

    tk.Frame(frame, bg="#DDD", height=1).pack(fill="x", padx=15, pady=(0, 8))

    status_label = tk.Label(
        frame,
        text="⚪ 사용 가능",
        bg="#F0F0F0",
        fg="#333",
        font=("맑은 고딕", 10, "bold"),
        anchor="w",
        padx=10,
        pady=4
    )
    status_label.pack(fill="x", padx=15)

    note_box = tk.Frame(frame, bg="#F7F7F7", bd=1, relief="solid")
    note_box.pack(fill="both", padx=15, pady=10, expand=True)

    tk.Label(
        note_box,
        text="비고",
        bg="#F7F7F7",
        fg="#444",
        font=("맑은 고딕", 10, "bold"),
    ).pack(anchor="w", padx=10, pady=(8, 2))

    note_label = tk.Label(
        note_box,
        text="(없음)",
        bg="#F7F7F7",
        fg="#555",
        anchor="w",
        justify="left",
    )
    note_label.pack(fill="both", padx=10, pady=(0, 8))

    btn_area = tk.Frame(frame, bg="white")
    btn_area.pack(anchor="w", padx=15, pady=(0, 10))

    tk.Button(
        btn_area,
        text="사용 시작",
        command=lambda n=name: on_start(n),
        bg="#4A90E2",
        fg="white",
        padx=12,
        pady=5,
        bd=0,
        font=("맑은 고딕", 10, "bold")
    ).pack(side="left", padx=(0, 7))

    tk.Button(
        btn_area,
        text="사용 종료",
        command=lambda n=name: on_stop(n),
        bg="#D0021B",
        fg="white",
        padx=12,
        pady=5,
        bd=0,
        font=("맑은 고딕", 10, "bold")
    ).pack(side="left", padx=(0, 7))

    tk.Button(
        btn_area,
        text="비고 편집",
        command=lambda n=name: edit_note_window(n),
        bg="#7B8D93",
        fg="white",
        padx=12,
        pady=5,
        bd=0,
        font=("맑은 고딕", 10, "bold")
    ).pack(side="left")


    server_widgets[name] = {
        "status_label": status_label,
        "note_label": note_label,
    }


def edit_note_window(server_name):
    win = tk.Toplevel(root)
    win.title(f"{server_name} 비고 수정")
    win.configure(bg="white")

    tk.Label(win, text="비고 입력:", bg="white").pack(pady=5, anchor="w", padx=10)

    var = tk.StringVar()
    var.set(server_notes.get(server_name, ""))

    entry = tk.Entry(win, textvariable=var, width=40)
    entry.pack(padx=10, pady=5)

    def save():
        server_notes[server_name] = var.get().strip()
        save_server_note(server_name, server_notes[server_name])
        update_single_server_ui(server_name)
        win.destroy()

    tk.Button(
        win, text="저장", command=save,
        bg="#4A90E2", fg="white",
        bd=0, padx=15, pady=6
    ).pack(pady=10)

    win.grab_set()


for i, name in enumerate(SERVER_LIST):
    create_card(main, name, i // 2, i % 2)


# 설정 버튼
bottom = tk.Frame(root, bg="#F2F2F7")
bottom.pack(fill="x", pady=(0, 10), padx=15)

settings_btn = tk.Button(
    bottom,
    text="설정 (PC 이름)",
    command=open_settings_window,
    bg="white",
    fg="#333",
    bd=1,
    relief="solid",
    padx=12,
    pady=5
)
settings_btn.pack(side="right")


# 초기화
load_initial_pc_name()
load_server_notes()
update_all_servers_ui()

# Polling
threading.Thread(target=polling_thread, daemon=True).start()

root.mainloop()
