from datetime import datetime, timedelta, timezone

import backend.database  # noqa: F401 - register complete model metadata
import pytest
from backend.db.base import Base
from backend.db.device import DevicePairingRequest
from backend.db.user import User
from backend.services.device_pairing import (
    PairingApprovalError,
    PairingCodeUnavailableError,
    approve_pairing_request,
    claim_pairing_code,
    issue_pairing_code,
    pairing_code_hash,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            User(
                username="owner",
                email="owner@example.com",
                hashed_password="not-a-real-hash",
                role="admin",
            )
        )
        session.commit()
        yield session
    engine.dispose()


def test_pairing_code_is_high_entropy_and_only_its_hash_is_stored(db: Session) -> None:
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)

    issued = issue_pairing_code(db, created_by_user_id=1, now=now)
    stored = db.get(DevicePairingRequest, issued.request_id)

    assert len(issued.code) >= 24
    assert issued.expires_at == now + timedelta(minutes=10)
    assert stored is not None
    assert stored.code_hash == pairing_code_hash(issued.code)
    assert issued.code not in stored.code_hash


def test_pairing_code_can_be_claimed_exactly_once(db: Session) -> None:
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    issued = issue_pairing_code(db, created_by_user_id=1, now=now)

    claimed = claim_pairing_code(
        db,
        code=issued.code,
        requested_device_id="dev_0123456789abcdef0123456789abcdef",
        public_key="agent-public-key",
        requested_metadata={
            "display_name": "Test Agent",
            "role": "node",
            "protocol_version": "1.0",
        },
        now=now + timedelta(seconds=5),
    )

    assert claimed.requested_device_id == "dev_0123456789abcdef0123456789abcdef"
    assert claimed.public_key == "agent-public-key"
    with pytest.raises(PairingCodeUnavailableError):
        claim_pairing_code(
            db,
            code=issued.code,
            requested_device_id="dev_ffffffffffffffffffffffffffffffff",
            public_key="different-key",
            requested_metadata={
                "display_name": "Replay",
                "role": "node",
                "protocol_version": "1.0",
            },
            now=now + timedelta(seconds=6),
        )


def test_expired_and_unknown_pairing_codes_fail_the_same_way(db: Session) -> None:
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    issued = issue_pairing_code(
        db,
        created_by_user_id=1,
        now=now,
        ttl=timedelta(seconds=1),
    )

    for code in (issued.code, "unknown-code"):
        with pytest.raises(
            PairingCodeUnavailableError,
            match="invalid or unavailable",
        ):
            claim_pairing_code(
                db,
                code=code,
                requested_device_id="dev_0123456789abcdef0123456789abcdef",
                public_key="agent-public-key",
                requested_metadata={
                    "display_name": "Test Agent",
                    "role": "node",
                    "protocol_version": "1.0",
                },
                now=now + timedelta(seconds=2),
            )


def test_pairing_requires_timezone_and_positive_ttl(db: Session) -> None:
    with pytest.raises(ValueError, match="timezone"):
        issue_pairing_code(
            db,
            created_by_user_id=1,
            now=datetime(2026, 8, 9, 12, 0),
        )
    with pytest.raises(ValueError, match="positive"):
        issue_pairing_code(
            db,
            created_by_user_id=1,
            ttl=timedelta(0),
        )


def test_pending_pairing_request_requires_explicit_approval(db: Session) -> None:
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    issued = issue_pairing_code(db, created_by_user_id=1, now=now)
    claim_pairing_code(
        db,
        code=issued.code,
        requested_device_id="dev_0123456789abcdef0123456789abcdef",
        public_key="agent-public-key",
        requested_metadata={
            "display_name": "Test Agent",
            "role": "node",
            "protocol_version": "1.0",
        },
        now=now + timedelta(seconds=1),
    )

    device = approve_pairing_request(
        db,
        request_id=issued.request_id,
        approved_by_user_id=1,
        now=now + timedelta(seconds=2),
    )

    assert device.device_id == "dev_0123456789abcdef0123456789abcdef"
    assert device.credentials == []
    with pytest.raises(PairingApprovalError, match="not pending"):
        approve_pairing_request(
            db,
            request_id=issued.request_id,
            approved_by_user_id=1,
            now=now + timedelta(seconds=3),
        )
