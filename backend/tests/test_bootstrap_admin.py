import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.user import User
from backend.scripts.bootstrap_admin import (
    AdminBootstrapError,
    create_initial_admin,
    prompt_for_admin,
)
from backend.utils.auth import verify_password


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_creates_first_admin_with_hashed_password(db: Session) -> None:
    admin = create_initial_admin(
        db,
        username="owner",
        email="OWNER@example.com",
        password="a-long-test-password",
    )

    assert admin.email == "owner@example.com"
    assert admin.role == "admin"
    assert admin.hashed_password != "a-long-test-password"
    assert verify_password("a-long-test-password", admin.hashed_password)


def test_refuses_second_admin(db: Session) -> None:
    create_initial_admin(db, "first", "first@example.com", "first-password-123")

    with pytest.raises(AdminBootstrapError, match="already exists"):
        create_initial_admin(
            db,
            "second",
            "second@example.com",
            "second-password-123",
        )


def test_promotes_matching_existing_account_and_replaces_password(db: Session) -> None:
    existing = User(
        username="owner",
        email="owner@example.com",
        hashed_password="old-hash",
        role="user",
    )
    db.add(existing)
    db.commit()

    admin = create_initial_admin(
        db,
        username="owner",
        email="OWNER@example.com",
        password="replacement-password-123",
    )

    assert admin.id == existing.id
    assert admin.role == "admin"
    assert verify_password("replacement-password-123", admin.hashed_password)


def test_refuses_ambiguous_existing_identity(db: Session) -> None:
    db.add_all(
        [
            User(username="owner", email="first@example.com", hashed_password="x"),
            User(username="other", email="owner@example.com", hashed_password="y"),
        ]
    )
    db.commit()

    with pytest.raises(AdminBootstrapError, match="same existing account"):
        create_initial_admin(
            db,
            username="owner",
            email="owner@example.com",
            password="replacement-password-123",
        )


def test_short_password_requires_explicit_development_override(db: Session) -> None:
    with pytest.raises(AdminBootstrapError, match="at least"):
        create_initial_admin(db, "owner", "owner@example.com", "admin")

    admin = create_initial_admin(
        db,
        "owner",
        "owner@example.com",
        "admin",
        allow_insecure_password=True,
    )

    assert verify_password("admin", admin.hashed_password)


def test_prompt_requires_matching_passwords() -> None:
    answers = iter(("owner", "owner@example.com"))
    passwords = iter(("first-password-123", "different-password"))

    with pytest.raises(AdminBootstrapError, match="do not match"):
        prompt_for_admin(lambda _: next(answers), lambda _: next(passwords))
