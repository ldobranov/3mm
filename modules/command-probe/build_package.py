"""Build the independent output-button application using the public SDK only."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "0.1.0"
MODULE_ID = "org.3mm.command-probe"


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def descriptors():
    text = lambda en, bg: {"en": en, "translations": {"bg": bg}}
    request_id = {"type": "string", "pattern": "^[0-9a-f]{32}$"}
    nullable = {"type": ["string", "null"]}
    observation = obj({"access": {"type": "string", "enum": ["granted", "required"]},
        "readiness": {"type": "string", "enum": ["ready", "unavailable", "unknown"]},
        "target_device_id": nullable, "provider_id": nullable})
    outcome = obj({"request_id": request_id, "status": {"type": "string", "enum": [
        "queued", "delivered", "succeeded", "failed", "expired", "unknown", "invalidated", "not_found", "not_submitted"]},
        "command_id": nullable, "target_device_id": nullable, "expires_at": nullable,
        "confirmed_value": {"type": ["boolean", "null"]}})
    def operation(name, kind, schema, output):
        return {"operation_id": name, "kind": kind, "audiences": ["operator"],
            "required_permission": "control_output", "idempotency": "required" if kind == "command" else "forbidden",
            "input_schema": schema, "output_schema": output}
    manifest = {"manifest_version": 2, "module_id": MODULE_ID, "name": "Output button", "version": VERSION,
        "description": "One explicitly approved output through the public application SDK.",
        "runtimes": ["core", "ui"], "entrypoints": {"core": "application-extension.json", "ui": "compiled-ui.json"},
        "compatibility": {"protocol": "1.0", "core": ">=0.3.0", "agent": ">=0.1.0", "architectures": ["any"]},
        "capabilities": {"provides": [], "consumes": ["gpio.digital.control"]},
        "permissions": ["data.read", "data.write", "process.spawn", "capabilities.invoke"],
        "dependencies": {}, "conflicts": [],
        "configuration_schema": obj({"OUTPUT_DEVICE_ID": {"type": "string", "pattern": "^dev_[0-9a-f]{32}$"}}),
        "configuration_defaults": {}, "registrations": [],
        "health_check": {"type": "json_file", "path": "application-extension.json"}}
    definition = {"application_extension_version": 1, "module_id": MODULE_ID, "version": VERSION,
        "service": {"artifact": f"service/command_probe-{VERSION}-py3-none-any.whl", "artifact_sha256": "0" * 64,
            "entrypoint": "command_probe.service:create_service", "health_operation_id": "health", "sdk_version": "1.3"},
        "permissions": [{"permission_id": "control_output", "label": text("Control selected output", "Управление на избрания изход"),
            "description": text("Switch only the reviewed output and read its command outcomes.", "Включване и изключване само на одобрения изход и проверка на резултатите.")}],
        "operations": [{"operation_id": "health", "kind": "query", "audiences": ["internal"], "idempotency": "forbidden",
            "output_schema": obj({"status": {"type": "string", "enum": ["ready"]}})},
            operation("observe", "query", obj({}), observation),
            operation("set_output", "command", obj({"value": {"type": "boolean"}}), outcome),
            operation("lookup", "query", obj({"request_id": request_id}), outcome)],
        "command_bindings": [{"binding_id": "output", "target_device_config_key": "OUTPUT_DEVICE_ID",
            "capability_id": "gpio.digital.control", "contract_version": "1.0", "action": "set_output", "max_ttl_seconds": 10,
            "arguments_schema": obj({"channel": {"type": "string", "maxLength": 32, "enum": ["gpio.output.1"]},
                "value": {"type": "boolean"}})}],
        "routes": [{"route_id": "output_button", "entrypoint_id": "button", "audience": "operator",
            "required_permissions": ["control_output"], "order": 30}],
        "event_subscriptions": [], "connectors": [], "jobs": [],
        "storage": {"schema_revision": "0001", "migration_entrypoint": "command_probe.migrations:get_migrations",
            "classifications": ["private"], "contains_personal_data": False}}
    ui = {"compiled_ui_version": 1, "module_id": MODULE_ID, "version": VERSION,
        "entrypoints": [{"entrypoint_id": "button", "kind": "route", "source": "source/frontend/Button.vue",
            "route": "/output-button", "label": text("Output button", "Управление на изход")} ]}
    return manifest, definition, ui


def write(archive, name, data):
    info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def build_package():
    files = {"command_probe/" + p.name: p.read_bytes().replace(b"\r\n", b"\n")
        for p in sorted((ROOT / "service/command_probe").glob("*.py"))}
    # Reuse the existing neutral SDK consumer rather than creating a second path.
    files["command_probe/probe.py"] = (ROOT.parents[1] / "examples/command_probe/__init__.py").read_bytes().replace(b"\r\n", b"\n")
    dist = f"command_probe-{VERSION}.dist-info"
    files[dist + "/METADATA"] = f"Metadata-Version: 2.1\nName: command-probe\nVersion: {VERSION}\n".encode()
    files[dist + "/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, "sha256=" + digest, len(data)])
    writer.writerow([dist + "/RECORD", "", ""])
    files[dist + "/RECORD"] = record.getvalue().encode()
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in sorted(files.items()):
            write(archive, name, data)
    manifest, definition, ui = descriptors()
    definition["service"]["artifact_sha256"] = hashlib.sha256(wheel.getvalue()).hexdigest()
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        for name, value in (("manifest.json", manifest), ("application-extension.json", definition), ("compiled-ui.json", ui)):
            write(archive, name, json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        write(archive, definition["service"]["artifact"], wheel.getvalue())
        for path in sorted((ROOT / "source/frontend").glob("*")):
            write(archive, "source/frontend/" + path.name, path.read_bytes().replace(b"\r\n", b"\n"))
    return package.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = build_package()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"SHA256 {hashlib.sha256(payload).hexdigest()}")
