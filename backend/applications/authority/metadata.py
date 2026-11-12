"""Internal M20 metadata transactions; not effect authorization.

Readers never initialize state or flush pending objects. The explicit write scope
owns a fresh Session transaction, locks the singleton before other mutable rows,
and commits/rolls back as a unit. Only explicitly integrated writers participate.
"""

from contextlib import contextmanager
from dataclasses import dataclass, replace
import re

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.authority import (
    CoreAuthorityGuard,
    MAX_AUTHORITY_REVISION,
    new_authority_generation,
)
from backend.db.device import Device, DevicePlatformState
from backend.db.module import (
    ApplicationConnectorBinding,
    ApplicationExtensionInstallation,
)


class AuthorityMetadataError(ValueError):
    def __init__(self):
        super().__init__("Authority metadata is unavailable or stale")


@dataclass(frozen=True)
class AuthorityGuardSnapshot:
    generation: str
    revision: int


@dataclass(frozen=True)
class ApplicationAuthoritySnapshot:
    installation_id: int
    module_id: str
    incarnation: str
    epoch: str
    mode: str


@dataclass(frozen=True)
class ConnectorAuthoritySnapshot:
    binding_id: int
    connector_id: str
    revision: str
    application: ApplicationAuthoritySnapshot


@dataclass(frozen=True)
class DeviceControlSnapshot:
    device_db_id: int
    device_id: str
    generation: str


def _generation(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise AuthorityMetadataError()
    return value


def _positive_id(value):
    if type(value) is not int or value < 1:
        raise AuthorityMetadataError()
    return value


def _application(row):
    if row is None or row.authority_mode not in {"compatibility", "review_required", "enforced"}:
        raise AuthorityMetadataError()
    return ApplicationAuthoritySnapshot(
        row.id,
        row.module_id,
        _generation(row.authority_incarnation),
        _generation(row.authority_epoch),
        row.authority_mode,
    )


_APPLICATION_COLUMNS = (
    ApplicationExtensionInstallation.id,
    ApplicationExtensionInstallation.module_id,
    ApplicationExtensionInstallation.authority_incarnation,
    ApplicationExtensionInstallation.authority_epoch,
    ApplicationExtensionInstallation.authority_mode,
)


def read_authority_guard(db: Session) -> AuthorityGuardSnapshot:
    with db.no_autoflush:
        row = db.execute(
            select(CoreAuthorityGuard.generation, CoreAuthorityGuard.revision).where(
                CoreAuthorityGuard.singleton_id == 1
            )
        ).one_or_none()
    if (
        row is None
        or type(row.revision) is not int
        or not 1 <= row.revision <= MAX_AUTHORITY_REVISION
    ):
        raise AuthorityMetadataError()
    return AuthorityGuardSnapshot(_generation(row.generation), row.revision)


def read_application_authority(
    db: Session, installation_id: int
) -> ApplicationAuthoritySnapshot:
    with db.no_autoflush:
        row = db.execute(
            select(*_APPLICATION_COLUMNS).where(
                ApplicationExtensionInstallation.id == _positive_id(installation_id)
            )
        ).one_or_none()
    return _application(row)


def read_connector_authority(
    db: Session, *, installation_id: int, binding_id: int
) -> ConnectorAuthoritySnapshot:
    with db.no_autoflush:
        row = db.execute(
            select(
                *_APPLICATION_COLUMNS,
                ApplicationConnectorBinding.id.label("binding_id"),
                ApplicationConnectorBinding.connector_id,
                ApplicationConnectorBinding.authority_revision,
            )
            .join(
                ApplicationConnectorBinding,
                ApplicationConnectorBinding.application_installation_id
                == ApplicationExtensionInstallation.id,
            )
            .where(
                ApplicationExtensionInstallation.id == _positive_id(installation_id),
                ApplicationConnectorBinding.id == _positive_id(binding_id),
            )
        ).one_or_none()
    application = _application(row)
    return ConnectorAuthoritySnapshot(
        row.binding_id,
        row.connector_id,
        _generation(row.authority_revision),
        application,
    )


def read_device_control(db: Session, device_db_id: int) -> DeviceControlSnapshot:
    with db.no_autoflush:
        row = db.execute(
            select(Device.id, Device.device_id, DevicePlatformState.control_generation)
            .join(DevicePlatformState, DevicePlatformState.device_id == Device.id)
            .where(Device.id == _positive_id(device_db_id))
        ).one_or_none()
    if row is None:
        raise AuthorityMetadataError()
    return DeviceControlSnapshot(
        row.id, row.device_id, _generation(row.control_generation)
    )


class AuthorityMutation:
    """Short-lived CAS helpers, usable only inside authority_transaction.

    Metadata primitives only. Participating callers own resource writes and audit;
    lifecycle command invalidation and effect-boundary checks remain separate.
    """

    def __init__(self, db, guard):
        self._db, self.guard = db, guard
        self._transaction = db.get_transaction()
        self._active, self._failed = True, False

    def _fail(self):
        self._failed = True
        raise AuthorityMetadataError()

    def _check(self):
        if (
            not self._active
            or self._failed
            or self._db.get_transaction() is not self._transaction
            or not self._transaction.is_active
            or self._db.in_nested_transaction()
            or self.guard.revision >= MAX_AUTHORITY_REVISION
        ):
            self._fail()

    def _write(self, statement):
        try:
            result = self._db.execute(
                statement.execution_options(synchronize_session=False)
            )
        except SQLAlchemyError as exc:
            self._failed = True
            raise AuthorityMetadataError() from exc
        if result.rowcount != 1:
            self._fail()

    def _advance_guard(self):
        self._write(
            update(CoreAuthorityGuard)
            .where(
                CoreAuthorityGuard.singleton_id == 1,
                CoreAuthorityGuard.generation == self.guard.generation,
                CoreAuthorityGuard.revision == self.guard.revision,
            )
            .values(revision=self.guard.revision + 1)
        )
        self.guard = replace(self.guard, revision=self.guard.revision + 1)

    def require_session(self, db: Session) -> None:
        """Reject use from another Session or outside the owning transaction."""
        self._check()
        if db is not self._db:
            self._fail()

    def reject(self) -> None:
        """A participating writer's stale resource check poisons the whole scope."""
        self._fail()

    def advance_guard_revision(self) -> AuthorityGuardSnapshot:
        """Fence review metadata without changing an active application's policy.

        Staging/denying a candidate must not invalidate the running grant/epoch.
        The participating writer must commit its actual metadata and audit here.
        """
        self._check()
        self._advance_guard()
        return self.guard

    def lock_application(
        self, expected: ApplicationAuthoritySnapshot, *, lifecycle_status: str | None = None
    ) -> None:
        """Lock/recheck the owner; ordinary writers cannot cross a lifecycle fence.

        Only a lifecycle completion supplies its exact pending status, alongside
        the incarnation/epoch CAS. An unconfirmed helper outcome stays blocked.
        """
        self._check()
        status_condition = (
            ApplicationExtensionInstallation.status == lifecycle_status
            if lifecycle_status is not None
            else ApplicationExtensionInstallation.status.not_in(
                ("activating", "disabling", "uninstalling", "recovering", "recovery_required")
            )
        )
        self._write(
            update(ApplicationExtensionInstallation)
            .where(*self._application_conditions(expected), status_condition)
            .values(
                authority_epoch=ApplicationExtensionInstallation.authority_epoch,
                updated_at=ApplicationExtensionInstallation.updated_at,
            )
        )

    @staticmethod
    def _application_conditions(expected):
        return (
            ApplicationExtensionInstallation.id == expected.installation_id,
            ApplicationExtensionInstallation.module_id == expected.module_id,
            ApplicationExtensionInstallation.authority_incarnation
            == expected.incarnation,
            ApplicationExtensionInstallation.authority_epoch == expected.epoch,
            ApplicationExtensionInstallation.authority_mode == expected.mode,
        )

    def _advance_application(self, expected):
        epoch = new_authority_generation()
        self._write(
            update(ApplicationExtensionInstallation)
            .where(*self._application_conditions(expected))
            .values(authority_epoch=epoch)
        )
        return replace(expected, epoch=epoch)

    def advance_application_epoch(
        self, expected: ApplicationAuthoritySnapshot
    ) -> ApplicationAuthoritySnapshot:
        self._check()
        current = self._advance_application(expected)
        self._advance_guard()
        return current

    def set_application_mode(self, expected, mode):
        """Explicit adoption/revocation; never silently downgrade to compatibility."""
        if mode not in {"enforced", "review_required"}:
            self._fail()
        current = self.advance_application_epoch(expected)
        self._write(update(ApplicationExtensionInstallation)
            .where(*self._application_conditions(current)).values(authority_mode=mode))
        return replace(current, mode=mode)

    def advance_connector_revision(
        self, expected: ConnectorAuthoritySnapshot
    ) -> ConnectorAuthoritySnapshot:
        self._check()
        application = self._advance_application(expected.application)
        revision = new_authority_generation()
        self._write(
            update(ApplicationConnectorBinding)
            .where(
                ApplicationConnectorBinding.id == expected.binding_id,
                ApplicationConnectorBinding.application_installation_id
                == expected.application.installation_id,
                ApplicationConnectorBinding.connector_id == expected.connector_id,
                ApplicationConnectorBinding.authority_revision == expected.revision,
            )
            .values(authority_revision=revision)
        )
        self._advance_guard()
        return replace(expected, revision=revision, application=application)

    def advance_device_control(
        self, expected: DeviceControlSnapshot
    ) -> DeviceControlSnapshot:
        self._check()
        generation = new_authority_generation()
        self._write(
            update(DevicePlatformState)
            .where(
                DevicePlatformState.device_id == expected.device_db_id,
                DevicePlatformState.control_generation == expected.generation,
                select(Device.id)
                .where(
                    Device.id == expected.device_db_id,
                    Device.device_id == expected.device_id,
                )
                .exists(),
            )
            .values(control_generation=generation)
        )
        self._advance_guard()
        return replace(expected, generation=generation)


@contextmanager
def authority_transaction(
    db: Session, *, expected_guard: AuthorityGuardSnapshot | None = None
):
    """Own begin/commit/rollback on a clean dedicated Session, never across I/O.

    Must be the first transaction/write, before resolving mutable rows. No lazy
    singleton creation, savepoints, caller-authored grants or unsupported dialects.
    A caught failed CAS poisons the scope and still rolls everything back on exit.
    """
    if (
        db.in_transaction()
        or db.new
        or db.dirty
        or db.deleted
        or db.get_bind().dialect.name not in {"sqlite", "postgresql"}
    ):
        raise AuthorityMetadataError()
    mutation = None
    try:
        with db.begin(), db.no_autoflush:
            statement = update(CoreAuthorityGuard).where(
                CoreAuthorityGuard.singleton_id == 1
            )
            if expected_guard is not None:
                statement = statement.where(
                    CoreAuthorityGuard.generation == expected_guard.generation,
                    CoreAuthorityGuard.revision == expected_guard.revision,
                )
            result = db.execute(statement.values(revision=CoreAuthorityGuard.revision))
            if result.rowcount != 1:
                raise AuthorityMetadataError()
            mutation = AuthorityMutation(db, read_authority_guard(db))
            yield mutation
            if mutation._failed or db.get_transaction() is not mutation._transaction:
                raise AuthorityMetadataError()
    finally:
        if mutation is not None:
            mutation._active = False
