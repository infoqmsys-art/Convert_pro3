"""
계측관리 통합시스템 — **웹 포털** (Flask UI·API) 버전.

데이터수집프로그램(로컬 GUI/CLI) 버전은 `scripts/collector_version.py` 입니다.

올리기: `python scripts/bump_versions.py auto` 또는 `portal`
(헤더·로그인·/__portal_ping 등에 표시)
"""
from __future__ import annotations

VERSION_MAJOR = 0
VERSION_MINOR = 2
VERSION_PATCH = 0

VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"
VERSION_LABEL = f"v{VERSION}"
