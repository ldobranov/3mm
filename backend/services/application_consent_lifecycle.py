"""Resume exact saved resource consent across confirmed stop/start transitions.

Human consent remains historical. Each confirmed lifecycle completion binds that
same consent to its fresh execution epoch, without reviving old effect tickets.
"""

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
import zipfile
import zlib

from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.audit_log import AuditLog
from backend.db.authority import new_authority_generation
from backend.services.application_authority_inspection import AuthorityInspectionBaseline, _read_baseline
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_authority_management import (
    AuthorityManagementError, _PreparedAuthority, _load, _parse, _resource_identity, _save,
)
from backend.services.application_authority_sources import _package_pin
from backend.services.authority_metadata import read_application_authority, read_authority_guard


_UNAVAILABLE = (AuthorityManagementError, AuthorityReviewKeyError, ValueError,
    TypeError, KeyError, AttributeError, OSError, RuntimeError, zipfile.BadZipFile, zlib.error)


def _artifact_pin(pin):
    return (pin.module_package_id, pin.module_id, pin.package_module_id,
        pin.version, pin.sha256)


@dataclass(frozen=True)
class SavedConsent:
    manager: object
    prepared: object
    application: object
    instance_id: str
    guard_generation: str
    grant: dict
    identity: bytes


@dataclass(frozen=True)
class LifecycleConsent:
    manager: object = None
    prepared: object = None
    expected: object = None
    saved: SavedConsent | None = None
    key: object = None

    @contextmanager
    def lease(self):
        """An optional key lease BEFORE the route's authority writer.

        Stopping an application never depends on a valid permission record/key.
        The lease ends before helper I/O; exceptions from the route aren't hidden.
        """
        with ExitStack() as stack:
            key = None
            if self.manager is not None:
                try:
                    key = stack.enter_context(self.manager.keys.locked())
                except _UNAVAILABLE:
                    pass
            yield key

    def capture(self, db, key):
        if key is None or self.manager is None:
            return None
        try:
            current = read_application_authority(db, self.expected.installation_id)
            if current != self.expected or current.mode != "enforced":
                return None
            grant = self.manager._require_current_grant(db, key,
                current.installation_id, self.prepared)
            subject = self.manager._subject(db, key, current.installation_id, self.prepared)
            from backend.db.module import ApplicationExtensionInstallation
            installation = db.get(ApplicationExtensionInstallation, current.installation_id)
            return SavedConsent(self.manager, self.prepared, current, installation.instance_id,
                read_authority_guard(db).generation, deepcopy(grant), _resource_identity(subject))
        except _UNAVAILABLE:
            return None

    def resume(self, db, installation, actor_id):
        saved, key = self.saved, self.key
        if saved is None or key is None:
            return False
        try:
            current = read_application_authority(db, installation.id)
            if (current.installation_id != saved.application.installation_id
                    or current.module_id != saved.application.module_id
                    or current.incarnation != saved.application.incarnation
                    or current.mode != "enforced"
                    or installation.instance_id != saved.instance_id
                    or read_authority_guard(db).generation != saved.guard_generation):
                return False
            row = db.get(Grant, installation.id, populate_existing=True)
            grant = _load(db, key, "grant", row, installation.id)
            if grant != saved.grant or grant["state"] != "active":
                return False
            db.flush()  # The authoritative subject sees the confirmed stable state.
            pin = _package_pin(db, installation.id)
            if _artifact_pin(pin) != _artifact_pin(self.prepared.pin):
                return False
            prepared = replace(self.prepared, pin=pin)
            subject = self.manager._subject(db, key, installation.id, prepared)
            if _resource_identity(subject) != saved.identity:
                return False
            native, _ = self.manager._policy(db, key, subject,
                grant["data"]["native_review_id"])
            approved = _parse(type(subject), grant["data"]["subject"])
            _, approved_policy = self.manager._policy(db, key, approved,
                grant["data"]["native_review_id"])
            if (native["revision"] != grant["data"]["native_revision"]
                    or approved_policy.model_dump(mode="json") != grant["data"]["policy"]
                    or row.revision != grant["data"]["grant_revision"]):
                return False
        except _UNAVAILABLE:
            return False
        # Keep the exact approved subject, scope selection and human consent
        # revision. A new envelope fences sessions bound to the previous epoch.
        grant["revision"] = new_authority_generation()
        grant["data"]["authority_epoch"] = current.epoch
        _save(db, key, "grant", row, grant)
        db.add(AuditLog(user_id=actor_id, action="APPLICATION_CONSENT_RESUMED",
            entity_type="application_extension", entity_name=current.module_id,
            changes={"grant_revision": row.revision, "revision": grant["revision"],
                "authority_epoch": current.epoch, "lifecycle_status": installation.status}))
        return True


def prepare_lifecycle_consent(engine, expected):
    """Validate artifact bytes before the optional key and authority locks."""
    if expected is None or expected.mode != "enforced":
        return LifecycleConsent()
    try:
        from backend.services.application_authority_management import configured_manager
        manager = configured_manager(engine)
        return LifecycleConsent(manager, manager._prepare(expected.installation_id), expected)
    except _UNAVAILABLE:
        return LifecycleConsent()


@contextmanager
def completing_lifecycle_consent(saved):
    """Refresh immutable code outside locks, then acquire key before DB guard."""
    if saved is None:
        yield LifecycleConsent()
        return
    manager, previous = saved.manager, saved.prepared
    try:
        pin = previous.pin
        package = _read_baseline(AuthorityInspectionBaseline(pin.module_id,
            pin.version, pin.sha256, pin.active_version, pin.status, None),
            manager.uploads_root, manager.core_version)
        build = None
        if package.compiled_ui is not None:
            from backend.services.compiled_ui import load_compiled_ui_artifact
            build = load_compiled_ui_artifact(package).built_ui_sha256
        prepared = _PreparedAuthority(pin, package, build)
    except _UNAVAILABLE:
        yield LifecycleConsent()
        return
    consent = LifecycleConsent(manager, prepared, saved.application, saved)
    with consent.lease() as key:
        yield replace(consent, key=key)
