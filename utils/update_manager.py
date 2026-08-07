"""
Convert Pro 3 - 소스 업데이트 (git pull)
개발 PC에서 push 후, 서버/실행 PC에서 업데이트 버튼으로 pull.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class UpdateManager:
    """실행 폴더(git 저장소)에서 git pull --ff-only."""

    def __init__(self, logger=None):
        self.logger = logger

    def _log(self, msg: str, level: str = "INFO") -> None:
        if self.logger:
            self.logger.log(f"[Update] {msg}", level=level)

    def pull_latest(self, repo_path: str, status_cb=None) -> dict:
        """
        repo_path 에서 git pull --ff-only.

        Returns:
            {
              'pulled': bool,      # HEAD가 바뀌었으면 True
              'already_latest': bool,
              'old_head': str,
              'new_head': str,
              'message': str,
            }
        """
        def _status(msg: str) -> None:
            self._log(msg)
            if status_cb:
                status_cb(msg)

        repo = Path(repo_path)
        if not (repo / ".git").exists():
            raise RuntimeError(
                f"git 저장소가 아닙니다:\n{repo}\n\n"
                "Convert_pro3 를 git clone / pull 해 둔 폴더에서 프로그램을 실행하세요."
            )

        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        def _run(args, timeout=120):
            return subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=no_window,
            )

        try:
            before = _run(["git", "-C", str(repo), "rev-parse", "HEAD"], timeout=30)
        except FileNotFoundError as e:
            raise RuntimeError(
                "git 명령을 찾을 수 없습니다.\n"
                "PC에 Git을 설치하고 PATH에 넣은 뒤 다시 시도하세요."
            ) from e

        if before.returncode != 0:
            raise RuntimeError((before.stderr or before.stdout or "rev-parse 실패").strip())
        old_head = (before.stdout or "").strip()

        _status("git pull 중…")
        pull = _run(["git", "-C", str(repo), "pull", "--ff-only"], timeout=120)
        if pull.returncode != 0:
            err = (pull.stderr or pull.stdout or "git pull 실패").strip()
            raise RuntimeError(
                f"git pull 실패:\n{err}\n\n원격 인증·충돌·네트워크를 확인하세요."
            )

        out = ((pull.stdout or "") + (pull.stderr or "")).strip()
        if out:
            _status(out.splitlines()[-1][:160])

        after = _run(["git", "-C", str(repo), "rev-parse", "HEAD"], timeout=30)
        new_head = (after.stdout or "").strip() if after.returncode == 0 else old_head
        pulled = bool(new_head and new_head != old_head)

        if pulled:
            msg = f"새 코드를 받았습니다. ({old_head[:7]} → {new_head[:7]})"
        else:
            msg = "이미 최신입니다. (변경 없음)"
        _status(msg)

        return {
            "pulled": pulled,
            "already_latest": not pulled,
            "old_head": old_head,
            "new_head": new_head,
            "message": msg,
        }
