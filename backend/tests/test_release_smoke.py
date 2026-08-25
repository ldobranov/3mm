from __future__ import annotations

import json

import pytest

from deployment import release_smoke


class FakeResponse:
    def __init__(self, value: dict | str):
        self.body = value.encode() if isinstance(value, str) else json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


def response_map(device_id: str = "device-123") -> dict[str, dict | str]:
    return {
        "http://core/ready": {"status": "ready"},
        "http://core/openapi.json": {"paths": {
            "/api/displays": {},
            "/api/ai/extensions/plan": {},
            "/api/v1/extension-projects": {},
            "/api/v1/runtime-extensions/catalog": {},
        }},
        "http://agent/ready": {"status": "ready", "device_id": device_id},
        "http://agent/api/v1/agent/hello": {"device_id": device_id},
        "http://agent/api/v1/agent/inventory": {
            "device_id": device_id,
            "python_version": "3.13.0",
            "memory_total_bytes": 1_073_741_824,
            "architecture": "aarch64",
        },
        "http://web/user/login": '<html><div id="app"></div></html>',
        "http://web/extensions/ai-builder": '<html><div id="app"></div></html>',
    }


def install_fake_network(monkeypatch, responses: dict[str, dict | str]) -> None:
    def fake_open(request, timeout):
        assert timeout == 2
        return FakeResponse(responses[request.full_url])

    monkeypatch.setattr(release_smoke, "urlopen", fake_open)


def test_release_smoke_covers_web_core_agent_and_identity(monkeypatch):
    install_fake_network(monkeypatch, response_map())

    result = release_smoke.verify_release(release_smoke.ReleaseEndpoints(
        core="http://core", agent="http://agent", web="http://web", timeout=2
    ))

    assert result == {
        "core": "ready",
        "agent": "ready",
        "web": "ready",
        "device_id": "device-123",
        "architecture": "aarch64",
    }


def test_release_smoke_rejects_inconsistent_agent_identity(monkeypatch):
    responses = response_map()
    responses["http://agent/api/v1/agent/inventory"] = {
        "device_id": "different-device",
        "python_version": "3.13.0",
        "memory_total_bytes": 1_073_741_824,
    }
    install_fake_network(monkeypatch, responses)

    with pytest.raises(release_smoke.SmokeFailure, match="inventory identity"):
        release_smoke.verify_release(release_smoke.ReleaseEndpoints(
            core="http://core", agent="http://agent", web="http://web", timeout=2
        ))
