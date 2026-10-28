"""Private one-shot start of an exact prepared reviewed-native application.

No preparation, migration, key generation, data rollback or grant restoration.
Unknown outcomes retain a protected witness and are never restarted/replayed.
Only explicit local administration through the Core-UID helper boundary, not a
public/SDK writer. The existing systemd unit's restart policy is not changed;
this coordinator never retries a start and does not enable boot autostart.
"""

import hashlib
import os
import stat
import subprocess
import time
from itertools import islice
from pathlib import Path

from backend.services.application_requirements import require_platform_requirements

from three_mm_application_sdk.relational_wire import (
    _activation_ticket,
    _RelationalActivationResult,
    canonical,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import (
    SystemdApplicationSupervisor,
    _application_metadata,
    _validate_instance_id,
    _wait_for_health,
    _write_atomic,
)
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_namespace import (
    _exclusive_file,
    _roots,
    _sync_directory,
    _validate_dependencies,
)
from three_mm_runtime.application_relational_preparation import _key, _live
from three_mm_runtime.application_relational_session import _decode, _prepared, _regular
from three_mm_runtime.application_transport import ApplicationServiceClient


class RelationalActivationError(RuntimeError):
    pass


def _service_access(path, uid, gid, rights):
    """Conservative DAC check with no supplemental-group/Root permission fallback."""
    info = path.lstat()
    shift = 6 if info.st_uid == uid else 3 if info.st_gid == gid else 0
    if (stat.S_IMODE(info.st_mode) >> shift) & rights != rights:
        raise ValueError("Prepared path is not accessible to its service principal")
    for parent in path.parents:
        info = parent.lstat()
        shift = 6 if info.st_uid == uid else 3 if info.st_gid == gid else 0
        if not stat.S_ISDIR(info.st_mode) or not ((info.st_mode >> shift) & 1):
            raise ValueError(
                "Prepared ancestry is not traversable by its service principal"
            )


class PreparedServiceSupervisor(SystemdApplicationSupervisor):
    """Fixed unit, checked non-root account, one start without boot enable."""

    def start(self, instance_id):
        _validate_instance_id(instance_id)
        self._run(["start"], instance_id)

    def verify_identity(self, instance_id, uid, gid, *, running):
        return self._verify_identity(
            instance_id, uid, gid, running=running, unit_file_state="disabled"
        )

    def _verify_identity(self, instance_id, uid, gid, *, running, unit_file_state):
        """Shared kernel check; ordinary prepared starts still require disabled."""
        import grp
        import pwd

        _validate_instance_id(instance_id)
        try:
            result = subprocess.run(
                [
                    "/usr/bin/systemctl",
                    "show",
                    f"3mm-application-extension@{instance_id}.service",
                    "--no-pager",
                    "--property=User,Group,MainPID,LoadState,ActiveState,UnitFileState,Job",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            fields = dict(line.split("=", 1) for line in result.stdout.splitlines())
            user = fields["User"]
            group = fields["Group"]
            actual_uid = int(user) if user.isdecimal() else pwd.getpwnam(user).pw_uid
            actual_gid = int(group) if group.isdecimal() else grp.getgrnam(group).gr_gid
            if (
                set(fields)
                != {
                    "User",
                    "Group",
                    "MainPID",
                    "LoadState",
                    "ActiveState",
                    "UnitFileState",
                    "Job",
                }
                or (actual_uid, actual_gid) != (uid, gid)
                or uid <= 0
                or gid <= 0
                or fields["LoadState"] != "loaded"
                or fields["UnitFileState"] != unit_file_state
                or fields["Job"] not in {"", "0"}
                or fields["ActiveState"]
                not in ({"active"} if running else {"inactive", "failed"})
            ):
                raise ValueError("Prepared unit principal/state changed")
            pid = int(fields["MainPID"])
            if not running:
                if pid != 0:
                    raise ValueError("Prepared unit is not stopped")
                return
            if pid <= 0:
                raise ValueError("Prepared service has no process")
            # Kernel-reported real/effective/saved/fs credentials, not a health
            # payload asserting an application-selected UID or root fallback.
            status = Path(f"/proc/{pid}/status").read_text(encoding="ascii")
            identity = {
                name: tuple(int(part) for part in value.split())
                for line in status.splitlines()
                if ":" in line
                for name, value in [line.split(":", 1)]
                if name in {"Uid", "Gid"}
            }
            if identity != {"Uid": (uid,) * 4, "Gid": (gid,) * 4}:
                raise ValueError("Prepared process principal changed")
            return pid
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            raise RelationalActivationError(
                "Prepared service identity unavailable"
            ) from exc


def activate_prepared_relational_service(
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
    """Leases/SQL closed before process I/O; no factory/migration in Root.

    Success means healthy and review_required, NOT permitted business SQL.
    Failure requests a Core fence and a verified stop, but never hides lost ACKs
    or deletes evidence if either cannot be confirmed. Reviewed-native only.
    """
    if os.name != "posix" or os.geteuid() != 0 or not callable(checkpoint):
        raise RelationalActivationError("Protected activation helper required")
    ticket, purpose = _activation_ticket(ticket)
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    selected = supervisor or PreparedServiceSupervisor()
    instance = root / ticket["instance_id"]
    key_path = key_root / (ticket["instance_id"] + ".key")
    marker = state_root / ("relational-activation-" + ticket["instance_id"] + ".json")
    history = state_root / (
        "relational-activation-"
        + ticket["instance_id"]
        + "-"
        + ticket["preparation_id"]
        + ".json"
    )
    if purpose == "reactivation":
        # Independent per-action witness: retained original uncertainty is not
        # silently removed/renamed to make room for another start.
        history = state_root / (
            "relational-reactivation-"
            + ticket["instance_id"]
            + "-"
            + ticket["preparation_id"]
            + ".json"
        )
        marker = history.with_suffix(".pending.json")
    with _release_lock(), _runtime_lock(state_root):
        _roots((root, key_root, state_root), coordinator_uid)
        secret = _key(key_path)
        info = _regular(key_path, protected=True)
        if info.st_gid != service_gid or stat.S_IMODE(info.st_mode) != 0o640:
            raise RelationalActivationError("Prepared key principal changed")
        verify_metadata(secret, purpose, ticket)
        validated, configuration = _validate_dependencies(
            package_path,
            ticket,
            configuration=configuration,
            transport_secret=secret,
            service_uid=service_uid,
            service_gid=service_gid,
            coordinator_uid=coordinator_uid,
        )
        expected_metadata = _application_metadata(
            validated, configuration, instance.name, root
        )
        require_platform_requirements(validated.application_extension)
        expected_metadata["storage"]["relational"] = (
            validated.application_extension.storage.relational.model_dump(mode="json")
        )

        def verify_prepared():
            _live(ticket)
            if _key(key_path) != secret:
                raise ValueError("Prepared transport key changed")
            _service_access(key_path, service_uid, service_gid, 4)
            for path in (instance, instance / "data", instance / "run"):
                _service_access(path, service_uid, service_gid, 5)
            for name in ("data", "run"):
                info = (instance / name).lstat()
                if (
                    not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != service_uid
                    or info.st_gid != service_gid
                    or stat.S_IMODE(info.st_mode) != 0o750
                ):
                    raise ValueError("Prepared namespace principal changed")
            for suffix in ("", "-wal", "-shm", "-journal"):
                path = instance / "data" / ("state.sqlite3" + suffix)
                if suffix and not os.path.lexists(path):
                    continue
                info = _regular(path)
                if info.st_uid != service_uid or info.st_gid != service_gid:
                    raise ValueError("Prepared database principal changed")
            active = instance / "active.json"
            if _regular(active, protected=True).st_size > 131072:
                raise ValueError("Prepared active metadata exceeds budget")
            if _decode(active.read_bytes(), limit=131072) != expected_metadata:
                raise ValueError("Prepared active metadata changed")
            record = _prepared(
                instance, secret
            )  # Read-only readiness, no business SQL.
            for path in (
                active,
                instance / "relational.json",
                instance / "releases" / record["package_sha256"] / "service.whl",
                instance / "data" / "state.sqlite3",
            ):
                _service_access(path, service_uid, service_gid, 4)
            if (
                hashlib.sha256(canonical(record)).hexdigest()
                != ticket["prepared_lifecycle_sha256"]
                or record["database_lineage"] != ticket["database_lineage"]
                or record["lifecycle_id"] != ticket["source_preparation_id"]
            ):
                raise ValueError("Prepared lifecycle changed")
            if purpose == "reactivation":
                from three_mm_runtime.application_relational_reactivation import (
                    verify_stopped_source,
                )

                verify_stopped_source(state_root, ticket, secret)

        verify_prepared()
        if purpose == "activation":
            from three_mm_runtime.application_relational_activation_recovery import (
                _activation_marker,
            )

            # A closed legacy witness remains byte-for-byte intact. A NEW
            # separately consented start gets its own path, never a retry of
            # the old action or permission inferred from the historical stop.
            marker = _activation_marker(
                state_root, instance.name, ticket["preparation_id"], secret
            )
        if (
            os.path.lexists(marker)
            or os.path.lexists(history)
            or len(
                tuple(
                    islice(
                        state_root.glob(
                            "relational-" + purpose + "-" + instance.name + "-*.json"
                        ),
                        32,
                    )
                )
            )
            >= 32
        ):
            raise RelationalActivationError(
                "Activation requires explicit recovery review"
            )
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise RelationalActivationError("Activation authority unavailable")
        selected.recover_disabled(instance.name)
        selected.verify_identity(instance.name, service_uid, service_gid, running=False)
        evidence = {
            "version": 1,
            "activation_id": ticket["preparation_id"],
            "ticket_sha256": hashlib.sha256(canonical(ticket)).hexdigest(),
            "prepared_lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
            "phase": "activation_unconfirmed",
        }
        _exclusive_file(marker, canonical(evidence), 0o600, 0)
        begun = False
        try:
            # Mark before calling: lost begin ACK may already have fenced Core.
            begun = True
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Activation begin unconfirmed")
            verify_prepared()
            selected.start(instance.name)  # Exactly once; no restart/enable fallback.
            selected.verify_identity(
                instance.name, service_uid, service_gid, running=True
            )

            def bounded_client(path, signing_secret, timeout):
                return client_factory(
                    path, signing_secret, min(timeout, _live(ticket) / 1000)
                )

            def bounded_sleep(delay):
                sleep(min(delay, _live(ticket) / 1000))
                _live(ticket)

            _wait_for_health(
                expected_metadata,
                secret,
                instance / "run/service.sock",
                client_factory=bounded_client,
                sleep=bounded_sleep,
            )
            verify_prepared()
            selected.verify_identity(
                instance.name, service_uid, service_gid, running=True
            )
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Activation current authority unavailable")
            result = _RelationalActivationResult.model_validate(
                sign_metadata(
                    secret,
                    purpose + "_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
                        "outcome": "active_review_required",
                    },
                )
            ).model_dump(mode="json")
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "active_review_required"
            }:
                raise ValueError("Activation completion unconfirmed")
            _write_atomic(
                marker,
                canonical(
                    dict(evidence, phase="active_review_required", receipt=result)
                ),
                0o600,
                uid=0,
                gid=0,
            )
            marker.rename(history)
            _sync_directory(state_root)
            return result
        except Exception as exc:
            if begun:
                try:
                    checkpoint(ticket, "abort")
                except Exception:
                    pass  # Keep unknown outcome; never infer success from an exception.
            try:
                selected.recover_disabled(instance.name)
            except Exception:
                pass  # Retained witness also covers an unconfirmed stop.
            raise RelationalActivationError(
                "Activation unconfirmed; preserve evidence for explicit recovery review"
            ) from exc
