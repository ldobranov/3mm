import http.client

import pytest

from setup_service.captive_portal import captive_portal_redirect


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("path,host", [
    ('/generate_204', 'connectivitycheck.gstatic.com'),
    ('/hotspot-detect.html', 'captive.apple.com'),
    ('/connecttest.txt', 'www.msftconnecttest.com'),
    ('/ncsi.txt', 'www.msftncsi.com'),
])
def test_captive_port_redirects_any_http_probe_to_setup(method, path, host):
    setup_url = "http://10.42.0.1:8895/setup"
    with captive_portal_redirect("127.0.0.1", 0, setup_url) as server:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_address[1],
            timeout=2,
        )
        connection.request(
            method,
            path,
            headers={"Host": host},
        )
        response = connection.getresponse()
        response.read()
        connection.close()

    assert response.status == 302
    assert response.getheader("Location") == setup_url
    assert response.getheader("Cache-Control") == "no-store"


def test_captive_port_rejects_a_relative_setup_url():
    with pytest.raises(ValueError):
        with captive_portal_redirect("127.0.0.1", 0, "/setup"):
            pass


def test_recovery_redirect_requires_ap_destination_active_ap_and_marker(monkeypatch):
    import setup_service.captive_portal as portal
    import three_mm_provisioning.recovery_access_point as ap
    from three_mm_provisioning import FileNetworkRecoveryMarker
    state = {'state': 'active'}
    enabled = [True]
    monkeypatch.setattr(ap, 'read_status', lambda: state)
    monkeypatch.setattr(FileNetworkRecoveryMarker, 'is_active', lambda _: enabled[0])
    assert portal.recovery_setup_url('10.42.0.1') == portal.AP_SETUP_URL
    for address in ('127.0.0.1', '192.168.1.88', '::1'):
        assert portal.recovery_setup_url(address) is None
    enabled[0] = False
    assert portal.recovery_setup_url('10.42.0.1') is None
    enabled[0] = True
    for phase in ('inactive', 'restoring', 'failed', 'unavailable'):
        state['state'] = phase
        assert portal.recovery_setup_url('10.42.0.1') is None


def test_node_recovery_listener_closes_redirect_when_ap_stops(monkeypatch):
    import setup_service.captive_portal as portal
    active = [True]
    monkeypatch.setattr(portal, 'recovery_setup_url', lambda address: portal.AP_SETUP_URL if active[0] else None)
    with captive_portal_redirect('127.0.0.1', 0, portal.AP_SETUP_URL, recovery_only=True) as server:
        for enabled, expected in ((True, 302), (False, 404)):
            active[0] = enabled
            connection = http.client.HTTPConnection(*server.server_address, timeout=2)
            connection.request('GET', '/generate_204', headers={'Host': 'connectivitycheck.gstatic.com'})
            response = connection.getresponse()
            response.read()
            assert response.status == expected
            connection.close()


def test_optional_listener_does_not_take_over_existing_web_port():
    with captive_portal_redirect('127.0.0.1', 0, 'http://10.42.0.1:8895/setup') as existing:
        with captive_portal_redirect('127.0.0.1', existing.server_address[1],
                'http://10.42.0.1:8895/setup', recovery_only=True, optional=True) as duplicate:
            assert duplicate is None
