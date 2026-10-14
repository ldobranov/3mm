"""Private enable-only coordinator for an exact healthy prepared application.

No start/restart, --now, migrations, key/lineage replacement or grant replay.
Root evidence and current Core consent are BOTH required. Not deployed CLI
dispatch or independent hostile-native-code isolation. Unknown outcomes stay
unknown; a cleanup disable is best effort and never reported as success.
"""

import hashlib
import os
import stat
import time
from itertools import islice
from pathlib import Path

from three_mm_application_sdk.relational_wire import (
    _RelationalActivationResult,
    _RelationalBootEnableResult,
    _RelationalBootEnableTicket,
    canonical,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import (
    _application_metadata,
    _wait_for_health,
    _write_atomic,
)
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_activation import PreparedServiceSupervisor
from three_mm_runtime.application_relational_activation_recovery import (
    _stopped_prepared,
)
from three_mm_runtime.application_relational_boot_policy import (
    boot_gate_present,
    confirm_boot_policy,
    publish_pending_boot,
)
from three_mm_runtime.application_relational_namespace import (
    _exclusive_file,
    _roots,
    _validate_dependencies,
)
from three_mm_runtime.application_relational_preparation import _key, _live
from three_mm_runtime.application_relational_session import _decode, _regular
from three_mm_runtime.application_transport import ApplicationServiceClient


class RelationalBootEnableError(RuntimeError):
    pass


class PreparedBootSupervisor(PreparedServiceSupervisor):
    """Separate fixed-unit adapter; ordinary start still rejects enabled units."""

    def enable_boot(self, instance_id):
        from three_mm_runtime.application_activation import _validate_instance_id

        _validate_instance_id(instance_id)
        self._run(["enable"], instance_id)

    def disable_boot(self, instance_id):
        from three_mm_runtime.application_activation import _validate_instance_id

        _validate_instance_id(instance_id)
        self._run(["disable"], instance_id)

    def verify_boot_identity(self, instance_id, uid, gid, *, enabled):
        pid = self._verify_identity(
            instance_id,
            uid,
            gid,
            running=True,
            unit_file_state="enabled" if enabled else "disabled",
        )
        # Pin the kernel process incarnation, not merely a recycled PID.
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        prefix, separator, tail = raw.rpartition(") ")
        fields = tail.split()
        if not separator or prefix.split(" ", 1)[0] != str(pid) or len(fields) < 20:
            raise RelationalBootEnableError("Prepared process incarnation unavailable")
        started = int(fields[19])  # /proc stat field 22, after pid and (comm).
        if started <= 0:
            raise RelationalBootEnableError("Prepared process incarnation invalid")
        return pid, started


def _successful_start_witness(state_root, ticket, secret):
    repeated = ticket["source_activation_action"] == "reactivate_prepared_service"
    path = state_root / (
        ("relational-reactivation-" if repeated else "relational-activation-")
        + ticket["instance_id"]
        + "-"
        + ticket["source_activation_id"]
        + ".json"
    )
    pending = (
        path.with_suffix(".pending.json")
        if repeated
        else state_root / ("relational-activation-" + ticket["instance_id"] + ".json")
    )
    if os.path.lexists(pending):
        raise ValueError("Unconfirmed start witness cannot enable boot")
    info = _regular(path, protected=True)
    if info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 8192:
        raise ValueError("Successful start witness is not protected/bounded")
    value = _decode(path.read_bytes())
    expected = {
        "version": 1,
        "activation_id": ticket["source_activation_id"],
        "ticket_sha256": ticket["source_ticket_sha256"],
        "prepared_lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
        "phase": "active_review_required",
    }
    if (
        type(value) is not dict
        or type(value.get("version")) is not int
        or set(value) != set(expected) | {"receipt"}
        or any(value[name] != item for name, item in expected.items())
    ):
        raise ValueError("Successful start witness changed")
    receipt = _RelationalActivationResult.model_validate(value["receipt"]).model_dump(
        mode="json"
    )
    verify_metadata(
        secret, "reactivation_result" if repeated else "activation_result", receipt
    )
    if (
        receipt["preparation_id"] != ticket["source_activation_id"]
        or receipt["lifecycle_sha256"] != ticket["prepared_lifecycle_sha256"]
        or hashlib.sha256(canonical(receipt)).hexdigest()
        != ticket["source_receipt_sha256"]
    ):
        raise ValueError("Successful start receipt changed")
    return hashlib.sha256(canonical(value)).hexdigest()


def enable_prepared_relational_boot(
    package_path,
    ticket,
    *,
    configuration,
    root,
    key_root,
    state_root,
    service_uid,
    service_gid,
    coordinator_uid,
    checkpoint,
    supervisor=None,
    client_factory=ApplicationServiceClient,
    sleep=time.sleep,
):
    """Enable only, after same-process health; never restores current SQL rights.

    Reboot creates a new host runtime nonce. Admission still requires today's
    independent grant/native/epoch and never replays this expired one-use ticket.
    Protected witnesses are retained on loss/crash; use explicit stop/review,
    not automatic retry or assumptions based on an installed DB row.
    """
    if os.name != "posix" or os.geteuid() != 0 or not callable(checkpoint):
        raise RelationalBootEnableError("Protected boot enable helper required")
    ticket = _RelationalBootEnableTicket.model_validate(ticket).model_dump(mode="json")
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    selected = supervisor or PreparedBootSupervisor()
    instance = root / ticket["instance_id"]
    key_path = key_root / (instance.name + ".key")
    record_path = state_root / (
        "relational-boot-" + instance.name + "-" + ticket["preparation_id"] + ".json"
    )
    with _release_lock(), _runtime_lock(state_root):
        _roots((root, key_root, state_root), coordinator_uid)
        secret = _key(key_path)
        verify_metadata(secret, "boot_enable", ticket)
        validated, configuration = _validate_dependencies(
            package_path,
            ticket,
            configuration=configuration,
            transport_secret=secret,
            service_uid=service_uid,
            service_gid=service_gid,
            coordinator_uid=coordinator_uid,
        )
        expected = _application_metadata(validated, configuration, instance.name, root)
        expected["storage"]["relational"] = (
            validated.application_extension.storage.relational.model_dump(mode="json")
        )

        def prepared():
            # Shared read-only layout check; the function itself neither checks
            # nor changes process state despite its recovery-oriented name.
            _stopped_prepared(
                instance, key_path, secret, ticket, expected, service_uid, service_gid
            )

        prepared()
        witness_sha = _successful_start_witness(state_root, ticket, secret)
        if (
            os.path.lexists(record_path)
            or boot_gate_present(instance)
            or len(
                tuple(
                    islice(
                        state_root.glob("relational-boot-" + instance.name + "-*.json"),
                        32,
                    )
                )
            )
            >= 32
        ):
            raise RelationalBootEnableError(
                "Boot enable requires explicit evidence review"
            )
        identity = selected.verify_boot_identity(
            instance.name, service_uid, service_gid, enabled=False
        )
        if (
            type(identity) is not tuple
            or len(identity) != 2
            or any(type(x) is not int or x <= 0 for x in identity)
        ):
            raise RelationalBootEnableError("Prepared process identity unavailable")
        if checkpoint(ticket, "authorize") != {"state": "authorized_enable_only"}:
            raise RelationalBootEnableError("Boot enable authority unavailable")
        evidence = {
            "version": 1,
            "boot_enable_id": ticket["preparation_id"],
            "source_activation_id": ticket["source_activation_id"],
            "ticket_sha256": hashlib.sha256(canonical(ticket)).hexdigest(),
            "witness_sha256": witness_sha,
            "phase": "enable_unconfirmed",
        }
        _exclusive_file(record_path, canonical(evidence), 0o600, 0)
        enable_attempted = False
        try:
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Boot enable begin unconfirmed")
            publish_pending_boot(instance, ticket, secret)

            def unchanged(*, enabled):
                prepared()
                if (
                    _successful_start_witness(state_root, ticket, secret) != witness_sha
                    or selected.verify_boot_identity(
                        instance.name, service_uid, service_gid, enabled=enabled
                    )
                    != identity
                ):
                    raise ValueError(
                        "Prepared start/process changed during boot enable"
                    )

            unchanged(enabled=False)
            _wait_for_health(
                expected,
                secret,
                instance / "run/service.sock",
                client_factory=lambda path, key, timeout: client_factory(
                    path, key, min(timeout, _live(ticket) / 1000)
                ),
                sleep=lambda delay: sleep(min(delay, _live(ticket) / 1000)),
            )
            unchanged(enabled=False)
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Boot enable current authority unavailable")
            _live(ticket)
            enable_attempted = True  # Includes an unknown systemd result.
            selected.enable_boot(instance.name)  # No --now, start or restart.
            unchanged(enabled=True)
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Boot enable authority changed after enable")
            _live(ticket)
            result = _RelationalBootEnableResult.model_validate(
                sign_metadata(
                    secret,
                    "boot_enable_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "ticket_sha256": evidence["ticket_sha256"],
                        "source_activation_id": ticket["source_activation_id"],
                        "lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
                        "witness_sha256": witness_sha,
                        "outcome": "boot_enabled_not_started",
                    },
                )
            ).model_dump(mode="json")
            _write_atomic(
                record_path,
                canonical(dict(evidence, phase="enabled_unconfirmed", receipt=result)),
                0o600,
            )
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "boot_enabled_not_started"
            }:
                raise ValueError("Boot enable completion unconfirmed")
            _write_atomic(
                record_path,
                canonical(
                    dict(evidence, phase="boot_enabled_not_started", receipt=result)
                ),
                0o600,
            )
            confirm_boot_policy(instance, ticket, result, secret)
            return result
        except Exception as exc:
            if enable_attempted:
                try:
                    selected.disable_boot(
                        instance.name
                    )  # Do not stop/restart the running application.
                    selected.verify_boot_identity(
                        instance.name, service_uid, service_gid, enabled=False
                    )
                except Exception:
                    pass  # Retained evidence; no claim about the cleanup outcome.
            raise RelationalBootEnableError(
                "Boot enable unconfirmed; preserve evidence, do not retry"
            ) from exc
