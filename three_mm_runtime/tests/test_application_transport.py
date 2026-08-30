import time

import pytest

from three_mm_runtime.application_transport import (
    ApplicationTransportError,
    sign_message,
    verify_message,
)


def message():
    return {
        "version": 1,
        "request_id": "a" * 32,
        "timestamp": int(time.time()),
        "operation_id": "health",
        "payload": {},
        "context": {"audience": "internal", "correlation_id": "test"},
    }


def test_transport_signature_binds_the_complete_request():
    secret = b"s" * 32
    signed = sign_message(message(), secret)

    assert verify_message(signed, secret)["operation_id"] == "health"
    signed["operation_id"] = "erase_data"
    with pytest.raises(ApplicationTransportError, match="signature"):
        verify_message(signed, secret)


def test_transport_rejects_expired_and_mismatched_messages():
    secret = b"s" * 32
    value = message()
    value["timestamp"] = 10
    signed = sign_message(value, secret)

    with pytest.raises(ApplicationTransportError, match="expired"):
        verify_message(signed, secret, now=100)
    value = message()
    signed = sign_message(value, secret)
    with pytest.raises(ApplicationTransportError, match="does not match"):
        verify_message(signed, secret, expected_request_id="another")
