"""Co-located credential repair must not erase a pin or bypass revocation."""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from backend.tests.test_local_agent_pairing import db, _provision
from backend.db.device import DeviceCredential, Device
from backend.services.installation_identity import installation_identity
from backend.services.device_platform import release_authority, prepare_reenrollment
from deployment.local_agent_pairing import (
    ensure_automatic_local_agent_pairing,
    LocalAgentPairingError,
)
from agent.core_client import DeviceCredentialStore
from three_mm_protocol.device_authority import DeviceAuthorityStore
from datetime import UTC, datetime


def test_local_pin_credential_repair_and_explicit_revocation_recovery(
    db, tmp_path, monkeypatch
):
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    installation = installation_identity(db).identity
    data, provisioning = tmp_path / "agent", tmp_path / "provisioning"
    _provision(provisioning)

    def bootstrap():
        return ensure_automatic_local_agent_pairing(
            db, agent_data_dir=data, provisioning_data_dir=provisioning
        )

    assert bootstrap().status == "paired"
    credential = DeviceCredentialStore(data).load()
    pin = DeviceAuthorityStore(
        data, credential.device_id, credential.credential_id
    ).load()
    assert pin.installation == installation
    (data / "core-credential.json").unlink()
    assert bootstrap().status == "repaired"
    credential = DeviceCredentialStore(data).load()
    assert (
        DeviceAuthorityStore(data, credential.device_id, credential.credential_id)
        .load()
        .installation
        == installation
    )
    db.scalar(
        select(DeviceCredential).where(DeviceCredential.revoked_at.is_(None))
    ).revoked_at = datetime.now(UTC)
    db.commit()
    with pytest.raises(LocalAgentPairingError, match="revoked"):
        bootstrap()
    device = db.scalar(select(Device))
    released = release_authority(
        db,
        device,
        expected_revision=0,
        confirmed_device_id=device.device_id,
        actor_id=1,
    )
    prepare_reenrollment(
        db,
        device,
        expected_revision=released.revision,
        confirmed_device_id=device.device_id,
        actor_id=1,
    )
    assert bootstrap().status == "repaired"
    credential = DeviceCredentialStore(data).load()
    assert (
        DeviceAuthorityStore(data, credential.device_id, credential.credential_id)
        .load()
        .installation
        == installation
    )
