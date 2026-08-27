"""Command-line entry point for the headless setup prototype."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from pathlib import Path
from typing import Sequence

import uvicorn

from setup_service.config import SetupSettings
from setup_service.captive_portal import captive_portal_redirect
from setup_service.main import create_app


def build_parser() -> argparse.ArgumentParser:
    defaults = SetupSettings.from_env()
    parser = argparse.ArgumentParser(description="Run the 3mm setup service")
    parser.add_argument("--host", default=defaults.host)
    parser.add_argument("--port", type=int, default=defaults.port)
    parser.add_argument("--data-dir", type=Path, default=defaults.data_dir)
    parser.add_argument(
        "--network-helper-socket",
        type=Path,
        default=defaults.network_helper_socket,
    )
    parser.add_argument("--captive-port", type=int)
    parser.add_argument(
        "--captive-url",
        default="http://10.42.0.1:8895/setup",
    )
    parser.add_argument("--log-level", default="info")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    settings = SetupSettings(
        data_dir=arguments.data_dir,
        host=arguments.host,
        port=arguments.port,
        network_helper_socket=arguments.network_helper_socket,
    )
    captive_entrypoint = (
        captive_portal_redirect(
            host=settings.host,
            port=arguments.captive_port,
            setup_url=arguments.captive_url,
        )
        if arguments.captive_port is not None
        else nullcontext()
    )
    with captive_entrypoint:
        uvicorn.run(
            create_app(settings=settings),
            host=settings.host,
            port=settings.port,
            log_level=arguments.log_level,
        )
