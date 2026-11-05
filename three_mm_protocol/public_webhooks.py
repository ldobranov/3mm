"""CAP12 signed POST verification; no transport, admission or replay state."""

from dataclasses import dataclass
import hashlib
import hmac
import re


MAX_WEBHOOK_BYTES = 64 * 1024
MAX_WEBHOOK_AGE_SECONDS = 300
MAX_WEBHOOK_CLOCK_SKEW_SECONDS = 30
_AUDIENCE = re.compile(r"[0-9a-f]{32}")
_EVENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_TIMESTAMP = re.compile(r"[1-9][0-9]{0,10}")
_SIGNATURE = re.compile(r"v1=[0-9a-f]{64}")


class WebhookRejected(ValueError):
    """Untrusted input; never include received fields, body or key in the error."""


@dataclass(frozen=True, slots=True)
class VerifiedWebhook:
    audience: str
    event_id: str
    signed_at: int
    body_sha256: str


def valid_webhook_event_id(event_id: object) -> bool:
    return isinstance(event_id, str) and _EVENT_ID.fullmatch(event_id) is not None


def webhook_delivery_input_schema() -> dict:
    properties = {
        "receipt_id": {"type": "string", "pattern": r"^[0-9a-f]{32}$"},
        "event_id": {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"},
        "body_base64": {"type": "string", "minLength": 4, "maxLength": ((MAX_WEBHOOK_BYTES + 2) // 3) * 4},
    }
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(properties)}


def webhook_delivery_result_schema() -> dict:
    return {"type": "object", "additionalProperties": False,
            "properties": {"status": {"type": "string", "enum": ["accepted", "rejected"]}},
            "required": ["status"]}


def validate_webhook_endpoint(audience: str, secret: bytes) -> None:
    if (not isinstance(audience, str) or _AUDIENCE.fullmatch(audience) is None
            or type(secret) is not bytes or len(secret) != 32):
        raise ValueError("Invalid webhook verifier configuration")


def verify_webhook(
    body: bytes,
    *,
    audience: str,
    event_id: str,
    timestamp: str,
    signature: str,
    secret: bytes,
    now: int,
) -> VerifiedWebhook:
    """Verify exact POST bytes against trusted endpoint configuration.

    Audience, secret and current time are supplied by the caller, not the
    sender. A valid signature is not a new delivery or permission to dispatch:
    the caller must still do durable deduplication and check current authority.
    """
    validate_webhook_endpoint(audience, secret)
    if type(now) is not int or not 0 < now < 10**11:
        raise ValueError("Invalid webhook verifier configuration")
    if (type(body) is not bytes or not 1 <= len(body) <= MAX_WEBHOOK_BYTES
            or not valid_webhook_event_id(event_id)
            or not isinstance(timestamp, str) or _TIMESTAMP.fullmatch(timestamp) is None
            or not isinstance(signature, str) or _SIGNATURE.fullmatch(signature) is None):
        raise WebhookRejected("Webhook verification failed")
    signed_at = int(timestamp)
    if not now - MAX_WEBHOOK_AGE_SECONDS <= signed_at <= now + MAX_WEBHOOK_CLOCK_SKEW_SECONDS:
        raise WebhookRejected("Webhook verification failed")

    prefix = f"3mm.webhook.v1\nPOST\n{audience}\n{timestamp}\n{event_id}\n".encode("ascii")
    mac = hmac.new(secret, prefix, "sha256")
    mac.update(body)
    if not hmac.compare_digest(mac.hexdigest(), signature[3:]):
        raise WebhookRejected("Webhook verification failed")
    return VerifiedWebhook(audience, event_id, signed_at, hashlib.sha256(body).hexdigest())
