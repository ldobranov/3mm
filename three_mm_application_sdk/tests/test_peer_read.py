"""Public SDK validation and no fallback; no Core imports or live connections."""

from pathlib import Path

import pytest

from three_mm_application_sdk import (
    ApplicationPlatformClient,
    ApplicationPlatformError,
    SDK_VERSION,
)
from three_mm_protocol.application_peer_read import ApplicationPeerReadV1
from three_mm_protocol.tests.test_installation_identity import identity_and_key


def result():
    # Existing protocol fixture makes a real valid public key pair.
    receiver, _ = identity_and_key()
    return {
        "read_version": 1,
        "binding_id": "remote_link",
        "peer": {
            "link_id": "peer_" + "a" * 32,
            "state": "active",
            "consent_revision": 1,
            "consent": {
                "consent_version": 1,
                "summary_fields": [],
                "node_ids": [],
                "node_fields": [],
            },
            "origin": "https://receiver.example",
            "receiver_identity": receiver.model_dump(mode="json"),
            "target_module_id": "org.example.receiver",
            "remote_binding_id": "peer_" + "b" * 32,
            "credential_expires_at": None,
        },
    }


def test_additive_method_uses_one_exact_logical_selector(monkeypatch):
    client = ApplicationPlatformClient(Path("unused.sock"), "a" * 24, b"s" * 32)
    calls = []
    monkeypatch.setattr(
        client,
        "_call",
        lambda action, payload: calls.append((action, payload)) or result(),
    )
    assert client.read_installation_peer("remote_link")["peer"]["state"] == "active"
    assert calls == [("installation.peers.read", {"binding_id": "remote_link"})]
    assert SDK_VERSION == "1.3"


@pytest.mark.parametrize(
    "binding",
    [
        None,
        True,
        1,
        "",
        "*",
        "peer:remote:read",
        "../peer",
        "remote\n",
        "UPPER",
        "x" * 97,
    ],
)
def test_bad_selector_is_rejected_before_transport(monkeypatch, binding):
    client = ApplicationPlatformClient(Path("unused.sock"), "a" * 24, b"s" * 32)
    monkeypatch.setattr(
        client, "_call", lambda *_: pytest.fail("Invalid selector reached transport")
    )
    with pytest.raises(ValueError):
        client.read_installation_peer(binding)


@pytest.mark.parametrize(
    "fault", ["foreign", "version", "secret", "receiver", "wire", "metadata"]
)
def test_response_is_closed_and_correlated(monkeypatch, fault):
    value = result()
    if fault == "foreign":
        value["binding_id"] = "another_link"
    elif fault == "version":
        value["read_version"] = True
    elif fault == "secret":
        value["peer"]["credential"] = {"secret": "NEVER"}
    elif fault == "receiver":
        value["peer"]["receiver_identity"]["private_key"] = "NEVER"
    elif fault == "wire":
        value["peer"]["peer_version"] = True
    else:
        value["peer"]["peer_version"] = 2
        value["peer"]["enrollment_metadata"] = {}
    client = ApplicationPlatformClient(Path("unused.sock"), "a" * 24, b"s" * 32)
    monkeypatch.setattr(client, "_call", lambda *_: value)
    with pytest.raises(ApplicationPlatformError):
        client.read_installation_peer("remote_link")


def test_unsupported_old_core_and_lost_reply_never_retry_or_use_legacy_list(
    monkeypatch,
):
    client = ApplicationPlatformClient(Path("unused.sock"), "a" * 24, b"s" * 32)
    calls = []

    def refuse(action, payload):
        calls.append(action)
        raise ApplicationPlatformError("Platform action is unsupported")

    monkeypatch.setattr(client, "_call", refuse)
    with pytest.raises(ApplicationPlatformError):
        client.read_installation_peer("remote_link")
    assert calls == ["installation.peers.read"]
    assert ApplicationPeerReadV1.model_validate(result()).binding_id == "remote_link"
