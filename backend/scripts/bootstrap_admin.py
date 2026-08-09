"""Interactively create the first administrator without exposing a password."""

from __future__ import annotations

import argparse
import getpass
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.db.user import User
from backend.utils.auth import hash_password

MINIMUM_PASSWORD_LENGTH = 12


class AdminBootstrapError(RuntimeError):
    pass


def create_initial_admin(
    db: Session,
    username: str,
    email: str,
    password: str,
    allow_insecure_password: bool = False,
) -> User:
    normalized_username = username.strip()
    normalized_email = email.strip().lower()
    if not normalized_username:
        raise AdminBootstrapError("Username cannot be empty")
    if "@" not in normalized_email:
        raise AdminBootstrapError("Email address is invalid")
    if not allow_insecure_password and len(password) < MINIMUM_PASSWORD_LENGTH:
        raise AdminBootstrapError(
            f"Password must be at least {MINIMUM_PASSWORD_LENGTH} characters"
        )
    existing_admin = db.scalar(select(User).where(User.role == "admin"))
    if existing_admin is not None:
        raise AdminBootstrapError("An administrator already exists")
    username_owner = db.scalar(
        select(User).where(User.username == normalized_username)
    )
    email_owner = db.scalar(select(User).where(User.email == normalized_email))
    if username_owner is not None or email_owner is not None:
        if (
            username_owner is None
            or email_owner is None
            or username_owner is not email_owner
        ):
            raise AdminBootstrapError(
                "Username and email must identify the same existing account"
            )
        setattr(username_owner, "hashed_password", hash_password(password))
        setattr(username_owner, "role", "admin")
        db.commit()
        db.refresh(username_owner)
        return username_owner

    admin = User(
        username=normalized_username,
        email=normalized_email,
        hashed_password=hash_password(password),
        role="admin",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def prompt_for_admin(
    input_fn: Callable[[str], str] = input,
    password_fn: Callable[[str], str] = getpass.getpass,
) -> tuple[str, str, str]:
    username = input_fn("Administrator username: ")
    email = input_fn("Administrator email: ")
    password = password_fn("Administrator password: ")
    confirmation = password_fn("Confirm password: ")
    if password != confirmation:
        raise AdminBootstrapError("Passwords do not match")
    return username, email, password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first 3mm administrator")
    parser.add_argument(
        "--allow-insecure-development-password",
        action="store_true",
        help="allow a short password for an isolated development installation",
    )
    arguments = parser.parse_args()
    try:
        username, email, password = prompt_for_admin()
        with SessionLocal() as db:
            admin = create_initial_admin(
                db,
                username,
                email,
                password,
                allow_insecure_password=arguments.allow_insecure_development_password,
            )
    except AdminBootstrapError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Administrator created for {admin.email}")


if __name__ == "__main__":
    main()
