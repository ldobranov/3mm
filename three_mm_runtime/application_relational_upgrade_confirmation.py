"""Root readonly confirmation of a fully published prepared-database upgrade.

Never imports package code, changes SQL/lineage/keys or restores a preimage.
Unknown/partial checkpoints remain blocking. Archive only exact known evidence
after a separate durable Core confirmation, without service enable/restart.
"""

import hashlib
import os
import stat
from pathlib import Path

from backend.services.application_configuration import resolve_application_configuration
from three_mm_application_sdk.relational_receipts import (
    MAX_COMMIT_RECEIPTS,
    _RelationalReceiptStore,
)
from three_mm_application_sdk.relational_upgrade_receipts import (
    validate_upgrade_history,
)
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeConfirmationTicket,
    _RelationalUpgradeResult,
    _RelationalUpgradeTicket,
    upgraded_lifecycle,
)
from three_mm_application_sdk.relational_wire import (
    canonical,
    profile_digest,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import (
    SystemdApplicationSupervisor,
    _stop_for_data,
    _write_atomic,
    application_instance_id,
)
from three_mm_runtime.application_database_snapshot import _preimage, _sync_directory
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_boot_policy import require_no_boot_gate
from three_mm_runtime.application_relational_preparation import _auxiliary, _key, _live
from three_mm_runtime.application_relational_recovery import _recovery_connection
from three_mm_runtime.application_relational_recovery_confirmation import (
    MAX_CONFIRMATION_MARKERS,
    _files_preimage,
    _json,
    _record,
    _snapshot_connection,
)
from three_mm_runtime.application_relational_session import (
    _protected_directory,
    _regular,
)
from three_mm_runtime.application_relational_upgrade import (
    RelationalUpgradeError,
    _metadata,
    _package,
)

BINDING_FIELDS = (
    "database_lineage",
    "instance_id",
    "owner_sha256",
    "package_sha256",
    "service_sha256",
    "configuration_sha256",
    "profile_sha256",
    "schema_revision",
    "recovery_generation",
    "transport_key_sha256",
)
STABLE_FIELDS = (
    "source_upgrade_id",
    "source_ticket_sha256",
    "published_lifecycle_sha256",
    *BINDING_FIELDS,
    "grant_record_revision",
    "binding_sha256",
)


def _markers(instance, ticket, source, secret):
    pending = []
    for pattern in (".activation-*.rollback", ".database-*.rollback"):
        for path in instance.glob(pattern):
            pending.append(path)
            if len(pending) >= MAX_CONFIRMATION_MARKERS:
                raise ValueError("Upgrade confirmation checkpoint budget exceeded")
    original = instance / (".database-" + source["preparation_id"] + ".rollback")
    archived = instance / (".upgrade-evidence-" + source["preparation_id"])
    if os.path.lexists(original) == os.path.lexists(archived):
        raise ValueError("Upgrade evidence unavailable or archive collision")
    evidence = original if os.path.lexists(original) else archived
    _protected_directory(evidence)
    value = _json(evidence / "upgrade.json")
    if (
        type(value) is not dict
        or type(value.get("version")) is not int
        or value
        not in [
            {"version": 1, "ticket": source, "phase": phase}
            for phase in ("completion_unconfirmed", "upgraded_not_started")
        ]
    ):
        raise ValueError("Upgrade publication requires separate recovery")
    # Dict equality alone treats True and 1 as equal. Decode the embedded
    # historical ticket strictly as well; malformed protected evidence is not
    # confirmation authority even if its coerced values happen to compare equal.
    proof_ticket = _RelationalUpgradeTicket.model_validate(value["ticket"]).model_dump(
        mode="json"
    )
    verify_metadata(secret, "database_upgrade", proof_ticket)
    for path in pending:
        if path == original:
            continue
        _protected_directory(path)
        proof = _json(path / "upgrade-confirmation.json")
        if (
            type(proof) is not dict
            or set(proof) != {"version", "ticket", "phase"}
            or type(proof["version"]) is not int
            or proof["version"] != 1
            or proof["phase"]
            not in {"checking", "completion_unconfirmed", "upgraded_not_started"}
        ):
            raise ValueError("Unknown upgrade confirmation checkpoint")
        old = _RelationalUpgradeConfirmationTicket.model_validate(
            proof["ticket"]
        ).model_dump(mode="json")
        verify_metadata(secret, "database_upgrade_confirmation", old)
        if path.name != ".database-" + old["preparation_id"] + ".rollback" or any(
            old[name] != ticket[name] for name in STABLE_FIELDS
        ):
            raise ValueError("Foreign upgrade confirmation checkpoint")
    return pending, evidence


def _wheel(instance, package, digest):
    path = instance / "releases" / package / "service.whl"
    _protected_directory(path.parent)
    _regular(path, protected=True)
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise ValueError("Upgrade confirmation wheel changed")


def _history(connection, lineage, revision, secret):
    _RelationalReceiptStore(
        database_lineage=lineage, schema_revision=revision, secret=secret
    )._validate(connection)
    validate_upgrade_history(connection, schema_revision=revision, secret=secret)
    rows = connection.execute(
        "SELECT substr(transaction_id,1,33), substr(payload,1,2049) "
        "FROM three_mm_relational_commits ORDER BY transaction_id LIMIT ?",
        (MAX_COMMIT_RECEIPTS + 1,),
    ).fetchall()
    history = connection.execute(
        "SELECT substr(revision,1,65) FROM three_mm_schema_migrations ORDER BY rowid LIMIT 129"
    ).fetchall()
    return hashlib.sha256(canonical(rows)).hexdigest(), history


def _preimage_metadata(instance, evidence, package, source, secret, root):
    previous = _record(evidence / "previous-relational.json", secret)
    active = _json(evidence / "previous-active.json", 131072)
    definition = package.application_extension
    configuration = resolve_application_configuration(
        package.manifest.configuration_schema,
        package.manifest.configuration_defaults,
        definition,
        overrides=active.get("configuration"),
    )
    if (
        hashlib.sha256(canonical(previous)).hexdigest()
        != source["source_lifecycle_sha256"]
        or previous["lifecycle_id"] != source["source_preparation_id"]
        or any(
            previous[name] != source[name]
            for name in ("instance_id", "owner_sha256", "recovery_generation")
        )
        or any(
            previous[name] != source["source_" + name]
            for name in (
                "package_sha256",
                "service_sha256",
                "configuration_sha256",
                "profile_sha256",
                "schema_revision",
                "database_lineage",
            )
        )
        or active != _metadata(package, configuration, instance, root)
        or hashlib.sha256(canonical(configuration)).hexdigest()
        != source["source_configuration_sha256"]
        or definition.service.artifact_sha256 != source["source_service_sha256"]
        or definition.storage.schema_revision != source["source_schema_revision"]
        or profile_digest(
            definition.storage.relational, definition.storage.schema_revision
        )
        != source["source_profile_sha256"]
    ):
        raise ValueError("Upgrade preimage publication changed")


def confirm_published_relational_upgrade(
    source_package_path,
    package_path,
    ticket,
    source_ticket,
    *,
    configuration,
    root,
    key_root,
    state_root,
    service_uid,
    service_gid,
    checkpoint,
    supervisor=None,
):
    """Trusted helper parameters only; no application-selected paths or callbacks."""
    if (
        os.name != "posix"
        or os.geteuid() != 0
        or not callable(checkpoint)
        or type(service_uid) is not int
        or service_uid <= 0
        or type(service_gid) is not int
        or service_gid <= 0
    ):
        raise RelationalUpgradeError("Protected upgrade confirmation unavailable")
    ticket = _RelationalUpgradeConfirmationTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    source = _RelationalUpgradeTicket.model_validate(source_ticket).model_dump(
        mode="json"
    )
    root, key_root, state_root = map(Path, (root, key_root, state_root))
    previous_package, _ = _package(source_package_path, source["source_package_sha256"])
    target, _ = _package(package_path, ticket["package_sha256"])
    definition = target.application_extension
    configuration = resolve_application_configuration(
        target.manifest.configuration_schema,
        target.manifest.configuration_defaults,
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
    if previous_package.application_extension.module_id != definition.module_id or any(
        ticket[name] != value for name, value in expected.items()
    ):
        raise ValueError("Upgrade confirmation candidate changed")
    instance = root / ticket["instance_id"]
    database = instance / "data" / "state.sqlite3"
    key_path = key_root / (instance.name + ".key")
    selected = supervisor or SystemdApplicationSupervisor()
    with _release_lock(), _runtime_lock(state_root):
        for path in (root, instance, instance / "releases", key_root):
            _protected_directory(path)
        for path in (instance / "data", instance / "run"):
            info = path.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != service_uid
                or info.st_mode & 0o022
            ):
                raise ValueError("Upgrade confirmation namespace changed")
        require_no_boot_gate(instance)
        secret = _key(key_path)
        verify_metadata(secret, "database_upgrade_confirmation", ticket)
        verify_metadata(secret, "database_upgrade", source)
        record = upgraded_lifecycle(source, secret)
        if (
            ticket["transport_key_sha256"] != hashlib.sha256(secret).hexdigest()
            or ticket["source_upgrade_id"] != source["preparation_id"]
            or ticket["source_ticket_sha256"]
            != hashlib.sha256(canonical(source)).hexdigest()
            or ticket["published_lifecycle_sha256"]
            != hashlib.sha256(canonical(record)).hexdigest()
            or any(ticket[name] != source[name] for name in BINDING_FIELDS)
        ):
            raise ValueError("Upgrade confirmation source changed")
        _live(ticket)
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise ValueError("Core upgrade confirmation authorization unavailable")
        pending, evidence = _markers(instance, ticket, source, secret)
        if not pending:
            raise ValueError("No interrupted upgrade requires confirmation")
        marker = instance / (".database-" + ticket["preparation_id"] + ".rollback")
        marker.mkdir(mode=0o700)

        def phase(value):
            _write_atomic(
                marker / "upgrade-confirmation.json",
                canonical({"version": 1, "ticket": ticket, "phase": value}),
                0o600,
                uid=0,
                gid=0,
            )

        phase("checking")
        try:
            _stop_for_data(selected, instance.name)
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core upgrade confirmation begin unavailable")
            if (
                _json(instance / "active.json", 131072)
                != _metadata(target, configuration, instance, root)
                or _record(instance / "relational.json", secret) != record
            ):
                raise ValueError("Upgrade confirmation publication incomplete")
            _wheel(instance, ticket["package_sha256"], ticket["service_sha256"])
            _wheel(
                instance,
                source["source_package_sha256"],
                source["source_service_sha256"],
            )
            _preimage_metadata(
                instance, evidence, previous_package, source, secret, root
            )
            _files_preimage(evidence)
            if _regular(database).st_uid != service_uid:
                raise ValueError("Upgrade confirmation database owner changed")
            _auxiliary(database, definition.storage.relational)
            preimage = evidence / "state.sqlite3"
            _regular(evidence / "database.json", protected=True)
            if (
                _regular(preimage, protected=True).st_size
                > previous_package.application_extension.storage.relational.max_database_bytes
            ):
                raise ValueError("Upgrade confirmation preimage exceeds profile")
            _preimage(preimage, True)
            histories = []
            for path, lineage, revision in (
                (
                    preimage,
                    source["source_database_lineage"],
                    source["source_schema_revision"],
                ),
                (database, ticket["database_lineage"], ticket["schema_revision"]),
            ):
                connection = (
                    _snapshot_connection(preimage, ticket)
                    if path == preimage
                    else _recovery_connection(
                        database, ticket, definition.storage.relational, write=False
                    )
                )
                try:
                    connection.execute("BEGIN")
                    histories.append(_history(connection, lineage, revision, secret))
                finally:
                    connection.close()
            old_receipts, old_history = histories[0]
            receipts, history = histories[1]
            if (
                old_receipts != receipts
                or history[: len(old_history)] != old_history
                or len(history) <= len(old_history)
            ):
                raise ValueError("Upgrade confirmation historical evidence changed")
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core upgrade confirmation changed")
            if _key(key_path) != secret:
                raise ValueError("Upgrade confirmation key changed")
            _live(ticket)
            result = _RelationalUpgradeResult.model_validate(
                sign_metadata(
                    secret,
                    "database_upgrade_confirmation_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "lifecycle_sha256": ticket["published_lifecycle_sha256"],
                        "outcome": "upgraded_not_started",
                    },
                )
            ).model_dump(mode="json")
            phase("completion_unconfirmed")
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "upgraded_not_started"
            }:
                raise ValueError("Core upgrade confirmation completion unconfirmed")
            if _key(key_path) != secret:
                raise ValueError("Upgrade confirmation key changed before archive")
            _live(ticket)
            phase("upgraded_not_started")
            for path in (*pending, marker):
                destination = instance / (
                    ".upgrade-evidence-" + source["preparation_id"]
                    if path.name
                    == ".database-" + source["preparation_id"] + ".rollback"
                    else ".upgrade-confirmation-evidence-"
                    + path.name.removeprefix(".database-").removesuffix(".rollback")
                )
                if os.path.lexists(destination):
                    raise ValueError("Upgrade confirmation archive already exists")
                path.rename(destination)
                _sync_directory(instance)
            return result
        except Exception as error:
            raise RelationalUpgradeError(
                "Upgrade confirmation incomplete; evidence retained, explicit review required"
            ) from error
