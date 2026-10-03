"""C1 through authenticated HTTP/storage, plus existing module/consent readers."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCredential, DeviceInventorySnapshot
from backend.db.module import ApplicationExtensionInstallation
from backend.routes import device_capabilities, device_ingest
from backend.routes.modules import _device_architecture
from backend.services.device_pairing import credential_secret_hash
from backend.services.installation_projection import installation_projection
from backend.tests.test_device_ingest_routes import (
    DEVICE_ID,
    CREDENTIAL_ID,
    CREDENTIAL_SECRET,
    device_headers,
    inventory_payload,
)
from backend.tests.test_device_registry_routes import make_client
from backend.tests.test_installation_peers import (
    NODE,
    pair,
)  # noqa: F401 - shared fixture
from backend.utils import jwt_utils
from three_mm_protocol import AgentInventory
from three_mm_protocol.device_inventory import upgrade_agent_inventory
from three_mm_protocol.tests.test_device_inventory import embedded_inventory


@pytest.fixture(params=["standalone", "hub", "node"])
def core(monkeypatch, request):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "c1-test-only-key-at-least-32-bytes")
    client, db, admin, viewer = make_client()
    device = Device(
        device_id=DEVICE_ID,
        role=request.param,
        protocol_version="1.0",
        approved_at=datetime.now(UTC),
    )
    credential = DeviceCredential(
        credential_id=CREDENTIAL_ID,
        secret_hash=credential_secret_hash(CREDENTIAL_SECRET),
    )
    device.credentials.append(credential)
    db.add(device)
    db.commit()
    client.app.include_router(device_ingest.router)
    client.app.include_router(device_capabilities.router)
    yield client, db, device, credential, {"Authorization": f"Bearer {admin}"}, {
        "Authorization": f"Bearer {viewer}"
    }
    client.close()
    engine = db.get_bind()
    db.close()
    engine.dispose()


@pytest.mark.parametrize("schema", ["legacy", "linux", "embedded"])
def test_inventory_ingestion_raw_compatibility_and_neutral_views(core, schema):
    client, db, device, _, admin, viewer = core
    payload = inventory_payload()
    if schema == "linux":
        payload = upgrade_agent_inventory(
            AgentInventory.model_validate(payload),
            runtime_version="test",
            platform_family="linux",
            platform_system="linux",
        ).model_dump(mode="json")
    elif schema == "embedded":
        payload = embedded_inventory(DEVICE_ID)
    prefix = f"/api/v1/devices/{DEVICE_ID}"
    assert (
        client.post(
            prefix + "/inventory", json=payload, headers=device_headers()
        ).status_code
        == 202
    )
    stored = db.scalar(select(DeviceInventorySnapshot)).inventory.copy()
    assert client.get(prefix, headers=admin).json()["latest_inventory"] == stored
    assert (
        client.get("/api/v1/devices", headers=admin).json()["items"][0][
            "latest_inventory"
        ]
        == stored
    )
    for path in (prefix, "/api/v1/devices"):
        response = client.get(
            path, params={"inventory_schema_version": 2}, headers=admin
        )
        assert response.status_code == 200, response.text
        item = response.json() if path == prefix else response.json()["items"][0]
        assert item["latest_inventory"]["schema_version"] == 2
        assert (
            client.get(
                path, params={"inventory_schema_version": 2}, headers=viewer
            ).status_code
            == 403
        )
        assert (
            client.get(path, params={"inventory_schema_version": 2}).status_code == 401
        )
    db.expire_all()
    assert db.scalar(select(DeviceInventorySnapshot)).inventory == stored
    assert _device_architecture(db, device) == (
        None if schema == "embedded" else "aarch64"
    )
    # An inventory advertisement does NOT bypass the registered module/provider boundary.
    assert client.get(prefix + "/capabilities", headers=admin).json() == []
    assert (
        client.get(
            prefix, params={"inventory_schema_version": 3}, headers=admin
        ).status_code
        == 422
    )


def test_new_inventory_keeps_device_auth_and_identity_binding(core):
    client, db, _, credential, _, _ = core
    prefix = f"/api/v1/devices/{DEVICE_ID}"
    payload = embedded_inventory(DEVICE_ID)
    assert client.post(prefix + "/inventory", json=payload).status_code == 401
    assert (
        client.post(
            prefix + "/inventory", json=payload, headers=device_headers("wrong")
        ).status_code
        == 401
    )
    other = "dev_" + "b" * 32
    assert (
        client.post(
            f"/api/v1/devices/{other}/inventory",
            json=embedded_inventory(other),
            headers=device_headers(),
        ).status_code
        == 403
    )
    assert (
        client.post(
            prefix + "/inventory",
            json=embedded_inventory(other),
            headers=device_headers(),
        ).status_code
        == 403
    )
    assert (
        client.post(
            prefix + "/inventory",
            json={**payload, "schema_version": 3},
            headers=device_headers(),
        ).status_code
        == 422
    )
    credential.revoked_at = datetime.now(UTC)
    db.commit()
    assert (
        client.post(
            prefix + "/inventory", json=payload, headers=device_headers()
        ).status_code
        == 401
    )
    assert db.query(DeviceInventorySnapshot).count() == 0


def test_schema2_read_does_not_rewrite_partial_historic_snapshot(core):
    client, db, device, _, admin, _ = core
    raw = {"hostname": "historic-node"}
    db.add(DeviceInventorySnapshot(device_id=device.id, inventory=raw))
    db.commit()
    prefix = f"/api/v1/devices/{DEVICE_ID}"
    view = client.get(
        prefix, params={"inventory_schema_version": 2}, headers=admin
    ).json()["latest_inventory"]
    assert view["network"]["hostname"] == "historic-node"
    assert view["platform"]["architecture"] is None
    assert view["resources"]["memory_total_bytes"] is None
    assert client.get(prefix, headers=admin).json()["latest_inventory"] == raw


def test_schema2_projection_respects_existing_consent_and_unknowns(pair):
    with Session(pair.sender.engine) as db:
        device = db.scalar(select(Device).where(Device.device_id == NODE))
        payload = embedded_inventory(NODE)
        payload["platform"]["architecture"] = "test-architecture"
        payload["platform_metadata"] = {"private_note": "not-consented"}
        db.add(DeviceInventorySnapshot(device_id=device.id, inventory=payload))
        db.commit()
        application = db.scalar(select(ApplicationExtensionInstallation))
        result = installation_projection(db, application, pair.sender.link_id)
        fields = result.nodes[0].fields
        assert set(fields) == {"online", "agent_version", "architecture"}
        assert fields["architecture"].value == "test-architecture"
        assert fields["architecture"].source == "device.inventory"
        assert fields["agent_version"].status == "unknown"
        assert "not-consented" not in result.model_dump_json()
