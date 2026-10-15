"""Root-only boot gate publication/readers; no grant or package execution.

The required marker precedes any enable. Pending/lost publication never falls
back to a manual prepared start. Only explicit verified-stop reconciliation may
archive these exact records; original enable/start witnesses remain unchanged.
"""

import hashlib
import os
import stat
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from three_mm_application_sdk.relational_wire import (
    _RelationalBootEnableResult,
    _RelationalBootEnableTicket,
    canonical,
    verify_metadata,
)
from three_mm_runtime.application_activation import _write_atomic
from three_mm_runtime.application_relational_namespace import (
    _exclusive_file,
    _sync_directory,
)
from three_mm_runtime.application_relational_session import (
    _decode,
    _protected_directory,
    _regular,
)

REQUIRED_NAME = "boot-required.json"
POLICY_NAME = "boot-authority.json"


class _BootPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    phase: Literal["boot_pending", "boot_confirmed"]
    ticket: _RelationalBootEnableTicket
    receipt: _RelationalBootEnableResult | None

    @model_validator(mode="after")
    def confirmed_receipt(self):
        if (self.phase == "boot_confirmed") != (self.receipt is not None):
            raise ValueError("Incomplete boot publication")
        return self


def boot_gate_present(instance):
    return any(
        os.path.lexists(Path(instance) / name) for name in (REQUIRED_NAME, POLICY_NAME)
    )


def require_no_boot_gate(instance):
    """Fence lineage/preparation helpers that cannot reconcile boot authority.

    Caller holds the Root mutation locks and validates protected parent paths.
    Even partial, malformed or dangling-link evidence is a gate, not absence.
    This neither disables a unit nor archives boot records: only the separate
    exact-source, verified-stop coordinator has that authority.
    """
    if boot_gate_present(instance):
        raise ValueError("Boot policy requires explicit stopped-boot reconciliation")


def _read(path, *, gid):
    info = _regular(path, protected=True)
    if (
        stat.S_IMODE(info.st_mode) != 0o640
        or info.st_gid != gid
        or not 0 < info.st_size <= 8192
    ):
        raise ValueError("Boot gate metadata is not protected/bounded")
    return _decode(path.read_bytes())


def _required(instance, secret):
    _protected_directory(instance.parent)
    _protected_directory(instance)
    path = instance / REQUIRED_NAME
    info = _regular(path, protected=True)
    if not 0 < info.st_size <= 8192:
        raise ValueError("Boot required marker exceeds budget")
    value = _decode(path.read_bytes())
    ticket = _RelationalBootEnableTicket.model_validate(value).model_dump(mode="json")
    verify_metadata(secret, "boot_enable", ticket)
    if (
        ticket["instance_id"] != instance.name
        or _read(path, gid=ticket["service_gid"]) != ticket
    ):
        raise ValueError("Boot required identity changed")
    return ticket


def read_boot_policy(instance, secret, *, confirmed=True):
    instance = Path(instance)
    ticket = _required(instance, secret)
    value = _BootPolicy.model_validate(
        _read(instance / POLICY_NAME, gid=ticket["service_gid"])
    ).model_dump(mode="json")
    if value["ticket"] != ticket or (confirmed and value["phase"] != "boot_confirmed"):
        raise ValueError("Boot policy is not confirmed/current")
    receipt = value["receipt"]
    if receipt is not None:
        verify_metadata(secret, "boot_enable_result", receipt)
        if (
            receipt["preparation_id"] != ticket["preparation_id"]
            or receipt["source_activation_id"] != ticket["source_activation_id"]
            or receipt["ticket_sha256"] != hashlib.sha256(canonical(ticket)).hexdigest()
            or receipt["lifecycle_sha256"] != ticket["prepared_lifecycle_sha256"]
        ):
            raise ValueError("Boot publication receipt changed")
    return value


def publish_pending_boot(instance, ticket, secret):
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Protected boot publisher required")
    instance = Path(instance)
    _protected_directory(instance)
    ticket = _RelationalBootEnableTicket.model_validate(ticket).model_dump(mode="json")
    verify_metadata(secret, "boot_enable", ticket)
    if ticket["instance_id"] != instance.name or boot_gate_present(instance):
        raise ValueError("Boot gate requires explicit recovery review")
    # Durable marker FIRST: a crash or partial policy write cannot become a
    # prepared/manual-start fallback. No unit enable has occurred yet.
    _exclusive_file(
        instance / REQUIRED_NAME, canonical(ticket), 0o640, ticket["service_gid"]
    )
    value = {"version": 1, "phase": "boot_pending", "ticket": ticket, "receipt": None}
    _exclusive_file(
        instance / POLICY_NAME, canonical(value), 0o640, ticket["service_gid"]
    )
    if read_boot_policy(instance, secret, confirmed=False) != value:
        raise ValueError("Boot pending publication unavailable")


def confirm_boot_policy(instance, ticket, receipt, secret):
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Protected boot publisher required")
    instance = Path(instance)
    pending = read_boot_policy(instance, secret, confirmed=False)
    if pending["phase"] != "boot_pending" or pending["ticket"] != ticket:
        raise ValueError("Boot pending publication changed")
    value = _BootPolicy.model_validate(
        dict(pending, phase="boot_confirmed", receipt=receipt)
    ).model_dump(mode="json")
    path = instance / POLICY_NAME
    _write_atomic(path, canonical(value), 0o640)
    os.chown(path, 0, ticket["service_gid"])
    _sync_directory(instance)
    if read_boot_policy(instance, secret) != value:
        raise ValueError("Boot confirmed publication unavailable")


def archive_stopped_boot(instance, state_root, stop_ticket, secret):
    """Caller holds Root locks and has independently verified STOP + disabled.

    Also accepts a required-marker-only crash. Known exact copies can complete
    under a NEW explicit stop request, never an automatic replay or overwrite.
    """
    instance, state_root = Path(instance), Path(state_root)
    if not boot_gate_present(instance):
        return
    if os.geteuid() != 0:
        raise ValueError("Protected boot recovery required")
    ticket = _required(instance, secret)
    if (
        ticket["source_activation_id"] != stop_ticket["source_activation_id"]
        or ticket["source_ticket_sha256"] != stop_ticket["source_ticket_sha256"]
        or any(
            ticket[name] != stop_ticket[name]
            for name in (
                "instance_id",
                "database_lineage",
                "prepared_lifecycle_sha256",
                "transport_key_sha256",
                "service_uid",
                "service_gid",
                "configuration_sha256",
                "package_sha256",
            )
        )
    ):
        raise ValueError("Stopped boot policy belongs to a different source")
    present = [REQUIRED_NAME]
    if os.path.lexists(instance / POLICY_NAME):
        read_boot_policy(instance, secret, confirmed=False)
        present.insert(0, POLICY_NAME)  # Required marker LAST, no partial fallback.
    for name in present:
        source = instance / name
        value = _read(source, gid=ticket["service_gid"])
        destination = state_root / (
            "relational-boot-archive-"
            + instance.name
            + "-"
            + ticket["preparation_id"]
            + "-"
            + name
        )
        payload = canonical(value)
        if os.path.lexists(destination):
            info = _regular(destination, protected=True)
            if (
                info.st_gid != 0
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > 8192
                or _decode(destination.read_bytes()) != value
            ):
                raise ValueError("Conflicting archived boot evidence")
        else:
            _exclusive_file(destination, payload, 0o600, 0)
        if _read(source, gid=ticket["service_gid"]) != value:
            raise ValueError("Boot evidence changed during archive")
        source.unlink()  # Exact protected metadata only; recoverable copy retained.
        _sync_directory(instance)
