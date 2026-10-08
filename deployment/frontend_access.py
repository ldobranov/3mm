"""Bounded frontend-origin policy shared by clean install and UI/console update.

Only explicit HTTP(S) origins are allowed. Never execute the service environment
or replace it here: the immutable installer owns protected writes and rollback.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

MAX_ORIGINS = 128
MAX_ENVIRONMENT_BYTES = 1024 * 1024
LOCAL_ORIGINS = (
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
)


def normalize_origin(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 512
        or any(ord(character) <= 32 for character in value)
        or any(character in value for character in ("\\", "?", "#"))
    ):
        raise ValueError("Frontend access requires plain HTTP(S) origins")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or (port is not None and not 1 <= port <= 65535)
            or parsed.netloc.endswith(":")
        ):
            raise ValueError
        if ":" in host:
            host = f"[{ipaddress.IPv6Address(host).compressed}]"
        elif len(host) > 253 or not re.fullmatch(r"[a-z0-9.-]+", host):
            raise ValueError
    except ValueError as exc:
        raise ValueError("Frontend access requires plain HTTP(S) origins") from exc
    if port == (80 if parsed.scheme == "http" else 443):
        port = None
    return f"{parsed.scheme}://{host}" + (f":{port}" if port is not None else "")


def stored_cors_origins(environment_file: Path) -> list[str]:
    if not environment_file.exists():
        return []
    with environment_file.open("rb") as source:
        data = source.read(MAX_ENVIRONMENT_BYTES + 1)
    if len(data) > MAX_ENVIRONMENT_BYTES:
        raise ValueError("Stored service environment is too large")
    value = ""
    for line in data.decode("utf-8").splitlines():
        key, separator, candidate = line.partition("=")
        if separator and key.strip() == "CORS_ORIGINS":
            value = candidate.strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        value = value[1:-1]
    if not value:
        return []
    try:
        origins = (
            json.loads(value)
            if value.startswith("[")
            else [origin.strip() for origin in value.split(",") if origin.strip()]
        )
    except json.JSONDecodeError as exc:
        raise ValueError("Stored CORS_ORIGINS is invalid") from exc
    if not isinstance(origins, list) or len(origins) > MAX_ORIGINS:
        raise ValueError("Stored CORS_ORIGINS must be a bounded origin list")
    return [normalize_origin(origin) for origin in origins]


def frontend_access_origins(
    environment_file: Path, frontend_origin: str, hostname: str
) -> list[str]:
    primary = normalize_origin(frontend_origin)
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", hostname):
        raise ValueError("Device hostname is invalid")
    parsed = urlsplit(primary)
    host = parsed.netloc.rsplit(":", 1)[0] if parsed.port else parsed.netloc
    # For a bracketed IPv6 address without a port, keep the whole netloc.
    generated = [
        primary,
        f"{parsed.scheme}://{host}",
        f"{parsed.scheme}://{host}:8080",
        f"http://{hostname.lower()}.local",
        f"http://{hostname.lower()}.local:8080",
        *LOCAL_ORIGINS,
    ]
    origins = list(
        dict.fromkeys(
            [*stored_cors_origins(environment_file), *map(normalize_origin, generated)]
        )
    )
    if len(origins) > MAX_ORIGINS:
        raise ValueError("Frontend access origin limit exceeded")
    return origins


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, type=Path)
    parser.add_argument("--frontend-origin", required=True)
    parser.add_argument("--hostname", required=True)
    arguments = parser.parse_args()
    try:
        origins = frontend_access_origins(
            arguments.environment, arguments.frontend_origin, arguments.hostname
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise SystemExit(f"Frontend access preflight failed: {exc}") from exc
    print(json.dumps(origins, separators=(",", ":")))


if __name__ == "__main__":
    main()
