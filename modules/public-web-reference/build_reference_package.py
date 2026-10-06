#!/usr/bin/env python3
"""Build the deterministic public-web reference application package."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
REFERENCE_VERSION = "1.0.0"


def wheel_name(version: str) -> str:
    return f"public_web_reference-{version}-py3-none-any.whl"


def _write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload)


def build_wheel(version: str = REFERENCE_VERSION) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted((ROOT / "service" / "public_web_reference").glob("*.py")):
            _write(archive, f"public_web_reference/{path.name}", path.read_bytes())
        _write(
            archive,
            f"public_web_reference-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: public-web-reference\nVersion: {version}\n".encode(),
        )
        _write(
            archive,
            f"public_web_reference-{version}.dist-info/WHEEL",
            b"Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        _write(archive, f"public_web_reference-{version}.dist-info/RECORD", b"")
    return output.getvalue()


def build_package(*, version: str = REFERENCE_VERSION) -> bytes:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    definition = json.loads(
        (ROOT / "application-extension.json").read_text(encoding="utf-8")
    )
    manifest["version"] = version
    definition["version"] = version
    definition["service"]["artifact"] = f"service/{wheel_name(version)}"
    wheel = build_wheel(version)
    definition["service"]["artifact_sha256"] = hashlib.sha256(wheel).hexdigest()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        _write(
            archive,
            "manifest.json",
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(),
        )
        _write(
            archive,
            "application-extension.json",
            json.dumps(definition, sort_keys=True, separators=(",", ":")).encode(),
        )
        _write(archive, f"service/{wheel_name(version)}", wheel)
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default=REFERENCE_VERSION)
    arguments = parser.parse_args()
    payload = build_package(version=arguments.version)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(payload)
    print(hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    main()
