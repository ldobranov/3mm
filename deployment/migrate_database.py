#!/usr/bin/env python3
"""Bring legacy create_all databases under Alembic before upgrading."""

from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import inspect

from backend.database import engine


def main() -> None:
    release_root = Path(__file__).resolve().parents[1]
    config = Config(str(release_root / "alembic.ini"))
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables:
        if "device_commands" in tables:
            command.stamp(config, "8b42d8e9f120")
        elif "devices" in tables:
            command.stamp(config, "7a31d5d293e1")
        elif tables:
            raise RuntimeError(
                "Legacy database predates the supported device-registry baseline"
            )
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
