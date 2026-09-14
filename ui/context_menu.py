import tkinter as tk
from tkinter import messagebox, simpledialog


class FolderContextMenu:
    """
    Treeview 우클릭 컨텍스트 메뉴.

    MainUI 에서 사용하는 기능:
      - 비고 편집
      - 파일 위/아래 이동
      - 현장/폴더/파일 삭제
    """

    def __init__(self, root, app, tree):
        self.root = root
        self.app = app
        self.tree = tree

        # 공용 메뉴 객체 (우클릭 시 타입에 따라 동적으로 구성)
        self.menu = tk.Menu(self.root, tearoff=0)

    def popup(self, event):
        """우클릭 시 컨텍스트 메뉴 표시 (노드 타입에 따라 구성 변경)"""
        item = self.tree.identify_row(event.y)
        if item:
            # extended 모드: 우클릭한 행이 현재 선택에 없으면 해당 행만 선택.
            # 이미 선택된 항목 중 하나를 우클릭하면 다중 선택 그대로 유지.
            selected = self.tree.selection()
            if item not in selected:
                self.tree.selection_set(item)
            self.tree.focus(item)

        info = self._get_current_item_info()
        node_type = info["type"] if info else None

        # 다중 선택된 항목이 모두 file 타입이면 다중 trim 메뉴 사용
        selected_items = self.tree.selection()
        all_files = (
            len(selected_items) > 1
            and all(self.tree.set(i, "type") == "file" for i in selected_items)
        )
        self._build_menu_for_type(node_type, multi_file=all_files)

        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _build_menu_for_type(self, node_type: str | None, multi_file: bool = False):
        """노드 타입(file/folder/site/summary 등)에 따라 메뉴 항목 동적 구성"""
        self.menu.delete(0, "end")

        # 비고 편집 (summary 이외에는 항상 가능)
        self.menu.add_command(label="비고 편집", command=self._edit_note)

        if multi_file:
            # 다중 파일 선택 전용: 변환본 시간 이후 삭제(일괄)만 제공
            self.menu.add_separator()
            self.menu.add_command(
                label=f"변환본 시간 이후 삭제 (선택 {len(self.tree.selection())}개)",
                command=self._trim_converted_multi,
            )
        elif node_type == "file":
            # 파일 전용: 순서 이동 + 단일 업로드 + 변환본 시간 이후 삭제
            self.menu.add_separator()
            self.menu.add_command(label="파일 위로 이동", command=self._move_file_up)
            self.menu.add_command(label="파일 아래로 이동", command=self._move_file_down)
            self.menu.add_separator()
            self.menu.add_command(
                label="로거파일 단일 업로드", command=self._upload_single_file
            )
            self.menu.add_command(
                label="변환본 시간 이후 삭제", command=self._trim_converted_from_time
            )
            self.menu.add_separator()
            self.menu.add_command(
                label=self._align60_menu_label(),
                command=self._toggle_align_60,
            )
        elif node_type == "folder":
            # 폴더 전용: 폴더 업로드
            self.menu.add_separator()
            self.menu.add_command(label="폴더 업로드", command=self._upload_folder)
        elif node_type == "site":
            self.menu.add_separator()
            self.menu.add_command(label="시간차단…", command=self._edit_site_time_block)
        # site / company / summary 등은 기본 메뉴(비고 편집 + 삭제)만 사용 — site는 시간차단 추가

        self.menu.add_separator()
        self.menu.add_command(label="삭제", command=self._delete_selected)

    def _get_current_item_info(self):
        item = self.tree.focus()
        if not item:
            return None
        return {
            "item": item,
            "type": self.tree.set(item, "type"),
            "company": self.tree.set(item, "company"),
            "site": self.tree.set(item, "site"),
            "folder": self.tree.set(item, "folder"),
            "filename": self.tree.set(item, "filename"),
        }

    # =========================
    # 비고 편집
    # =========================
    def _edit_note(self):
        info = self._get_current_item_info()
        if not info:
            messagebox.showwarning(
                "안내", "편집할 항목을 먼저 선택해주세요.", parent=self.root
            )
            return

        node_type = info["type"]
        company = info["company"]
        site = info["site"]
        folder = info["folder"]
        filename = info["filename"]

        if node_type == "summary":
            messagebox.showwarning(
                "안내", "요약 정보는 편집할 수 없습니다.", parent=self.root
            )
            return

        current_note = self.tree.set(info["item"], "note") or ""
        new_note = simpledialog.askstring(
            "비고 편집",
            f"{node_type}의 비고를 입력하세요:",
            initialvalue=current_note,
            parent=self.root,
        )
        if new_note is None:
            return

        new_note = new_note.strip()

        try:
            if node_type == "site":
                self.app.tree.set_site_note(company, site, new_note)
            elif node_type == "folder":
                self.app.tree.set_folder_note(company, site, folder, new_note)
            elif node_type == "file":
                self.app.tree.set_file_note(company, site, folder, filename, new_note)

            self.tree.set(info["item"], "note", new_note)
            messagebox.showinfo("수정 완료", "비고가 성공적으로 수정되었습니다.", parent=self.root)
        except Exception as e:
            self.app.logger.log(f"[UI] 비고 수정 실패: {e}", level="ERROR")
            messagebox.showerror(
                "수정 실패",
                f"비고 수정 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.",
                parent=self.root,
            )

    def _edit_site_time_block(self):
        """현장 단위 — 변환 시 데이터 시각이 현재 시각보다 늦으면 해당 행을 넣지 않음."""
        info = self._get_current_item_info()
        if not info or info["type"] != "site":
            messagebox.showwarning(
                "안내", "현장 노드를 선택한 뒤 다시 시도해주세요.", parent=self.root
            )
            return
        company = info["company"]
        site = info["site"]
        try:
            initial = self.app.tree.get_site_time_block_future(company, site)
        except Exception:
            initial = False

        dlg = tk.Toplevel(self.root)
        dlg.title("시간차단")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry(
            "+{}+{}".format(self.root.winfo_rootx() + 40, self.root.winfo_rooty() + 80)
        )

        fr = tk.Frame(dlg, padx=16, pady=12)
        fr.pack(fill="both", expand=True)

        tk.Label(fr, text=f"현장: {site}", font=("맑은 고딕", 10, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        tk.Label(
            fr,
            text=(
                "켜두면 이 현장에 속한 로거 파일을 변환할 때,\n"
                "각 행의 첫 번째 열(timestamp)을 읽어\n"
                "「변환을 실행하는 시점의 PC 시각」보다 늦은 시각인 행은\n"
                "변환 결과에 포함하지 않습니다.\n\n"
                "(로거 시간 오설정·미래 타임스탬프 보정 등에 활용)"
            ),
            justify="left",
            font=("맑은 고딕", 9),
            fg="#333",
            wraplength=420,
        ).pack(anchor="w", pady=(0, 10))

        var = tk.BooleanVar(value=initial)
        tk.Checkbutton(
            fr,
            text="현장 시간차단 사용 (미래 시각 행 제외)",
            variable=var,
            font=("맑은 고딕", 9),
        ).pack(anchor="w", pady=(0, 12))

        btn_row = tk.Frame(fr)
        btn_row.pack(fill="x")

        def apply_and_close():
            val = var.get()
            try:
                self.app.tree.set_site_time_block_future(company, site, val)
            except Exception as e:
                messagebox.showerror("오류", str(e), parent=dlg)
                return
            dlg.destroy()
            try:
                self.app.ui.refresh_tree()
            except Exception:
                pass
            messagebox.showinfo(
                "저장 완료",
                "현장 시간차단을 켰습니다." if val else "현장 시간차단을 껐습니다.",
                parent=self.root,
            )

        tk.Button(
            btn_row, text="확인", width=10, command=apply_and_close
        ).pack(side="right", padx=(6, 0))
        tk.Button(btn_row, text="취소", width=10, command=dlg.destroy).pack(side="right")

        dlg.wait_visibility()
        dlg.focus_force()

    # =========================
    # 파일 순서 변경 (위/아래)
    # =========================
    def _move_file_up(self):
        info = self._get_current_item_info()
        if not info or info["type"] != "file":
            return

        company = info["company"]
        site = info["site"]
        folder = info["folder"]
        filename = info["filename"]

        folder_id = self.tree.parent(info["item"])
        if not folder_id:
            return

        file_items = []
        for child in self.tree.get_children(folder_id):
            if self.tree.set(child, "type") == "file":
                file_items.append(self.tree.set(child, "filename"))

        try:
            idx = file_items.index(filename)
        except ValueError:
            return

        if idx == 0:
            messagebox.showinfo("안내", "이미 맨 위에 있습니다.", parent=self.root)
            return

        file_items[idx], file_items[idx - 1] = file_items[idx - 1], file_items[idx]
        order_list = [(name, i) for i, name in enumerate(file_items)]

        try:
            if self.app.tree.reorder_files(company, site, folder, order_list):
                self.app.logger.log(
                    f"[UI] 파일 위로 이동: {company}/{site}/{folder}/{filename}"
                )
        except Exception as e:
            self.app.logger.log(f"[UI] 파일 순서 변경 실패: {e}", level="ERROR")
            messagebox.showerror(
                "순서 변경 실패",
                f"파일 순서 변경 중 문제가 발생했습니다.\n\n오류 내용: {e}",
                parent=self.root,
            )

    def _move_file_down(self):
        info = self._get_current_item_info()
        if not info or info["type"] != "file":
            return

        company = info["company"]
        site = info["site"]
        folder = info["folder"]
        filename = info["filename"]

        folder_id = self.tree.parent(info["item"])
        if not folder_id:
            return

        file_items = []
        for child in self.tree.get_children(folder_id):
            if self.tree.set(child, "type") == "file":
                file_items.append(self.tree.set(child, "filename"))

        try:
            idx = file_items.index(filename)
        except ValueError:
            return

        if idx == len(file_items) - 1:
            messagebox.showinfo("안내", "이미 맨 아래에 있습니다.", parent=self.root)
            return

        file_items[idx], file_items[idx + 1] = file_items[idx + 1], file_items[idx]
        order_list = [(name, i) for i, name in enumerate(file_items)]

        try:
            if self.app.tree.reorder_files(company, site, folder, order_list):
                self.app.logger.log(
                    f"[UI] 파일 아래로 이동: {company}/{site}/{folder}/{filename}"
                )
        except Exception as e:
            self.app.logger.log(f"[UI] 파일 순서 변경 실패: {e}", level="ERROR")
            messagebox.showerror(
                "순서 변경 실패",
                f"파일 순서 변경 중 문제가 발생했습니다.\n\n오류 내용: {e}",
                parent=self.root,
            )

    # =========================
    # 업로드 (단일 파일 / 폴더)
    # =========================
    def _upload_single_file(self):
        """현재 선택된 단일 로거 파일 변환 (우클릭 메뉴에서 실행)"""
        info = self._get_current_item_info()
        if not info or info["type"] != "file":
            messagebox.showwarning(
                "안내", "변환할 로거 파일을 먼저 선택해주세요.", parent=self.root
            )
            return

        company = info["company"]
        site = info["site"]
        folder = info["folder"]
        filename = info["filename"]

        # 실제 파일 변환 실행
        self.app.convert_single_file(company, site, folder, filename)

    def _trim_converted_from_time(self):
        """변환본에서 지정 시간 이후(~끝) 데이터 삭제 — 단일 파일 (우클릭 메뉴)"""
        info = self._get_current_item_info()
        if not info or info["type"] != "file":
            messagebox.showwarning(
                "안내", "파일을 먼저 선택해주세요.", parent=self.root
            )
            return
        self.app.trim_converted_file(
            info["company"], info["site"], info["folder"], info["filename"]
        )

    def _align60_menu_label(self) -> str:
        info = self._get_current_item_info()
        if not info or info["type"] != "file":
            return "60분 정렬 파일 지정"
        try:
            fc = (
                self.app.config.data.get(info["company"], {})
                .get(info["site"], {})
                .get(info["folder"], {})
                .get(info["filename"], {})
            )
            if bool(fc.get("__align_60__", False)):
                return "60분 정렬 해제"
        except Exception:
            pass
        return "60분 정렬 파일 지정"

    def _toggle_align_60(self):
        """파일별 60분 정렬 변환본({파일명}_60.csv) 생성 플래그 토글."""
        info = self._get_current_item_info()
        if not info or info["type"] != "file":
            messagebox.showwarning(
                "안내", "로거 파일을 먼저 선택해주세요.", parent=self.root
            )
            return

        company = info["company"]
        site = info["site"]
        folder = info["folder"]
        filename = info["filename"]

        try:
            file_cfg = self.app.config.ensure_logger(company, site, folder, filename)
            enabled = bool(file_cfg.get("__align_60__", False))
            file_cfg["__align_60__"] = not enabled
            self.app.config.save()
        except Exception as e:
            messagebox.showerror(
                "설정 실패",
                f"60분 정렬 설정 저장 중 오류가 발생했습니다.\n\n{e}",
                parent=self.root,
            )
            return

        from utils.convert_paths import align60_filename

        if file_cfg["__align_60__"]:
            out_name = align60_filename(filename)
            messagebox.showinfo(
                "60분 정렬 파일",
                f"변환 시 파일이 두 개로 나갑니다.\n\n"
                f"• {filename}\n"
                f"  → 10분 변환본 (진동계 등, 센서·누락보충 적용)\n\n"
                f"• {out_name}\n"
                f"  → 위 10분본을 60분에 가장 가까운 행만 골라 정렬 (EL·CR 등록용)\n"
                f"  → 값은 10분본과 동일, 행 수만 줄어듭니다.",
                parent=self.root,
            )
            if messagebox.askyesno(
                "변환 실행",
                "지금 변환을 실행할까요?",
                parent=self.root,
            ):
                self.app.convert_single_file(company, site, folder, filename)
        else:
            messagebox.showinfo(
                "60분 정렬 해제",
                f"{filename}의 60분 정렬 생성을 끄었습니다.\n"
                f"(기존 {align60_filename(filename)} 파일은 삭제하지 않습니다.)",
                parent=self.root,
            )

    def _trim_converted_multi(self):
        """변환본에서 지정 시간 이후(~끝) 데이터 삭제 — 다중 파일 일괄 (우클릭 메뉴)"""
        selected = self.tree.selection()
        file_infos = []
        for item in selected:
            if self.tree.set(item, "type") == "file":
                file_infos.append({
                    "company":  self.tree.set(item, "company"),
                    "site":     self.tree.set(item, "site"),
                    "folder":   self.tree.set(item, "folder"),
                    "filename": self.tree.set(item, "filename"),
                })
        if not file_infos:
            messagebox.showwarning("안내", "file 타입 항목을 선택해주세요.", parent=self.root)
            return
        self.app.trim_converted_files_multi(file_infos)

    def _upload_folder(self):
        """현재 선택된 폴더 단위 변환 (우클릭 메뉴에서 실행)"""
        info = self._get_current_item_info()
        if not info or info["type"] != "folder":
            messagebox.showwarning(
                "안내", "변환할 폴더를 먼저 선택해주세요.", parent=self.root
            )
            return

        company = info["company"]
        site = info["site"]
        folder = info["folder"]

        # 실제 폴더 변환 실행
        self.app.convert_folder(company, site, folder)

    def _collect_file_nodes(self, parent_item):
        """parent_item 아래 모든 file 타입 노드를 재귀 수집.
        반환: [(company, site, folder, filename), ...]
        """
        result = []
        for child in self.tree.get_children(parent_item):
            if self.tree.set(child, "type") == "file":
                result.append((
                    self.tree.set(child, "company"),
                    self.tree.set(child, "site"),
                    self.tree.set(child, "folder"),
                    self.tree.set(child, "filename"),
                ))
            else:
                result.extend(self._collect_file_nodes(child))
        return result

    # =========================
    # 삭제 (현장 / 폴더 / 파일)
    # =========================
    def _delete_selected(self):
        info = self._get_current_item_info()
        if not info:
            messagebox.showwarning(
                "안내", "삭제할 항목을 먼저 선택해주세요.", parent=self.root
            )
            return

        node_type = info["type"]
        company = info["company"]
        site = info["site"]
        folder = info["folder"]
        filename = info["filename"]

        if node_type == "summary":
            messagebox.showwarning(
                "안내", "요약 정보는 삭제할 수 없습니다.", parent=self.root
            )
            return

        if node_type == "site":
            confirm_msg = (
                f"현장 '{site}'를 삭제하시겠습니까?\n\n"
                "주의: 이 현장의 모든 폴더와 파일 설정이 함께 삭제됩니다.\n"
                "이 작업은 되돌릴 수 없습니다."
            )
            if not messagebox.askyesno("삭제 확인", confirm_msg, parent=self.root):
                return
            try:
                self.app.tree.delete_site(company, site)
                self.app.logger.log(f"[UI] 현장 삭제: {company}/{site}")
                self.tree.delete(info["item"])
                messagebox.showinfo(
                    "삭제 완료",
                    f"현장 '{site}'가 성공적으로 삭제되었습니다.",
                    parent=self.root,
                )
            except Exception as e:
                self.app.logger.log(f"[UI] 현장 삭제 실패: {e}", level="ERROR")
                messagebox.showerror(
                    "삭제 실패",
                    f"현장 삭제 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.",
                    parent=self.root,
                )
        elif node_type == "folder":
            confirm_msg = (
                f"폴더 '{folder}'를 삭제하시겠습니까?\n\n"
                "주의: 이 폴더의 모든 파일 설정이 함께 삭제됩니다.\n"
                "이 작업은 되돌릴 수 없습니다."
            )
            if not messagebox.askyesno("삭제 확인", confirm_msg, parent=self.root):
                return
            try:
                self.app.tree.delete_folder(company, site, folder)
                self.app.logger.log(f"[UI] 폴더 삭제: {company}/{site}/{folder}")
                self.tree.delete(info["item"])
                messagebox.showinfo(
                    "삭제 완료",
                    f"폴더 '{folder}'가 성공적으로 삭제되었습니다.",
                    parent=self.root,
                )
            except Exception as e:
                self.app.logger.log(f"[UI] 폴더 삭제 실패: {e}", level="ERROR")
                messagebox.showerror(
                    "삭제 실패",
                    f"폴더 삭제 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.",
                    parent=self.root,
                )
        elif node_type == "file":
            confirm_msg = (
                f"파일 '{filename}'을(를) 삭제하시겠습니까?\n\n"
                "주의: 이 파일의 모든 설정이 삭제됩니다.\n"
                "이 작업은 되돌릴 수 없습니다."
            )
            if not messagebox.askyesno("삭제 확인", confirm_msg, parent=self.root):
                return
            try:
                self.app.tree.delete_file(company, site, folder, filename)
                self.app.logger.log(
                    f"[UI] 파일 삭제: {company}/{site}/{folder}/{filename}"
                )
                self.tree.delete(info["item"])
                messagebox.showinfo(
                    "삭제 완료",
                    f"파일 '{filename}'이(가) 성공적으로 삭제되었습니다.",
                    parent=self.root,
                )
            except Exception as e:
                self.app.logger.log(f"[UI] 파일 삭제 실패: {e}", level="ERROR")
                messagebox.showerror(
                    "삭제 실패",
                    f"파일 삭제 중 문제가 발생했습니다.\n\n오류 내용: {e}\n\n다시 시도해주세요.",
                    parent=self.root,
                )