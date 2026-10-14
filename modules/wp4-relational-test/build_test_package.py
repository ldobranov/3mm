"""Build/validate a deterministic test ZIP, never install, import service or grant."""

import argparse
import base64
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"


def _write(archive, name, data):
    entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
    entry.create_system = 3
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    archive.writestr(entry, data)


def build_package():
    files = {
        "wp4_relational_test/" + path.name: path.read_bytes().replace(b"\r\n", b"\n")
        for path in sorted((ROOT / "service/wp4_relational_test").glob("*.py"))
    }
    dist = f"wp4_relational_test-{VERSION}.dist-info"
    files[dist + "/METADATA"] = (
        f"Metadata-Version: 2.1\nName: wp4-relational-test\nVersion: {VERSION}\n"
    ).encode()
    files[dist + "/WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
        writer.writerow([name, "sha256=" + digest.decode("ascii"), len(data)])
    writer.writerow([dist + "/RECORD", "", ""])
    files[dist + "/RECORD"] = record.getvalue().encode()
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in sorted(files.items()):
            _write(archive, name, data)
    definition = json.loads(
        (ROOT / "application-extension.json").read_text(encoding="utf-8")
    )
    definition["service"]["artifact_sha256"] = hashlib.sha256(
        wheel.getvalue()
    ).hexdigest()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in (
            ("manifest.json", manifest),
            ("application-extension.json", definition),
        ):
            _write(
                archive,
                name,
                json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
            )
        _write(archive, definition["service"]["artifact"], wheel.getvalue())
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from backend.services.module_packages import validate_module_package

    payload = build_package()
    validate_module_package(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"ZIP SHA-256: {hashlib.sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
