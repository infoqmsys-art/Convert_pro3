"""
데이터수집프로그램 — CSV 적재 GUI·CLI (`measurement_ingest*.py`) 전용 버전.

계측관리 통합시스템 **웹** 버전은 `portal_version.py` 를 참고하세요.
버전 올리기: `python scripts/bump_versions.py auto` 또는 `collector` / `portal`.
"""
from __future__ import annotations

VERSION_MAJOR = 0
VERSION_MINOR = 1
VERSION_PATCH = 0

VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"
VERSION_LABEL = f"v{VERSION}"

PRODUCT_NAME = "데이터수집프로그램"
