import hashlib
import hmac

import pytest

from three_mm_protocol.public_webhooks import (
    MAX_WEBHOOK_BYTES, VerifiedWebhook, WebhookRejected, verify_webhook,
)


AUDIENCE = "0123456789abcdef0123456789abcdef"
SECRET = bytes(range(32))
SIGNED_AT = 1793894400
BODY = b'{"x":1}\n'
# Independent HMAC-SHA256 and SHA-256 vector, computed with .NET.
SIGNATURE = "v1=8de92807483793588b999e0fa5ffa53c07531578e9bd36e581d0cacbb3053489"
BODY_DIGEST = "bb157861a164e35cdde9d726b0af9ce2765a8f530c35d9e45732b94ee65e9557"


def verify(**overrides):
    return verify_webhook(**({
        "body": BODY, "audience": AUDIENCE, "event_id": "event-42",
        "timestamp": str(SIGNED_AT), "signature": SIGNATURE, "secret": SECRET,
        "now": SIGNED_AT,
    } | overrides))


def signature_for(body):
    prefix = b"3mm.webhook.v1\nPOST\n0123456789abcdef0123456789abcdef\n1793894400\nevent-42\n"
    return "v1=" + hmac.digest(SECRET, prefix + body, "sha256").hex()


def test_cross_implementation_vector_and_exact_body_identity():
    proof = verify()
    assert proof == VerifiedWebhook(AUDIENCE, "event-42", SIGNED_AT, BODY_DIGEST)
    assert verify() == proof  # Verification alone does not claim a delivery.
    assert not hasattr(proof, "body")


@pytest.mark.parametrize("overrides", [
    {"body": b'{"x":1}'},  # Stripping a trailing newline changes the signature.
    {"body": b'{"x": 1}\n'},
    {"audience": "f" * 32},
    {"event_id": "event-43"},
    {"timestamp": str(SIGNED_AT + 1)},
    {"secret": bytes(reversed(range(32)))},
    {"signature": "v1=" + "0" * 64},
])
def test_valid_mac_cannot_be_reused_for_changed_input(overrides):
    with pytest.raises(WebhookRejected, match="^Webhook verification failed$"):
        verify(**overrides)


@pytest.mark.parametrize("overrides", [
    {"timestamp": "0" + str(SIGNED_AT)}, {"timestamp": "+" + str(SIGNED_AT)},
    {"timestamp": str(SIGNED_AT) + "\n"}, {"timestamp": "١٧٩٣٨٩٤٤٠٠"},
    {"timestamp": SIGNED_AT}, {"timestamp": "9" * 12},
    {"event_id": "event-42\nevent-43"}, {"event_id": "x" * 129},
    {"signature": SIGNATURE.upper()}, {"signature": "v2=" + SIGNATURE[3:]},
    {"signature": SIGNATURE + "," + SIGNATURE},
    {"body": bytearray(BODY)}, {"body": b""},
])
def test_noncanonical_or_wrong_type_input_is_refused(overrides):
    with pytest.raises(WebhookRejected, match="^Webhook verification failed$"):
        verify(**overrides)


def test_signed_oversize_is_refused_and_limit_is_inclusive():
    body = b"\x00\xff" * (MAX_WEBHOOK_BYTES // 2)
    assert verify(body=body, signature=signature_for(body)).body_sha256 == hashlib.sha256(body).hexdigest()
    oversized = body + b"\x00"
    with pytest.raises(WebhookRejected):
        verify(body=oversized, signature=signature_for(oversized))


@pytest.mark.parametrize("clock_delta,accepted", [(-31, False), (-30, True), (300, True), (301, False)])
def test_past_and_future_time_windows(clock_delta, accepted):
    if accepted:
        assert verify(now=SIGNED_AT + clock_delta).signed_at == SIGNED_AT
    else:
        with pytest.raises(WebhookRejected):
            verify(now=SIGNED_AT + clock_delta)


@pytest.mark.parametrize("overrides", [{"audience": "unconfigured"}, {"secret": b"short"}, {"now": True}])
def test_missing_or_malformed_trusted_configuration_fails_closed(overrides):
    with pytest.raises(ValueError, match="^Invalid webhook verifier configuration$") as error:
        verify(**overrides)
    assert not isinstance(error.value, WebhookRejected)
