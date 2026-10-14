"""Private pre-import admission for Root-managed boot, not a grant/start writer.

Root publication + Core-sealed confirmed boot setting + CURRENT trust/rights are
all required. Historical enable tickets are never renewed/replayed. A fresh
one-use permit binds this kernel process/host nonce/current boot for five seconds.
No package imports, application SQL, Root files or host IPC under Core leases.
"""

import hashlib
import os
from pathlib import Path

from sqlalchemy import func, select, update

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.user import User
from backend.services import application_authority_management as authority
from backend.services import application_relational_boot as boot
from backend.services import application_relational_lifecycle as preparation
from backend.services.application_files import _clean_session
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalBootStartupPermit,
    canonical,
    sign_metadata,
)
from three_mm_runtime.application_relational_boot_policy import read_boot_policy
from three_mm_runtime.application_relational_session import _call_host_metadata

OPERATION = "relational_boot_startup"


class RelationalStartupError(ValueError):
    def __init__(self):
        super().__init__("Relational boot startup authority unavailable; do not retry")


def _process(peer):
    if (
        os.name != "posix"
        or type(peer) is not tuple
        or len(peer) != 3
        or any(type(value) is not int or not 0 < value <= 2147483647 for value in peer)
    ):
        raise RelationalStartupError()
    pid, uid, gid = peer
    fields = (
        Path(f"/proc/{pid}/stat")
        .read_text(encoding="ascii")
        .rpartition(") ")[2]
        .split()
    )
    if len(fields) < 20 or not 0 < int(fields[19]) <= 9007199254740990:
        raise RelationalStartupError()
    return pid, uid, gid, int(fields[19])


def admit_boot_startup(
    db,
    installation_id,
    runtime_nonce,
    *,
    transport_secret,
    runtime_root,
    peer_credentials,
):
    """Only the existing platform server supplies trusted root and SO_PEERCRED.

    No human token at unattended boot: the setting is durable consent, not a
    session replay. Its author must still be an unblocked Core administrator;
    native trust and the independently applied exact grant must still be current.
    Lost replies consume the nonce and never authorize an import by retry.
    """
    try:
        requested = authority._identifier(runtime_nonce)
        process = _process(peer_credentials)
        if (
            type(transport_secret) is not bytes
            or len(transport_secret) != 32
            or not Path(runtime_root).is_absolute()
        ):
            raise RelationalStartupError()
        _clean_session(db)
        installation = db.get(Installation, installation_id, populate_existing=True)
        if (
            installation is None
            or not installation.enabled
            or installation.status != "active"
        ):
            raise RelationalStartupError()
        instance_id = installation.instance_id
        if (
            type(instance_id) is not str
            or len(instance_id) != 24
            or any(ch not in "0123456789abcdef" for ch in instance_id)
        ):
            raise RelationalStartupError()
        instance = Path(runtime_root) / instance_id
        db.rollback()  # End routing snapshot before ANY protected file or host I/O.
        policy = read_boot_policy(instance, transport_secret)
        ticket = policy["ticket"]
        if peer_credentials[1:] != (ticket["service_uid"], ticket["service_gid"]):
            raise RelationalStartupError()
        hello = _call_host_metadata(
            instance / "run/relational.sock",
            transport_secret,
            expected_peer=peer_credentials,
        )
        manager = authority.configured_manager(db.get_bind().engine)
        prepared = manager._prepare(installation_id)  # ZIP validation outside lease.
        if _process(peer_credentials) != process:
            raise RelationalStartupError()
        with manager.keys.locked() as key, authority_transaction(db) as mutation:
            bindings = boot._current(
                manager,
                db,
                key,
                installation_id,
                prepared,
                mutation.guard.generation,
                runtime_root,
            )
            row = db.get(Action, ticket["preparation_id"], populate_existing=True)
            setting = authority._load(db, key, "action", row, ticket["preparation_id"])
            _, source, original = boot._source(
                db,
                key,
                installation_id,
                ticket["source_activation_id"],
                transport_secret,
                bindings,
                reserved=ticket["preparation_id"],
            )
            current_boot, now = authority._clock()
            record = hello["lifecycle"]
            if (
                setting["installation_id"] != installation_id
                or setting["state"] != "confirmed"
                or setting["data"]["operation"] != boot.OPERATION
                or setting["data"]["result"]["ticket"] != ticket
                or setting["data"]["receipt"] != policy["receipt"]
                or source["revision"] != ticket["source_activation_revision"]
                or original["action"] != ticket["source_activation_action"]
                or hashlib.sha256(canonical(original)).hexdigest()
                != ticket["source_ticket_sha256"]
                or hashlib.sha256(canonical(source["data"]["receipt"])).hexdigest()
                != ticket["source_receipt_sha256"]
                or any(ticket[name] != value for name, value in bindings.items())
                or hello["runtime_nonce"] != requested
                or hello["boot_id"] != current_boot
                or not 0 <= now - hello["clock_ms"] <= 2000
                or hello["invocation"] is not None
                or hashlib.sha256(canonical(record)).hexdigest()
                != ticket["prepared_lifecycle_sha256"]
                or record["database_lineage"] != ticket["database_lineage"]
                or record["lifecycle_id"] != ticket["source_preparation_id"]
                or record["instance_id"] != instance_id
                or db.get(Action, requested) is not None
                or db.scalar(
                    select(func.count())
                    .select_from(Action)
                    .where(Action.installation_id == installation_id)
                )
                >= preparation.MAX_PREPARATION_ACTIONS
            ):
                raise RelationalStartupError()
            # Durable author attribution, NOT token/session resurrection. Lock
            # the current account before application, as the local writer does.
            actor = setting["data"]["actor"]
            if type(actor) is not list or len(actor) != 3 or type(actor[0]) is not int:
                raise RelationalStartupError()
            if (
                db.execute(
                    update(User)
                    .where(
                        User.id == actor[0],
                        User.role == "admin",
                        User.is_blocked.is_(False),
                    )
                    .values(token_version=User.token_version)
                    .execution_options(synchronize_session=False)
                ).rowcount
                != 1
            ):
                raise RelationalStartupError()
            mutation.lock_application(read_application_authority(db, installation_id))
            permit = _RelationalBootStartupPermit.model_validate(
                sign_metadata(
                    transport_secret,
                    "boot_startup",
                    {
                        "version": 1,
                        "action": "boot_startup",
                        "instance_id": instance_id,
                        "runtime_nonce": requested,
                        "boot_enable_id": ticket["preparation_id"],
                        "policy_sha256": hashlib.sha256(canonical(policy)).hexdigest(),
                        "lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
                        "authority_epoch": bindings["authority_epoch"],
                        "recovery_generation": bindings["recovery_generation"],
                        "grant_record_revision": bindings["grant_record_revision"],
                        "process_pid": process[0],
                        "service_uid": process[1],
                        "service_gid": process[2],
                        "process_start_ticks": process[3],
                        "boot_id": current_boot,
                        "issued_at_ms": now,
                        "deadline_ms": now + 5000,
                    },
                )
            ).model_dump(mode="json")
            authority._save(
                db,
                key,
                "action",
                Action(request_id=requested, installation_id=installation_id),
                authority._envelope(
                    "action",
                    requested,
                    installation_id,
                    "admitted",
                    {
                        "operation": OPERATION,
                        "actor": ["host", str(installation_id)],
                        "boot_enable_id": ticket["preparation_id"],
                        "permit": permit,
                    },
                ),
            )
            db.add(
                AuditLog(
                    user_id=actor[0],
                    action="APPLICATION_BOOT_STARTUP_ADMITTED",
                    entity_type="application_extension",
                    entity_name=prepared[0].module_id,
                    changes={
                        "runtime_nonce": requested,
                        "boot_enable_id": ticket["preparation_id"],
                        "process_pid": process[0],
                    },
                )
            )
            mutation.advance_guard_revision()
        return permit
    except Exception:
        db.rollback()
        raise RelationalStartupError() from None
