#!/usr/bin/env python3
"""Pair a co-located Agent with Core without exposing its credential."""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from agent.core_client import DeviceCredential, DeviceCredentialStore
from agent.identity import AgentIdentity
from backend.database import SessionLocal
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services.device_pairing import (
    approve_pairing_request,
    claim_pairing_code,
    complete_pairing_request,
    issue_pairing_code,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--credential-dir", type=Path, required=True)
    parser.add_argument("--public-key-file", type=Path, required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--role", choices=("standalone", "hub", "node"), required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    identity = AgentIdentity.model_validate_json(
        args.identity_file.read_text(encoding="utf-8")
    )
    public_key = args.public_key_file.read_text(encoding="utf-8").strip()
    store = DeviceCredentialStore(args.credential_dir)
    if store.load() is not None:
        raise SystemExit("Local Agent is already paired")

    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == args.admin_email))
        if admin is None or admin.role != "admin":
            raise SystemExit("Requested administrator was not found")

        issued = issue_pairing_code(db, created_by_user_id=admin.id)
        claim_pairing_code(
            db,
            code=issued.code,
            requested_device_id=identity.device_id,
            public_key=public_key,
            requested_metadata={
                "display_name": args.display_name,
                "role": args.role,
                "protocol_version": "1.0",
            },
        )
        device = approve_pairing_request(
            db,
            request_id=issued.request_id,
            approved_by_user_id=admin.id,
        )
        issued_credential = complete_pairing_request(
            db,
            code=issued.code,
            requested_device_id=identity.device_id,
        )
        db.add(
            AuditLog(
                user_id=admin.id,
                action="DEVICE_PAIRING_APPROVED",
                entity_type="device",
                entity_id=device.id,
                entity_name=device.device_id,
                changes={"pairing_request_id": issued.request_id, "source": "local-bootstrap"},
            )
        )
        db.commit()

    store.save(
        DeviceCredential(
            device_id=issued_credential.device_id,
            credential_id=issued_credential.credential_id,
            credential_secret=issued_credential.secret,
        )
    )
    print(f"Paired {identity.device_id} as {args.display_name}")


if __name__ == "__main__":
    main()
