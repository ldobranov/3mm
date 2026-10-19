#!/usr/bin/env python3
"""Build the deterministic neutral application-extension acceptance package."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
REFERENCE_VERSION = "1.0.1"
SCOPED_VERSION = "1.1.0"


def scoped_declarations(manifest, definition, device_id, command_spec):
    """Use an explicit public contract, never guess a provider's action/schema."""
    from three_mm_protocol.application_extension import ApplicationCommandBindingV1
    from three_mm_protocol.capability_contracts import validate_schema, validate_value

    if type(command_spec) is not dict or set(command_spec) != {"capability_id", "contract_version", "action", "arguments_schema", "arguments"}:
        raise ValueError("A scoped probe requires one exact versioned command specification")
    binding = ApplicationCommandBindingV1.model_validate({
        **{key: value for key, value in command_spec.items() if key != "arguments"},
        "binding_id": "acceptance", "target_device_config_key": "TARGET_DEVICE_ID",
        "max_ttl_seconds": 5,
    }).model_dump(mode="json", exclude_none=True)
    if binding.get("contract_version") is None:
        raise ValueError("The acceptance command requires a versioned contract")
    validate_schema(binding["arguments_schema"])
    validate_value(command_spec["arguments"], binding["arguments_schema"])
    manifest.update(
        name="Application Reference — scoped capability acceptance",
        capabilities={"provides": [], "consumes": [binding["capability_id"]]},
        permissions=["data.read", "data.write", "capabilities.invoke", "process.spawn"],
        configuration_schema={"type": "object", "additionalProperties": False,
            "properties": {"TARGET_DEVICE_ID": {"type": "string"}}},
        configuration_defaults={"TARGET_DEVICE_ID": device_id},
    )
    definition["service"]["entrypoint"] = "reference_application.scoped:create_service"
    definition["service"]["sdk_version"] = "1.3"
    definition.update(
        permissions=[{"permission_id": "probe_use", "label": {"en": "Use mock capability probe"},
                      "description": {"en": "Submit and inspect explicitly reviewed mock capability requests."}}],
        operations=[definition["operations"][0], {
            "operation_id": "probe", "kind": "command", "idempotency": "required",
            "audiences": ["kiosk", "operator", "administrator"],
            "required_permission": "probe_use",
            "input_schema": {"type": "object", "additionalProperties": False,
                "properties": {"arguments": binding["arguments_schema"]}, "required": ["arguments"]},
            "output_schema": {"type": "object", "additionalProperties": False,
                "properties": {"request_id": {"type": "string"}, "status": {"type": "string"}},
                "required": ["request_id", "status"]},
        }, {
            "operation_id": "lookup", "kind": "query", "idempotency": "forbidden",
            "audiences": ["operator", "administrator"], "required_permission": "probe_use",
            "input_schema": {"type": "object", "additionalProperties": False,
                "properties": {"request_id": {"type": "string", "maxLength": 160}},
                "required": ["request_id"]},
            "output_schema": {"type": "object", "additionalProperties": False,
                "properties": {"status": {"type": "string"}, "command": {"type": "object"}},
                "required": ["status"]},
        }],
        routes=[{"route_id": "registration", "entrypoint_id": "registration", "audience": "kiosk",
                 "layout": "kiosk", "order": 10},
                {"route_id": "operations", "entrypoint_id": "operations", "audience": "operator",
                 "required_permissions": ["probe_use"], "order": 20}],
        command_bindings=[binding], event_subscriptions=[], connectors=[], jobs=[],
        storage={"schema_revision": "0001", "migration_entrypoint": "reference_application.scoped:get_migrations",
                 "classifications": ["private"], "contains_personal_data": False},
    )


def wheel_name(version: str) -> str:
    return f"reference_application-{version}-py3-none-any.whl"


def _write(archive: zipfile.ZipFile, name: str, payload: bytes, *, canonical: bool = False) -> None:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    if canonical:
        info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload)


def build_wheel(
    version: str = REFERENCE_VERSION,
    *,
    broken_health: bool = False,
    scoped: bool = False,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted((ROOT / "service" / "reference_application").glob("*.py")):
            if path.name == "scoped.py" and not scoped:
                continue
            payload = path.read_bytes()
            if scoped:
                payload = payload.replace(b"\r\n", b"\n")
            if broken_health and path.name in {"service.py", "scoped.py"}:
                payload = payload.replace(
                    b'return {"status": "ready"}',
                    b'return {"status": "broken"}',
                )
            _write(archive, f"reference_application/{path.name}", payload, canonical=scoped)
        _write(
            archive,
            f"reference_application-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: reference-application\nVersion: {version}\n".encode(), canonical=scoped,
        )
        _write(
            archive,
            f"reference_application-{version}.dist-info/WHEEL",
            b"Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n", canonical=scoped,
        )
        _write(archive, f"reference_application-{version}.dist-info/RECORD", b"", canonical=scoped)
    return output.getvalue()


def build_package(
    reader_device_id: str,
    destination: str,
    *,
    version: str | None = None,
    broken_health: bool = False,
    scoped_command: dict | None = None,
) -> bytes:
    if version is None:
        version = SCOPED_VERSION if scoped_command is not None else REFERENCE_VERSION
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest["configuration_defaults"]["READER_DEVICE_ID"] = reader_device_id
    manifest["configuration_defaults"]["BUSINESS_API_URL"] = destination
    definition = json.loads(
        (ROOT / "application-extension.json").read_text(encoding="utf-8")
    )
    definition["version"] = version
    if scoped_command is not None:
        scoped_declarations(manifest, definition, reader_device_id, scoped_command)
    definition["service"]["artifact"] = f"service/{wheel_name(version)}"
    wheel = build_wheel(version, broken_health=broken_health, scoped=scoped_command is not None)
    definition["service"]["artifact_sha256"] = hashlib.sha256(wheel).hexdigest()
    compiled_ui = json.loads((ROOT / "compiled-ui.json").read_text(encoding="utf-8"))
    compiled_ui["version"] = version
    if scoped_command is not None:
        for entry in compiled_ui["entrypoints"]:
            entry["source"] = ("source/frontend/ScopedRegistration.vue" if entry["entrypoint_id"] == "registration"
                               else "source/frontend/ScopedOperations.vue")
            entry["label"] = {"en": "Mock capability acceptance"}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        _write(archive, "manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(), canonical=scoped_command is not None)
        _write(archive, "application-extension.json", json.dumps(definition, sort_keys=True, separators=(",", ":")).encode(), canonical=scoped_command is not None)
        _write(archive, "compiled-ui.json", json.dumps(compiled_ui, sort_keys=True, separators=(",", ":")).encode(), canonical=scoped_command is not None)
        _write(archive, f"service/{wheel_name(version)}", wheel, canonical=scoped_command is not None)
        for path in sorted((ROOT / "source" / "frontend").glob("*")):
            if path.name in {"Capability.vue", "ScopedRegistration.vue", "ScopedOperations.vue"} and scoped_command is None:
                continue
            if path.is_file():
                payload = path.read_bytes()
                if scoped_command is not None:
                    payload = payload.replace(b"\r\n", b"\n")
                _write(archive, f"source/frontend/{path.name}", payload, canonical=scoped_command is not None)
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reader-device-id", required=True)
    parser.add_argument("--destination", default="http://127.0.0.1:9911")
    parser.add_argument("--version")
    parser.add_argument("--broken-health", action="store_true")
    parser.add_argument("--scoped-command", type=Path,
                        help="Exact capability/action/schema/arguments JSON; mock acceptance only")
    arguments = parser.parse_args()
    scoped_command = (json.loads(arguments.scoped_command.read_text(encoding="utf-8"))
                      if arguments.scoped_command else None)
    if arguments.scoped_command and type(scoped_command) is not dict:
        raise ValueError("The scoped command file must contain a JSON object")
    payload = build_package(
        arguments.reader_device_id,
        arguments.destination,
        version=arguments.version,
        broken_health=arguments.broken_health,
        scoped_command=scoped_command,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(payload)
    print(hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    main()
