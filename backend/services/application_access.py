"""Server-owned principals and route authorization for application extensions."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.module import (
    ApplicationExtensionInstallation,
    ApplicationKioskTerminal,
    ApplicationPermissionGrant,
)
from backend.db.user import User
from backend.utils.jwt_utils import decode_token
from three_mm_protocol import ApplicationRouteV1


@dataclass(frozen=True, slots=True)
class ApplicationPrincipal:
    kind: str
    user_id: int | None = None
    is_admin: bool = False
    kiosk_module_id: str | None = None
    terminal_id: str | None = None


ANONYMOUS_PRINCIPAL = ApplicationPrincipal(kind="anonymous")


def resolve_application_principal(
    authorization: str | None,
    db: Session,
) -> ApplicationPrincipal:
    if not authorization:
        return ANONYMOUS_PRINCIPAL
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authorization header is invalid")
    claims = decode_token(authorization.split(" ", 1)[1].strip())
    token_type = claims.get("token_type", "user")
    if token_type == "application_kiosk":
        terminal_id = claims.get("terminal_id")
        module_id = claims.get("module_id")
        if not isinstance(terminal_id, str) or not isinstance(module_id, str):
            raise HTTPException(401, "Kiosk token is invalid")
        terminal = db.scalar(
            select(ApplicationKioskTerminal)
            .join(
                ApplicationExtensionInstallation,
                ApplicationExtensionInstallation.id
                == ApplicationKioskTerminal.application_installation_id,
            )
            .where(
                ApplicationKioskTerminal.terminal_id == terminal_id,
                ApplicationKioskTerminal.enabled.is_(True),
                ApplicationExtensionInstallation.module_id == module_id,
                ApplicationExtensionInstallation.enabled.is_(True),
                ApplicationExtensionInstallation.status == "active",
            )
        )
        if terminal is None:
            raise HTTPException(401, "Kiosk terminal is revoked or unavailable")
        return ApplicationPrincipal(
            kind="kiosk",
            kiosk_module_id=module_id,
            terminal_id=terminal_id,
        )
    if token_type != "user":
        raise HTTPException(401, "Token type is not supported")
    subject = claims.get("sub") or claims.get("user_id")
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(401, "User token subject is invalid") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "User is unavailable")
    return ApplicationPrincipal(
        kind="user",
        user_id=user.id,
        is_admin=user.role == "admin",
    )


def application_permission_ids(
    db: Session,
    installation_id: int,
    user_id: int,
) -> frozenset[str]:
    return frozenset(
        db.scalars(
            select(ApplicationPermissionGrant.permission_id).where(
                ApplicationPermissionGrant.application_installation_id
                == installation_id,
                ApplicationPermissionGrant.user_id == user_id,
            )
        )
    )


def can_access_application_route(
    route: ApplicationRouteV1,
    principal: ApplicationPrincipal,
    *,
    module_id: str,
    permission_ids: frozenset[str] = frozenset(),
) -> bool:
    if route.audience == "public":
        return True
    if route.audience == "kiosk":
        return (
            principal.kind == "kiosk"
            and principal.kiosk_module_id == module_id
        )
    if principal.kind != "user":
        return False
    if route.audience == "administrator":
        return principal.is_admin
    if route.audience == "operator":
        return principal.is_admin or set(route.required_permissions) <= permission_ids
    return False
