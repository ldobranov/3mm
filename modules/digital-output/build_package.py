"""Build output-only GPIO; opt-in versioned 1.1.0 leaves legacy 1.0.0 intact."""

import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

SOURCE = Path(__file__).resolve().parent


def versioned_manifest():
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = "1.1.0"
    def obj(properties, required=None):
        return {"type": "object", "additionalProperties": False,
                "properties": properties, "required": list(properties) if required is None else required}
    channel = {"type": "string", "maxLength": 32, "enum": ["gpio.output.1"]}
    duration = {"type": "integer", "minimum": 50, "maximum": 10000}
    output = obj({"gpio.output.1": {"type": "boolean"}})
    result = {"inputs": obj({}), "outputs": output}
    contract = {"schema_version": 1, "capability_id": "gpio.digital.control",
        "contract_version": "1.0", "state_schema": output, "actions": {
            "set_output": {"arguments_schema": obj({"channel": channel, "value": {"type": "boolean"}}),
                           "result_schema": obj(result)},
            "pulse_output": {"arguments_schema": obj({"channel": channel, "duration_ms": duration}),
                "result_schema": obj({**result, "pulse": obj({"channel": channel,
                    "duration_ms": duration, "active_value": {"type": "boolean"},
                    "safe_value": {"type": "boolean"}})})},
        }}
    manifest["registrations"][0]["contract"] = contract
    return manifest


def build_package(*, versioned=False):
    manifest = (versioned_manifest() if versioned
                else json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8")))
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        payloads = {"manifest.json": (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
                    "health/ready": (SOURCE / "health/ready").read_bytes().replace(b"\r\n", b"\n")}
        for name, payload in payloads.items():
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return output.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--versioned-command", action="store_true")
    args = parser.parse_args()
    blob = build_package(versioned=args.versioned_command)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(blob)
    print(hashlib.sha256(blob).hexdigest())
