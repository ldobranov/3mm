"""Trusted composition of session executors; discovery and connectivity grant nothing.

Sources are installed by the platform composition root, never an application,
provider hello or browser. Each source probes without launching/importing code,
then resolves the exact M20 resource to a disposable SDK provider. Ambiguity is
unavailable, not a preference order or a local/SSH fallback. A source must pin
its connection/process generation and check it throughout an admitted session.
"""

from dataclasses import dataclass
from copy import deepcopy
import threading
from typing import Callable, Protocol
from weakref import WeakKeyDictionary

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ReviewedSessionRuntime:
    device_id: str
    provider_id: str
    provider_version: str
    control_revision: str
    provider: object
    is_current: Callable[[], bool]


class SessionRuntimeSource(Protocol):
    def available(self, db, resource: dict) -> bool: ...
    def resolve(self, engine, resource: dict) -> ReviewedSessionRuntime | None: ...


class SessionRuntimeDirectory:
    def __init__(self, sources):
        self.sources = tuple(sources)
        if not 1 <= len(self.sources) <= 8 or any(
            not callable(getattr(source, method, None))
            for source in self.sources for method in ("available", "resolve")
        ):
            raise ValueError("Session runtime sources are outside bounds")

    def _select(self, db, resource):
        selected = []
        try:
            for source in self.sources:
                result = source.available(db, deepcopy(resource))
                if type(result) is not bool:
                    return None
                if result:
                    selected.append(source)
        except Exception:
            return None  # A broken source cannot silently select another route.
        return selected[0] if len(selected) == 1 else None

    def available(self, db, resource):
        return self._select(db, resource) is not None

    def resolve(self, engine, resource):
        identity = (resource["target_device_id"], resource["declaration"]["provider_id"],
                    resource["provider_version"], resource["control_revision"])
        with Session(engine) as db:
            source = self._select(db, resource)
        if source is None:
            return None
        # Code/wheel I/O is outside the caller's authority snapshot/key lease.
        try:
            runtime = source.resolve(engine, deepcopy(resource))
            if type(runtime) is not ReviewedSessionRuntime or (
                runtime.device_id, runtime.provider_id, runtime.provider_version,
                runtime.control_revision,
            ) != identity or not callable(runtime.is_current) or runtime.is_current() is not True:
                return None
            if not all(callable(getattr(runtime.provider, name, None)) for name in
                       ("open", "receive", "control", "close", "read_output")):
                return None
            return runtime
        except Exception:
            return None


_directories = WeakKeyDictionary()
_lock = threading.RLock()


def _engine(bind):
    return getattr(bind, "engine", bind)


def configure_session_runtimes(engine, sources):
    """Composition-root only; replacing a live directory requires a fresh runtime.

    No endpoint, plugin registration, token or credential is accepted here.
    Existing sessions retain their own exact source generation until cleanup.
    """
    directory = SessionRuntimeDirectory(sources)
    with _lock:
        engine = _engine(engine)
        if engine in _directories:
            raise ValueError("Session runtime composition is already initialized")
        _directories[engine] = directory
    return directory


def session_runtimes(bind):
    engine = _engine(bind)
    with _lock:
        directory = _directories.get(engine)
        if directory is None:
            from backend.services.application_local_sessions import LocalSessionRuntime
            from backend.services.application_remote_sessions import configured_remote_sources
            directory = SessionRuntimeDirectory((LocalSessionRuntime(), *configured_remote_sources()))
            _directories[engine] = directory
        return directory


def configured_browser_service(engine):
    from backend.config import get_settings
    from backend.services.application_authority_management import configured_manager
    from backend.services.application_browser_sessions import ApplicationBrowserSessions
    from backend.services.application_session_authority import M20SessionAuthority

    settings = get_settings()
    origins = set(settings.backend.cors_origins) | {settings.frontend.frontend_url}
    if not origins or "*" in origins:
        raise ValueError("Exact session browser origins required")
    directory = session_runtimes(engine)
    return ApplicationBrowserSessions(
        M20SessionAuthority(configured_manager(engine)),
        runtime_resolver=lambda resource: directory.resolve(engine, resource),
        allowed_origins=origins,
    )
