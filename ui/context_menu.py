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

    _CAT_NODE_TYPES = {"cat_group", "cat_station", "cat_unassigned"}

    def _build_menu_for_type(self, node_type: str | None, multi_file: bool = False):
        """노드 타입(file/folder/site/summary 등)에 따라 메뉴 항목 동적 구성"""
        self.menu.delete(0, "end")

        # 카테고리 가상 노드: 대분류/소분류/미배정 → 업로드 메뉴 제공
        if node_type == "cat_group":
            self.menu.add_command(label="대분류 업로드", command=self._upload_cat_node)
            return
        if node_type == "cat_station":
            self.menu.add_command(label="소분류 업로드", command=self._upload_cat_node)
            return
        if node_type == "cat_unassigned":
            self.menu.add_command(label="미배정 파일 업로드", command=self._upload_cat_node)
            return

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
        elif node_type == "folder":
            # 폴더 전용: 폴더 업로드
            self.menu.add_separator()
            self.menu.add_command(label="폴더 업로드", command=self._upload_folder)
        # site / company / summary 등은 기본 메뉴(비고 편집 + 삭제)만 사용

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

    def _upload_cat_node(self):
        """대분류/소분류/미배정 노드 아래 파일을 일괄 업로드."""
        info = self._get_current_item_info()
        if not info:
            return
        node_type = info["type"]
        label_map = {
            "cat_group":      "대분류",
            "cat_station":    "소분류",
            "cat_unassigned": "미배정",
        }
        label = label_map.get(node_type, "카테고리")
        files = self._collect_file_nodes(info["item"])
        if not files:
            messagebox.showinfo("안내", f"{label}에 파일이 없습니다.", parent=self.root)
            return
        node_name = self.tree.item(info["item"], "text").split("(")[0].strip()
        self.app.convert_files_batch(files, label=f"{label}({node_name})")

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