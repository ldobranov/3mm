"""C10 HTTP boundary tests; never contact a live Core."""

import hashlib

import pytest

from agent.core_client import DeviceCredential
from agent.device_transport import HttpDeviceTransport, HttpRejected
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
