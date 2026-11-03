"""Build an inert, deterministic Agent display provider; never activate hardware."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
from zipfile import ZIP_STORED, ZipFile, ZipInfo

# Support direct execution from a source checkout without installing Core.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from three_mm_protocol import ModuleManifestV2
from three_mm_protocol.character_display import (
    CharacterDisplayProfileV1, DISPLAY_CAPABILITY, DISPLAY_ENTRYPOINT,
)


def manifest(profile: CharacterDisplayProfileV1) -> dict:
    value = {
        "manifest_version": 2, "module_id": "org.3mm.character-display." + profile.digest(),
        "name": "Character display (" + profile.driver + ")", "version": "1.0.0",
        "description": f"{profile.columns}x{profile.rows} character display with an exact, opt-in hardware profile.",
        "runtimes": ["agent"], "entrypoints": {"agent": DISPLAY_ENTRYPOINT},
        "compatibility": {"protocol": "1.0", "architectures": ["armv6l", "aarch64", "x86_64"]},
        "permissions": ["hardware.display"],
        "capabilities": {"provides": [DISPLAY_CAPABILITY], "consumes": []},
        "configuration_defaults": profile.model_dump(),
        "health_check": {"type": "file_exists", "path": "health/ready"},
        "registrations": [{"kind": "capability", "registration_id": DISPLAY_CAPABILITY,
                           "metadata": {"driver": profile.driver, "simulated": profile.driver == "mock",
                                        "controller": profile.controller, "pin_map": profile.pin_map,
                                        "backlight_active_high": profile.backlight_active_high,
                                        "bus": profile.bus, "address": profile.address,
                                        "columns": profile.columns, "rows": profile.rows,
                                        "profile_sha256": profile.digest()},
                           "contract": profile.contract().model_dump()}],
    }
    return ModuleManifestV2.model_validate(value).model_dump(exclude_defaults=False)


def build_package(profile: CharacterDisplayProfileV1 | None = None) -> bytes:
    profile = profile or CharacterDisplayProfileV1()
    if profile.driver == 'pcf8574':
        from agent.hardware.character_display import NativeCharacterDisplay
        # Construction validates topology only: no device open or bus transaction.
        NativeCharacterDisplay(profile, Path('/unused/display-profile-validation'))
    elif profile.driver != 'mock':
        raise ValueError('This builder supports the installed mock/PCF8574 drivers')
    output = io.BytesIO()
    payloads = {"manifest.json": (json.dumps(manifest(profile), sort_keys=True, indent=2) + "\n").encode(),
                "health/ready": b"provider package; not a hardware health proof\n"}
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, data in sorted(payloads.items()):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--display-id", default="display.main")
    parser.add_argument("--driver", choices=("mock", "pcf8574"), default="mock")
    parser.add_argument("--bus", type=int, default=1)
    parser.add_argument("--columns", type=int, default=20)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x27)
    parser.add_argument("--backlight-active-low", action="store_true")
    args = parser.parse_args()
    profile = CharacterDisplayProfileV1(display_id=args.display_id, driver=args.driver,
                                       bus=args.bus, address=args.address, columns=args.columns, rows=args.rows,
                                       backlight_active_high=not args.backlight_active_low)
    blob = build_package(profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Do not silently replace an already reviewed artifact with different bytes.
    if args.output.exists() and args.output.read_bytes() != blob:
        parser.error("Output already exists with different content; choose a new path")
    args.output.write_bytes(blob)
    print(json.dumps({"archive": str(args.output.resolve()), "sha256": hashlib.sha256(blob).hexdigest(),
                      "bytes": len(blob), "profile_sha256": profile.digest(),
                      "module_id": manifest(profile)["module_id"],
                      "driver": profile.driver, "columns": profile.columns, "rows": profile.rows,
                      "activation": "not_requested"}))


if __name__ == "__main__":
    main()
