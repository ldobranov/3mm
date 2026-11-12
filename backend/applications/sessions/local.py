"""Opt-in Core-local adapter for declared SDK providers, never SSH or Node routing.

Uses the existing capability registry's adapter boundary (like agent modules),
not a second user-selected discovery source. Metadata may be reviewed while an
application is disabled; runtime admission separately requires it to be active.
No key creation, human/service approval, code import or launch during discovery.
"""

import hashlib
import io
import json
import os
import stat
import threading
import zipfile
from collections import OrderedDict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.identity import AgentIdentity
from backend.config import get_settings
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import (
    ModulePackage,
)
from backend.artifacts.packages import MAX_PACKAGE_BYTES
from components.system_runtime.session_worker_client import (
    SOCKET_PATH, HOST_SOCKET_PATH, SandboxedSessionProvider, HostAccountSessionProvider,
)
from components.system_runtime.host_session_policy import read_host_session_policy
from packages.protocol.application_sessions import HostSessionAccountV1

_prepared = OrderedDict()
_prepared_lock = threading.Lock()


def remember_prepared(package):
    """Only authoritative package validation, OUTSIDE key/read-snapshot leases.

    This bounded declaration cache grants nothing. Every session is self-provided
    and its calling M20 manager re-reads/re-hashes that exact installed artifact
    before every authority check. A cold/evicted cache fails closed, never imports.
    """
    if (
        package.application_extension
        and package.application_extension.session_providers
    ):
        with _prepared_lock:
            _prepared[package.sha256] = package
            _prepared.move_to_end(package.sha256)
            while len(_prepared) > 128:
                _prepared.popitem(last=False)


def enabled():
    return os.getenv("THREE_MM_LOCAL_SESSIONS") == "1"


def local_device_id():
    if not enabled() or os.name != "posix":
        return None
    path = get_settings().backups.agent_data_dir / "identity.json"
    # Read existing local identity only; no creation and no network hello.
    for component in (path, *path.parents):
        info = component.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or info.st_uid not in {0, os.geteuid()}
            or info.st_mode & 0o022
        ):
            raise ValueError("Local session identity path is untrusted")
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError("Local session identity exceeds bounds")
    return AgentIdentity.model_validate_json(raw).device_id


def supervisor_available():
    if not enabled():
        return False
    return _socket_available(SOCKET_PATH)


def _socket_available(endpoint):
    try:
        for path in (endpoint, *endpoint.parents):
            info = path.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or info.st_uid != 0
                or info.st_mode & (0o002 if path == endpoint else 0o022)
            ):
                return False
        return (
            stat.S_ISSOCK(endpoint.lstat().st_mode)
            and Path("/sys/fs/cgroup/cgroup.controllers").is_file()
        )
    except OSError:
        return False


def host_supervisor_available():
    if not enabled():
        return False
    try:
        read_host_session_policy()
        return _socket_available(HOST_SOCKET_PATH)
    except (ValueError, OSError, KeyError):
        return False


def provider_supervisor_available(metadata):
    profile = metadata.get('resource_profile')
    if profile == 'host_account_session_v1':
        return host_supervisor_available()
    return profile == 'isolated_session_v1' and supervisor_available()


def _host_account():
    policy = read_host_session_policy()
    return HostSessionAccountV1(resource_profile='host_account_session_v1',
        account=policy.account, uid=policy.uid, gid=policy.gid,
        home=policy.home, policy_sha256=policy.sha256)


def _installed(db):
    rows = db.execute(
        select(Installation, ModulePackage)
        .join(ModulePackage, Installation.module_package_id == ModulePackage.id)
        .order_by(Installation.id)
        .limit(65)
    ).all()
    if len(rows) > 64:
        raise ValueError("Local session installation limit reached")
    for installation, row in rows:
        if installation.active_version != row.version or (
            installation.status,
            installation.enabled,
        ) not in {("active", True), ("disabled", False)}:
            continue
        # Untrusted persisted metadata can only opt into validation, not execute.
        if (
            row.manifest.get("entrypoints", {}).get("core")
            != "application-extension.json"
        ):
            continue
        with _prepared_lock:
            package = _prepared.get(row.sha256)
        if package is None:
            continue
        if (
            package.manifest.module_id != installation.module_id
            or package.manifest.version != installation.active_version
        ):
            raise ValueError("Session installation changed")
        if package.application_extension is not None:
            yield installation, package


def provider_offers(db, device):
    if not enabled():
        return []
    try:
        if local_device_id() != device.device_id:
            return []  # A remote device ID never selects a local process.
        offers = []
        for installation, package in _installed(db):
            for declaration in package.application_extension.session_providers:
                host = None
                if declaration.resource_profile == 'host_account_session_v1':
                    try:
                        host = _host_account()
                    except (ValueError, OSError, KeyError):
                        continue  # Disabled/broken host policy grants no offer.
                offers.append(
                    {
                        "capability_id": declaration.capability_id,
                        "provider_type": "core_application",
                        "provider_id": installation.module_id,
                        "provider_version": installation.active_version,
                        "metadata": {
                            "interactive_session_contract": json.dumps(
                                declaration.contract.model_dump(mode="json"),
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            "package_artifact_sha256": package.sha256,
                            "installation_incarnation": installation.authority_incarnation,
                            "instance_id": installation.instance_id,
                            "factory": declaration.factory,
                            "resource_profile": declaration.resource_profile,
                            **({'host_account': host.model_dump_json()} if host is not None else {}),
                        },
                        "configured": True,
                        "requires_health": False,
                        "local_active": installation.enabled
                        and installation.status == "active",
                    }
                )
        if len(offers) > 64:
            return []
        return offers
    except (ValueError, OSError, KeyError, TypeError):
        return []  # No partial or fallback registration from a broken source.


def runtime_offer(db, resource):
    from backend.db.device import Device

    device = db.scalar(
        select(Device).where(Device.device_id == resource["target_device_id"])
    )
    if device is None:
        return None
    declaration = resource["declaration"]
    # A different provider app needs separate code-trust authority. The first
    # profile is self-provided: this consumer's native review covers its wheel.
    if resource["owner"]["module_id"] != declaration["provider_id"]:
        return None
    offers = [
        offer
        for offer in provider_offers(db, device)
        if offer["local_active"]
        and offer["provider_id"] == declaration["provider_id"]
        and offer["provider_version"] == resource["provider_version"]
        and offer["capability_id"] == declaration["capability_id"]
    ]
    if len(offers) != 1:
        return None
    offer = offers[0]
    if (
        offer["metadata"]["package_artifact_sha256"]
        != resource["package_artifact_sha256"]
        or offer["metadata"]["installation_incarnation"]
        != resource["owner"]["incarnation"]
    ):
        return None
    if not provider_supervisor_available(offer['metadata']):
        return None
    # Recompute the exact registry/control/policy generation, not just the app
    # name or a valid old grant. A changed account/policy cannot use old review.
    from backend.applications.authority.context import AuthorityPrincipal
    from backend.applications.authority.sources import _session, _Unavailable
    from packages.protocol.application_sessions import ApplicationSessionBindingV1
    try:
        current = _session(db, ApplicationSessionBindingV1.model_validate(declaration),
            {declaration['target_device_config_key']: resource['target_device_id']},
            AuthorityPrincipal.model_validate(resource['owner']), resource['package_artifact_sha256'])
        if (current.control_revision != resource['control_revision']
                or current.model_dump(mode='json').get('host_account') != resource.get('host_account')):
            return None
    except (_Unavailable, ValueError, KeyError, TypeError, OSError):
        return None
    return offer


def runtime_for_resource(engine, resource):
    from backend.applications.sessions.runtimes import ReviewedSessionRuntime

    with Session(engine) as db:
        offer = runtime_offer(db, resource)
        if offer is None:
            return None
        for installation, package in _installed(db):
            if installation.module_id != offer["provider_id"]:
                continue
            path = (
                get_settings().backend.uploads_dir
                / "modules"
                / (package.sha256 + ".zip")
            )
            if path.is_symlink():
                return None
            with path.open("rb") as stream:
                raw = stream.read(MAX_PACKAGE_BYTES + 1)
            if hashlib.sha256(raw).hexdigest() != package.sha256:
                return None
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                wheel = archive.read(package.application_extension.service.artifact)
            host = offer['metadata']['resource_profile'] == 'host_account_session_v1'
            generation = host_supervisor_generation() if host else supervisor_generation()
            if generation is None:
                return None
            if host:
                reviewed = HostSessionAccountV1.model_validate_json(offer['metadata']['host_account'], strict=True)
                provider = HostAccountSessionProvider(wheel=wheel, factory=offer['metadata']['factory'],
                    provider_id=installation.module_id, policy_sha256=reviewed.policy_sha256)
                def current():
                    try:
                        return (host_supervisor_generation() == generation
                                and _host_account() == reviewed)
                    except (ValueError, OSError, KeyError):
                        return False
            else:
                provider = SandboxedSessionProvider(wheel=wheel, factory=offer['metadata']['factory'],
                    provider_id=installation.module_id)
                current = lambda: supervisor_generation() == generation
            return ReviewedSessionRuntime(
                resource["target_device_id"],
                installation.module_id,
                installation.active_version,
                resource["control_revision"],
                provider, current,
            )
    return None



def supervisor_generation():
    if not supervisor_available():
        return None
    try:
        info = SOCKET_PATH.lstat()
        return info.st_dev, info.st_ino, info.st_ctime_ns
    except OSError:
        return None


def host_supervisor_generation():
    if not host_supervisor_available():
        return None
    try:
        info = HOST_SOCKET_PATH.lstat()
        return info.st_dev, info.st_ino, info.st_ctime_ns
    except OSError:
        return None


class LocalSessionRuntime:
    """Local execution source behind the common, exact resource boundary."""

    def available(self, db, resource):
        return runtime_offer(db, resource) is not None

    def resolve(self, engine, resource):
        return runtime_for_resource(engine, resource)
