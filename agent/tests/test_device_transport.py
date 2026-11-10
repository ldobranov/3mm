"""C10 HTTP boundary tests; never contact a live Core."""

import hashlib
from types import SimpleNamespace

import pytest

from agent.core_client import DeviceCredential
from agent.device_transport import HttpDeviceTransport, HttpRejected, HttpTransportError
from three_mm_protocol.fleet_pairing import NodeEnrollmentRequest


def enrollment():
    credential = DeviceCredential(
        device_id="dev_" + "a" * 32,
        credential_id="cred_" + "b" * 32,
        credential_secret="s" * 43,
    )
    request = NodeEnrollmentRequest(
        device_id=credential.device_id,
        credential_id=credential.credential_id,
        display_name="Reference node",
        request_token="c" * 64,
        credential_secret_hash=hashlib.sha256(
            credential.credential_secret.encode()
        ).hexdigest(),
    )
    return HttpDeviceTransport("http://core.test", credential), request


@pytest.mark.parametrize("field", ["device_id", "credential_id"])
def test_enrollment_rejects_response_for_another_identity(monkeypatch, field):
    transport, request = enrollment()
    payload = {
        "device_id": request.device_id,
        "credential_id": request.credential_id,
        "status": "approved",
    }
    payload[field] = "unrelated"

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return payload

    monkeypatch.setattr(
        "agent.device_transport.requests.post", lambda *a, **k: Response()
    )
    with pytest.raises(HttpRejected, match="identity mismatch"):
        transport.enroll(request)


def test_wrong_enrollment_principal_is_rejected_before_delivery(monkeypatch):
    transport, request = enrollment()
    monkeypatch.setattr(
        "agent.device_transport.requests.post",
        lambda *a, **k: pytest.fail("Mismatched enrollment must not be delivered"),
    )
    request = request.model_copy(update={"device_id": "dev_" + "d" * 32})
    with pytest.raises(ValueError, match="identity mismatch"):
        transport.enroll(request)


@pytest.mark.parametrize("signed", [False, True])
def test_execution_permit_uses_remaining_budget_and_verifies_signed_response(monkeypatch, signed):
    transport, _ = enrollment()
    clock = [0.0]
    monkeypatch.setattr("agent.device_transport.time", SimpleNamespace(monotonic=lambda: clock[0]))
    command_id = "cmd_" + "c" * 32
    permit = {"command_id": command_id, "authorized": True}
    calls = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return permit

    def verify(payload, request, *, bootstrap=False):
        calls.append((request.operation, bootstrap))
        return payload

    def post(url, *, timeout, **kwargs):
        calls.append((url.rsplit("/", 1)[-1], timeout))
        if url.endswith("authority-proof"):
            clock[0] += 3
        return Response()

    if signed:
        transport.authority_store = SimpleNamespace(check_current=lambda: True, verify=verify)
    monkeypatch.setattr("agent.device_transport.requests.post", post)
    assert transport.authorize_execution(command_id, timeout_seconds=8) == permit
    if signed:
        assert calls == [("authority-proof", 8), ("identity", True),
                         ("authority-exchange", 5), ("execution_permit", False)]
    else:
        assert calls == [("authorize-execution", 8)]


def test_expired_execution_budget_does_not_dispatch_after_proving_authority(monkeypatch):
    transport, _ = enrollment()
    clock = [0.0]
    monkeypatch.setattr("agent.device_transport.time", SimpleNamespace(monotonic=lambda: clock[0]))
    transport.authority_store = SimpleNamespace(check_current=lambda: True, verify=lambda *a, **k: None)

    def post(url, **kwargs):
        assert url.endswith("authority-proof")
        clock[0] += 3
        return SimpleNamespace(status_code=200, json=dict)

    monkeypatch.setattr("agent.device_transport.requests.post", post)
    with pytest.raises(HttpTransportError, match="deadline expired"):
        transport.authorize_execution("cmd_" + "c" * 32, timeout_seconds=2)


@pytest.mark.parametrize('field', ['device_id','provider_type','provider_id'])
def test_provider_reads_and_acknowledgements_reject_foreign_identity(monkeypatch, field):
    from datetime import UTC, datetime
    from agent.hardware.identifier import MockIdentifierAdapter
    from three_mm_protocol.device_capabilities import CapabilityProviderSnapshotV2
    from pathlib import Path
    transport,_=enrollment()
    declaration=MockIdentifierAdapter(Path('/unused')).provider_declaration()
    value=CapabilityProviderSnapshotV2(device_id=transport.device_id,provider_type=declaration.provider_type,
        provider_id=declaration.provider_id,provider_version=declaration.provider_version,revision=1,enabled=True,
        capabilities=declaration.capabilities,configured_capability_ids=(),reported_at=datetime.now(UTC)).model_dump(mode='json')
    value[field] = 'dev_'+'f'*32 if field=='device_id' else 'foreign'
    class Response:
        status_code=200
        def raise_for_status(self):pass
        def json(self):return value
    monkeypatch.setattr('agent.device_transport.requests.get',lambda *a,**k:Response())
    monkeypatch.setattr('agent.device_transport.requests.put',lambda *a,**k:Response())
    with pytest.raises(HttpRejected):transport.provider(*declaration.identity)
    with pytest.raises(HttpRejected):transport.report_provider(declaration.report(transport.device_id,0))
