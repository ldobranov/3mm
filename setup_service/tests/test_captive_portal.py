import http.client

import pytest

from setup_service.captive_portal import captive_portal_redirect


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_captive_port_redirects_any_http_probe_to_setup(method):
    setup_url = "http://10.42.0.1:8895/setup"
    with captive_portal_redirect("127.0.0.1", 0, setup_url) as server:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_address[1],
            timeout=2,
        )
        connection.request(
            method,
            "/generate_204",
            headers={"Host": "connectivitycheck.gstatic.com"},
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
