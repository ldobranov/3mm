"""Build a deterministic, hardware-free Agent lifecycle acceptance package."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo


SOURCE = Path(__file__).resolve().parent


def build_package() -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name in ("manifest.json", "health/ready.json"):
            # Normalize JSON/newlines so a Windows and Linux checkout build alike.
            value = json.loads((SOURCE / name).read_text(encoding="utf-8"))
            payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_package()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"Package: {args.output}")
    print(f"SHA256: {hashlib.sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
