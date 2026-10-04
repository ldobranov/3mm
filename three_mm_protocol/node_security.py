"""Generic Node message limits; independent of hardware and deployment role."""

import json
import math

NODE_MESSAGE_BYTES = 64 * 1024
NODE_JSON_DEPTH = 16
NODE_JSON_ITEMS = 8192
# Existing module v2 ZIP limit, plus base64 expansion and normal metadata.
MODULE_ARCHIVE_BYTES = 10 * 1024 * 1024
MODULE_COMMAND_BYTES = 4 * ((MODULE_ARCHIVE_BYTES + 2) // 3) + NODE_MESSAGE_BYTES
CORE_DEVICE_AUDIT_EVENTS = frozenset(
    {"runtime.features.updated", "capability.provider.updated", "device.lifecycle.updated", "device.authority.released", "device.authority.enrollment_prepared", "device.authority.bound"}
)


def validate_node_json(value, *, max_bytes=NODE_MESSAGE_BYTES):
    remaining = NODE_JSON_ITEMS

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > NODE_JSON_DEPTH:
            raise ValueError("Node JSON structure limit exceeded")
        if item is None or type(item) in (bool, int):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("Node JSON numbers must be finite")
        elif type(item) is str:
            if len(item) > max_bytes:
                raise ValueError("Node JSON string limit exceeded")
        elif type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("Node JSON keys must be strings")
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif type(item) in (list, tuple):
            for child in item:
                visit(child, depth + 1)
        else:
            raise ValueError("Node payload must contain JSON values only")

    visit(value, 0)
    try:
        serialized = json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, UnicodeError, OverflowError) as exc:
        raise ValueError("Node JSON encoding is invalid") from exc
    if len(serialized) > max_bytes:
        raise ValueError("Node JSON byte limit exceeded")


def bounded_node_message(model):
    validate_node_json(model.model_dump(mode="json"))
    return model


def validate_command_payload(command_type, payload):
    if command_type == "module.install" and "package_base64" in payload:
        archive = payload.get("package_base64")
        if (
            type(archive) is not str
            or len(archive) > MODULE_COMMAND_BYTES - NODE_MESSAGE_BYTES
        ):
            raise ValueError("Module package encoding is missing or too large")
        # The larger exception is only the existing package field, not arbitrary
        # unbounded module metadata. ZIP validation remains the runtime's job.
        validate_node_json({k: v for k, v in payload.items() if k != "package_base64"})
        validate_node_json(payload, max_bytes=MODULE_COMMAND_BYTES)
    else:
        validate_node_json(payload)
