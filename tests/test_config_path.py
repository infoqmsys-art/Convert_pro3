"""CONVERT_PRO_CONFIG 가 있으면 그 경로, 없으면 실행 폴더."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_path import ENV_NAME, resolve_config_path


def test_local_when_env_empty():
    old = os.environ.pop(ENV_NAME, None)
    try:
        path, shared = resolve_config_path(r"C:\Projects\Convert_pro3")
        assert shared is False
        assert path.lower().endswith(os.path.normpath(r"Convert_pro3\config.json").lower())
    finally:
        if old is not None:
            os.environ[ENV_NAME] = old


def test_env_wins():
    unc = r"\\QMMAIN3\ConvertPro3\config.json"
    old = os.environ.get(ENV_NAME)
    os.environ[ENV_NAME] = f'  "{unc}"  '
    try:
        path, shared = resolve_config_path(r"C:\Projects\Convert_pro3")
        assert shared is True
        assert path == os.path.normpath(unc)
    finally:
        if old is None:
            os.environ.pop(ENV_NAME, None)
        else:
            os.environ[ENV_NAME] = old


if __name__ == "__main__":
    test_local_when_env_empty()
    test_env_wins()
    print("ok")
