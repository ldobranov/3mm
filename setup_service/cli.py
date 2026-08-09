"""Command-line entry point for the headless setup prototype."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import uvicorn

from setup_service.config import SetupSettings
from setup_service.main import create_app


def build_parser() -> argparse.ArgumentParser:
    defaults = SetupSettings.from_env()
    parser = argparse.ArgumentParser(description="Run the 3mm setup service")
    parser.add_argument("--host", default=defaults.host)
    parser.add_argument("--port", type=int, default=defaults.port)
    parser.add_argument("--data-dir", type=Path, default=defaults.data_dir)
    parser.add_argument("--log-level", default="info")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    settings = SetupSettings(
        data_dir=arguments.data_dir,
        host=arguments.host,
        port=arguments.port,
    )
    uvicorn.run(
        create_app(settings=settings),
        host=settings.host,
        port=settings.port,
        log_level=arguments.log_level,
    )
