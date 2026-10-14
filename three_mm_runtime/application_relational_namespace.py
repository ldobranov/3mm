"""Explicit root-only fresh namespace setup; not an installation endpoint.

No SQL, package imports, account creation, activation or automatic recovery.
Uses the existing Core preparation journal and release/runtime mutation locks.
Partial creation/unknown completion retains evidence and is never retried.
Reviewed-native lifecycle boundary, not hostile native-code isolation.
"""

import hashlib
import os
import stat
from pathlib import Path

from backend.services.application_configuration import resolve_application_configuration
from backend.services.module_packages import MAX_PACKAGE_BYTES, validate_module_package
from three_mm_application_sdk.relational_wire import (
    _RelationalNamespacePreparationResult,
    _RelationalNamespacePreparationTicket,
    canonical,
    profile_digest,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import (
    SystemdApplicationSupervisor,
    _set_owner,
    _stop_for_data,
    _write_atomic,
    application_instance_id,
)
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_preparation import (
    RelationalPreparationError,
    _live,
)
from three_mm_runtime.application_relational_session import (
    _protected_directory,
    _regular,
)


def _roots(paths, coordinator_uid):
    """Trusted local paths: no symlink/service-owned writable ancestry."""
    paths = tuple(Path(path).absolute() for path in paths)
    for path in paths:
        _protected_directory(path)
        for parent in path.parents:
            info = parent.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid not in {0, coordinator_uid}
                or (
                    info.st_mode & 0o022
                    and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)
                )
            ):
                raise ValueError("Namespace ancestry is not protected")
    paths = tuple(path.resolve(strict=True) for path in paths)
    if any(
        first.is_relative_to(second)
        for index, first in enumerate(paths)
        for other, second in enumerate(paths)
        if index != other
    ):
        raise ValueError("Namespace roots must be distinct and disjoint")
    return paths


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _exclusive_file(path, content, mode, gid):
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        mode,
    )
    with os.fdopen(fd, "wb") as stream:
        os.fchown(stream.fileno(), 0, gid)
        os.fchmod(stream.fileno(), mode)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


def _validate_dependencies(
    package_path,
    ticket,
    *,
    configuration,
    transport_secret,
    service_uid,
    service_gid,
    coordinator_uid,
):
    """Exact package and trusted local principals, shared by bootstrap recovery."""
    if (
        type(service_uid) is not int
        or type(service_gid) is not int
        or type(coordinator_uid) is not int
        or coordinator_uid != ticket["coordinator_uid"]
        or (service_uid, service_gid) != (ticket["service_uid"], ticket["service_gid"])
        or hashlib.sha256(transport_secret).hexdigest()
        != ticket["transport_key_sha256"]
    ):
        raise RelationalPreparationError("Namespace helper dependencies changed")
    package_path = Path(package_path)
    if _regular(package_path).st_size > MAX_PACKAGE_BYTES:
        raise RelationalPreparationError("Namespace package too large")
    blob = package_path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != ticket["package_sha256"]:
        raise RelationalPreparationError("Namespace artifact changed")
    validated = validate_module_package(blob)
    definition = validated.application_extension
    if definition is None or definition.storage.relational is None:
        raise RelationalPreparationError("Relational declaration unavailable")
    configuration = resolve_application_configuration(
        validated.manifest.configuration_schema,
        validated.manifest.configuration_defaults,
        definition,
        overrides=configuration,
    )
    expected = {
        "instance_id": application_instance_id(definition.module_id),
        "service_sha256": definition.service.artifact_sha256,
        "configuration_sha256": hashlib.sha256(canonical(configuration)).hexdigest(),
        "profile_sha256": profile_digest(
            definition.storage.relational, definition.storage.schema_revision
        ),
        "schema_revision": definition.storage.schema_revision,
    }
    if any(ticket[name] != value for name, value in expected.items()):
        raise RelationalPreparationError("Namespace identity changed")
    return validated, configuration


def create_fresh_relational_namespace(
    package_path,
    ticket,
    *,
    configuration,
    transport_secret,
    root,
    key_root,
    state_root,
    service_uid,
    service_gid,
    coordinator_uid,
    checkpoint,
    supervisor=None,
):
    """Create only an absent own namespace/key under separately confirmed consent.

    A fresh per-instance secret is supplied by the trusted local coordinator,
    never by a manifest, HTTP payload or service. Existing paths/keys/markers are
    refused, not repaired or replaced. Success stays disabled, with no active
    metadata or database. Business migrations need their own fresh human ticket.
    """
    if os.name != "posix" or os.geteuid() != 0 or not callable(checkpoint):
        raise RelationalPreparationError("Protected namespace helper unavailable")
    ticket = _RelationalNamespacePreparationTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    verify_metadata(transport_secret, "namespace_preparation", ticket)
    _validate_dependencies(
        package_path,
        ticket,
        configuration=configuration,
        transport_secret=transport_secret,
        service_uid=service_uid,
        service_gid=service_gid,
        coordinator_uid=coordinator_uid,
    )
    # Validate before creating even the helper lock file under these roots, then
    # recheck while serialized. Roots are trusted local dependencies, not payload.
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    with _release_lock(), _runtime_lock(state_root):
        root, key_root, state_root = _roots(
            (root, key_root, state_root), coordinator_uid
        )
        instance = root / ticket["instance_id"]
        key_path = key_root / (ticket["instance_id"] + ".key")
        marker = state_root / (
            "relational-namespace-" + ticket["instance_id"] + ".json"
        )
        if any(os.path.lexists(path) for path in (instance, key_path, marker)):
            raise RelationalPreparationError(
                "Namespace already exists or requires recovery"
            )
        _live(ticket)
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise RelationalPreparationError("Namespace authorization unavailable")
        _stop_for_data(
            supervisor or SystemdApplicationSupervisor(), ticket["instance_id"]
        )
        if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
            raise RelationalPreparationError("Namespace begin unavailable")
        # No secret bytes in either evidence file. A lost begin ACK causes no
        # filesystem effects; Core still consumes it. Never erase partial state
        # after creation starts, including a lost finish ACK.
        evidence = {
            "schema_version": 1,
            "operation": ticket["action"],
            "preparation_id": ticket["preparation_id"],
            "ticket_sha256": hashlib.sha256(canonical(ticket)).hexdigest(),
            "phase": "creation_unconfirmed",
        }
        try:
            _exclusive_file(marker, canonical(evidence), 0o600, 0)
            instance.mkdir(mode=0o750)
            instance.chmod(0o750)
            _set_owner(instance, 0, service_gid)
            rollback = instance / (
                ".activation-" + ticket["preparation_id"] + ".rollback"
            )
            rollback.mkdir(mode=0o700)
            _write_atomic(rollback / "activation.json", canonical(evidence), 0o600)
            for name, uid in (
                ("releases", 0),
                ("data", service_uid),
                ("run", service_uid),
            ):
                path = instance / name
                path.mkdir(mode=0o750)
                path.chmod(0o750)
                _set_owner(path, uid, service_gid)
            _exclusive_file(key_path, transport_secret, 0o640, service_gid)
            _sync_directory(instance)
            _sync_directory(root)
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Namespace publication authority unavailable")
            _live(ticket)
            _protected_directory(instance)
            for name, uid in (
                ("releases", 0),
                ("data", service_uid),
                ("run", service_uid),
            ):
                path = instance / name
                info = path.lstat()
                if (
                    not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != uid
                    or info.st_gid != service_gid
                    or stat.S_IMODE(info.st_mode) != 0o750
                    or any(path.iterdir())
                ):
                    raise ValueError("Fresh namespace changed")
            info = _regular(key_path, protected=True)
            if (
                info.st_gid != service_gid
                or stat.S_IMODE(info.st_mode) != 0o640
                or info.st_size != 32
                or key_path.read_bytes() != transport_secret
            ):
                raise ValueError("Namespace key changed")
            if set(path.name for path in instance.iterdir()) != {
                "releases",
                "data",
                "run",
                rollback.name,
            }:
                raise ValueError("Unexpected namespace metadata")
            result = _RelationalNamespacePreparationResult.model_validate(
                sign_metadata(
                    transport_secret,
                    "namespace_preparation_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "ticket_sha256": evidence["ticket_sha256"],
                        "outcome": "namespace_created_not_started",
                    },
                )
            ).model_dump(mode="json")
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "namespace_created_not_started"
            }:
                raise ValueError("Namespace completion unconfirmed")
            _write_atomic(
                marker,
                canonical(
                    dict(
                        evidence, phase="namespace_created_not_started", receipt=result
                    )
                ),
                0o600,
            )
            # Remove only our exact, confirmed checkpoint, never namespace/key.
            (rollback / "activation.json").unlink()
            rollback.rmdir()
            _sync_directory(instance)
            return result
        except Exception as exc:
            raise RelationalPreparationError(
                "Namespace creation incomplete; preserve evidence for recovery review"
            ) from exc
