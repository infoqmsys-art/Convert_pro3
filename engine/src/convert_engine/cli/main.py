"""
convert-engine CLI — UI 없이 변환만 실행 (초기 스켈레ton).

사용 예:
  convert-engine --config C:/path/config.json convert-all
  convert-engine --config config.json convert-file --company X --site Y --folder Z --file 1227998430.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


class _PrintLogger:
    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")


def _build_processor(config_path: str, convert_root: str | None):
    from convert_engine.config.manager import ConfigManager
    from convert_engine.fill.interval import FillIntervalProcessor
    from convert_engine.pipeline.processor import FileProcessor
    from convert_engine.sensors.processor import SensorProcessor

    logger = _PrintLogger()
    config = ConfigManager(path=config_path, logger=logger)
    sensor = SensorProcessor(logger=logger)
    fill = FillIntervalProcessor(logger=logger)
    fp = FileProcessor(
        config=config,
        tree=None,
        sensor=sensor,
        fill_interval=fill,
        logger=logger,
        convert_root=convert_root or r"C:\data\Convertfile",
    )
    return config, fp


def cmd_convert_all(args) -> int:
    _, fp = _build_processor(args.config, args.convert_root)
    fp.convert_all()
    return 0


def cmd_convert_file(args) -> int:
    _, fp = _build_processor(args.config, args.convert_root)
    result = fp.convert_file(args.company, args.site, args.folder, args.file)
    print(f"result: {result}")
    return 0 if result != "error" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="convert-engine",
        description="Convert Pro 변환 코어 (UI 없음)",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="config.json 경로 (기본: cwd/config.json)",
    )
    parser.add_argument(
        "--convert-root",
        default=None,
        help="변환본 루트 (기본: C:\\data\\Convertfile)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_all = sub.add_parser("convert-all", help="config 전체 파일 변환")
    p_all.set_defaults(func=cmd_convert_all)

    p_one = sub.add_parser("convert-file", help="단일 파일 변환")
    p_one.add_argument("--company", required=True)
    p_one.add_argument("--site", required=True)
    p_one.add_argument("--folder", required=True)
    p_one.add_argument("--file", required=True, help="CSV 파일명")
    p_one.set_defaults(func=cmd_convert_file)

    args = parser.parse_args(argv)
    cfg = Path(args.config)
    if not cfg.is_file():
        print(f"config 없음: {cfg.resolve()}", file=sys.stderr)
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
