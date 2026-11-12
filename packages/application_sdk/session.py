"""M21 session-provider interface exposed to supervised application extensions.

This additive SDK 1.3 surface defines the provider contract a reviewed application
can implement; it does NOT start processes, grant authority, or establish OS
isolation. Core/runtime admission and review remain separate responsibilities.

Provider code never binds its own TCP port or reaches Core databases/secrets.
The explicit process-profile guard below only verifies an already established
OS boundary. It cannot create isolation, grant authority or launch a child.

The ``SessionProvider`` protocol here is the single public contract. The Core
runtime adapter (``backend.sessions.broker``) is structurally
identical, so a provider written against this SDK works without Core changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

from packages.protocol.interactive_session import (
    SESSION_CAPABILITY_PATTERN,
    SESSION_CONTRACT_VERSION_PATTERN,
    SESSION_CONTROL_ACTION_PATTERN,
)
from packages.protocol.module_manifest import MODULE_ID_PATTERN

SESSION_SDK_ERROR = "core.unsupported_session"
HOST_SESSION_PROFILE = "host_account_session_v1"
HOST_SESSION_ACCOUNT = "3mm-terminal"
HOST_SESSION_HOME = "/var/lib/3mm-terminal"


class SessionProviderError(RuntimeError):
    """A provider cannot satisfy a session request/operation."""


@dataclass(frozen=True, slots=True)
class SessionTargetLimits:
    """Advisory per-session bounds a provider advertises for review.

    These are declaration metadata validated by M20 review, not OS quota or
    hostile-code isolation. Enforcement is a runtime/WP4 concern.
    """

    max_sessions: int = 1
    max_buffer_bytes: int = 65536
    idle_timeout_seconds: int = 900
    max_lifetime_seconds: int = 14400

    def __post_init__(self) -> None:
        if not 1 <= self.max_sessions <= 64:
            raise ValueError("Session max_sessions is outside bounds")
        if not 1024 <= self.max_buffer_bytes <= 64 * 1024 * 1024:
            raise ValueError("Session buffer bound is outside supported bounds")
        if not 1 <= self.idle_timeout_seconds <= 86400:
            raise ValueError("Session idle timeout is outside bounds")
        if not 1 <= self.max_lifetime_seconds <= 86400 * 7:
            raise ValueError("Session maximum lifetime is outside bounds")
        if self.idle_timeout_seconds > self.max_lifetime_seconds:
            raise ValueError("Session idle timeout cannot exceed maximum lifetime")


@dataclass(frozen=True, slots=True)
class SessionContext:
    """Runtime-supplied identity for one session; never a package-supplied claim.

    Core resolves these values from the authenticated installed service and the
    current granting authority. Providers must not trust caller payloads for
    identity.
    """

    session_id: str
    device_id: str
    capability_id: str
    access_mode: str
    options: Mapping[str, object] = field(default_factory=dict)


@runtime_checkable
class SessionProvider(Protocol):
    """Interface an installed application implements to serve one session type.

    ``provider_id``, ``contract_version`` and ``capability_ids`` are validated
    before the provider is eligible for review; they never self-authorize.

    ``receive`` returns the provider's outbound bytes for the delivered input
    (an echo returns the same bytes; a counter returns its next value). A real
    provider may also push outbound frames asynchronously through the gateway;
    the return value is the synchronous, testable path.
    """

    provider_id: str
    capability_ids: tuple[str, ...]
    control_actions: tuple[str, ...]

    async def open(self, context: Mapping[str, object]) -> None: ...

    async def receive(self, session_id: str, data: bytes) -> bytes: ...

    async def control(self, session_id: str, message: Mapping[str, object]) -> None: ...

    async def close(self, session_id: str, reason: str) -> None: ...


@runtime_checkable
class SessionOutputProvider(SessionProvider, Protocol):
    """Optional independent output stream over the SAME session contract.

    Await one nonempty, bounded chunk, or return ``None`` at EOF. A pending
    read must be cancellable and must not block receive/control/close. There
    is no polling, route selection or transport/authentication in this API.
    The runtime supplies backpressure, current-authority checks and framing.
    Existing request/response providers need not implement this extension.
    """

    async def read_output(self, session_id: str) -> bytes | None: ...


def validate_session_provider_metadata(
    *,
    provider_id: str,
    contract_version: str,
    capability_ids: tuple[str, ...] | list[str],
    control_actions: tuple[str, ...] | list[str] = (),
) -> None:
    """Validate declaration metadata; raises without performing any I/O."""
    if not re.fullmatch(MODULE_ID_PATTERN, provider_id):
        raise SessionProviderError("Session provider id is invalid")
    if not re.fullmatch(SESSION_CONTRACT_VERSION_PATTERN, contract_version):
        raise SessionProviderError("Session contract version is invalid")
    if not capability_ids:
        raise SessionProviderError("Session provider must declare a capability")
    if len(set(capability_ids)) != len(capability_ids):
        raise SessionProviderError("Session provider capabilities must be unique")
    for item in capability_ids:
        if not re.fullmatch(SESSION_CAPABILITY_PATTERN, item):
            raise SessionProviderError("Session capability id is invalid")
    for item in control_actions:
        if not re.fullmatch(SESSION_CONTROL_ACTION_PATTERN, item):
            raise SessionProviderError("Session control action is invalid")


def require_isolated_session_process() -> None:
    """Verify the platform's existing isolated_session_v1 Linux process profile.

    Public provider SPI: no private Core/runtime import, caller credential or
    device routing. These OS checks are NOT an authorization/isolation token;
    the platform still owns M20 admission, cgroup policy and process cleanup.
    """
    import os
    import socket
    import sys
    from pathlib import Path

    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("Unprivileged Linux session sandbox required")
    if (
        not 61184 <= os.geteuid() <= 65519
        or os.getenv("THREE_MM_SESSION_PROFILE") != "isolated_session_v1"
    ):
        raise RuntimeError("Installed session sandbox identity required")
    cgroup = Path("/proc/self/cgroup").read_text()
    if re.search(
        r"/3mm-session-worker[^/]*@[^/]+\.service(?:\n|$)", cgroup
    ) is None or not re.fullmatch(r"[0-9a-f]{32}", os.getenv("INVOCATION_ID", "")):
        raise RuntimeError("Session cgroup boundary is unavailable")
    status = Path("/proc/self/status").read_text()
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    if fields.get("NoNewPrivs", "").strip() != "1" or int(
        fields.get("CapEff", "1").strip(), 16
    ):
        raise RuntimeError("Session privilege boundary is unavailable")
    for path in ("/etc/3mm", "/var/lib/3mm", "/run/3mm", "/mnt", "/home", "/root"):
        if os.access(path, os.R_OK | os.X_OK):
            raise RuntimeError("Session private paths are accessible")
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        pass
    else:
        probe.close()
        raise RuntimeError("Session network boundary is unavailable")


def require_host_account_session_process() -> None:
    """Verify the separate installed unprivileged LOCAL host-account profile.

    This does not grant access or turn an isolated worker into a host worker.
    Reviewed provider code and its children receive the fixed account's normal
    filesystem permissions, including its persistent home. Core still owns
    exact package/resource/human approval, policy freshness and cgroup cleanup.
    """
    import os
    import socket
    import sys
    from pathlib import Path

    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("Unprivileged Linux host-session process required")
    import grp
    import pwd

    account = pwd.getpwnam(HOST_SESSION_ACCOUNT)
    if (account.pw_uid != os.geteuid() or account.pw_gid != os.getegid()
            or account.pw_uid <= 0 or account.pw_gid <= 0
            or grp.getgrgid(account.pw_gid).gr_name != HOST_SESSION_ACCOUNT
            or set(os.getgroups()) - {account.pw_gid}
            or account.pw_dir != HOST_SESSION_HOME
            or account.pw_shell not in {"/usr/sbin/nologin", "/sbin/nologin", "/bin/false"}
            or os.getenv("THREE_MM_SESSION_PROFILE") != HOST_SESSION_PROFILE):
        raise RuntimeError("Installed host-session account identity required")
    home = Path(HOST_SESSION_HOME)
    info = home.lstat()
    import stat
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != account.pw_uid or info.st_gid != account.pw_gid
            or info.st_mode & 0o077):
        raise RuntimeError("Host-session account home is unavailable")
    cgroup = Path("/proc/self/cgroup").read_text()
    if (re.search(r"^0::/system\.slice/(?:[A-Za-z0-9_@.\\:-]+/)*3mm-host-session-worker@[^/\n]+\.service$", cgroup, re.MULTILINE) is None
            or not re.fullmatch(r"[0-9a-f]{32}", os.getenv("INVOCATION_ID", ""))):
        raise RuntimeError("Host-session cgroup boundary is unavailable")
    fields = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
    if (fields.get("NoNewPrivs", "").strip() != "1"
            or any(int(fields.get(name, "1").strip(), 16) for name in
                   ("CapInh", "CapPrm", "CapEff", "CapAmb"))):
        raise RuntimeError("Host-session privilege boundary is unavailable")
    for path in ("/etc/3mm", "/var/lib/3mm", "/run/3mm", "/run/3mm-public-web",
                 "/run/3mm-sessions", "/run/dbus", "/run/systemd/private", "/root"):
        if os.access(path, os.R_OK | os.X_OK):
            raise RuntimeError("Host-session platform private paths are accessible")
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            probe = socket.socket(family, socket.SOCK_STREAM)
        except OSError:
            pass
        else:
            probe.close()
            raise RuntimeError("Host-session network boundary is unavailable")


__all__ = [
    "SESSION_SDK_ERROR",
    "HOST_SESSION_PROFILE",
    "HOST_SESSION_ACCOUNT",
    "HOST_SESSION_HOME",
    "SessionProviderError",
    "SessionTargetLimits",
    "SessionContext",
    "SessionProvider",
    "SessionOutputProvider",
    "validate_session_provider_metadata",
    "require_isolated_session_process",
    "require_host_account_session_process",
]
