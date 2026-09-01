#!/usr/bin/env python3
"""Pair a co-located Agent with Core without exposing its credential."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.identity import AgentIdentity
from backend.database import SessionLocal
from deployment.local_agent_pairing import (
    LocalAgentPairingError,
    ensure_automatic_local_agent_pairing,
    ensure_local_agent_pairing,
)
from three_mm_protocol import AgentRole


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--automatic", action="store_true")
    parser.add_argument("--admin-email")
    parser.add_argument("--identity-file", type=Path)
    parser.add_argument("--credential-dir", type=Path)
    parser.add_argument("--public-key-file", type=Path)
    parser.add_argument("--display-name")
    parser.add_argument("--role", choices=("standalone", "hub", "node"))
    parser.add_argument(
        "--agent-data-dir",
        type=Path,
        default=Path("/var/lib/3mm/agent"),
    )
    parser.add_argument(
        "--provisioning-data-dir",
        type=Path,
        default=Path("/var/lib/3mm/provisioning"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        with SessionLocal() as db:
            if args.automatic:
                result = ensure_automatic_local_agent_pairing(
                    db,
                    agent_data_dir=args.agent_data_dir,
                    provisioning_data_dir=args.provisioning_data_dir,
                    admin_email=args.admin_email,
                )
            else:
                required = {
                    "identity-file": args.identity_file,
                    "credential-dir": args.credential_dir,
                    "public-key-file": args.public_key_file,
                    "display-name": args.display_name,
                    "role": args.role,
                }
                missing = [name for name, value in required.items() if value is None]
                if missing:
                    raise LocalAgentPairingError(
                        "Manual pairing requires: " + ", ".join(missing)
                    )
                identity = AgentIdentity.model_validate_json(
                    args.identity_file.read_text(encoding="utf-8")
                )
                public_key = args.public_key_file.read_text(encoding="utf-8")
                result = ensure_local_agent_pairing(
                    db,
                    identity=identity,
                    credential_dir=args.credential_dir,
                    display_name=args.display_name,
                    role=AgentRole(args.role),
                    admin_email=args.admin_email,
                    public_key=public_key,
                )
    except (LocalAgentPairingError, OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Local Agent pairing status: {result.status} ({result.device_id or 'external Core'})")


if __name__ == "__main__":
    main()
