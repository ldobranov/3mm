"""CAP12 reviewed inbox and separate delivery decision; no network or invocation."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import re

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction, ApplicationAuthorityGrant
from backend.db.module import ApplicationExtensionInstallation
from backend.applications.authority import management
from backend.applications.authority.keys import AuthorityReviewKeyError
from backend.applications.authority.policy_reviews import PolicyReviewStoreError, _actor
from backend.applications.public_web.routes import ApplicationPublicWebError, require_reviewed_webhook_route
from backend.applications.authority.metadata import (
    AuthorityMetadataError, authority_transaction, read_application_authority, read_authority_guard,
)
from packages.protocol.public_webhooks import WebhookRejected


@dataclass(frozen=True, slots=True)
class ReviewedWebhookTarget:
    installation_id: int
    instance_id: str
    package_sha256: str


@dataclass(frozen=True, slots=True)
class WebhookHostTarget:
    module_id: str
    instance_id: str
    artifact_sha256: str
    socket_path: str | None
    operation_id: str
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class _ReviewedBinding:
    target: ReviewedWebhookTarget
    core_generation: str
    review_key_id: str
    incarnation: str
    epoch: str
    grant_revision: str
    webhook_id: str
    path: str
    handler_operation_id: str
    timeout_seconds: int


def _denied():
    return WebhookRejected("Webhook installation approval is not current")


def _prepare_binding(manager, target):
    if type(target.installation_id) is not int or target.installation_id < 1:
        raise _denied()
    prepared = manager._prepare(target.installation_id)
    if (prepared.pin.sha256 != target.package_sha256
            or prepared.package.application_extension.public_webhook is None):
        raise _denied()
    return prepared


def _resolve_binding(db, key, manager, prepared, target):
    installation = db.get(ApplicationExtensionInstallation, target.installation_id, populate_existing=True)
    if (installation is None or not installation.enabled or installation.status != "active"
            or installation.instance_id != target.instance_id
            or installation.module_package_id != prepared.pin.module_package_id
            or installation.active_version != prepared.pin.version):
        raise _denied()
    grant = manager._require_current_grant(db, key, target.installation_id, prepared)
    grant_key_id = db.get(ApplicationAuthorityGrant, target.installation_id).key_id
    current = read_application_authority(db, target.installation_id)
    definition = prepared.package.application_extension
    declaration = definition.public_webhook
    handler = next(op for op in definition.operations if op.operation_id == declaration.handler_operation_id)
    return _ReviewedBinding(target, read_authority_guard(db).generation, grant_key_id,
                            current.incarnation, current.epoch, grant["revision"],
                            declaration.webhook_id, declaration.path, declaration.handler_operation_id,
                            handler.timeout_seconds)


_NO_ACTOR = object()


@contextmanager
def _current_binding(engine, target, *, actor_token=_NO_ACTOR):
    try:
        manager = management.configured_manager(engine)
        prepared = _prepare_binding(manager, target)
        # Package I/O is outside the lease. The grant resolver rechecks the
        # prepared package under the key -> authority fence lock order.
        with manager.keys.read_locked() as key, Session(engine) as db, authority_transaction(db):
            if actor_token is not _NO_ACTOR:
                _actor(db, actor_token)
            yield db, key, _resolve_binding(db, key, manager, prepared, target)
    except (management.AuthorityManagementError, AuthorityMetadataError, AuthorityReviewKeyError,
            PolicyReviewStoreError, SQLAlchemyError, OSError):
        raise _denied() from None


@dataclass(frozen=True, slots=True, init=False)
class ReviewedWebhookAdmission:
    """Explicit trusted lab selection; never construct from request headers."""

    _engine: Engine
    _binding: _ReviewedBinding
    _head_id: str
    audience: str
    path: str
    binding_sha256: str

    def __init__(self, engine, target: ReviewedWebhookTarget, *, audience: str):
        if not isinstance(audience, str) or re.fullmatch(r"[0-9a-f]{32}", audience) is None:
            raise _denied()
        object.__setattr__(self, "_engine", engine)
        object.__setattr__(self, "audience", audience)
        with _current_binding(engine, target) as (_, _, binding):
            object.__setattr__(self, "_binding", binding)
        object.__setattr__(self, "path", binding.path)
        identity = asdict(binding)
        # The package digest already pins the timeout; keep existing inbox and
        # approval identities stable when that derived value becomes observable.
        del identity["timeout_seconds"]
        object.__setattr__(self, "binding_sha256", _fingerprint(b"3mm.reviewed-webhook-lab.v2",
                                                              {"audience": audience, "binding": identity}))
        # One current approval per installation incarnation and declaration.
        # Different packages, grants or audiences cannot mint competing heads.
        object.__setattr__(self, "_head_id", _fingerprint(b"3mm.webhook-delivery-head.v1", {
            "installation_id": target.installation_id, "incarnation": binding.incarnation,
            "webhook_id": binding.webhook_id, "core_generation": binding.core_generation,
            "review_key_id": binding.review_key_id,
        })[:32])

    @contextmanager
    def _current(self, *, actor_token=_NO_ACTOR):
        with _current_binding(self._engine, self._binding.target, actor_token=actor_token) as (db, key, current):
            if current != self._binding:
                raise _denied()
            yield db, key

    @contextmanager
    def hold(self):
        """Authorize through the local inbox commit, release before HTTP output."""
        with self._current():
            yield

    def check_route_ownership(self) -> None:
        """Pilot startup check; never load other packages under the review-key lease."""
        try:
            with Session(self._engine) as db:
                require_reviewed_webhook_route(db, self._binding.target.installation_id, self.path)
        except (ApplicationPublicWebError, SQLAlchemyError, OSError):
            raise WebhookRejected("Reviewed public webhook route is unavailable or overlaps another route") from None
        with self._current():
            pass

    def _approval(self, db, key):
        row = db.get(ApplicationAuthorityAction, self._head_id)
        if row is None:
            return None, None
        try:
            approval = management._load(db, key, "action", row, self._head_id)
        except (TypeError, ValueError):
            raise _denied() from None
        if (approval["installation_id"] != self._binding.target.installation_id
                or approval["state"] not in {"approved", "revoked"}
                or not isinstance(approval["data"], dict)
                or set(approval["data"]) != {"operation", "binding_sha256"}
                or approval["data"]["operation"] != "webhook_delivery_head"):
            raise _denied()
        return row, approval

    def review_delivery(self, *, actor_token):
        """Authenticated review of the exact target, without granting access."""
        with self._current(actor_token=actor_token) as (db, key):
            _, approval = self._approval(db, key)
            state = "not_approved"
            if approval is not None:
                state = approval["state"] if approval["data"]["binding_sha256"] == self.binding_sha256 else "stale"
            return {"state": state, "revision": approval["revision"] if approval else None,
                    "binding_sha256": self.binding_sha256, "webhook_id": self._binding.webhook_id,
                    "path": self.path, "handler_operation_id": self._binding.handler_operation_id,
                    "instance_id": self._binding.target.instance_id,
                    "package_sha256": self._binding.target.package_sha256, "audience": self.audience}

    def decide_delivery(self, *, actor_token, request_id, binding_sha256, expected_revision, decision, confirmed):
        """Separate sealed, audited local admin decision. No event can be sent here."""
        if (confirmed is not True or decision not in ("approve", "revoke")
                or binding_sha256 != self.binding_sha256 or request_id == self._head_id
                or expected_revision is not None and (not isinstance(expected_revision, str)
                    or re.fullmatch(r"[0-9a-f]{32}", expected_revision) is None)):
            raise _denied()
        target = self._binding.target
        request = {"binding_sha256": binding_sha256, "expected_revision": expected_revision, "decision": decision}
        try:
            manager = management.configured_manager(self._engine)
            prepared = _prepare_binding(manager, target)
            with manager._write(target.installation_id, actor_token, request_id,
                                "webhook_delivery_" + decision, request) as (db, key, _, _, result):
                if result:
                    return result  # Historical receipt; never a delivery permit.
                if _resolve_binding(db, key, manager, prepared, target) != self._binding:
                    raise _denied()
                row, approval = self._approval(db, key)
                if (approval["revision"] if approval else None) != expected_revision:
                    raise _denied()
                if decision == "revoke" and (approval is None or approval["state"] != "approved"
                        or approval["data"]["binding_sha256"] != binding_sha256):
                    raise _denied()
                state = "approved" if decision == "approve" else "revoked"
                record = management._envelope("action", self._head_id, target.installation_id,
                    state, {"operation": "webhook_delivery_head", "binding_sha256": binding_sha256})
                management._save(db, key, "action", row or ApplicationAuthorityAction(
                    request_id=self._head_id, installation_id=target.installation_id), record)
                result.update(state=state, revision=record["revision"], binding_sha256=binding_sha256)
                return result
        except (management.AuthorityManagementError, OSError, SQLAlchemyError):
            raise _denied() from None

    @contextmanager
    def hold_delivery(self):
        """Pin the delivery target; a caller can durably claim while fenced."""
        with self._current() as (db, key):
            _, approval = self._approval(db, key)
            if (approval is None or approval["state"] != "approved"
                    or approval["data"]["binding_sha256"] != self.binding_sha256):
                raise _denied()
            target = self._binding.target
            installation = db.get(ApplicationExtensionInstallation, target.installation_id)
            yield WebhookHostTarget(installation.module_id, target.instance_id, target.package_sha256,
                                    installation.socket_path, self._binding.handler_operation_id,
                                    self._binding.timeout_seconds)


def _fingerprint(domain, value):
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(domain + b"\0" + canonical).hexdigest()
