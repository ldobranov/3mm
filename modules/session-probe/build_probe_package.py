"""Build a deterministic Manifest v2 test ZIP; never install or grant it."""
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


def _write(archive, name, data):
    info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def build_package():
    files = {"session_probe/" + path.name: path.read_bytes().replace(b"\r\n", b"\n")
        for path in sorted((ROOT / "service" / "session_probe").glob("*.py"))}
    dist = f"session_probe-{VERSION}.dist-info"
    files[dist + "/METADATA"] = f"Metadata-Version: 2.1\nName: session-probe\nVersion: {VERSION}\n".encode()
    files[dist + "/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: 3mm\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
        writer.writerow([name, "sha256=" + digest, len(data)])
    writer.writerow([dist + "/RECORD", "", ""])
    files[dist + "/RECORD"] = record.getvalue().encode()
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in sorted(files.items()):
            _write(archive, name, data)
    wheel_bytes = wheel.getvalue()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    definition = json.loads((ROOT / "application-extension.json").read_text(encoding="utf-8"))
    definition["service"]["artifact_sha256"] = hashlib.sha256(wheel_bytes).hexdigest()
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        for name, value in [("manifest.json", manifest), ("application-extension.json", definition)]:
            _write(archive, name, json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        _write(archive, definition["service"]["artifact"], wheel_bytes)
        _write(archive, "compiled-ui.json", (ROOT / "compiled-ui.json").read_bytes())
        _write(archive, "source/frontend/Probe.vue", (ROOT / "source/frontend/Probe.vue").read_bytes())
    return package.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = build_package()
    # Structural Core validation before delivering the artifact. No installation.
    import sys
    sys.path.insert(0, str(ROOT.parents[1]))
    from backend.services.module_packages import validate_module_package
    validate_module_package(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"SHA-256: {hashlib.sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
