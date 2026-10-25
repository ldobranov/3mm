"""Initial administrator establishment against an explicitly selected migrated DB.

No implicit schema creation, default account, reset, promotion or global engine.
An interrupted setup can prove the already-created account on retry.
"""

import sqlite3
from pathlib import Path

from backend.utils.auth import hash_password, verify_password


class InitialAdministratorError(ValueError):
    pass


def establish_administrator(database: Path, username: str, email: str, password: str) -> None:
    username, email = username.strip(), email.strip().lower()
    if not username or "@" not in email or not password:
        raise InitialAdministratorError("administrator_invalid")
    try:
        with sqlite3.connect(f"file:{database.as_posix()}?mode=rw", uri=True, timeout=3) as connection:
            connection.execute("BEGIN IMMEDIATE")
            admins = connection.execute(
                "SELECT username, email, hashed_password, is_blocked FROM users WHERE role='admin'"
            ).fetchall()
            if admins:
                valid = any(name == username and address.lower() == email and not blocked
                            and verify_password(password, hashed) for name, address, hashed, blocked in admins)
                if not valid:
                    raise InitialAdministratorError("administrator_authentication_failed")
                return
            if connection.execute("SELECT 1 FROM users WHERE username=? OR email=?", (username, email)).fetchone():
                raise InitialAdministratorError("administrator_account_conflict")
            connection.execute("INSERT INTO users (username,email,hashed_password,role,is_blocked,token_version) "
                               "VALUES (?,?,?,'admin',0,0)", (username, email, hash_password(password)))
    except (sqlite3.Error, TypeError, ValueError) as exc:
        if isinstance(exc, InitialAdministratorError):
            raise
        raise InitialAdministratorError("administrator_database_unavailable") from None
