"""Private two-consent first preparation, not a public install/enable endpoint.

The trusted root coordinator generates and durably hands off a fresh instance
key. Namespace completion precedes separate current Core migration authority.
Failure never retries SQL, repairs keys, activates or erases recovery evidence.
"""

import hashlib
import os
import secrets
import stat

from three_mm_application_sdk.relational_wire import (
    _RelationalMigrationPreparationTicket,
    _RelationalNamespacePreparationTicket,
    verify_metadata,
)
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_migrations import (
    require_migration_worker_privileges,
)
from three_mm_runtime.application_relational_namespace import (
    _exclusive_file,
    _roots,
    _validate_dependencies,
    create_fresh_relational_namespace,
)
from three_mm_runtime.application_relational_preparation import (
    RelationalPreparationError,
    prepare_migrated_relational_database,
)
from three_mm_runtime.application_relational_session import (
    _protected_directory,
    _regular,
)

MAX_HANDOFF_KEYS = 32
CONTINUITY = (
    "instance_id",
    "owner_sha256",
    "package_sha256",
    "service_sha256",
    "configuration_sha256",
    "profile_sha256",
    "schema_revision",
    "grant_record_revision",
    "binding_sha256",
    "authority_epoch",
    "recovery_generation",
)


def _handoff_path(state_root, source):
    return state_root / (
        "namespace-key-"
        + source["instance_id"]
        + "-"
        + source["preparation_id"]
        + ".key"
    )


def _read_bootstrap_secret(state_root, source_ticket):
    """Root-only recovery dependency; never a service/HTTP key retrieval contract."""
    if os.name != "posix" or os.geteuid() != 0:
        raise RelationalPreparationError("Protected bootstrap key unavailable")
    from pathlib import Path

    state_root = Path(state_root)
    _protected_directory(state_root)
    source = _RelationalNamespacePreparationTicket.model_validate(
        source_ticket
    ).model_dump(mode="json")
    path = _handoff_path(state_root, source)
    info = _regular(path, protected=True)
    if info.st_size != 32 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_gid != 0:
        raise ValueError("Bootstrap key handoff changed")
    secret = path.read_bytes()
    verify_metadata(secret, "namespace_preparation", source)
    if hashlib.sha256(secret).hexdigest() != source["transport_key_sha256"]:
        raise ValueError("Bootstrap key binding changed")
    return secret


def prepare_fresh_relational_installation(
    package_path,
    *,
    configuration,
    root,
    key_root,
    state_root,
    service_uid,
    service_gid,
    coordinator_uid,
    confirm_fresh_owned_namespace,
    confirm_owned_business_migrations,
    issue_namespace,
    issue_migration,
    checkpoint,
    supervisor=None,
):
    """Prepare once from absence; explicit enable remains a separate operation.

    Issuers/checkpoint are trusted Core adapters closing leases before helper
    I/O, not callbacks supplied by a package. They must use the same local human
    and exact expected grant revision. Caller-provided service/key/profile or
    changed current authority cannot silently become a new consent mid-flow.
    Account provisioning is outside this private entrypoint: fixed UID/GID are
    trusted local configuration, never manifest/HTTP fields.
    """
    if (
        os.name != "posix"
        or os.geteuid() != 0
        or confirm_fresh_owned_namespace is not True
        or confirm_owned_business_migrations is not True
        or not all(
            callable(value) for value in (issue_namespace, issue_migration, checkpoint)
        )
    ):
        raise RelationalPreparationError("Explicit fresh preparation unavailable")
    # A deployed root helper may lack UID-switch capabilities despite UID 0.
    # Fail before tickets, a fresh secret, handoff, namespace or key creation.
    require_migration_worker_privileges()
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    secret = secrets.token_bytes(32)
    source = _RelationalNamespacePreparationTicket.model_validate(
        issue_namespace(
            transport_secret=secret,
            request_id=secrets.token_hex(16),
        )
    ).model_dump(mode="json")
    verify_metadata(secret, "namespace_preparation", source)
    _validate_dependencies(
        package_path,
        source,
        configuration=configuration,
        transport_secret=secret,
        service_uid=service_uid,
        service_gid=service_gid,
        coordinator_uid=coordinator_uid,
    )
    with _release_lock(), _runtime_lock(state_root):
        root, key_root, state_root = _roots(
            (root, key_root, state_root), coordinator_uid
        )
        instance = root / source["instance_id"]
        if any(
            os.path.lexists(path)
            for path in (
                instance,
                key_root / (instance.name + ".key"),
                state_root / ("relational-namespace-" + instance.name + ".json"),
            )
        ):
            raise RelationalPreparationError(
                "First preparation requires absent namespace"
            )
        count = 0
        for _path in state_root.glob("namespace-key-" + instance.name + "-*.key"):
            count += 1
            if count >= MAX_HANDOFF_KEYS:
                raise RelationalPreparationError("Bootstrap key review budget exceeded")
        # fsync before creation begins; even a partial actual key write can be
        # reconciled later using exact protected source evidence and this key.
        _exclusive_file(_handoff_path(state_root, source), secret, 0o600, 0)
    if _read_bootstrap_secret(state_root, source) != secret:
        raise ValueError("Fresh bootstrap key changed")

    def current(value, phase, **kwargs):
        return checkpoint(value, phase, transport_secret=secret, **kwargs)

    namespace_result = create_fresh_relational_namespace(
        package_path,
        source,
        configuration=configuration,
        transport_secret=secret,
        root=root,
        key_root=key_root,
        state_root=state_root,
        service_uid=service_uid,
        service_gid=service_gid,
        coordinator_uid=coordinator_uid,
        checkpoint=current,
        supervisor=supervisor,
    )
    migration = _RelationalMigrationPreparationTicket.model_validate(
        issue_migration(
            transport_secret=secret,
            request_id=secrets.token_hex(16),
        )
    ).model_dump(mode="json")
    verify_metadata(secret, "migration_preparation", migration)
    if any(migration[name] != source[name] for name in CONTINUITY):
        raise RelationalPreparationError(
            "First preparation authority changed between consents"
        )
    if _read_bootstrap_secret(state_root, source) != secret:
        raise ValueError("Bootstrap handoff changed before migration")
    database_result = prepare_migrated_relational_database(
        package_path,
        migration,
        configuration=configuration,
        root=root,
        key_root=key_root,
        state_root=state_root,
        service_uid=service_uid,
        service_gid=service_gid,
        checkpoint=current,
        supervisor=supervisor,
    )
    # No secret bytes, activation, grant mutation or retry in this result.
    return {"namespace": namespace_result, "database": database_result}
