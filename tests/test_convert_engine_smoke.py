"""convert-engine import smoke test (pytest optional)."""

from convert_engine import (
    ConfigManager,
    FileProcessor,
    FillIntervalProcessor,
    SensorProcessor,
    STANDARD_HEADER,
    __version__,
)


class _NullLogger:
    def log(self, msg, level="INFO"):
        pass


def test_public_api_imports():
    assert __version__ == "0.1.0"
    assert STANDARD_HEADER[0] == "timestamp"
    assert FileProcessor is not None


def test_file_processor_construct():
    logger = _NullLogger()
    config = ConfigManager(path="config.example.json", logger=logger)
    fp = FileProcessor(
        config=config,
        tree=None,
        sensor=SensorProcessor(logger=logger),
        fill_interval=FillIntervalProcessor(logger=logger),
        logger=logger,
    )
    assert fp.fill_interval is not None
    assert hasattr(fp.fill_interval, "map_slots")
