"""LOCAL inert version adoption after a confirmed exact-source stop.

Only Core metadata changes; catalog artifacts and the Core review key are read.
No package import, migration, runtime namespace/transport-key/business-file I/O,
helper call or trust/grant creation. Owner and prepared database remain unchanged;
fresh native review, normal resource approval and explicit upgrade follow.
"""

import hashlib
import zipfile
import zlib

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.services import application_authority_management as authority
from backend.services import application_authority_sources as sources
from backend.services import application_relational_activation_recovery as recovery
from backend.services import application_relational_registration as registration
from backend.services.application_authority_context import _canonical_bytes
from backend.services.application_authority_inspection import (
    AuthorityInspectionBaseline,
    _read_baseline,
)
from backend.services.application_commands import invalidate_commands
from backend.services.application_configuration import resolve_application_configuration
from backend.services.application_policy_reviews import _actor
from backend.services.application_relational_lifecycle import MAX_PREPARATION_ACTIONS
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_wire import (
    _activation_recovery_ticket,
    _RelationalActivationRecoveryResult,
    canonical,
)

OPERATION = "relational_candidate_adoption"


def _version_key(value):
    """Order validated manifest semvers; build metadata does not advance version."""
    core, separator, prerelease = value.split("+", 1)[0].partition("-")
    return tuple(map(int, core.split("."))), (
        (
            0,
            tuple(
                (0, int(x)) if x.isdigit() else (1, x) for x in prerelease.split(".")
            ),
        )
        if separator
        else (1,)
    )


def _stop_source(db, key, installation_id, prepared, generation, identifier, revision):
    """Authenticate Core's accepted stop receipt, not a fresh OS stop permit.

    The existing Root stop callback verified transport signatures before sealing
    this receipt. This metadata-only writer never reads Root transport secrets or
    treats historical stop evidence as permission to execute code/change files.
    Upgrade independently verifies current stop/boot/key/filesystem state.
    """
    stable = recovery._stable(db, key, installation_id, prepared, generation)
    row = db.get(Action, identifier, populate_existing=True)
    value = authority._load(db, key, "action", row, identifier)
    ticket, purpose = _activation_recovery_ticket(value["data"]["result"]["ticket"])
    receipt = _RelationalActivationRecoveryResult.model_validate(
        value["data"]["receipt"]
    ).model_dump(mode="json")
    source_row, source, original = recovery._sealed_source(
        db, key, installation_id, ticket["source_activation_id"], stable
    )
    current = read_application_authority(db, installation_id)
    if (
        value["installation_id"] != installation_id
        or value["data"].get("operation") != recovery.OPERATION
        or value["state"] != "confirmed"
        or value["revision"] != revision
        or value["data"].get("reactivation_id") is not None
        or value["data"].get("candidate_adoption_id") is not None
        or source["data"].get("reactivation_id") is not None
        or source["data"].get("candidate_adoption_id") is not None
        or source["data"].get("activation_recovery_id") != identifier
        or source["revision"] != ticket["source_activation_revision"]
        or source["state"] != ticket["source_state"]
        or ticket["preparation_id"] != identifier
        or ticket["authority_epoch"] != current.epoch
        or current.mode != "review_required"
        or (purpose == "reactivation_recovery")
        != (original["action"] == "reactivate_prepared_service")
        or ticket["source_ticket_sha256"]
        != hashlib.sha256(canonical(original)).hexdigest()
        or any(ticket[name] != item for name, item in stable.items())
        or receipt["preparation_id"] != identifier
        or receipt["source_activation_id"] != original["preparation_id"]
        or receipt["ticket_sha256"] != hashlib.sha256(canonical(ticket)).hexdigest()
        or receipt["lifecycle_sha256"] != original["prepared_lifecycle_sha256"]
    ):
        raise authority.AuthorityManagementError("candidate_stop_changed")
    return row, value, source_row, source, ticket


def verify_candidate(db, key, installation_id, pin, package, row):
    """Keyed installed-subject composition only; no unsigned candidate authority."""
    identifier = registration.candidate_registration_id(db, installation_id, pin)
    value = authority._load(db, key, "action", row, identifier)
    installed = db.get(Installation, installation_id, populate_existing=True)
    if (
        value["installation_id"] != installation_id
        or value["state"] != "candidate_not_started"
        or value["data"].get("operation") != OPERATION
        or installed.previous_package_id != value["data"]["previous_package_id"]
        or _canonical_bytes(value["data"]["binding"])
        != _canonical_bytes(
            registration._binding(db, key, installation_id, pin, package)
        )
    ):
        raise authority.AuthorityManagementError("candidate_provenance_changed")


def adopt_relational_version(
    manager,
    installation_id,
    *,
    actor_token,
    request_id,
    package_id,
    artifact_sha256,
    expected_current_artifact_sha256,
    source_recovery_id,
    expected_recovery_revision,
    confirm_adopt_without_execution,
):
    """Adopt one uploaded newer version; requires separate confirmed stop first.

    This bounded path preserves resolved configuration exactly. A candidate that
    needs configuration changes, an unconfirmed stop, compatibility installation
    or a second candidate before completing the first is deliberately refused.
    """
    if (
        type(installation_id) is not int
        or not 1 <= installation_id < 2**53
        or type(package_id) is not int
        or not 1 <= package_id < 2**53
        or confirm_adopt_without_execution is not True
    ):
        raise authority.AuthorityManagementError("invalid_candidate_request")
    request_id = authority._identifier(request_id)
    artifact_sha256 = authority._digest(artifact_sha256)
    old_digest = authority._digest(expected_current_artifact_sha256)
    source_id = authority._identifier(source_recovery_id)
    revision = authority._identifier(expected_recovery_revision)
    try:
        # Authenticate before any uploaded artifact is opened.
        with Session(manager.engine) as db, authority_transaction(db):
            _actor(db, actor_token)
            target = db.execute(
                select(
                    ModulePackage.module_id, ModulePackage.version, ModulePackage.sha256
                ).where(ModulePackage.id == package_id)
            ).one_or_none()
            if target is None or target.sha256 != artifact_sha256:
                raise authority.AuthorityManagementError(
                    "candidate_artifact_unavailable"
                )
        prepared = manager._prepare(installation_id)
        package = _read_baseline(
            AuthorityInspectionBaseline(
                target.module_id, target.version, target.sha256, None, "disabled", None
            ),
            manager.uploads_root,
            manager.core_version,
        )
        definition = package.application_extension
        if definition.storage.relational is None:
            raise authority.AuthorityManagementError("relational_declaration_required")
        request = {
            "package_id": package_id,
            "artifact_sha256": artifact_sha256,
            "expected_current_artifact_sha256": old_digest,
            "source_recovery_id": source_id,
            "expected_recovery_revision": revision,
        }
        with manager._write(
            installation_id, actor_token, request_id, OPERATION, request
        ) as (db, key, mutation, actor, result):
            if result:
                return result  # Historical metadata receipt only; no effects/reissue.
            current = read_application_authority(db, installation_id)
            installed = db.get(Installation, installation_id, populate_existing=True)
            pin = sources._package_pin(db, installation_id)
            current_target = db.execute(
                select(
                    ModulePackage.module_id, ModulePackage.version, ModulePackage.sha256
                ).where(ModulePackage.id == package_id)
            ).one_or_none()
            if (
                pin != prepared[0]
                or pin.sha256 != old_digest
                or pin.active_version != pin.version
                or installed.enabled
                or installed.status != "disabled"
                or current.mode != "review_required"
                or target != current_target
                or target.module_id != current.module_id
                or _version_key(target.version) <= _version_key(pin.version)
                or definition.storage.schema_revision
                == prepared[1].application_extension.storage.schema_revision
                or db.scalar(
                    select(func.count())
                    .select_from(Action)
                    .where(Action.installation_id == installation_id)
                )
                > MAX_PREPARATION_ACTIONS - 2
            ):
                raise authority.AuthorityManagementError("candidate_binding_changed")
            stopped_row, stopped, start_row, start, stop_ticket = _stop_source(
                db,
                key,
                installation_id,
                prepared,
                mutation.guard.generation,
                source_id,
                revision,
            )
            configuration = sources._configuration(db, installation_id, prepared[1])
            resolved = resolve_application_configuration(
                package.manifest.configuration_schema,
                {},
                definition,
                existing=configuration,
            )
            if _canonical_bytes(resolved) != _canonical_bytes(configuration):
                raise authority.AuthorityManagementError(
                    "candidate_configuration_changed"
                )
            invalidate_commands(db, installation_id)
            mutation.set_application_mode(current, "review_required")
            installed.previous_package_id = pin.module_package_id
            installed.module_package_id = package_id
            installed.active_version = None
            installed.socket_path = "pending"
            installed.activated_at = installed.health_checked_at = None
            installed.error = None
            db.flush()
            new_pin = db.execute(
                select(
                    ModulePackage.id.label("module_package_id"),
                    ModulePackage.version,
                    ModulePackage.sha256,
                ).where(ModulePackage.id == package_id)
            ).one()
            identifier = registration.candidate_registration_id(
                db, installation_id, new_pin
            )
            if identifier == request_id or db.get(Action, identifier) is not None:
                raise authority.AuthorityManagementError("candidate_already_adopted")
            authority._save(
                db,
                key,
                "action",
                Action(request_id=identifier, installation_id=installation_id),
                authority._envelope(
                    "action",
                    identifier,
                    installation_id,
                    "candidate_not_started",
                    {
                        "operation": OPERATION,
                        "actor": actor,
                        "binding": registration._binding(
                            db, key, installation_id, new_pin, package
                        ),
                        "previous_package_id": pin.module_package_id,
                        "previous_artifact_sha256": old_digest,
                        "source_recovery_id": source_id,
                        "source_recovery_revision": revision,
                        "adoption_request_id": request_id,
                    },
                ),
            )
            # Preserve old ticket/outcome/receipt bytes and fence old callbacks.
            for saved_row, saved in ((stopped_row, stopped), (start_row, start)):
                saved["data"]["candidate_adoption_id"] = request_id
                saved["revision"] = authority.new_authority_generation()
                authority._save(db, key, "action", saved_row, saved)
            manager._subject(
                db,
                key,
                installation_id,
                (sources._package_pin(db, installation_id), package),
            )
            result.update(
                installation_id=installation_id,
                registration_id=identifier,
                artifact_sha256=artifact_sha256,
                previous_artifact_sha256=old_digest,
                source_preparation_id=stop_ticket["source_preparation_id"],
                status="candidate_not_started",
                active_version=None,
                permission_approval="not_evaluated",
            )
        return result
    except authority.AuthorityManagementError:
        raise
    except (
        SQLAlchemyError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RuntimeError,
        zipfile.BadZipFile,
        zlib.error,
    ):
        raise authority.AuthorityManagementError("candidate_unavailable") from None
