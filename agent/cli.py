"""Command-line entry point for the 3mm Agent."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import uvicorn

from agent.config import AgentSettings
from agent.hardware import HardwareProfile
from agent.main import create_app
from three_mm_protocol import AgentRole


def build_parser() -> argparse.ArgumentParser:
    defaults = AgentSettings.from_env()
    parser = argparse.ArgumentParser(description="Run the 3mm device Agent")
    parser.add_argument("--host", default=defaults.host)
    parser.add_argument("--port", type=int, default=defaults.port)
    parser.add_argument("--data-dir", type=Path, default=defaults.data_dir)
    parser.add_argument(
        "--provisioning-data-dir",
        type=Path,
        default=defaults.provisioning_data_dir,
    )
    parser.add_argument("--name", default=defaults.display_name)
    parser.add_argument(
        "--role",
        choices=[role.value for role in AgentRole],
        default=defaults.role.value,
    )
    parser.add_argument(
        "--hardware-profile",
        choices=[profile.value for profile in HardwareProfile],
        default=defaults.hardware_profile.value,
    )
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--core-url", default=defaults.core_url)
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=int,
        default=defaults.heartbeat_interval_seconds,
    )
    parser.set_defaults(
        gpio_driver=defaults.gpio_driver,
        gpio_chip=defaults.gpio_chip,
        gpio_inputs=defaults.gpio_inputs,
        gpio_outputs=defaults.gpio_outputs,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    settings = AgentSettings(
        data_dir=arguments.data_dir,
        host=arguments.host,
        port=arguments.port,
        display_name=arguments.name,
        role=AgentRole(arguments.role),
        hardware_profile=HardwareProfile(arguments.hardware_profile),
        provisioning_data_dir=arguments.provisioning_data_dir,
        core_url=arguments.core_url,
        heartbeat_interval_seconds=arguments.heartbeat_interval_seconds,
        gpio_driver=arguments.gpio_driver,
        gpio_chip=arguments.gpio_chip,
        gpio_inputs=arguments.gpio_inputs,
        gpio_outputs=arguments.gpio_outputs,
    )
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=arguments.log_level,
    )
