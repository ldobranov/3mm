"""Read-only identity of the independently delivered application host."""
import json
from pathlib import Path
import re
import sys
import zipfile

HOST_CONTRACT = 1


def build_identity():
    path = Path(sys.argv[0])
    if path.suffix != ".pyz":
        return "source"
    with zipfile.ZipFile(path) as bundle:
        value = json.loads(bundle.read("host-build.json"))
    if (value.get("host_contract") != HOST_CONTRACT
            or not isinstance(value.get("build_id"), str)
            or re.fullmatch(r"[0-9a-f]{64}", value["build_id"]) is None):
        raise ValueError("Application host build is invalid")
    return value["build_id"]
