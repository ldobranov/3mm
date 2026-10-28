"""Build a deterministic, independent bounded-result task package."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "0.2.0"
MODULE_ID = "org.3mm.task-probe"


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def descriptors(*, with_command=False):
    manifest = {"manifest_version": 2, "module_id": MODULE_ID, "name": "Result task probe", "version": VERSION,
        "description": "One-shot scoped task acceptance with a bounded arithmetic result.", "runtimes": ["core"],
        "entrypoints": {"core": "application-extension.json"},
        "compatibility": {"protocol": "1.0", "core": ">=0.3.0", "agent": ">=0.1.0", "architectures": ["any"]},
        "capabilities": {"provides": [], "consumes": []}, "permissions": ["data.read", "data.write", "process.spawn"],
        "dependencies": {}, "conflicts": [], "configuration_schema": obj({}), "configuration_defaults": {},
        "registrations": [], "health_check": {"type": "json_file", "path": "application-extension.json"}}
    definition = {"application_extension_version": 1, "module_id": MODULE_ID, "version": VERSION,
        "service": {"artifact": f"service/task_probe-{VERSION}-py3-none-any.whl", "artifact_sha256": "0" * 64,
            "entrypoint": "task_probe.service:create_service", "health_operation_id": "health", "sdk_version": "1.3"},
        "permissions": [], "operations": [
            {"operation_id": "health", "kind": "query", "audiences": ["internal"], "idempotency": "forbidden",
                "output_schema": obj({"status": {"type": "string", "enum": ["ready"]}})},
            {"operation_id": "calculate", "kind": "task", "audiences": ["internal"], "idempotency": "required", "timeout_seconds": 2,
                "input_schema": obj({"upper": {"type": "integer", "minimum": 0, "maximum": 1000000},
                    "pause_ms": {"type": "integer", "minimum": 0, "maximum": 3000}}),
                "output_schema": obj({"total": {"type": "integer", "minimum": 0, "maximum": 1000000000000}})}],
        "tasks": [{"task_id": "calculate", "handler_operation_id": "calculate", "profile": "bounded_task_v1",
            "max_runtime_seconds": 2, "max_delay_seconds": 3600, "max_pending": 8}],
        "storage": {"schema_revision": "0001", "migration_entrypoint": "task_probe.migrations:get_migrations",
            "classifications": ["private"], "contains_personal_data": False}}
    if with_command:
        module_id = "org.3mm.task-command-probe"
        manifest.update(module_id=module_id, name="Task command probe",
            configuration_schema=obj({"OUTPUT_DEVICE_ID":{"type":"string","pattern":r"^dev_[0-9a-f]{32}$"}}))
        manifest["permissions"].append("capabilities.invoke")
        manifest["capabilities"]["consumes"]=["gpio.digital.control"]
        definition["module_id"]=module_id
        definition["operations"][1].update(operation_id="switch_output",timeout_seconds=5,
            input_schema=obj({"value":{"type":"boolean"}}),
            output_schema=obj({"command_id":{"type":"string","maxLength":64},
                "request_id":{"type":"string","maxLength":64},"value":{"type":"boolean"}}))
        definition["tasks"][0].update(task_id="switch_output",handler_operation_id="switch_output",max_runtime_seconds=5)
        definition["command_bindings"]=[{"binding_id":"output","target_device_config_key":"OUTPUT_DEVICE_ID",
            "capability_id":"gpio.digital.control","contract_version":"1.0","action":"set_output","max_ttl_seconds":5,
            "arguments_schema":obj({"channel":{"type":"string","enum":["gpio.output.1"],"maxLength":32},
                "value":{"type":"boolean"}})}]
    return manifest, definition


def write(archive, name, data):
    info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)); info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def build_package(*, with_command=False):
    files = {"task_probe/" + p.name: p.read_bytes().replace(b"\r\n", b"\n") for p in sorted((ROOT / "service/task_probe").glob("*.py"))}
    dist = f"task_probe-{VERSION}.dist-info"
    files[dist + "/METADATA"] = f"Metadata-Version: 2.1\nName: task-probe\nVersion: {VERSION}\n".encode()
    files[dist + "/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    record = io.StringIO(newline=""); writer = csv.writer(record, lineterminator="\n")
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, "sha256=" + digest, len(data)])
    writer.writerow([dist + "/RECORD", "", ""]); files[dist + "/RECORD"] = record.getvalue().encode()
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in sorted(files.items()): write(archive, name, data)
    manifest, definition = descriptors(with_command=with_command)
    definition["service"]["artifact_sha256"] = hashlib.sha256(wheel.getvalue()).hexdigest()
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        write(archive, "manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
        write(archive, "application-extension.json", json.dumps(definition, sort_keys=True, separators=(",", ":")).encode())
        write(archive, definition["service"]["artifact"], wheel.getvalue())
    return package.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--with-command",action="store_true")
    args = parser.parse_args(); blob = build_package(with_command=args.with_command)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(blob)
    print(hashlib.sha256(blob).hexdigest())
