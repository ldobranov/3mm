"""Explicit inert first registration, using the existing sealed Action journal.

No helper, package import, namespace, native trust, grant or activation. A
deterministic provenance record binds the newly created incarnation; an ordinary
staged/failed record cannot masquerade as a never-started registered package.
"""

import hashlib

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.services import application_authority_management as authority
from backend.services import application_authority_sources as sources
from backend.services.application_authority_context import (
    AuthorityPrincipal,
    _bounded_json,
    _canonical_bytes,
)
from backend.services.application_authority_inspection import (
    AuthorityInspectionBaseline,
    _read_baseline,
)
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_configuration import resolve_application_configuration
from backend.services.application_requirements import require_platform_requirements
from backend.services.application_policy_reviews import PolicyReviewStoreError, _actor
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_runtime.application_activation import application_instance_id

OPERATION = "relational_first_registration"


def registration_id(db, installation_id):
    current = read_application_authority(db, installation_id)
    return hashlib.sha256(
        b"3mm:m20:inert-registration:v1\x00"
        + _canonical_bytes(
            {
                "core": sources._core_identity(db),
                "installation_id": installation_id,
                "incarnation": current.incarnation,
            }
        )
    ).hexdigest()[:32]


def candidate_registration_id(db, installation_id, pin):
    """Per-artifact inert provenance; never replace first-registration history."""
    return hashlib.sha256(
        b"3mm:m20:inert-candidate:v1\x00"
        + _canonical_bytes(
            {
                "registration": registration_id(db, installation_id),
                "package_id": pin.module_package_id,
                "sha256": pin.sha256,
            }
        )
    ).hexdigest()[:32]


def _binding(db, key, installation_id, pin, package):
    current = read_application_authority(db, installation_id)
    principal = AuthorityPrincipal(
        core_installation_id=sources._core_identity(db),
        application_installation_id=str(installation_id),
        incarnation=current.incarnation,
        module_id=current.module_id,
    )
    row = db.get(Installation, installation_id, populate_existing=True)
    return {
        "principal": principal.model_dump(mode="json"),
        "package_id": pin.module_package_id,
        "version": pin.version,
        "sha256": pin.sha256,
        "instance_id": row.instance_id,
        "configuration": key._fingerprint_in_snapshot(
            db, principal, sources._configuration(db, installation_id, package)
        ).model_dump(mode="json"),
    }


def verify_registration(db, key, installation_id, pin, package):
    """Authenticate inert binding provenance before subject/review/preparation."""
    if key is None:
        raise sources._Unavailable("installation_unavailable")
    from backend.services.application_configuration_provenance import binding_matches
    candidate_id = candidate_registration_id(db, installation_id, pin)
    candidate = db.get(Action, candidate_id)
    if candidate is not None:
        from backend.services.application_relational_candidate import verify_candidate

        verify_candidate(db, key, installation_id, pin, package, candidate)
        return
    identifier = registration_id(db, installation_id)
    proof = authority._load(db, key, "action", db.get(Action, identifier), identifier)
    if (
        proof["state"] != "registered_not_started"
        or set(proof["data"]) != {"operation", "actor", "binding"}
        or proof["data"]["operation"] != OPERATION
        or not binding_matches(db, key, installation_id, identifier, proof['revision'],
            proof['data']['binding'], _binding(db, key, installation_id, pin, package))
    ):
        raise authority.AuthorityManagementError("registration_unavailable")


def register_relational_package(
    manager,
    *,
    package_id,
    artifact_sha256,
    configuration,
    actor_token,
    request_id,
    confirm_register_without_start,
):
    """Local Core administration only; no HTTP/SDK writer or implicit adoption."""
    if (
        type(package_id) is not int
        or package_id < 1
        or confirm_register_without_start is not True
        or type(configuration) is not dict
    ):
        raise authority.AuthorityManagementError("invalid_request")
    request_id = authority._identifier(request_id)
    artifact_sha256 = authority._digest(artifact_sha256)
    configuration = _bounded_json(configuration)
    request_hash = hashlib.sha256(
        b"3mm:m20:inert-registration-request:v1\x00"
        + _canonical_bytes(
            {
                "package_id": package_id,
                "sha256": artifact_sha256,
                "configuration": configuration,
            }
        )
    ).hexdigest()
    try:
        # Authenticate before artifact I/O. No key/DB lease spans ZIP validation.
        with Session(manager.engine) as db, authority_transaction(db):
            _actor(db, actor_token)
            pin = db.execute(
                select(
                    ModulePackage.module_id, ModulePackage.version, ModulePackage.sha256
                ).where(ModulePackage.id == package_id)
            ).one_or_none()
            if pin is None or pin.sha256 != artifact_sha256:
                raise authority.AuthorityManagementError("artifact_unavailable")
        package = _read_baseline(
            AuthorityInspectionBaseline(
                pin.module_id, pin.version, pin.sha256, None, "disabled", None
            ),
            manager.uploads_root,
            manager.core_version,
        )
        if package.application_extension.storage.relational is None:
            raise authority.AuthorityManagementError("relational_declaration_required")
        require_platform_requirements(package.application_extension)
        resolved = resolve_application_configuration(
            package.manifest.configuration_schema,
            package.manifest.configuration_defaults,
            package.application_extension,
            overrides=configuration,
        )
        with (
            manager.keys.locked() as key,
            Session(manager.engine) as db,
            authority_transaction(db) as mutation,
        ):
            actor = list(_actor(db, actor_token))
            key._check(db)
            existing = db.get(Action, request_id)
            if existing is not None:
                receipt = authority._load(db, key, "action", existing, request_id)
                if (
                    receipt["state"] != "recorded"
                    or receipt["data"]["operation"] != OPERATION
                    or receipt["data"]["request_hash"] != request_hash
                    or receipt["data"]["actor"] != actor
                ):
                    raise authority.AuthorityManagementError("request_conflict")
                return {
                    **receipt["data"]["result"],
                    "historical": True,
                    "replayed": True,
                }
            current_pin = db.execute(
                select(
                    ModulePackage.module_id, ModulePackage.version, ModulePackage.sha256
                ).where(ModulePackage.id == package_id)
            ).one_or_none()
            if current_pin != pin:
                raise authority.AuthorityManagementError("artifact_changed")
            if (
                db.scalar(
                    select(Installation.id).where(
                        Installation.module_id == pin.module_id
                    )
                )
                is not None
            ):
                raise authority.AuthorityManagementError("existing_installation")
            installation = Installation(
                module_id=pin.module_id,
                module_package_id=package_id,
                instance_id=application_instance_id(pin.module_id),
                active_version=None,
                status="disabled",
                enabled=False,
                socket_path="pending",
                configuration=resolved,
                authority_mode="review_required",
            )
            db.add(installation)
            db.flush()
            identifier = registration_id(db, installation.id)
            if identifier == request_id or db.get(Action, identifier) is not None:
                raise authority.AuthorityManagementError("request_conflict")
            # Preliminary pin is allowed only after the provenance row exists;
            # final composition below must verify its exact authenticated binding.
            from types import SimpleNamespace

            candidate = SimpleNamespace(
                module_package_id=package_id, version=pin.version, sha256=pin.sha256
            )
            authority._save(
                db,
                key,
                "action",
                Action(request_id=identifier, installation_id=installation.id),
                authority._envelope(
                    "action",
                    identifier,
                    installation.id,
                    "registered_not_started",
                    {
                        "operation": OPERATION,
                        "actor": actor,
                        "binding": _binding(
                            db, key, installation.id, candidate, package
                        ),
                    },
                ),
            )
            prepared_pin = sources._package_pin(db, installation.id)
            manager._subject(db, key, installation.id, (prepared_pin, package))
            result = {
                "installation_id": installation.id,
                "registration_id": identifier,
                "artifact_sha256": pin.sha256,
                "status": "registered_not_started",
                "active_version": None,
                "permission_approval": "not_evaluated",
            }
            authority._save(
                db,
                key,
                "action",
                Action(request_id=request_id, installation_id=installation.id),
                authority._envelope(
                    "action",
                    request_id,
                    installation.id,
                    "recorded",
                    {
                        "operation": OPERATION,
                        "request_hash": request_hash,
                        "actor": actor,
                        "result": result,
                    },
                ),
            )
            db.add(
                AuditLog(
                    user_id=actor[0],
                    action="APPLICATION_RELATIONAL_REGISTER",
                    entity_type="application_extension",
                    entity_name=pin.module_id,
                    changes={"request_id": request_id, **result},
                )
            )
            mutation.advance_guard_revision()
        return result
    except authority.AuthorityManagementError:
        raise
    except (
        AuthorityReviewKeyError,
        PolicyReviewStoreError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
        RecursionError,
    ):
        raise authority.AuthorityManagementError("registration_unavailable") from None
