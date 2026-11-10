"""Build an inert, deterministic Agent display provider; never activate hardware."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

# Support direct execution from a source checkout without installing Core.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from three_mm_protocol.character_display import CharacterDisplayProfileV1
from three_mm_protocol.character_display_package import build_package, manifest
from three_mm_protocol.character_display_package import build_scene_package, scene_manifest
from three_mm_protocol.character_display_scene import CharacterDisplaySceneProfileV1


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
    parser.add_argument("--local-clock", action="store_true", help="Opt-in bounded local scenes; requires new Agent and separate profile approval")
    args = parser.parse_args()
    profile_type = CharacterDisplaySceneProfileV1 if args.local_clock else CharacterDisplayProfileV1
    profile = profile_type(display_id=args.display_id, driver=args.driver,
                                       bus=args.bus, address=args.address, columns=args.columns, rows=args.rows,
                                       backlight_active_high=not args.backlight_active_low)
    blob = build_scene_package(profile) if args.local_clock else build_package(profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Do not silently replace an already reviewed artifact with different bytes.
    if args.output.exists() and args.output.read_bytes() != blob:
        parser.error("Output already exists with different content; choose a new path")
    args.output.write_bytes(blob)
    print(json.dumps({"archive": str(args.output.resolve()), "sha256": hashlib.sha256(blob).hexdigest(),
                      "bytes": len(blob), "profile_sha256": profile.digest(),
                      "module_id": (scene_manifest(profile) if args.local_clock else manifest(profile))["module_id"],
                      "driver": profile.driver, "columns": profile.columns, "rows": profile.rows,
                      "activation": "not_requested"}))


if __name__ == "__main__":
    main()
