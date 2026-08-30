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


def wheel_name(version: str) -> str:
    return f"reference_application-{version}-py3-none-any.whl"


def _write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload)


def build_wheel(
    version: str = REFERENCE_VERSION,
    *,
    broken_health: bool = False,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted((ROOT / "service" / "reference_application").glob("*.py")):
            payload = path.read_bytes()
            if broken_health and path.name == "service.py":
                payload = payload.replace(
                    b'return {"status": "ready"}',
                    b'return {"status": "broken"}',
                )
            _write(archive, f"reference_application/{path.name}", payload)
        _write(
            archive,
            f"reference_application-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: reference-application\nVersion: {version}\n".encode(),
        )
        _write(
            archive,
            f"reference_application-{version}.dist-info/WHEEL",
            b"Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        _write(archive, f"reference_application-{version}.dist-info/RECORD", b"")
    return output.getvalue()


def build_package(
    reader_device_id: str,
    destination: str,
    *,
    version: str = REFERENCE_VERSION,
    broken_health: bool = False,
) -> bytes:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest["configuration_defaults"]["READER_DEVICE_ID"] = reader_device_id
    manifest["configuration_defaults"]["BUSINESS_API_URL"] = destination
    definition = json.loads(
        (ROOT / "application-extension.json").read_text(encoding="utf-8")
    )
    definition["version"] = version
    definition["service"]["artifact"] = f"service/{wheel_name(version)}"
    wheel = build_wheel(version, broken_health=broken_health)
    definition["service"]["artifact_sha256"] = hashlib.sha256(wheel).hexdigest()
    compiled_ui = json.loads((ROOT / "compiled-ui.json").read_text(encoding="utf-8"))
    compiled_ui["version"] = version
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        _write(archive, "manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
        _write(archive, "application-extension.json", json.dumps(definition, sort_keys=True, separators=(",", ":")).encode())
        _write(archive, "compiled-ui.json", json.dumps(compiled_ui, sort_keys=True, separators=(",", ":")).encode())
        _write(archive, f"service/{wheel_name(version)}", wheel)
        for path in sorted((ROOT / "source" / "frontend").glob("*")):
            if path.is_file():
                _write(archive, f"source/frontend/{path.name}", path.read_bytes())
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reader-device-id", required=True)
    parser.add_argument("--destination", default="http://127.0.0.1:9911")
    parser.add_argument("--version", default=REFERENCE_VERSION)
    parser.add_argument("--broken-health", action="store_true")
    arguments = parser.parse_args()
    payload = build_package(
        arguments.reader_device_id,
        arguments.destination,
        version=arguments.version,
        broken_health=arguments.broken_health,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(payload)
    print(hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    main()
