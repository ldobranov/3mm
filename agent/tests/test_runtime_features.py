import json
import pytest
import requests

from agent.core_client import (
    CommandJournal,
    CorePublisher,
    DeviceCredential,
    OutboxStore,
    ReconciliationStore,
)
from agent.runtime_features import RuntimeFeaturePublisher
from three_mm_protocol.node_features import CoreNodeProtocolV1


def publisher(tmp_path, **kwargs):
    return CorePublisher(
        core_url="http://core.test",
        credential=DeviceCredential(
            device_id="dev_" + "1" * 32,
            credential_id="cred_" + "2" * 32,
            credential_secret="test-secret-" + "x" * 32,
        ),
        inventory_provider=lambda: None,
        command_journal=CommandJournal(tmp_path),
        reconciliation_store=ReconciliationStore(tmp_path),
        outbox=OutboxStore(tmp_path),
        started_monotonic=0,
        **kwargs,
    )


def response(status, body=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    return result


def test_negotiation_cache_reconnect_and_identity_bound_ack(monkeypatch, tmp_path):
    node = publisher(tmp_path)
    declaration = node._runtime_declaration()
    helper = RuntimeFeaturePublisher(node.core_url, node.credential)
    now = [0]
    monkeypatch.setattr("agent.runtime_features.time.monotonic", lambda: now[0])
    calls = []

    def get(url, **kw):
        assert kw["allow_redirects"] is False
        calls.append("get")
        return response(
            200,
            CoreNodeProtocolV1(
                device_id=node.credential.device_id,
                runtime_features_revision=0 if len(calls) == 1 else 1,
            ).model_dump(mode="json"),
        )

    def put(url, **kw):
        assert kw["allow_redirects"] is False
        calls.append("put")
        assert kw["json"]["expected_revision"] == (0 if len(calls) == 2 else 1)
        return response(
            200,
            {
                "device_id": node.credential.device_id,
                "source": "advertised",
                "revision": 1,
                "declaration": declaration,
            },
        )

    monkeypatch.setattr("agent.runtime_features.requests.get", get)
    monkeypatch.setattr("agent.runtime_features.requests.put", put)
    assert helper.inventory_version(2, node._runtime_declaration) == 2
    now[0] = 31
    assert helper.inventory_version(1, node._runtime_declaration) == 1
    assert calls == ["get", "put"]
    now[0] = 301
    assert helper.inventory_version(2, node._runtime_declaration) == 2
    assert calls == ["get", "put", "get", "put"]


@pytest.mark.parametrize("status", [404, 405, 401, 403, 500, 302])
def test_only_missing_legacy_negotiation_endpoint_allows_inventory1_fallback(
    monkeypatch, tmp_path, status
):
    node = publisher(tmp_path)
    helper = RuntimeFeaturePublisher(node.core_url, node.credential)
    monkeypatch.setattr(
        "agent.runtime_features.requests.get", lambda *a, **k: response(status)
    )
    monkeypatch.setattr(
        "agent.runtime_features.requests.put",
        lambda *a, **k: pytest.fail("Unexpected feature PUT"),
    )
    if status in {404, 405}:
        assert helper.inventory_version(2, node._runtime_declaration) == 1
    else:
        with pytest.raises((requests.HTTPError, ValueError)):
            helper.inventory_version(2, node._runtime_declaration)


@pytest.mark.parametrize(
    "failure", ["offline", "wrong_device", "bad_ack", "unsupported_schema"]
)
def test_negotiation_failure_is_not_a_silent_downgrade(monkeypatch, tmp_path, failure):
    node = publisher(tmp_path)
    protocol = CoreNodeProtocolV1(device_id=node.credential.device_id).model_dump(
        mode="json"
    )
    if failure == "wrong_device":
        protocol["device_id"] = "dev_" + "f" * 32
    if failure == "unsupported_schema":
        protocol["runtime_feature_schema_versions"] = [2]

    def get(*a, **k):
        if failure == "offline":
            raise requests.ConnectionError("offline")
        return response(200, protocol)

    monkeypatch.setattr("agent.runtime_features.requests.get", get)
    monkeypatch.setattr(
        "agent.runtime_features.requests.put",
        lambda *a, **k: response(
            200,
            {
                "device_id": "dev_" + "f" * 32,
                "source": "advertised",
                "revision": 1,
                "declaration": node._runtime_declaration(),
            },
        ),
    )
    with pytest.raises((requests.RequestException, ValueError)):
        RuntimeFeaturePublisher(node.core_url, node.credential).inventory_version(
            2, node._runtime_declaration
        )


def test_optional_advertisement_matches_components_and_verified_update_helper(
    monkeypatch, tmp_path
):
    node = publisher(tmp_path)
    assert node._runtime_declaration()["command_types"] == [
        "agent.refresh_inventory",
        "capability.invoke",
    ]
    node.module_runtime = object()
    node.automation_store = object()
    node.gpio_configuration = object()
    node.node_update_transport = object()
    support = {"signed_apply_supported": False}
    monkeypatch.setattr(CorePublisher, "_node_update_support", lambda self: support)
    features = node._runtime_declaration()
    assert "module_lifecycle" in features["features"]
    assert "application.capability.invoke" in features["command_types"]
    assert "agent.update.prepare" in features["command_types"]
    assert "agent.update.apply" not in features["command_types"]
    support["signed_apply_supported"] = True
    assert "agent.update.apply" in node._runtime_declaration()["command_types"]
