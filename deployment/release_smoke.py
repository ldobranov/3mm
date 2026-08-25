#!/usr/bin/env python3
"""Dependency-free smoke verification for a running 3mm release."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SmokeFailure(RuntimeError):
    """Raised when a deployed release does not satisfy its public contract."""


@dataclass(frozen=True)
class ReleaseEndpoints:
    core: str = "http://127.0.0.1:8887"
    agent: str = "http://127.0.0.1:8890"
    web: str = "http://127.0.0.1:8080"
    timeout: float = 5.0


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _read(url: str, timeout: float) -> bytes:
    request = Request(url, headers={"Accept": "application/json, text/html"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - caller selects the target
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SmokeFailure(f"Request failed for {url}: {exc}") from exc


def _read_json(base: str, path: str, timeout: float) -> dict[str, Any]:
    url = _url(base, path)
    try:
        value = json.loads(_read(url, timeout))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SmokeFailure(f"Expected JSON from {url}") from exc
    if not isinstance(value, dict):
        raise SmokeFailure(f"Expected a JSON object from {url}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def verify_release(endpoints: ReleaseEndpoints) -> dict[str, str]:
    core_ready = _read_json(endpoints.core, "/ready", endpoints.timeout)
    _require(core_ready.get("status") == "ready", "Core is not ready")

    openapi = _read_json(endpoints.core, "/openapi.json", endpoints.timeout)
    paths = openapi.get("paths", {})
    _require(isinstance(paths, dict), "Core OpenAPI paths are unavailable")
    required_paths = {
        "/api/displays",
        "/api/ai/extensions/plan",
        "/api/v1/extension-projects",
        "/api/v1/runtime-extensions/catalog",
    }
    missing_paths = sorted(required_paths - set(paths))
    _require(not missing_paths, f"Core is missing required API paths: {', '.join(missing_paths)}")

    agent_ready = _read_json(endpoints.agent, "/ready", endpoints.timeout)
    hello = _read_json(endpoints.agent, "/api/v1/agent/hello", endpoints.timeout)
    inventory = _read_json(endpoints.agent, "/api/v1/agent/inventory", endpoints.timeout)
    device_id = str(agent_ready.get("device_id") or "")
    _require(agent_ready.get("status") == "ready", "Agent is not ready")
    _require(bool(device_id), "Agent did not expose a device identity")
    _require(hello.get("device_id") == device_id, "Agent hello identity does not match readiness")
    _require(inventory.get("device_id") == device_id, "Agent inventory identity does not match readiness")
    _require(bool(inventory.get("python_version")), "Agent inventory is incomplete")
    _require(int(inventory.get("memory_total_bytes") or 0) > 0, "Agent memory inventory is invalid")

    for path in ("/user/login", "/extensions/ai-builder"):
        html = _read(_url(endpoints.web, path), endpoints.timeout).decode("utf-8", errors="replace")
        _require('id="app"' in html, f"Web application shell is unavailable at {path}")

    return {
        "core": "ready",
        "agent": "ready",
        "web": "ready",
        "device_id": device_id,
        "architecture": str(inventory.get("architecture") or "unknown"),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-url", default=ReleaseEndpoints.core)
    parser.add_argument("--agent-url", default=ReleaseEndpoints.agent)
    parser.add_argument("--web-url", default=ReleaseEndpoints.web)
    parser.add_argument("--timeout", type=float, default=ReleaseEndpoints.timeout)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = verify_release(ReleaseEndpoints(
            core=args.core_url,
            agent=args.agent_url,
            web=args.web_url,
            timeout=args.timeout,
        ))
    except SmokeFailure as exc:
        print(f"FAILED: {exc}")
        return 1
    print("3mm release smoke test passed")
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
