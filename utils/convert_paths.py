"""
변환본 CSV 경로 규칙 (단일 소스).

레이아웃: {convert_root}/{company}/{folder}/{filename}
  - folder = 로거 식별자 (등록 폴더명)
  - site 는 config/UI 논리 레벨만 사용 (디스크 경로에 넣지 않음)

일시적으로 생겼던 site 포함 경로:
  {convert_root}/{company}/{site}/{folder}/{filename}
  → 읽기 fallback, 쓰기 시 로거 폴더 경로로 되돌림.
"""
from __future__ import annotations

import os
import shutil

DEFAULT_CONVERT_ROOT = r"C:\data\Convertfile"


def convert_out_dir(convert_root: str, company: str, folder: str) -> str:
    return os.path.join(convert_root, company, folder)


def convert_out_path(
    convert_root: str, company: str, folder: str, filename: str
) -> str:
    return os.path.join(convert_out_dir(convert_root, company, folder), filename)


def site_layout_out_path(
    convert_root: str, company: str, site: str, folder: str, filename: str
) -> str:
    """잘못 도입됐던 site 포함 경로 (마이그레이션용)."""
    return os.path.join(convert_root, company, site, folder, filename)


def resolve_convert_out_path(
    convert_root: str, company: str, site: str, folder: str, filename: str
) -> str:
    """읽기용: 로거 경로 우선, 없으면 site 포함 경로 fallback."""
    primary = convert_out_path(convert_root, company, folder, filename)
    if os.path.exists(primary):
        return primary
    if site:
        alt = site_layout_out_path(convert_root, company, site, folder, filename)
        if os.path.exists(alt):
            return alt
    return primary


def align60_filename(filename: str) -> str:
    """
    1227998430.csv → 1227998430_60.csv

    60분 정렬 파일 생성용. _60.csv는 10분 변환본을 map_slots(60)한 사본(동일 CH 값).
    """
    base, ext = os.path.splitext(filename)
    if not ext:
        ext = ".csv"
    if base.endswith("_60"):
        return filename
    return f"{base}_60{ext}"


def prepare_align60_out_path(
    convert_root: str,
    company: str,
    site: str,
    folder: str,
    filename: str,
    logger=None,
) -> str:
    """60분 정렬 변환본 경로 (파일명 _60 접미사)."""
    return prepare_convert_out_path(
        convert_root,
        company,
        site,
        folder,
        align60_filename(filename),
        logger=logger,
    )


def prepare_convert_out_path(
    convert_root: str,
    company: str,
    site: str,
    folder: str,
    filename: str,
    logger=None,
) -> str:
    """쓰기용: 로거 폴더 경로에 저장. site 경로에만 있으면 되돌림."""
    primary = convert_out_path(convert_root, company, folder, filename)
    os.makedirs(os.path.dirname(primary), exist_ok=True)

    if os.path.exists(primary):
        return primary

    if site:
        alt = site_layout_out_path(convert_root, company, site, folder, filename)
        if os.path.exists(alt):
            try:
                shutil.move(alt, primary)
                if logger:
                    logger.log(
                        f"변환본 경로 복구: {alt} → {primary}",
                        level="DEBUG",
                    )
            except Exception as e:
                if logger:
                    logger.log(
                        f"변환본 경로 복구 실패 (site 경로 사용): {e}",
                        level="WARN",
                    )
                return alt
    return primary
