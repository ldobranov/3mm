"""Build a source-only, worker-only reference with the public project wheel builder."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

from tools.application_project import build_service_wheel, write_member

ROOT = Path(__file__).resolve().parent


def obj(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def reference_parts():
    package, version, task = "report_example", "1.0.0", "render_table"
    module = "org.example.table-report"
    artifact = f"service/{package}-{version}-py3-none-any.whl"
    sources = {}
    for prefix, folder, files in (
        (package, ROOT / "service" / package, ("__init__.py", "migrations.py", "service.py")),
        (package + "/data_tools", ROOT.parents[1] / "application_data_tools", ("__init__.py", "tabular.py", "report.py")),
    ):
        for name in files:
            sources[f"{prefix}/{name}"] = (folder / name).read_bytes().replace(b"\r\n", b"\n")
    manifest = {
        "manifest_version": 2, "module_id": module, "name": "Reviewed table report", "version": version,
        "description": "Source-only application report example.", "runtimes": ["core"],
        "entrypoints": {"core": "application-extension.json"},
        "compatibility": {"protocol": "1.0", "core": ">=0.3.0", "agent": ">=0.1.0", "architectures": ["any"]},
        "capabilities": {"provides": [], "consumes": []}, "permissions": ["data.read", "data.write", "process.spawn"],
        "dependencies": {}, "conflicts": [], "configuration_schema": obj({}), "configuration_defaults": {},
        "registrations": [], "health_check": {"type": "json_file", "path": "application-extension.json"},
    }
    descriptor = {
        "application_extension_version": 1, "module_id": module, "version": version,
        "service": {"artifact": artifact,
                    "entrypoint": "report_example.service:create_service", "health_operation_id": "health", "sdk_version": "1.3"},
        "permissions": [],
        "operations": [
            {"operation_id": "health", "kind": "query", "audiences": ["internal"], "idempotency": "forbidden",
             "output_schema": obj({"status": {"type": "string", "enum": ["ready"]}})},
            {"operation_id": task, "kind": "task", "audiences": ["internal"], "idempotency": "required", "timeout_seconds": 5,
             "input_schema": obj({"report_ref": {"type": "string", "maxLength": 32}}),
             "output_schema": obj({"rows": {"type": "integer", "minimum": 0, "maximum": 64},
                                   "size_bytes": {"type": "integer", "minimum": 0, "maximum": 32768},
                                   "sha256": {"type": "string", "maxLength": 64}})},
        ],
        "tasks": [{"task_id": task, "handler_operation_id": task, "profile": "bounded_task_v1",
                   "max_runtime_seconds": 5, "max_delay_seconds": 180, "max_pending": 4}],
        "storage": {"schema_revision": "0001", "migration_entrypoint": "report_example.migrations:get_migrations",
                    "classifications": ["private"], "contains_personal_data": False},
    }
    return sources, manifest, descriptor


def pack(sources, manifest, descriptor):
    artifact = descriptor["service"]["artifact"]
    package = artifact.split("/")[-1].split("-")[0]
    wheel = build_service_wheel(package, manifest["version"], sources)
    descriptor = {**descriptor, "service": {**descriptor["service"], "artifact_sha256": hashlib.sha256(wheel).hexdigest()}}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in (("manifest.json", manifest), ("application-extension.json", descriptor)):
            write_member(archive, name, json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        write_member(archive, artifact, wheel)
    return stream.getvalue()


def build_package():
    return pack(*reference_parts())
