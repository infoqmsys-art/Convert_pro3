"""
데이터수집프로그램 — 웹(DB)에 등록된 로거를 표시하고 CSV 경로를 지정·주기 적재.

- 웹에서 로거를 추가한 뒤에는 「DB 목록 새로고침」 또는 순환 실행 시(목록 먼저 갱신) 반영됩니다.
- 파일경로: 한 번 클릭 → 경로 입력·수정·비우기 다이얼로그 / 더블클릭 → CSV 파일 선택 후 DB 저장.
- 사용: 해당 열 클릭 → `is_active` 토글.
- 순환: 활성 로거·유효한 파일 경로에 대해 `ingest_csv_for_logger` 호출(센서 열은 웹 센서설정과 동일).
- 순환 대기 중에는 다음 실행까지 남은 시간이 표시되고, 적재 중에는 CSV 물리 행 번호 기준으로 스캔 줄이 올라가며 현재 로거 행이 강조됩니다.
"""
from __future__ import annotations

import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

_PORTAL_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_PORTAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_PORTAL_ROOT))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import db  # noqa: E402

from measurement_ingest import ingest_csv_for_logger  # noqa: E402

try:
    import collector_version  # noqa: E402
except ImportError:
    collector_version = None  # type: ignore


COLS = (
    "site_name",
    "site_code",
    "logger_name",
    "use",
    "folder_path",
    "logger_kind",
    "serial",
    "memo",
    "updated",
    "xfer",
)

HEADINGS_KO = {
    "site_name": "현장명",
    "site_code": "현장코드",
    "logger_name": "로거명",
    "use": "사용",
    "folder_path": "파일경로",
    "logger_kind": "로거종류",
    "serial": "로거번호",
    "memo": "메모",
    "updated": "업데이트",
    "xfer": "전송크기",
}

_KIND_TO_KO = {"manual": "수동계측", "ftp": "FTP", "other": "기타"}


def _kind_label(kind: str | None) -> str:
    k = (kind or "manual").strip().lower()
    return _KIND_TO_KO.get(k, k or "—")


def _format_bytes(n: int | None) -> str:
    if n is None:
        return ""
    if n < 1024:
        return f"{n} byte"
    return f"{n / 1024.0:.1f} KB"


def _load_logger_rows() -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            """
            SELECT ld.id, ld.name AS logger_name, ld.folder_path, ld.logger_kind,
                   ld.serial_number, ld.is_active, ld.memo,
                   ld.last_comm_at, ld.last_ingest_at, ld.last_ingest_bytes,
                   s.name AS site_name, s.site_code
            FROM logger_device ld
            JOIN site s ON s.id = ld.site_id
            ORDER BY s.name COLLATE NOCASE, ld.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _row_to_values(r: dict) -> tuple:
    active = int(r.get("is_active") or 0)
    use_mark = "✓" if active else ""
    upd = (r.get("last_ingest_at") or r.get("last_comm_at") or "").strip()
    xfer = _format_bytes(r.get("last_ingest_bytes"))
    return (
        (r.get("site_name") or "").strip(),
        (r.get("site_code") or "").strip(),
        (r.get("logger_name") or "").strip(),
        use_mark,
        (r.get("folder_path") or "").strip(),
        _kind_label(r.get("logger_kind")),
        (r.get("serial_number") or "").strip(),
        (r.get("memo") or "").strip(),
        upd,
        xfer,
    )


def run_gui() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk
        from tkinter.scrolledtext import ScrolledText
    except ImportError as exc:
        print(
            "Tkinter를 사용할 수 없습니다. Python 설치 시 tcl/tk 포함 여부를 확인하세요.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    db.init_database()

    cv = collector_version
    title_lbl = (
        f"{cv.PRODUCT_NAME} ({cv.VERSION_LABEL})"
        if cv
        else "데이터수집프로그램 (dev)"
    )
    root = tk.Tk()
    root.title(title_lbl)
    root.minsize(960, 520)
    root.geometry("1100x720")

    polling_enabled = {"v": False}
    poll_after_id: dict[str, int | None] = {"id": None}
    idle_tick_after_id: dict[str, int | None] = {"id": None}
    next_cycle_deadline_s: dict[str, float | None] = {"t": None}
    ingest_lock = threading.Lock()
    ingest_busy = {"v": False}

    top = ttk.Frame(root, padding=(8, 6))
    top.pack(fill=tk.X)

    def toggle_poll() -> None:
        polling_enabled["v"] = not polling_enabled["v"]
        if not polling_enabled["v"]:
            btn_stop.configure(text="순환 시작")
            if poll_after_id["id"] is not None:
                root.after_cancel(poll_after_id["id"])
                poll_after_id["id"] = None
            cancel_idle_tick()
            next_cycle_deadline_s["t"] = None
            poll_status_var.set("")
            append_log("[순환] 중지됨.")
        else:
            btn_stop.configure(text="순환 중지")
            append_log("[순환] 시작 — 즉시 1회 실행 후, 설정한 주기마다 반복합니다.")
            kick_polling_round()

    btn_stop = ttk.Button(top, text="순환 시작", command=toggle_poll)
    btn_stop.pack(side=tk.LEFT, padx=(0, 12))

    ttk.Label(top, text="순환 주기(분)").pack(side=tk.LEFT)
    interval_var = tk.IntVar(value=5)
    sp = ttk.Spinbox(top, from_=1, to=120, width=5, textvariable=interval_var)
    sp.pack(side=tk.LEFT, padx=(4, 16))

    ttk.Label(top, text="인코딩").pack(side=tk.LEFT)
    enc_var = tk.StringVar(value="utf-8-sig")
    ttk.Combobox(
        top,
        textvariable=enc_var,
        values=("utf-8-sig", "utf-8", "cp949", "euc-kr"),
        width=11,
        state="readonly",
    ).pack(side=tk.LEFT, padx=(4, 16))

    full_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(top, text="전체 재적재", variable=full_var).pack(side=tk.LEFT, padx=(0, 12))

    tree_frm = ttk.Frame(root, padding=(8, 0))
    tree_frm.pack(fill=tk.BOTH, expand=True)
    tree = ttk.Treeview(tree_frm, columns=COLS, show="headings", selectmode="browse")
    vsb = ttk.Scrollbar(tree_frm, orient=tk.VERTICAL, command=tree.yview)
    hsb = ttk.Scrollbar(tree_frm, orient=tk.HORIZONTAL, command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    widths = {
        "site_name": 200,
        "site_code": 90,
        "logger_name": 100,
        "use": 44,
        "folder_path": 320,
        "logger_kind": 88,
        "serial": 80,
        "memo": 100,
        "updated": 140,
        "xfer": 90,
    }
    for c in COLS:
        tree.heading(c, text=HEADINGS_KO[c])
        tree.column(c, width=widths[c], minwidth=40, stretch=(c == "folder_path"))

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    tree_frm.grid_rowconfigure(0, weight=1)
    tree_frm.grid_columnconfigure(0, weight=1)

    preview_frm = ttk.LabelFrame(root, text="실시간 파일 스캔 (CSV 위에서 아래로 읽는 진행)")
    preview_frm.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 4))
    preview_box = ScrolledText(
        preview_frm,
        height=8,
        wrap=tk.NONE,
        state=tk.DISABLED,
        font=("Consolas", 9),
    )
    preview_box.pack(fill=tk.BOTH, expand=True)

    status_frm = ttk.Frame(root, padding=(8, 0))
    status_frm.pack(fill=tk.X)
    scan_status_var = tk.StringVar(
        value="대기 중 — 「지금 한 번 순환」으로 즉시 실행하거나 「순환 시작」으로 주기 실행합니다."
    )
    poll_status_var = tk.StringVar(value="")
    ttk.Label(status_frm, textvariable=scan_status_var, wraplength=1040).pack(
        anchor=tk.W
    )
    ttk.Label(status_frm, textvariable=poll_status_var, wraplength=1040).pack(
        anchor=tk.W
    )

    btn_row = ttk.Frame(root, padding=(8, 4))
    btn_row.pack(fill=tk.X)

    log_box = ScrolledText(root, height=10, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
    log_box.pack(fill=tk.BOTH, expand=False, padx=8, pady=(4, 8))

    def append_log(line: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_box.configure(state=tk.NORMAL)
        log_box.insert(tk.END, f"{ts}  {line}\n")
        log_box.see(tk.END)
        log_box.configure(state=tk.DISABLED)

    def refresh_table() -> None:
        tree.delete(*tree.get_children())
        for r in _load_logger_rows():
            tree.insert("", tk.END, iid=str(r["id"]), values=_row_to_values(r))

    def log_from_thread(msg: str) -> None:
        root.after(0, lambda m=msg: append_log(m))

    def refresh_table_from_thread() -> None:
        root.after(0, refresh_table)

    def cancel_idle_tick() -> None:
        if idle_tick_after_id["id"] is not None:
            root.after_cancel(idle_tick_after_id["id"])
            idle_tick_after_id["id"] = None

    def arm_poll_countdown() -> None:
        cancel_idle_tick()

        def tick() -> None:
            idle_tick_after_id["id"] = None
            if not polling_enabled["v"]:
                poll_status_var.set("")
                return
            if ingest_busy["v"]:
                poll_status_var.set(
                    "순환 모드: 이번 차례 수집이 끝나면 다음 실행까지 남은 시간이 표시됩니다."
                )
                idle_tick_after_id["id"] = root.after(450, tick)
                return
            dl = next_cycle_deadline_s.get("t")
            if dl is None:
                poll_status_var.set("순환: 다음 회차 시각을 잡는 중…")
                idle_tick_after_id["id"] = root.after(450, tick)
                return
            left = max(0, int(dl - time.time()))
            mm, ss = divmod(left, 60)
            poll_status_var.set(
                f"순환 대기 중 · 다음 실행까지 약 {mm}:{ss:02d} "
                f"(주기 {max(1, int(interval_var.get()))}분)"
            )
            idle_tick_after_id["id"] = root.after(1000, tick)

        tick()

    def trim_preview_widget(box: ScrolledText, max_lines: int = 200) -> None:
        box.configure(state=tk.NORMAL)
        try:
            while True:
                end_ln_s = box.index("end-1c")
                end_ln = int(float(end_ln_s.split(".")[0]))
                if end_ln <= max_lines:
                    break
                box.delete("1.0", "2.0")
        finally:
            box.configure(state=tk.DISABLED)

    def apply_progress_ui(logger_id: int, p: dict) -> None:
        phase = str(p.get("phase") or "")
        site = str(p.get("site_name") or "")
        lname = str(p.get("logger_name") or "")
        fn = str(p.get("file_name") or "")
        pl = int(p.get("physical_line") or 0)
        tok = int(p.get("time_ok_total") or 0)
        lo = str(p.get("last_observed") or "")
        pv = str(p.get("preview") or "").strip()

        try:
            tree.selection_set(str(logger_id))
            tree.focus(str(logger_id))
            tree.see(str(logger_id))
        except tk.TclError:
            pass

        if phase == "open":
            scan_status_var.set(f"📂 읽기 시작 │ {site} · {lname} │ {fn}")
            line = f"── 열음 │ {site} · {lname} │ {fn}\n"
        elif phase == "scan":
            scan_status_var.set(
                f"📖 스캔 중 │ {lname} │ 물리 행 약 {pl:,} │ "
                f"시각 파싱 누적 {tok:,}행 │ 마지막 시각 {lo or '—'}"
            )
            line = f"  행 {pl:,} │ 시각행 누적 {tok:,} │ {lo or '—'}\n"
            if pv:
                line += f"    └ {pv}\n"
        elif phase == "done":
            scan_status_var.set(
                f"✓ 스캔 완료 │ {lname} │ 물리 행 ~{pl:,} │ 시각 파싱 행 {tok:,}"
            )
            line = f"── 완료 │ 물리 행 ~{pl:,} │ 시각 파싱 {tok:,}행 │ 마지막 {lo or '—'}\n\n"
        else:
            line = f"{p}\n"

        preview_box.configure(state=tk.NORMAL)
        preview_box.insert(tk.END, line)
        trim_preview_widget(preview_box, 200)
        preview_box.see(tk.END)
        preview_box.configure(state=tk.DISABLED)

    def enqueue_progress(logger_id: int, site: str, name: str, payload: dict) -> None:
        pl = dict(payload)
        pl["site_name"] = site
        pl["logger_name"] = name
        root.after(0, lambda lid=logger_id, px=pl: apply_progress_ui(lid, px))

    def toggle_use(logger_id: int) -> None:
        row = next((x for x in _load_logger_rows() if int(x["id"]) == logger_id), None)
        if not row:
            return
        cur = int(row.get("is_active") or 0)
        newv = 0 if cur else 1
        db.update_logger(logger_id, is_active=newv)
        refresh_table()
        append_log(f"[설정] 로거 id={logger_id} 사용={'ON' if newv else 'OFF'}")

    def pick_file(logger_id: int) -> None:
        path = filedialog.askopenfilename(
            title="측정 파일 선택 (CSV/TXT)",
            filetypes=[
                ("CSV/TXT", "*.csv *.txt"),
                ("CSV", "*.csv"),
                ("TXT", "*.txt"),
                ("모든 파일", "*.*"),
            ],
        )
        if not path:
            return
        db.update_logger(logger_id, folder_path=path)
        refresh_table()
        append_log(f"[경로] 로거 id={logger_id} → {path}")

    path_edit_after_id: dict[str, int | None] = {"id": None}

    def cancel_path_edit_schedule() -> None:
        if path_edit_after_id["id"] is not None:
            root.after_cancel(path_edit_after_id["id"])
            path_edit_after_id["id"] = None

    def edit_folder_path_dialog(logger_id: int, current: str) -> None:
        top = tk.Toplevel(root)
        top.title("파일 경로 편집")
        top.transient(root)
        top.grab_set()
        top.geometry("720x120")
        v = tk.StringVar(value=current or "")
        row0 = ttk.Frame(top, padding=(8, 8))
        row0.pack(fill=tk.X)
        ttk.Label(row0, text="파일 경로 (CSV/TXT, 직접 수정 가능)").pack(anchor=tk.W)
        ent = ttk.Entry(row0, textvariable=v, width=100)
        ent.pack(fill=tk.X, pady=(4, 0))
        ent.focus_set()

        def save() -> None:
            p = (v.get() or "").strip()
            db.update_logger(logger_id, folder_path=p)
            refresh_table()
            if p:
                append_log(f"[경로] 로거 id={logger_id} 저장: {p}")
            else:
                append_log(f"[경로] 로거 id={logger_id} — 경로 비움")
            top.destroy()

        def clear_path() -> None:
            v.set("")

        def browse() -> None:
            path = filedialog.askopenfilename(
                parent=top,
                title="측정 파일 선택 (CSV/TXT)",
                filetypes=[
                    ("CSV/TXT", "*.csv *.txt"),
                    ("CSV", "*.csv"),
                    ("TXT", "*.txt"),
                    ("모든 파일", "*.*"),
                ],
            )
            if path:
                v.set(path)

        def on_return(_e: tk.Event) -> str:
            save()
            return "break"

        ent.bind("<Return>", on_return)

        btns = ttk.Frame(top, padding=(8, 0, 8, 8))
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="찾아보기", command=browse).pack(side=tk.LEFT)
        ttk.Button(btns, text="경로 비우기", command=clear_path).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="취소", command=top.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="저장", command=save).pack(side=tk.RIGHT, padx=(0, 8))

    def on_tree_click(event) -> None:
        if tree.identify_region(event.x, event.y) != "cell":
            return
        col = tree.identify_column(event.x)
        item = tree.identify_row(event.y)
        if not item:
            cancel_path_edit_schedule()
            return
        try:
            lid = int(item)
        except ValueError:
            return
        if col != "#5":
            cancel_path_edit_schedule()
        if col == "#4":
            toggle_use(lid)
            return
        if col == "#5":
            cancel_path_edit_schedule()
            vals = tree.item(item, "values")
            cur = vals[4] if len(vals) > 4 else ""

            def open_editor() -> None:
                path_edit_after_id["id"] = None
                edit_folder_path_dialog(lid, str(cur or ""))

            path_edit_after_id["id"] = root.after(320, open_editor)

    tree.bind("<Button-1>", on_tree_click)

    def on_tree_dblclick(event) -> None:
        cancel_path_edit_schedule()
        if tree.identify_region(event.x, event.y) != "cell":
            return
        col = tree.identify_column(event.x)
        item = tree.identify_row(event.y)
        if not item or col != "#5":
            return
        try:
            lid = int(item)
        except ValueError:
            return
        pick_file(lid)

    tree.bind("<Double-1>", on_tree_dblclick)

    def run_one_cycle_bg() -> None:
        def work() -> None:
            root.after(0, refresh_table)
            ingest_busy["v"] = True
            root.after(0, arm_poll_countdown)
            try:
                with ingest_lock:
                    _poll_cycle(
                        enc_var.get().strip() or "utf-8-sig",
                        not full_var.get(),
                        log_from_thread,
                    )
            finally:
                ingest_busy["v"] = False
                refresh_table_from_thread()

                def _done_manual() -> None:
                    if polling_enabled["v"]:
                        arm_poll_countdown()
                    else:
                        poll_status_var.set("")
                        scan_status_var.set(
                            "실행이 끝났습니다. 위 스캔 창과 아래 로그에서 결과를 확인하세요."
                        )

                root.after(0, _done_manual)

        threading.Thread(target=work, daemon=True).start()

    ttk.Button(btn_row, text="DB 목록 새로고침", command=refresh_table).pack(side=tk.LEFT)
    ttk.Button(btn_row, text="지금 한 번 순환", command=run_one_cycle_bg).pack(
        side=tk.LEFT, padx=(8, 0)
    )

    def _poll_cycle(encoding: str, incremental: bool, logfn) -> None:
        rows = _load_logger_rows()
        for r in rows:
            if not int(r.get("is_active") or 0):
                continue
            raw_p = (r.get("folder_path") or "").strip()
            if not raw_p:
                continue
            p = Path(raw_p)
            if not p.is_file():
                logfn(f"[건너뜀] 로거 {r.get('logger_name')} — 파일 없음: {raw_p}")
                continue
            lid = int(r["id"])
            site = (r.get("site_name") or "").strip()
            lname = (r.get("logger_name") or "").strip()
            logfn(f"[진행] {lname} ({site}) — CSV 스캔·적재: {p.name}")

            def prog(payload: dict) -> None:
                enqueue_progress(lid, site, lname, payload)

            try:
                out = ingest_csv_for_logger(
                    lid,
                    p,
                    encoding=encoding,
                    incremental=incremental,
                    progress_cb=prog,
                )
                if out.get("skipped"):
                    logfn(
                        f"[건너뜀] {r.get('logger_name')}: {out.get('message') or out.get('reason')}"
                    )
                else:
                    logfn(
                        f"[적재] {r.get('logger_name')} — "
                        f"삽입 {out.get('rows_inserted')}행, 파일={p.name}"
                    )
                    d0 = out.get("diag") or {}
                    if d0.get("csv_rows_time_ok"):
                        rule = (
                            "증분: 각 채널 DB최신시각보다 큰 observed_at 행만 적재 후보"
                            if incremental
                            else "전체모드: 시각 제한 없음(중복·스킵은 별도)"
                        )
                        logfn(f"  → 수집 조건: {rule}")
                        logfn(
                            f"  → 채널별 DB최신(이 시각 이하 CSV행은 증분에서 제외): "
                            f"{d0.get('incremental_per_channel_latest', '—')}"
                        )
                        logfn(
                            f"  → CSV에서 읽은 시각: 파일순 첫~끝 = "
                            f"{d0.get('csv_first_observed')} ~ {d0.get('csv_last_observed')} "
                            f"(문자열 min~max = {d0.get('csv_obs_min')} ~ {d0.get('csv_obs_max')})"
                        )
                        if d0.get("sample_time_col_raw") is not None:
                            logfn(
                                f"  → 첫 데이터 행 샘플: time열(원문)={d0.get('sample_time_col_raw')!r}, "
                                f"그 행 칸수={d0.get('sample_row_ncols')}"
                            )
                        if d0.get("sample_channels_cells"):
                            logfn(
                                f"  → 같은 행 값열: {d0.get('sample_channels_cells')}"
                            )
                    elif not out.get("skipped"):
                        logfn(
                            "  → CSV에서 시각이 파싱된 데이터 행이 없습니다 "
                            "(로거 time 열 번호·헤더·형식 확인)."
                        )
                    if int(out.get("rows_inserted") or 0) == 0:
                        d = out.get("diag") or {}
                        logfn(
                            f"  → 진단: 시각파싱성공행={d.get('csv_rows_time_ok', '?')}, "
                            f"적재후보점={d.get('points_prepared', '?')}, "
                            f"활성센서={d.get('active_channels', '?')}, "
                            f"time_col={d.get('time_column_index', '?')}"
                        )
                        sk = (
                            f"열없음={d.get('skip_col_index_oob', 0)}, "
                            f"증분제외={d.get('skip_incremental_old', 0)}, "
                            f"중복시각={d.get('skip_duplicate_time', 0)}, "
                            f"값비움={d.get('skip_empty_value', 0)}, "
                            f"숫자아님={d.get('skip_bad_number', 0)}, "
                            f"계산식오류={d.get('skip_formula_error', 0)}"
                        )
                        logfn(f"  → 스킵누적(행×센서): {sk}")
                        if d.get("incremental_latest_db_observed"):
                            logfn(
                                f"  → (증분) DB최신시각≤이면 스킵: 채널기준 max="
                                f"{d.get('incremental_latest_db_observed')}"
                            )
                        t_ok = int(d.get("csv_rows_time_ok") or 0)
                        prep = int(d.get("points_prepared") or 0)
                        sk_inc = int(d.get("skip_incremental_old") or 0)
                        sk_oob = int(d.get("skip_col_index_oob") or 0)
                        if t_ok == 0:
                            logfn(
                                "  → 힌트: 시각 열 번호(로거 설정)·시간 형식을 확인하세요 "
                                "(예: YYYY-MM-DD H:M, 한 자리 시)."
                            )
                        elif sk_oob >= t_ok and sk_oob > 0:
                            logfn(
                                "  → 힌트: 센서 「칼럼」(화면 번호·맨 왼쪽부터 1)이 이 파일 칸 수보다 큽니다. "
                                "포털에서 칼럼 번호를 줄이거나 CSV 구조를 확인하세요."
                            )
                        elif sk_inc >= t_ok and sk_inc > 0:
                            logfn(
                                "  → 힌트: 증분 때문에 파일 시각이 DB 최신보다 안 새면 전부 스킵됩니다. "
                                "「전체(증분 해제)」로 재시도하거나, 구간 삭제 후 재적재하세요."
                            )
                        elif prep == 0:
                            logfn(
                                "  → 힌트: 빈 값·계산식(수식)·중복 시각 등 위 스킵 수치를 보고 조정하세요."
                            )
                        else:
                            logfn(
                                "  → 힌트: 후보는 있으나 삽입 0 — 전부 중복일 수 있습니다. "
                                "「전체(증분 해제)」로 재시도하거나 DB 측정 구간을 확인하세요."
                            )
            except Exception as e:
                logfn(f"[오류] 로거 {r.get('logger_name')}: {e}\n{traceback.format_exc()}")

    def kick_polling_round() -> None:
        """한 번 순환 실행 후, 순환이 켜져 있으면 다음 after 예약."""

        def work() -> None:
            root.after(0, refresh_table)
            ingest_busy["v"] = True
            root.after(0, arm_poll_countdown)
            try:
                with ingest_lock:
                    _poll_cycle(
                        enc_var.get().strip() or "utf-8-sig",
                        not full_var.get(),
                        log_from_thread,
                    )
            finally:
                ingest_busy["v"] = False
                refresh_table_from_thread()
                if polling_enabled["v"]:
                    root.after(0, schedule_next_poll)
                else:
                    root.after(0, cancel_idle_tick)
                    root.after(0, lambda: poll_status_var.set(""))
                root.after(0, arm_poll_countdown)

        threading.Thread(target=work, daemon=True).start()

    def schedule_next_poll() -> None:
        if not polling_enabled["v"]:
            return
        ms = max(1, int(interval_var.get())) * 60 * 1000
        next_cycle_deadline_s["t"] = time.time() + ms / 1000.0
        poll_after_id["id"] = root.after(ms, on_poll_timer)
        arm_poll_countdown()

    def on_poll_timer() -> None:
        poll_after_id["id"] = None
        if not polling_enabled["v"]:
            return
        kick_polling_round()

    refresh_table()
    cv_line = (
        f"수집 프로그램 {collector_version.VERSION_LABEL}"
        if collector_version
        else "수집 프로그램 버전 미확인"
    )
    append_log(
        f"DB: {db.get_db_path()} — {cv_line} (웹 포털 버전은 별도: portal_version.py). "
        "웹에서 추가한 로거는 「DB 목록 새로고침」 또는 순환 시 목록이 갱신됩니다. "
        "파일경로: 한 번 클릭=수정/비우기, 더블클릭=CSV 선택. "
        "「순환 시작」을 누르면 바로 1회 적재 후 주기마다 반복합니다."
    )

    root.mainloop()


def main() -> None:
    run_gui()


if __name__ == "__main__":
    main()
