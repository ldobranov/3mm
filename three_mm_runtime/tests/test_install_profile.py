import pytest

from three_mm_runtime.install_profile import InstallProfile, read_install_profile, validate_profile_role
from three_mm_runtime import activate as activation
from three_mm_protocol import AgentRole
from three_mm_provisioning import FileProvisioningStore, NetworkCredentials, ProvisioningRequest, ProvisioningSnapshot


def test_legacy_release_is_full(tmp_path):
    assert read_install_profile(tmp_path) is InstallProfile.FULL


@pytest.mark.parametrize("value", ["", "NODE", "cloud", "../full"])
def test_invalid_marker_fails_closed(tmp_path, value):
    (tmp_path / '.3mm-install-profile').write_text(value)
    with pytest.raises(RuntimeError):
        read_install_profile(tmp_path)


@pytest.mark.parametrize("role", [None, "node"])
def test_node_allows_setup_and_agent(role):
    validate_profile_role(InstallProfile.NODE, role)


@pytest.mark.parametrize("role", [AgentRole.HUB, AgentRole.STANDALONE])
def test_minimal_profile_rejects_promotion_before_systemd(tmp_path, monkeypatch, role):
    (tmp_path / '.3mm-install-profile').write_text('node\n')
    FileProvisioningStore(tmp_path / 'state').save(ProvisioningSnapshot.provisioned(
        ProvisioningRequest(network=NetworkCredentials('wifi', 'test-only'),
            locale='en-GB', device_name='test-node', administrator_name='admin', role=role)))
    monkeypatch.setattr(activation, 'RELEASE_ROOT', tmp_path)
    monkeypatch.setattr(activation, '_systemctl', lambda *a: pytest.fail('No service mutation allowed'))
    monkeypatch.setattr(activation, '_bootstrap_local_agent', lambda *a: pytest.fail('No Core bootstrap allowed'))
    with pytest.raises(RuntimeError, match='full runtime'):
        activation.activate(tmp_path / 'state')


def test_full_profile_preserves_roles():
    for role in AgentRole:
        validate_profile_role(InstallProfile.FULL, role)


def test_minimal_setup_does_not_require_absent_core_units(tmp_path, monkeypatch):
    monkeypatch.setattr(activation, '_require_setup_interface', lambda: None)
    (tmp_path / '.3mm-install-profile').write_text('node\n')
    calls = []
    monkeypatch.setattr(activation, 'RELEASE_ROOT', tmp_path)
    monkeypatch.setattr(activation, '_systemctl', lambda *args: calls.append(args))
    activation.activate(tmp_path / 'state')
    assert calls[0] == ('disable', '--now', '3mm-agent.service')
    assert calls[1] == ('enable', '--now', *activation.SETUP_UNITS)
