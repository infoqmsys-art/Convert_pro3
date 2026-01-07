import os
import tkinter as tk
from tkinter import messagebox


class FolderContextMenu:
    """Reusable context menu for folder/file tree.

    Usage:
        menu = FolderContextMenu(root, app, tree)
        # on right-click: menu.popup(event)
    """

    def __init__(self, root, app, tree):
        self.root = root
        self.app = app
        self.tree = tree

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="폴더 업로드", command=self._on_upload)
        self.menu.add_command(label="선택 삭제", command=self._on_delete)

    def popup(self, event):
        # 선택 및 포커스 보장
        iid = self.tree.identify_row(event.y)
        if not iid:
            return

        self.tree.selection_set(iid)
        self.tree.focus(iid)

        # show menu
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _get_folder_info(self):
        iid = self.tree.focus()
        if not iid:
            return None, None, None

        node_type = self.tree.set(iid, "type")
        company = self.tree.set(iid, "company")
        folder = self.tree.set(iid, "folder")

        # if a file is selected, use its parent folder
        if node_type == "file":
            parent = self.tree.parent(iid)
            if parent:
                company = self.tree.set(parent, "company")
                folder = self.tree.set(parent, "folder")

        if not folder:
            return None, None, None

        return iid, company, folder

    def _on_upload(self):
        _, company, folder = self._get_folder_info()
        if not folder:
            messagebox.showwarning("경고", "업로드할 폴더를 선택하세요.")
            return

        company_data = self.app.tree.get_company_data(company)
        folder_cfg = company_data.get(folder, {})
        abs_path = folder_cfg.get("__absolute_path__")

        if not abs_path or not os.path.exists(abs_path):
            messagebox.showerror("오류", "폴더 경로가 존재하지 않습니다.")
            return

        # 간단한 옵션: 재귀 여부 확인
        recursive = messagebox.askyesno("재귀 업로드", "하위 항목도 함께 업로드합니까?", default="yes")

        # 호출 가능한 백엔드가 있으면 전달
        uploader = getattr(self.app.file_processor, "upload_folder", None)
        try:
            if callable(uploader):
                uploader(abs_path, recursive=recursive)
                self.app.logger.log(f"[UI] 업로드 요청: {company}/{folder} -> {abs_path}")
                messagebox.showinfo("업로드", "업로드 요청이 전송되었습니다.")
            else:
                # 구현되지 않음 → 로그와 안내
                self.app.logger.log(f"[UI] 업로드 미구현: {abs_path} (재귀={recursive})", level="WARN")
                messagebox.showinfo("알림", f"업로드 백엔드가 없습니다. 경로:\n{abs_path}")
        except Exception as e:
            self.app.logger.log(f"[UI] 업로드 실패: {e}", level="ERROR")
            messagebox.showerror("오류", f"업로드 중 오류가 발생했습니다:\n{e}")

    def _on_delete(self):
        # 재사용을 위해 MainUI의 삭제 핸들러를 호출
        try:
            if hasattr(self.app.ui, "_delete_selected"):
                self.app.ui._delete_selected()
            else:
                messagebox.showwarning("경고", "삭제 기능을 사용할 수 없습니다.")
        except Exception as e:
            messagebox.showerror("오류", f"삭제 중 오류: {e}")
