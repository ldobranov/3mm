import os
from pathlib import Path

import backend.database  # noqa: F401 - register complete model metadata
import pytest
from agent.core_client import DeviceCredentialStore
from backend.db.audit_log import AuditLog
from backend.db.base import Base
from backend.db.device import Device, DeviceCredential, DevicePairingRequest
from backend.db.user import User
from deployment.local_agent_pairing import (
    PAIRING_PRIVATE_KEY_NAME,
    ensure_automatic_local_agent_pairing,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from three_mm_protocol import AgentRole
from three_mm_provisioning import (
    FileProvisioningStore,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            User(
                username="admin",
                email="admin@example.com",
                hashed_password="not-a-real-hash",
                role="admin",
            )
        )
        session.commit()
        yield session
    engine.dispose()


def _provision(
    path: Path,
    *,
    role: AgentRole = AgentRole.STANDALONE,
) -> None:
    FileProvisioningStore(path).save(
        ProvisioningSnapshot.provisioned(
            ProvisioningRequest(
                network=NetworkCredentials("private-network", "not-persisted"),
                locale="en-GB",
                device_name="rasp-3mm",
                administrator_name="admin",
                role=role,
                hub_endpoint="http://hub.local" if role is AgentRole.NODE else None,
            )
        )
    )


def test_clean_standalone_setup_pairs_local_agent_once(
    db: Session,
    tmp_path: Path,
) -> None:
    agent_data = tmp_path / "agent"
    provisioning_data = tmp_path / "provisioning"
    _provision(provisioning_data)

    first = ensure_automatic_local_agent_pairing(
        db,
        agent_data_dir=agent_data,
        provisioning_data_dir=provisioning_data,
    )
    second = ensure_automatic_local_agent_pairing(
        db,
        agent_data_dir=agent_data,
        provisioning_data_dir=provisioning_data,
    )

    assert first.status == "paired"
    assert second.status == "already_paired"
    assert first.device_id == second.device_id
    assert (agent_data / "identity.json").is_file()
    assert DeviceCredentialStore(agent_data).load() is not None
    private_key = agent_data / PAIRING_PRIVATE_KEY_NAME
    assert private_key.is_file()
    if os.name != "nt":
        assert private_key.stat().st_mode & 0o077 == 0

    device = db.scalar(select(Device))
    request = db.scalar(select(DevicePairingRequest))
    audit = db.scalar(select(AuditLog))
    assert device is not None
    assert device.device_id == first.device_id
    assert device.display_name == "rasp-3mm"
    assert device.role == "standalone"
    assert request is not None
    assert request.public_key.startswith("ssh-ed25519 ")
    assert audit is not None
    assert audit.action == "DEVICE_PAIRING_APPROVED"
    assert db.query(Device).count() == 1
    assert db.query(DeviceCredential).count() == 1
    assert db.query(DevicePairingRequest).count() == 1


def test_node_setup_does_not_register_against_its_local_database(
    db: Session,
    tmp_path: Path,
) -> None:
    agent_data = tmp_path / "agent"
    provisioning_data = tmp_path / "provisioning"
    _provision(provisioning_data, role=AgentRole.NODE)

    result = ensure_automatic_local_agent_pairing(
        db,
        agent_data_dir=agent_data,
        provisioning_data_dir=provisioning_data,
    )

    assert result.status == "external_core"
    assert result.device_id is None
    assert not agent_data.exists()
    assert db.query(Device).count() == 0
