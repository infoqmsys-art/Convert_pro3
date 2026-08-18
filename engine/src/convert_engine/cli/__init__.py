"""CLI entry (see convert_engine.cli.main)."""

__all__ = ["main"]


def main(*args, **kwargs):
    from convert_engine.cli.main import main as _main

    return _main(*args, **kwargs)
