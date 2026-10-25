import pytest

from three_mm_provisioning import NetworkDeviceStatus, NetworkManagerStatus
from three_mm_provisioning import network_capabilities as capabilities


class Inspector:
    devices = (NetworkDeviceStatus('wlp2s0','wifi','disconnected'),)
    active = '--'
    ap = 'yes'

    def inspect(self):
        return NetworkManagerStatus(True,'disconnected','none',True,True,self.devices)

    def _execute(self,*arguments):
        return self.active if 'GENERAL.CONNECTION' in arguments else self.ap


@pytest.fixture
def inspector(monkeypatch):
    monkeypatch.setenv('THREE_MM_NETWORK_BACKEND','network-manager')
    value=Inspector()
    monkeypatch.setattr(capabilities.NetworkManagerReadOnlyAdapter,'from_system',lambda:value)
    return value


def test_host_never_probes_networkmanager(monkeypatch):
    monkeypatch.setenv('THREE_MM_NETWORK_BACKEND','host')
    monkeypatch.setattr(capabilities.NetworkManagerReadOnlyAdapter,'from_system',lambda:pytest.fail('Host must not probe NM'))
    assert capabilities.managed_interfaces()==[]


def test_wifi_without_ap_is_still_a_valid_managed_choice(inspector):
    inspector.ap='no'
    assert capabilities.managed_interfaces()==[dict(name='wlp2s0',access_point=False)]
    with pytest.raises(RuntimeError): capabilities.setup_interface()


def test_multiple_adapters_require_explicit_ap_selection(inspector):
    inspector.devices=(NetworkDeviceStatus('wlp2s0','wifi','disconnected'),NetworkDeviceStatus('wlan9','wifi','disconnected'))
    with pytest.raises(RuntimeError): capabilities.setup_interface()
    assert capabilities.setup_interface('wlan9')=='wlan9'
    assert capabilities.setup_interface('wlp2s0')=='wlp2s0'
    with pytest.raises(RuntimeError): capabilities.setup_interface('missing')


def test_setup_ap_does_not_steal_an_active_host_connection(inspector):
    inspector.active='Operating system Wi-Fi'
    with pytest.raises(RuntimeError): capabilities.setup_interface()
    inspector.active='3mm-setup'
    assert capabilities.setup_interface()=='wlp2s0'
