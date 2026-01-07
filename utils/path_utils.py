# utils/path_utils.py

import os
import sys


class PathUtils:
    """
    Convert Pro 3 - Path Utility

    - 프로그램 실행 기준 경로 획득
    - 경로 정규화 유틸
    """

    @staticmethod
    def get_app_dir() -> str:
        """
        실행 중인 프로그램(EXE 또는 python script)이 있는 실제 폴더
        - PyInstaller onefile / onedir / python 실행 모두 대응
        """
        if getattr(sys, "frozen", False):
            # PyInstaller exe 실행
            return os.path.dirname(sys.executable)
        else:
            # python script 실행
            return os.path.dirname(os.path.abspath(sys.argv[0]))

    @staticmethod
    def normalize(path: str) -> str:
        """
        경로 문자열 정규화 (UI / JSON 저장용)
        """
        if not path:
            return ""
        return os.path.normpath(path).replace("\\", "/")
