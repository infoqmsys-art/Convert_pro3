"""config.json 교체 전 검사.

저장은 항상 같은 폴더의 임시 파일에 쓰고, 다시 읽어 본 뒤에만 교체한다.
기존 파일을 해석하지 못하면 덮어쓰지 않는다.
업체 키가 전부 사라지거나, 업체는 그대로인데 크기가 절반 미만이면 거부한다.
직전 내용은 config.json.bak 한 부에 남긴다.

긴급히 큰 삭제를 저장해야 하면 환경변수
CONVERT_PRO_CONFIG_ALLOW_SHRINK=1
크기 검사만 넘긴다. 업체가 0개가 되는 저장은 그때도 거부한다.
"""
from __future__ import annotations

import json
import os
import shutil

_SHRINK_ENV = "CONVERT_PRO_CONFIG_ALLOW_SHRINK"
_MIN_COMPARE_CHARS = 8_192


class ConfigWriteRefused(Exception):
    """이 내용으로는 config.json 을 교체하지 않는다."""


def company_keys(data: dict) -> set[str]:
    out: set[str] = set()
    for key, value in data.items():
        if isinstance(key, str) and not key.startswith("__") and isinstance(value, dict):
            out.add(key)
    return out


def shrink_override_enabled() -> bool:
    return (os.environ.get(_SHRINK_ENV) or "").strip().lower() in ("1", "true", "yes")


def assert_config_replacement(old: dict | None, new: object) -> None:
    if not isinstance(new, dict):
        raise ConfigWriteRefused("config.json 최상위는 객체여야 합니다.")
    if old is None:
        return
    if not isinstance(old, dict):
        raise ConfigWriteRefused("기존 config.json 을 객체로 읽지 못했습니다.")

    old_companies = company_keys(old)
    new_companies = company_keys(new)
    if old_companies and not new_companies:
        raise ConfigWriteRefused("업체 목록이 전부 사라집니다. 저장을 멈춥니다.")

    if shrink_override_enabled():
        return

    old_n = len(json.dumps(old, ensure_ascii=False))
    new_n = len(json.dumps(new, ensure_ascii=False))
    if old_n < _MIN_COMPARE_CHARS or new_n >= old_n * 0.5:
        return
    if old_companies <= new_companies:
        raise ConfigWriteRefused(
            "업체는 그대로인데 내용이 절반 미만입니다. 저장을 멈춥니다."
        )
    if new_n < old_n * 0.15:
        raise ConfigWriteRefused(
            "기존 설정보다 너무 작습니다. 저장을 멈춥니다."
        )


def _read_existing(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigWriteRefused(
            f"기존 config.json 을 읽지 못했습니다. 덮어쓰지 않습니다. ({e})"
        ) from e
    if not isinstance(loaded, dict):
        raise ConfigWriteRefused("기존 config.json 최상위가 객체가 아닙니다. 덮어쓰지 않습니다.")
    return loaded


def file_mtime_ns(path: str) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def replace_config_file(
    path: str,
    new_obj: dict,
    *,
    allow_create: bool = True,
    expected_mtime_ns: int | None = None,
) -> int | None:
    """검사 → 임시 파일 → 재읽기 → .bak → 교체. 교체 후 mtime_ns 반환.

    expected_mtime_ns 를 주면, 그 뒤에 다른 곳에서 파일이 바뀐 경우 저장하지 않는다.
    """
    if expected_mtime_ns is not None:
        now = file_mtime_ns(path)
        if now is not None and now != expected_mtime_ns:
            raise ConfigWriteRefused(
                "읽은 뒤에 다른 곳에서 config.json 이 바뀌었습니다. "
                "프로그램을 다시 켜서 새 내용을 읽은 뒤 저장하세요."
            )
    old = _read_existing(path)
    if old is None and not allow_create:
        raise ConfigWriteRefused(f"config.json 이 없어 새로 만들지 않습니다: {path}")
    assert_config_replacement(old, new_obj)

    folder = os.path.dirname(path) or "."
    tmp = path + ".tmp"
    bak = path + ".bak"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_obj, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, "r", encoding="utf-8") as f:
            written = json.load(f)
        if company_keys(written) != company_keys(new_obj):
            raise ConfigWriteRefused("임시 파일을 다시 읽었을 때 업체 목록이 다릅니다.")
        if old is not None:
            shutil.copy2(path, bak)
        os.replace(tmp, path)
        return file_mtime_ns(path)
    except ConfigWriteRefused:
        raise
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigWriteRefused(f"config.json 저장에 실패했습니다. ({e})") from e
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
