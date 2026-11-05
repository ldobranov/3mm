from __future__ import annotations

import base64
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
import socket
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

import pytest

from three_mm_protocol import ApplicationPublicHttpResponseV1
from three_mm_public_web.server import (
    GuestPage,
    PublicWebRuntimeError,
    create_server,
)


class FakeClient:
    def __init__(self):
        self.requests = []
        self.response = ApplicationPublicHttpResponseV1.model_validate(
            {
                "status": 200,
                "content_type": "text/html; charset=utf-8",
                "headers": {"Cache-Control": "public, max-age=60"},
                "body": "<h1>Hello</h1>",
            }
        )
        self.error = None

    def request(self, **request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


@contextmanager
def running(client, **options):
    server = create_server(Path("unused"), port=0, client=client, **options)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_public_http_adapter_decodes_path_filters_credentials_and_supports_head():
    client = FakeClient()
    with running(client) as base:
        request = Request(
            base + "/caf%C3%A9?q=one&q=two",
            headers={
                "Accept-Language": "bg-BG",
                "Authorization": "Bearer private",
                "Cookie": "admin=session",
            },
        )
        with urlopen(request, timeout=2) as response:
            assert response.status == 200
            assert response.read() == b"<h1>Hello</h1>"
            assert response.headers["Cache-Control"] == "public, max-age=60"
            assert response.headers["X-Content-Type-Options"] == "nosniff"

        with urlopen(Request(base + "/caf%C3%A9", method="HEAD"), timeout=2) as response:
            assert response.status == 200
            assert response.read() == b""
            assert response.headers["Content-Length"] == str(len(b"<h1>Hello</h1>"))

    assert client.requests[0]["path"] == "/café"
    assert client.requests[0]["query"] == {"q": ["one", "two"]}
    assert client.requests[0]["headers"] == {"accept-language": "bg-BG"}
    assert "authorization" not in client.requests[0]["headers"]


def test_public_http_adapter_writes_binary_assets_and_redirects():
    client = FakeClient()
    payload = b"\x89PNG\r\n\x1a\n"
    client.response = ApplicationPublicHttpResponseV1.model_validate(
        {
            "status": 200,
            "content_type": "image/png",
            "headers": {"ETag": '"logo-v1"'},
            "body_base64": base64.b64encode(payload).decode("ascii"),
        }
    )
    with running(client) as base:
        with urlopen(base + "/logo.png", timeout=2) as response:
            assert response.read() == payload
            assert response.headers["Content-Type"] == "image/png"

    client.response = ApplicationPublicHttpResponseV1.model_validate(
        {"status": 301, "headers": {}, "location": "/new"}
    )

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    with running(client) as base:
        opener = build_opener(NoRedirect())
        with pytest.raises(HTTPError) as error:
            opener.open(base + "/old", timeout=2)
        assert error.value.code == 301
        assert error.value.headers["Location"] == "/new"


def test_public_http_adapter_returns_closed_errors_for_methods_and_core_failure():
    client = FakeClient()
    with running(client) as base:
        with pytest.raises(HTTPError) as method:
            urlopen(Request(base + "/", method="POST", data=b"x"), timeout=2)
        assert method.value.code == 405
        assert method.value.headers["Allow"] == "GET, HEAD"

        client.error = PublicWebRuntimeError(503)
        with pytest.raises(HTTPError) as unavailable:
            urlopen(base + "/", timeout=2)
        assert unavailable.value.code == 503
        assert unavailable.value.read() == b"Service Unavailable\n"


@pytest.mark.parametrize("path", ["/bad%2", "/bad%GG", "/%FF"])
def test_public_http_adapter_rejects_invalid_url_encoding(path):
    client = FakeClient()
    with running(client) as base:
        with pytest.raises(HTTPError) as error:
            urlopen(base + path, timeout=2)
        assert error.value.code == 400


FORM_ORIGIN = 'https://forms.example'
FORM_BODY = ('_request_id=' + 'a'*32 + '&choice=morning').encode()


def test_https_guest_cookie_is_host_only_and_ambient_cookies_are_not_relayed():
    client = FakeClient()
    token = f'{"a"*32}.{int(time.time())+60}.{"b"*64}'
    client.response = GuestPage(client.response, '/guest', token)
    with running(client, form_origin=FORM_ORIGIN, guest_forms=True) as base:
        with urlopen(Request(base+'/guest', headers={'Host': 'forms.example',
                'Cookie': 'unrelated=private', 'Authorization': 'Bearer private'}), timeout=5) as response:
            cookie = response.headers['Set-Cookie']
    assert cookie.startswith('__Host-3mm-guest-')
    assert '; Path=/;' in cookie and '; Secure' in cookie and '; HttpOnly' in cookie
    assert '; SameSite=Strict' in cookie and 'Domain=' not in cookie
    assert client.requests == [dict(method='GET', path='/guest', query={}, headers={},
                                    guest={'origin': FORM_ORIGIN, 'cookie': None})]


def test_guest_forms_on_plain_http_cannot_bind_a_non_loopback_address():
    with pytest.raises(ValueError, match='loopback listener'):
        create_server(Path('unused'), host='0.0.0.0', port=0,
                      form_origin='http://127.0.0.1:8081', guest_forms=True)


def post_form(base, *, body=FORM_BODY, path='/demo-request', **headers):
    request = Request(base + path, data=body, headers={
        'Host': 'forms.example', 'Origin': FORM_ORIGIN,
        'Content-Type': 'application/x-www-form-urlencoded', **headers})
    try:
        with urlopen(request, timeout=5) as response:
            return response.status
    except HTTPError as error:
        with error:
            return error.code


def test_post_forwards_only_bounded_fields_and_never_credentials():
    client = FakeClient()
    with running(client, form_origin=FORM_ORIGIN) as base:
        assert post_form(base, Cookie='private=yes', Authorization='Bearer private',
                         **{'X-Forwarded-For': '203.0.113.4'}) == 200
    assert client.requests == [dict(method='POST', path='/demo-request', query={}, headers={},
                                    form={'_request_id': 'a'*32, 'choice': 'morning'})]


@pytest.mark.parametrize('change,code', [
    ({'Origin': 'https://other.example'}, 403), ({'Origin': 'null'}, 403),
    ({'Host': 'other.example'}, 403), ({'Content-Type': 'application/json'}, 415),
    ({'Content-Encoding': 'gzip'}, 415), ({'Expect': '100-continue'}, 417),
    ({'path': '/demo-request?choice=morning'}, 400), ({'path': '/demo-request%FF'}, 400),
    ({'body': b'x'*4097}, 413), ({'body': b'choice=morning'}, 400),
    ({'body': FORM_BODY+b'&choice=afternoon'}, 400), ({'body': FORM_BODY+b'&x=%FF'}, 400),
    ({'body': FORM_BODY+b'&x=%GG'}, 400),
])
def test_post_refusals_never_reach_runtime(change, code):
    client = FakeClient()
    with running(client, form_origin=FORM_ORIGIN) as base:
        assert post_form(base, **change) == code
    assert client.requests == []


@pytest.mark.parametrize('origin,extra,code', [
    ('https://forms.example', 'Content-Length: 1\r\n', 400),
    ('https://forms.example', 'Transfer-Encoding: chunked\r\n', 400),
    ('https://forms.example', 'Origin: https://forms.example\r\n', 403),
    (None, '', 403),
])
def test_post_ambiguous_framing_or_missing_origin_refused(origin, extra, code):
    client = FakeClient()
    with running(client, form_origin=FORM_ORIGIN) as base:
        with socket.create_connection(('127.0.0.1', int(base.rsplit(':', 1)[1])), timeout=2) as peer:
            origin_header = f'Origin: {origin}\r\n' if origin is not None else ''
            peer.sendall(('POST /demo-request HTTP/1.1\r\nHost: forms.example\r\n'
                          f'{origin_header}Content-Type: application/x-www-form-urlencoded\r\n'
                          f'Content-Length: 1\r\n{extra}\r\nx').encode())
            with peer.makefile('rb') as response:
                received = response.read()
            assert received.startswith(f'HTTP/1.1 {code} '.encode())
            assert b'Connection: close\r\n' in received
    assert client.requests == []


def test_post_source_limit_ignores_proxy_claim_and_get_is_independent(monkeypatch):
    from three_mm_public_web import server
    monkeypatch.setattr(server, 'FORM_PER_SOURCE', 2)
    client = FakeClient()
    with running(client, form_origin=FORM_ORIGIN) as base:
        for index, status in enumerate([200, 200, 429]):
            assert post_form(base, **{'X-Forwarded-For': f'203.0.113.{index}'}) == status
        with urlopen(base + '/demo-request', timeout=5) as response:
            assert response.status == 200
    assert [item['method'] for item in client.requests] == ['POST', 'POST', 'GET']


def test_post_partial_body_hits_absolute_deadline_without_dispatch(monkeypatch):
    from three_mm_public_web import server
    monkeypatch.setattr(server, 'FORM_BODY_SECONDS', 0.15)
    client = FakeClient()
    with running(client, form_origin=FORM_ORIGIN) as base:
        connection = HTTPConnection('127.0.0.1', int(base.rsplit(':', 1)[1]), timeout=2)
        try:
            connection.request('POST', '/demo-request', b'x', headers={'Host': 'forms.example',
                'Origin': FORM_ORIGIN, 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': '100'})
            with connection.getresponse() as response:
                assert response.status == 408
        finally:
            connection.close()
    assert client.requests == []
