"""User-authorized operations; Core retains resource and execution authority."""
import hashlib
import re

from .probe import CommandProbe


def request_key(context, request_id):
    if (context.audience != "operator" or type(context.user_id) is not int or context.user_id < 1
            or not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id)):
        raise ValueError("A current operator and an original request ID are required")
    # Browser IDs are scoped to the authenticated actor, never a payload user ID.
    return hashlib.sha256(f"{context.user_id}:{request_id}".encode()).hexdigest()


def outcome(request_id, command=None, status="not_found"):
    command = command or {}
    state = command.get("status", status)
    result = command.get("result") or {}
    outputs = result.get("outputs", {}) if isinstance(result, dict) else {}
    value = outputs.get("gpio.output.1") if isinstance(outputs, dict) else None
    return {"request_id": request_id, "status": state,
        "command_id": command.get("command_id"), "target_device_id": command.get("target_device_id"),
        "expires_at": command.get("expires_at"),
        "confirmed_value": value if state == "succeeded" and type(value) is bool else None}


class Service:
    def __init__(self, application):
        self.application = application

    def handle(self, operation_id, payload, context):
        if operation_id == "health" and context.audience == "internal":
            return {"status": "ready"}
        if context.audience != "operator" or type(context.user_id) is not int or context.user_id < 1:
            raise ValueError("A current operator is required")
        if self.application.platform is None:
            raise RuntimeError("Public platform is unavailable")
        probe = CommandProbe(self.application.platform, "output")
        if operation_id == "observe" and payload == {}:
            value = probe.observe()
            candidates = value["candidates"]
            selected = candidates[0] if value["access"] == "granted" and len(candidates) == 1 else None
            return {"access": "granted" if selected else "required",
                "readiness": selected["readiness"] if selected and selected["selectable"] else "unavailable",
                "target_device_id": selected["device_id"] if selected else None,
                "provider_id": selected["provider_id"] if selected else None}
        if operation_id == "set_output" and set(payload) == {"value"} and type(payload["value"]) is bool:
            key = request_key(context, context.idempotency_key)
            result = probe.submit(request_id=key, arguments={"channel": "gpio.output.1", "value": payload["value"]}, ttl_seconds=10)
            return outcome(context.idempotency_key, result)
        if operation_id == "lookup" and set(payload) == {"request_id"}:
            key = request_key(context, payload["request_id"])
            result = probe.lookup(key)
            return outcome(payload["request_id"], result.get("command"))
        raise ValueError("Operation or payload is unsupported")


def create_service(application):
    return Service(application)
