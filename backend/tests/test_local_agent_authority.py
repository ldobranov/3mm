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


def _bootstrap_cli(db, tmp_path, monkeypatch, role):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    from sqlalchemy.orm import Session

    source = Path(__file__).resolve().parents[2] / 'deployment/bootstrap-local-agent.py'
    spec = importlib.util.spec_from_file_location('local_bootstrap_cli', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data, provisioning = tmp_path / 'agent', tmp_path / 'provisioning'
    _provision(provisioning, role=role)
    monkeypatch.setattr(module, 'SessionLocal', lambda: Session(db.get_bind()))
    monkeypatch.setattr(module, 'parse_args', lambda: SimpleNamespace(
        automatic=True, agent_data_dir=data, provisioning_data_dir=provisioning,
        admin_email=None))
    return module, data


@pytest.mark.parametrize('role', ['standalone', 'hub'])
def test_installed_bootstrap_pins_fresh_core_before_starting_agent(db, tmp_path, monkeypatch, role):
    from backend.db.installation_identity import CoreInstallationIdentity
    from three_mm_protocol import AgentRole

    monkeypatch.setenv('AI_SETTINGS_MASTER_KEY', Fernet.generate_key().decode())
    module, data = _bootstrap_cli(db, tmp_path, monkeypatch, AgentRole(role))
    assert db.get(CoreInstallationIdentity, 1) is None
    db.rollback()
    module.main()
    credential = DeviceCredentialStore(data).load()
    pin = DeviceAuthorityStore(data, credential.device_id, credential.credential_id).load()
    stored = db.get(CoreInstallationIdentity, 1)
    assert pin.installation.installation_id == stored.installation_id
    assert pin.installation.key_id == stored.key_id
    assert db.query(DeviceCredential).count() == 1
    module.main()
    assert DeviceAuthorityStore(data, credential.device_id, credential.credential_id).load() == pin
    assert db.query(DeviceCredential).count() == 1


def test_installed_bootstrap_missing_identity_key_issues_no_credential(db, tmp_path, monkeypatch):
    from three_mm_protocol import AgentRole
    monkeypatch.delenv('AI_SETTINGS_MASTER_KEY', raising=False)
    module, data = _bootstrap_cli(db, tmp_path, monkeypatch, AgentRole.STANDALONE)
    with pytest.raises(SystemExit, match='identity encryption key'):
        module.main()
    assert not (data / 'core-credential.json').exists()
    assert db.query(DeviceCredential).count() == 0


def test_node_bootstrap_does_not_create_local_core_identity(db, tmp_path, monkeypatch):
    from backend.db.installation_identity import CoreInstallationIdentity
    from three_mm_protocol import AgentRole
    monkeypatch.delenv('AI_SETTINGS_MASTER_KEY', raising=False)
    module, data = _bootstrap_cli(db, tmp_path, monkeypatch, AgentRole.NODE)
    module.main()
    assert db.get(CoreInstallationIdentity, 1) is None
    assert not (data / 'core-credential.json').exists()
