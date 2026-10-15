"""Fixed, explicitly authorized completion of a partially interrupted rollback.

Only called under the upgrade helper's locks after verified quiescence and Core
begin. Each human action gets NEW staging/evidence; never reuse partial stages,
run package code, erase candidates or infer a SQL transaction outcome.
"""

import os

from three_mm_application_sdk.relational_upgrade_wire import upgraded_lifecycle
from three_mm_application_sdk.relational_wire import canonical
from three_mm_runtime.application_activation import _write_atomic
from three_mm_runtime.application_database_snapshot import (
    _exclusive,
    _preimage,
    _sync_directory,
    restore_database,
)
from three_mm_runtime.application_files_snapshot import (
    capture_private_files,
    restore_private_files,
)
from three_mm_runtime.application_relational_recovery_confirmation import (
    _files_preimage,
    _json,
    _record,
)
from three_mm_runtime.application_relational_session import _regular
from three_mm_runtime.application_relational_upgrade import _metadata
from three_mm_runtime.application_relational_upgrade_confirmation import (
    _history,
    _preimage_metadata,
    _snapshot_connection,
    _wheel,
)


def _copy(source, destination, limit):
    if _regular(source, protected=True).st_size > limit:
        raise ValueError("Restore evidence exceeds budget")
    # Source is protected, regular/single-link and its enclosing Root directory
    # is verified by the caller. Stream bounded bytes, never load a database.
    _exclusive(destination)
    with source.open("rb") as reader, destination.open("wb") as writer:
        remaining = limit
        while chunk := reader.read(min(remaining + 1, 128 * 1024)):
            remaining -= len(chunk)
            if remaining < 0:
                raise ValueError("Restore evidence exceeds budget")
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())


def finish_partial_restore(
    instance,
    evidence,
    marker,
    source,
    previous,
    target,
    configuration,
    secret,
    *,
    root,
    service_uid,
    service_gid,
    check,
    ticket,
):
    """Restore exactly the original preimage, preserving ALL intermediate data.

    A new interruption leaves original phase 'restoring' and this attempt's
    marker. Fresh consent creates a different work directory. Orphan sidecars
    from a main-file detach are retained individually, not opened or discarded.
    """
    from three_mm_runtime.application_relational_upgrade_rollback import (
        record_completed_rollback,
    )

    old_profile = previous.application_extension.storage.relational
    target_profile = target.application_extension.storage.relational
    limit = old_profile.max_database_bytes
    snapshot = evidence / "state.sqlite3"
    _regular(evidence / "database.json", protected=True)
    if _regular(snapshot, protected=True).st_size > limit:
        raise ValueError("Restore preimage exceeds profile")
    _preimage(snapshot, True)
    _preimage_metadata(instance, evidence, previous, source, secret, root)
    _files_preimage(evidence)
    _wheel(instance, source["source_package_sha256"], source["source_service_sha256"])
    _wheel(instance, source["package_sha256"], source["service_sha256"])
    connection = _snapshot_connection(snapshot, ticket)
    try:
        connection.execute("BEGIN")
        _history(
            connection,
            source["source_database_lineage"],
            source["source_schema_revision"],
            secret,
        )
    finally:
        connection.close()

    # A split publication may contain old/new metadata or absence, not a third
    # installation/version. Validate before detaching any live namespace.
    for name, expected, current in (
        (
            "active.json",
            _json(evidence / "previous-active.json", 131072),
            _metadata(target, configuration, instance, root),
        ),
        (
            "relational.json",
            _record(evidence / "previous-relational.json", secret),
            upgraded_lifecycle(source, secret),
        ),
    ):
        path = instance / name
        if os.path.lexists(path):
            actual = (
                _record(path, secret)
                if name == "relational.json"
                else _json(path, 131072)
            )
            if canonical(actual) not in (canonical(expected), canonical(current)):
                raise ValueError("Partial restore publication changed")

    # Work is fresh even when the original restore already detached candidates
    # or staged bytes. Originals and earlier attempts are never overwritten.
    work = marker / "restore-work"
    work.mkdir(mode=0o700)
    _copy(snapshot, work / "state.sqlite3", limit)
    _copy(evidence / "database.json", work / "database.json", 1024)
    capture_private_files(evidence, work)
    _preimage(work / "state.sqlite3", True)
    _files_preimage(work)
    for name in ("active.json", "relational.json"):
        path = instance / name
        if os.path.lexists(path):
            _copy(path, work / ("partial-" + name), 131072)
    _copy(evidence / "upgrade.json", work / "original-upgrade.json", 16384)

    database = instance / "data/state.sqlite3"
    max_database = max(limit, target_profile.max_database_bytes)
    max_auxiliary = max(
        old_profile.auxiliary_pause_bytes, target_profile.auxiliary_pause_bytes
    )
    paths = [(database, max_database)] + [
        (database.with_name(database.name + suffix), max_auxiliary)
        for suffix in ("-wal", "-shm", "-journal")
    ]
    for path, maximum in paths:
        if os.path.lexists(path):
            info = _regular(path)
            if info.st_uid != service_uid or info.st_size > maximum:
                raise ValueError("Partial restore database namespace changed")
    check()  # Current human/grant/key/clock, before any live-data switch.
    restore_private_files(instance / "data", work, service_uid, service_gid)
    check()
    for path, _ in paths:
        if os.path.lexists(path):
            path.rename(work / ("partial-" + path.name))
            _sync_directory(database.parent)
            _sync_directory(work)
    restore_database(database, work / "state.sqlite3", True, service_uid, service_gid)
    check()
    for name in ("active.json", "relational.json"):
        _write_atomic(
            instance / name,
            (evidence / ("previous-" + name)).read_bytes(),
            0o640,
            uid=0,
            gid=service_gid,
        )
    check()
    # Preserve even an incomplete old witness instead of overwriting its proof.
    for name in ("restored-proof", "rollback-proof.json"):
        path = evidence / name
        if os.path.lexists(path):
            path.rename(work / ("previous-" + name))
            _sync_directory(evidence)
            _sync_directory(work)
    record_completed_rollback(instance, evidence, source, secret, database_limit=limit)
    _write_atomic(
        evidence / "upgrade.json",
        canonical(
            {
                "version": 1,
                "ticket": source,
                "phase": "restored_not_started",
            }
        ),
        0o600,
        uid=0,
        gid=0,
    )
