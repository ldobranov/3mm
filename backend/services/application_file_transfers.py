"""Bounded browser file access; bytes remain in memory or the owning host.

One existing private-file namespace, executor and sealed receipt journal. A route
must opt in and name human permissions; service storage consent remains separate.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import threading
from sqlalchemy import update

from sqlalchemy.orm import Session
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services.application_access import (
    application_permission_ids, can_access_application_route, resolve_application_principal,
)
from backend.services.application_files import ApplicationFileAuthorityError
from backend.db.user import User
from backend.db.session import UserSession
from backend.utils.jwt_utils import decode_token

_slots = threading.BoundedSemaphore(2)


@contextmanager
def transfer_slot():
    if not _slots.acquire(blocking=False):
        from fastapi import HTTPException
        raise HTTPException(429, 'File transfers are busy; no automatic retry')
    try:
        yield
    finally:
        _slots.release()


@dataclass(frozen=True)
class BrowserFileCaller:
    installation_id: int
    instance_id: str
    incarnation: str
    package_id: int
    package_sha256: str
    built_ui_sha256: str
    route: object
    authorization: str
    user_id: int
    operation: str
    subject_id: str

    @property
    def actor(self):
        return ['browser_user', self.subject_id]

    def check_permissions(self, principal, permissions, module_id):
        access = self.route.private_files
        permission = getattr(access, self.operation + '_permission', None) if access else None
        if (access is None or not can_access_application_route(self.route, principal,
                module_id=module_id, permission_ids=permissions)
                or permission is None
                or access.read_permission not in permissions or permission not in permissions):
            raise ApplicationFileAuthorityError()

    def check(self, db: Session, prepared=None):
        # No artifact I/O under the service's key/guard lease. The exact source
        # and UI build were read in preflight and are checked by current grants.
        db.expire_all()
        principal = resolve_application_principal(self.authorization, db)
        token = self.authorization.split(' ', 1)[1].strip()
        claims = decode_token(token)
        sid = claims.get('sid')
        if type(sid) is not int or sid < 1:
            raise ApplicationFileAuthorityError()
        # Serialize admission with account/session changes, without accepting a
        # claimed role or allowing a service token to choose the human actor.
        if db.execute(update(User).where(User.id == self.user_id,
                User.is_blocked.is_(False), User.token_version == claims.get('token_version'))
                .values(token_version=User.token_version)).rowcount != 1:
            raise ApplicationFileAuthorityError()
        if db.execute(update(UserSession).where(UserSession.id == sid,
                UserSession.user_id == self.user_id, UserSession.token == token,
                UserSession.is_active.is_(True)).values(is_active=UserSession.is_active)).rowcount != 1:
            raise ApplicationFileAuthorityError()
        installation = db.get(Installation, self.installation_id, populate_existing=True)
        package = db.get(ModulePackage, self.package_id, populate_existing=True)
        if (principal.kind != 'user' or principal.user_id != self.user_id
                or principal.subject_id != self.subject_id
                or installation is None or package is None
                or not installation.enabled or installation.status != 'active'
                or installation.authority_mode != 'enforced'
                or installation.instance_id != self.instance_id
                or installation.authority_incarnation != self.incarnation
                or installation.module_package_id != self.package_id
                or package.module_id != installation.module_id or package.sha256 != self.package_sha256):
            raise ApplicationFileAuthorityError()
        if prepared is not None and (prepared.pin.sha256 != self.package_sha256
                or prepared.built_ui_sha256 != self.built_ui_sha256):
            raise ApplicationFileAuthorityError()
        permissions = application_permission_ids(db, installation.id, principal.user_id)
        self.check_permissions(principal, permissions, installation.module_id)


@dataclass(frozen=True)
class PublicFileCaller:
    installation_id: int
    instance_id: str
    incarnation: str
    package_id: int
    package_sha256: str

    @property
    def actor(self):
        return ['public_file', str(self.installation_id)]

    def check(self, db, prepared=None):
        row = db.get(Installation, self.installation_id, populate_existing=True)
        if (row is None or not row.enabled or row.status != 'active'
                or row.authority_mode != 'enforced' or row.instance_id != self.instance_id
                or row.authority_incarnation != self.incarnation or row.module_package_id != self.package_id
                or prepared is not None and prepared.pin.sha256 != self.package_sha256):
            raise ApplicationFileAuthorityError()
