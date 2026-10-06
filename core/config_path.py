"""config.json 위치.

서버 PC는 실행 폴더의 config.json 을 그대로 쓴다.
개발 PC는 환경변수 CONVERT_PRO_CONFIG 에 서버 공유 경로를 넣는다.

  \\\\큐엠메인서버3\\ConvertPro3\\config.json

같은 파일이고, 개발 PC 복사본을 서버에 덮어쓰지 않는다.
"""
from __future__ import annotations

import os

ENV_NAME = "CONVERT_PRO_CONFIG"


def resolve_config_path(base_dir: str) -> tuple[str, bool]:
    """(경로, 환경변수로 지정됐는지).

    환경변수가 비어 있으면 base_dir/config.json.
    파일 생성은 하지 않는다.
    """
    raw = (os.environ.get(ENV_NAME) or "").strip().strip('"')
    if raw:
        return os.path.normpath(raw), True
    return os.path.normpath(os.path.join(base_dir, "config.json")), False
