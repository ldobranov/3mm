"""Pin a physically selected Hub's public OTA approval key; never replace trust."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from three_mm_protocol.node_updates import NodeUpdateApprovalKey
from three_mm_runtime.node_update_trust import pin_approval_key
from three_mm_runtime.node_update_helper import AGENT_DATA, read_small

KEY_ENDPOINT = "/api/v1/devices/node-updates/approval-key"


def normalize_hub(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Hub must be a plain HTTP(S) origin without credentials or a path")
    host = parsed.hostname.lower()
    try:
        address = ipaddress.ip_address(host)
        local = address.is_private or address.is_loopback
    except ValueError:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
            raise ValueError("Invalid Hub hostname")
        local = host.endswith(".local") or "." not in host
    if parsed.scheme == "http" and not local:
        raise ValueError("Non-local Hub approval keys require HTTPS")
    port = parsed.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid Hub port")
    authority = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{authority}" + (f":{port}" if port else "")


def fetch_approval_key(hub, *, session=None):
    session = session or requests.Session()
    # Do not send credentials; key is public, and root's proxy environment is not authority.
    session.trust_env = False
    with session.get(normalize_hub(hub) + KEY_ENDPOINT, timeout=(5, 10),
                     allow_redirects=False, stream=True, headers={"Accept-Encoding": "identity"}) as response:
        if response.status_code != 200:
            raise ValueError("Hub approval key endpoint did not return HTTP 200")
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise ValueError("Hub approval key must be uncompressed")
        payload = bytearray()
        for chunk in response.iter_content(chunk_size=1024):
            payload.extend(chunk)
            if len(payload) > 4096:
                raise ValueError("Hub approval key response is too large")
    return NodeUpdateApprovalKey.model_validate_json(bytes(payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub", required=True)
    parser.add_argument("--key-id", help="Fingerprint read independently on the selected Hub; required to pin")
    arguments = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        parser.error("Run this trust bootstrap as root on Linux")
    key = fetch_approval_key(arguments.hub)
    print("Hub approval key fingerprint (SHA-256): " + key.key_id)
    if not arguments.key_id:
        print("No trust was changed. Compare with the selected Hub, then repeat with --key-id.")
        return 0
    identity = json.loads(read_small(AGENT_DATA / "identity.json", 4096))
    if not isinstance(identity, dict):
        parser.error("Node identity is not available")
    changed = pin_approval_key(key, arguments.key_id, device_id=identity.get("device_id"))
    print("Hub approval key pinned." if changed else "Matching Hub approval key was already pinned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
