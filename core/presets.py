# core/presets.py
"""채널 설정 프리셋.

모드·라벨·소수점 등 공통 골격만 깔고, base는 파일마다 따로 넣는다.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def _slot(
    mode: str,
    *,
    label: str = "",
    decimal: str = "",
    scale: str = "",
    base: str = "",
    post_offset: str = "",
) -> dict[str, str]:
    return {
        "mode": mode,
        "base": base,
        "scale": scale,
        "post_offset": post_offset,
        "decimal": decimal,
        "label": label,
        "initial": "",
    }


# name → { desc, slots, globals? }
CHANNEL_PRESETS: dict[str, dict[str, Any]] = {
    "관수구_경사균열": {
        "desc": (
            "내장 degreeX/Y → EL_NEW, 외장 CH0 → CR(균열), CH1~7 → PASS. "
            "base는 비워 두었으니 파일별로 입력."
        ),
        "slots": {
            "degreeX": _slot("EL_NEW", label="내장ELX", decimal="4"),
            "degreeY": _slot("EL_NEW", label="내장ELY", decimal="4"),
            "CH0": _slot("CR", label="균열", decimal="4"),
            "CH1": _slot("PASS"),
            "CH2": _slot("PASS"),
            "CH3": _slot("PASS"),
            "CH4": _slot("PASS"),
            "CH5": _slot("PASS"),
            "CH6": _slot("PASS"),
            "CH7": _slot("PASS"),
        },
    },
}

PRESET_NAMES = tuple(CHANNEL_PRESETS.keys())


def get_preset(name: str) -> dict[str, Any] | None:
    p = CHANNEL_PRESETS.get(name)
    return deepcopy(p) if p else None


def apply_preset_to_file_cfg(
    file_cfg: dict,
    name: str,
    *,
    keep_base: bool = True,
) -> dict:
    """
    file_cfg에 프리셋 슬롯을 덮어쓴 새 dict 반환.
    keep_base=True 이면 기존 base/initial은 유지.
    """
    preset = get_preset(name)
    if not preset:
        raise KeyError(f"unknown preset: {name}")

    out = dict(file_cfg)
    for key, slot in preset.get("slots", {}).items():
        prev = out.get(key) if isinstance(out.get(key), dict) else {}
        merged = dict(slot)
        if keep_base:
            if prev.get("base") not in (None, ""):
                merged["base"] = prev["base"]
            if prev.get("initial") not in (None, ""):
                merged["initial"] = prev["initial"]
        out[key] = merged

    for gk, gv in (preset.get("globals") or {}).items():
        out[gk] = gv

    return out
