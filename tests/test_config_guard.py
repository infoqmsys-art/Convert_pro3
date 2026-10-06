"""config.json 교체 거부 조건. 실제 config.json 은 건드리지 않는다."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_guard import ConfigWriteRefused, replace_config_file
from core.config_manager import ConfigManager


class _QuietLogger:
    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def log(self, msg, level="INFO"):
        self.lines.append((level, msg))


def _sample(n_files: int = 400) -> dict:
    files = {
        f"{i:010d}.csv": {"CH0": {"mode": "SET", "base": "1.2345", "scale": "0.05"}}
        for i in range(n_files)
    }
    return {
        "__version__": 2,
        "KD_ENG": {"관수구": {"SAEGL-2026": files}},
        "새길이엔씨": {"구리": {"saegl-guli": {"2026092201.txt": {}}}},
    }


def _write(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _expect_refused(fn) -> str:
    try:
        fn()
    except ConfigWriteRefused as e:
        return str(e)
    raise AssertionError("저장이 거부되어야 합니다.")


def test_normal_save_keeps_bak():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.json")
        _write(p, _sample())
        new = _sample()
        new["KD_ENG"]["관수구"]["SAEGL-2026"]["0000000001.csv"]["CH0"]["base"] = "9.9"
        replace_config_file(p, new)
        with open(p, encoding="utf-8") as f:
            assert json.load(f)["KD_ENG"]["관수구"]["SAEGL-2026"]["0000000001.csv"]["CH0"]["base"] == "9.9"
        with open(p + ".bak", encoding="utf-8") as f:
            assert json.load(f)["KD_ENG"]["관수구"]["SAEGL-2026"]["0000000001.csv"]["CH0"]["base"] == "1.2345"
        assert not os.path.exists(p + ".tmp")


def test_refuse_when_existing_is_broken():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"KD_ENG": {"관수구": ')
        _expect_refused(lambda: replace_config_file(p, _sample()))
        with open(p, encoding="utf-8") as f:
            assert f.read() == '{"KD_ENG": {"관수구": '


def test_refuse_empty_companies():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.json")
        _write(p, _sample())
        _expect_refused(lambda: replace_config_file(p, {}))
        _expect_refused(lambda: replace_config_file(p, {"__version__": 2}))


def test_refuse_half_shrink_same_companies():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.json")
        _write(p, _sample(400))
        _expect_refused(lambda: replace_config_file(p, _sample(50)))
        os.environ["CONVERT_PRO_CONFIG_ALLOW_SHRINK"] = "1"
        try:
            replace_config_file(p, _sample(50))
        finally:
            os.environ.pop("CONVERT_PRO_CONFIG_ALLOW_SHRINK", None)


def test_refuse_create_on_share_path():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.json")
        _expect_refused(lambda: replace_config_file(p, _sample(), allow_create=False))
        assert not os.path.exists(p)


def test_refuse_when_changed_outside():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.json")
        _write(p, _sample())
        before = os.stat(p).st_mtime_ns
        time.sleep(0.05)
        outside = _sample()
        outside["KD_ENG"]["관수구"]["SAEGL-2026"]["0000000002.csv"]["CH0"]["base"] = "outside"
        _write(p, outside)
        _expect_refused(lambda: replace_config_file(p, _sample(), expected_mtime_ns=before))
        with open(p, encoding="utf-8") as f:
            assert json.load(f)["KD_ENG"]["관수구"]["SAEGL-2026"]["0000000002.csv"]["CH0"]["base"] == "outside"


def test_manager_keeps_outside_edit_and_does_not_raise():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.json")
        _write(p, _sample())
        log = _QuietLogger()
        cm = ConfigManager(p, log, persist_on_load=False)
        time.sleep(0.05)
        outside = _sample()
        outside["KD_ENG"]["관수구"]["SAEGL-2026"]["0000000003.csv"]["CH0"]["base"] = "outside"
        _write(p, outside)
        cm.data["KD_ENG"]["관수구"]["SAEGL-2026"]["0000000003.csv"]["CH0"]["base"] = "stale"
        assert cm.save() is False
        with open(p, encoding="utf-8") as f:
            assert json.load(f)["KD_ENG"]["관수구"]["SAEGL-2026"]["0000000003.csv"]["CH0"]["base"] == "outside"
        cm.load(quiet=True)
        cm.data["KD_ENG"]["관수구"]["SAEGL-2026"]["0000000004.csv"]["CH0"]["base"] = "after-reload"
        assert cm.save() is True


def test_manager_broken_reload_keeps_memory():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.json")
        _write(p, _sample())
        cm = ConfigManager(p, _QuietLogger(), persist_on_load=False)
        with open(p, "w", encoding="utf-8") as f:
            f.write("{broken")
        cm.load(quiet=True)
        assert "KD_ENG" in cm.data
        assert cm.save() is False
        with open(p, encoding="utf-8") as f:
            assert f.read() == "{broken"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
