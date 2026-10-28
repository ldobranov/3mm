"""Stdlib-only local wire and socket ownership, shared by Core, SDK and Runtime."""
import hashlib
import json
import os
import socket
import stat
import struct
import time
from pathlib import Path

TRANSPORT_VERSION = 1
CONTRACT_VERSION = 1
MAX_MESSAGE_BYTES = 6 * 1024 * 1024
MAX_CONNECTIONS = 16
READ_TIMEOUT_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 35
MAX_CLOCK_SKEW_SECONDS = 30
MAX_RECENT_REQUESTS = 4096
DISCOVERY_ACTION = "platform.discover"
SCOPED_ACTIONS = frozenset({
    DISCOVERY_ACTION, "command.discover", "command.submit", "command.status", "command.lookup",
    "task.submit", "task.lookup", "task.cancel", "task.start", "task.progress",
    "task.schedule.create", "task.schedule.lookup", "task.schedule.cancel",
    "connector.request", "event.publish", "files.execute", "files.status",
    "relational.admit", "relational.complete", "relational.status",
    "relational.boot.startup", "checkpoint.get", "checkpoint.put",
    "installation.identity.get", "installation.status.get", "installation.peers.read",
    "delegation.execute", "delegation.lookup",
})
COMPATIBILITY_ACTIONS = SCOPED_ACTIONS | frozenset({
    "installation.identity.prove", "installation.peers.enroll",
    "installation.peers.list", "installation.peers.capabilities",
    "installation.peers.approve", "installation.peers.revoke",
    "installation.peers.rotate", "installation.peers.report",
})
ERROR_REASONS = frozenset({
    "request_invalid", "authentication_failed", "installation_unavailable",
    "operation_unsupported", "operation_denied", "operation_failed",
    "deadline_exceeded", "response_too_large", "request_replayed", "overloaded",
})
ENVELOPE_FIELDS = frozenset({"version", "request_id", "timestamp", "instance_id", "action", "signature"})


def canonical(value):
    return json.dumps({k: v for k, v in value.items() if k != "signature"},
                      sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate platform field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite platform value")


def decode_frame(payload):
    try:
        value = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("Platform frame is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("Platform frame is invalid")
    return value


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("Platform deadline exceeded")
    return seconds


def read_frame(connection, deadline, *, max_bytes=None):
    """One bounded frame and absolute deadline, including slow trickle traffic."""
    max_bytes = MAX_MESSAGE_BYTES if max_bytes is None else max_bytes
    payload = bytearray()
    while len(payload) < max_bytes:
        connection.settimeout(remaining(deadline))
        chunk = connection.recv(min(65536, max_bytes - len(payload)))
        if not chunk:
            break
        payload.extend(chunk)
        if b"\n" in chunk:
            frame, _, tail = payload.partition(b"\n")
            if tail:
                raise ValueError("Platform connection accepts one frame")
            return decode_frame(frame)
    raise ValueError("Platform frame is incomplete or too large")


RUNTIME_ACTIONS = COMPATIBILITY_ACTIONS
AUTHORITY_CONTRACT = 2
AUTHORITY_MAX_BYTES = MAX_MESSAGE_BYTES
AUTHORITY_CONNECTIONS = 4
AUTHORITY_READ_SECONDS = READ_TIMEOUT_SECONDS
AUTHORITY_CALL_SECONDS = 3


def peer_identity(connection):
    if not hasattr(socket, "SO_PEERCRED"):
        raise ValueError("Authenticated local process identity is unavailable")
    return struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))


def process_generation(pid, uid):
    """Kernel identity of the peer; never a forwarded PID or authority lease."""
    directory = Path(f"/proc/{pid}")
    status=(directory/"status").read_text(encoding="ascii")
    identity=next((line.split() for line in status.splitlines() if line.startswith("Uid:")),None)
    if identity is None or int(identity[2])!=uid:
        raise ValueError("Local peer identity changed")
    ticks = (directory / "stat").read_text(encoding="ascii").rpartition(") ")[2].split()[19]
    boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    return hashlib.sha256(f"{uid}:{pid}:{ticks}:{boot}".encode("ascii")).hexdigest()[:32]


def socket_identity(path: Path):
    value = path.lstat()
    return value.st_dev, value.st_ino


def prepare_socket_path(path: Path) -> None:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(value.st_mode):
        raise FileExistsError("Local listener path is occupied")
    identity = value.st_dev, value.st_ino
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        try:
            probe.connect(str(path))
        except ConnectionRefusedError:
            unlink_owned_socket(path, identity)
            return
        except FileNotFoundError:
            return
    raise FileExistsError("Local listener is already active")


def unlink_owned_socket(path: Path, identity) -> None:
    if identity is None:
        return
    try:
        if socket_identity(path) == identity:
            path.unlink()
    except FileNotFoundError:
        pass


def send_authority_frame(connection, request, *, origin=None):
    """ABI 2: one marker, optional kernel socket FD, then the original signed JSON."""
    import array
    data = json.dumps(request, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(data) > AUTHORITY_MAX_BYTES:
        raise ValueError("Authority frame exceeds its budget")
    ancillary = []
    if origin is not None:
        ancillary = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [origin.fileno()]))]
    if connection.sendmsg([b"\1" if origin is not None else b"\0"], ancillary) != 1:
        raise OSError("Authority header was not sent")
    connection.sendall(data)


def receive_authority_frame(connection, deadline):
    """Own and close every received FD, including malformed/truncated headers."""
    import array
    descriptors = []
    origin = None
    try:
        connection.settimeout(remaining(deadline))
        marker, ancillary, flags, _ = connection.recvmsg(
            1, socket.CMSG_SPACE(array.array("i").itemsize * 4), socket.MSG_CMSG_CLOEXEC)
        invalid = bool(flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC))
        for level, kind, data in ancillary:
            if level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS:
                invalid = True
                continue
            received = array.array("i")
            usable = len(data) - len(data) % received.itemsize
            received.frombytes(data[:usable])
            descriptors.extend(received)
            invalid |= usable != len(data)
        if invalid or marker not in {b"\0", b"\1"} or len(descriptors) != (marker == b"\1"):
            raise ValueError("Authority origin header is invalid")
        if descriptors:
            origin = socket.socket(fileno=descriptors[0])
            descriptors.clear()
            if (origin.family != socket.AF_UNIX or origin.type != socket.SOCK_STREAM
                    or origin.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)):
                raise ValueError("Authority origin must be a connected Unix stream")
            origin.getpeername()
            peer_identity(origin)
        request = read_frame(connection, deadline, max_bytes=AUTHORITY_MAX_BYTES)
        return request, origin
    except BaseException:
        if origin is not None:
            origin.close()
        raise
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
