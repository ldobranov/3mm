"""Closed, correlated discovery and explicit transport failure without fallback."""

from copy import deepcopy
from pathlib import Path

import pytest

from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError


def observation():
    return {
        "discovery_version": 1, "binding_id": "output", "capability_id": "example.output",
        "contract_version": "1.0", "action": "pulse", "observed_at": "2026-10-25T12:00:00Z",
        "access": "granted", "selected_device_id": "dev_" + "1" * 32,
        "candidates": [{"device_id": "dev_" + "1" * 32, "provider_type": "native",
            "provider_id": "example.provider", "provider_version": "1.0.0", "contract_version": "1.0",
            "compatible": True, "selectable": True, "blockers": [], "readiness": "ready",
            "readiness_reason": None}], "next_after_device_id": None,
    }


@pytest.mark.parametrize("fault", ["binding", "version", "foreign_resource", "denied_resource", "inventory", "admin_inventory", "secret", "readiness", "selectable"])
def test_invalid_signed_observation_cannot_be_used_as_resource_authority(monkeypatch, fault):
    value = observation()
    if fault == "binding": value["binding_id"] = "other"
    elif fault == "version": value["discovery_version"] = True
    elif fault == "foreign_resource": value["selected_device_id"] = "dev_" + "2" * 32
    elif fault == "denied_resource": value["access"] = "required"
    elif fault == "inventory": value["candidates"].append(deepcopy(value["candidates"][0]))
    elif fault == "admin_inventory": value["access"] = "not_evaluated"
    elif fault == "secret": value["candidates"][0]["credential"] = "not-public"
    elif fault == "readiness": value["candidates"][0]["readiness"] = "unknown"
    else: value["candidates"][0]["blockers"] = ["contract_missing"]
    client = ApplicationPlatformClient(Path("unused"), "a" * 24, b"s" * 32)
    monkeypatch.setattr(client, "_call", lambda *_: value)
    with pytest.raises(ApplicationPlatformError) as error:
        client.discover_command("output")
    assert error.value.reason == "response_invalid"


@pytest.mark.parametrize("reason", ["operation_unsupported", "deadline_exceeded"])
def test_unsupported_or_lost_discovery_never_falls_back_to_inventory_or_submit(monkeypatch, reason):
    client = ApplicationPlatformClient(Path("unused"), "a" * 24, b"s" * 32)
    calls = []

    def fail(action, payload):
        calls.append((action, payload))
        raise ApplicationPlatformError("unavailable", reason=reason)

    monkeypatch.setattr(client, "_call", fail)
    with pytest.raises(ApplicationPlatformError) as error:
        client.discover_command("output")
    assert not error.value.retryable
    assert calls == [("command.discover", {"binding_id": "output"})]
