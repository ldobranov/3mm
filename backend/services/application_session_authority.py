"""Current M20 service AND human authority for one exact M21 session.

Internal Core adapter, not a ticket endpoint, process launcher or an isolation
proof. Reads actual sealed review/apply records and the live user/role/device
state. No writes, compatibility fallback or authority based on a transport hello.
The production gateway remains unmounted until its execution boundary exists.
"""

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.db.device import Device
from backend.db.module import ApplicationExtensionInstallation
from backend.services.application_access import application_permission_ids
from backend.services.application_authority_context import (
    ResolvedSessionScope,
    _bounded_json,
    _canonical_bytes,
    _parse,
)
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_authority_management import AuthorityManagementError
from backend.services.application_authority_sources import _read_snapshot
from backend.services.device_capability_registry import capability_catalog
from backend.utils.auth_dep import require_user
from three_mm_protocol.interactive_session import (
    SESSION_ID_PATTERN,
    SessionOpenRequestV1,
)


class SessionAuthorityError(ValueError):
    """No current authority. Never retry or reopen automatically."""


@dataclass(frozen=True, slots=True)
class SessionAuthorityBinding:
    session_id: str
    installation_id: int
    binding_id: str
    user_id: int
    login_session_id: int
    token_version: int
    grant_revision: str
    authority_sha256: str
    request_sha256: str


class M20SessionAuthority:
    def __init__(self, manager):
        # Trusted Core composition root only; no manager/configuration from HTTP.
        self.manager = manager

    def admit(
        self,
        *,
        installation_id,
        binding_id,
        session_id,
        authorization,
        request: SessionOpenRequestV1,
    ) -> SessionAuthorityBinding:
        """Resolve permission, not permission to launch an unrestricted child."""
        return self._resolve(
            installation_id, binding_id, session_id, authorization, request
        )[0]

    def check(
        self,
        binding,
        *,
        authorization,
        request,
        session_id,
        operation,
        control_action=None,
    ):
        """Re-resolve on input/control/output; an old binding never renews itself."""
        if (
            type(binding) is not SessionAuthorityBinding
            or binding.session_id != session_id
            or type(operation) is not str
            or control_action is not None
            and type(control_action) is not str
        ):
            raise SessionAuthorityError("Session authority is unavailable")
        current, resource = self._resolve(
            binding.installation_id,
            binding.binding_id,
            session_id,
            authorization,
            request,
        )
        if current != binding:
            raise SessionAuthorityError("Session authority changed")
        if operation == "input":
            if (
                resource.declaration.access_mode != "write"
                or control_action is not None
            ):
                raise SessionAuthorityError("Session input is not authorized")
        elif operation == "control":
            if control_action not in resource.declaration.control_actions:
                raise SessionAuthorityError("Session control is not authorized")
        elif operation not in {"output", "status"} or control_action is not None:
            raise SessionAuthorityError("Session operation is not authorized")

    def output_checker(self, binding, *, authorization, request, session_id):
        """Bind the real M20 check to the bounded pump; never block its event loop."""

        async def authorize():
            await asyncio.to_thread(
                self.check,
                binding,
                authorization=authorization,
                request=request,
                session_id=session_id,
                operation="output",
            )

        return authorize

    def _resolve(self, installation_id, binding_id, session_id, authorization, request):
        if (
            type(installation_id) is not int
            or installation_id < 1
            or type(binding_id) is not str
            or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", binding_id) is None
            or type(session_id) is not str
            or re.fullmatch(SESSION_ID_PATTERN, session_id) is None
            or type(authorization) is not str
            or len(authorization) > 8192
        ):
            raise SessionAuthorityError("Session authority is unavailable")
        try:
            # Revalidate constructed models, too. Nothing chooses an owner from
            # provider-supplied context or a browser's claimed user/device metadata.
            request = SessionOpenRequestV1.model_validate_json(
                json.dumps(_bounded_json(request.model_dump(mode="python"))),
                strict=True,
            )
            prepared = self.manager._prepare(installation_id)
            scope = f"session:{binding_id}:open"
            # ZIP I/O before key -> one fresh read-only Core DB snapshot.
            with (
                self.manager.keys.locked() as key,
                _read_snapshot(self.manager.engine) as db,
            ):
                claims = require_user(authorization=authorization, db=db)
                if (
                    type(claims.get("sid")) is not int
                    or claims["sid"] < 1
                    or type(claims.get("token_version")) is not int
                    or type(claims.get("exp")) is not int
                    or claims["exp"] <= datetime.now(UTC).timestamp()
                ):
                    raise SessionAuthorityError(
                        "A current tracked user login is required"
                    )
                grant = self.manager._require_grant(
                    db, key, installation_id, prepared, scope
                )
                installation = db.get(ApplicationExtensionInstallation, installation_id)
                if (
                    installation is None
                    or not installation.enabled
                    or installation.status != "active"
                ):
                    raise SessionAuthorityError("Session application is inactive")
                resources = grant["data"]["subject"].get("sessions", ())
                resource = next(
                    (
                        _parse(ResolvedSessionScope, value)
                        for value in resources
                        if value["declaration"]["binding_id"] == binding_id
                    ),
                    None,
                )
                if resource is None:
                    raise SessionAuthorityError("Session resource is unavailable")
                declaration = resource.declaration
                device = db.scalar(
                    select(Device).where(Device.device_id == resource.target_device_id)
                )
                if device is None or not any(
                    item.capability_id == declaration.capability_id
                    and item.provider_id == declaration.provider_id
                    and item.registered
                    and item.available is True
                    for item in capability_catalog(db, device)
                ):
                    raise SessionAuthorityError(
                        "Session target is not currently available"
                    )
                if (
                    request.device_id != resource.target_device_id
                    or request.provider_id != declaration.provider_id
                    or request.capability_id != declaration.capability_id
                    or request.access_mode != declaration.access_mode
                    or _canonical_bytes(request.options)
                    != _canonical_bytes(declaration.options)
                ):
                    raise SessionAuthorityError(
                        "Session request does not match the reviewed resource"
                    )
                user_id = int(claims.get("sub") or claims.get("user_id"))
                # Even a system administrator needs a separate current human
                # grant. A native review or the app's resource grant is not one.
                if declaration.required_permission not in application_permission_ids(
                    db, installation_id, user_id
                ):
                    raise SessionAuthorityError(
                        "Current user has no session permission"
                    )
                subject = grant["data"]["subject"]
                authority = {
                    "binding": subject["binding"],
                    "resource": resource.model_dump(mode="json"),
                    "authority_epoch": grant["data"]["authority_epoch"],
                    "instance_id": installation.instance_id,
                }
                bound = SessionAuthorityBinding(
                    session_id=session_id,
                    installation_id=installation_id,
                    binding_id=binding_id,
                    user_id=user_id,
                    login_session_id=claims["sid"],
                    token_version=claims["token_version"],
                    grant_revision=grant["revision"],
                    authority_sha256=hashlib.sha256(
                        _canonical_bytes(authority)
                    ).hexdigest(),
                    request_sha256=hashlib.sha256(
                        _canonical_bytes(request.model_dump(mode="json"))
                    ).hexdigest(),
                )
                return bound, resource
        except (
            HTTPException,
            AuthorityManagementError,
            AuthorityReviewKeyError,
            SQLAlchemyError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
        ):
            raise SessionAuthorityError(
                "Session authority is unavailable or changed"
            ) from None
