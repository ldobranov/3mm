"""Core's short reservation/handoff and async wait; no app response read here."""
import asyncio
from dataclasses import dataclass
import socket
import time
import uuid

from three_mm_platform_wire import (
    decode_frame, peer_identity, process_generation, read_frame, remaining, send_authority_frame,
)

CONTRACT = 1
REPLY_BYTES = 1024 * 1024 + 1024


class ApplicationResponseError(ValueError):
    """Closed, non-sensitive Runtime observation; never proof of non-execution."""
    def __init__(self, reason):
        self.reason = reason if type(reason) is str and reason in {
            'deadline_exceeded', 'response_unconfirmed', 'response_invalid', 'transport_unavailable',
        } else 'response_invalid'
        super().__init__('Application response is unconfirmed')


@dataclass
class ResponseWaiter:
    connection: socket.socket
    nonce: str
    timeout_seconds: int = 5
    handoff_deadline: float = 0

    @classmethod
    def reserve(cls, path, runtime_uid):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            deadline = time.monotonic() + 1
            connection.settimeout(remaining(deadline)); connection.connect(str(path))
            pid, uid, _ = peer_identity(connection)
            if uid != runtime_uid: raise ValueError("Response Runtime principal is not trusted")
            process_generation(pid, uid)
            nonce = uuid.uuid4().hex
            connection.settimeout(remaining(deadline))
            send_authority_frame(connection, {"application_response_contract": CONTRACT, "reserve": nonce})
            answer = read_frame(connection, deadline, max_bytes=1024)
            if (type(answer.get("application_response_contract")) is not int
                    or answer != {"application_response_contract": CONTRACT, "reserved": nonce}):
                raise ValueError("Response Runtime reservation is unavailable")
            return cls(connection, nonce, handoff_deadline=time.monotonic()+2)
        except BaseException:
            connection.close(); raise

    def handoff(self, origin):
        self.connection.settimeout(remaining(self.handoff_deadline))
        origin.shutdown(socket.SHUT_WR)  # Kernel-enforced response-only FD, including its duplicates.
        send_authority_frame(self.connection, {"application_response_contract": CONTRACT,
            "reserved": self.nonce, "timeout_seconds": self.timeout_seconds}, origin=origin)

    def close(self):
        self.connection.close()

    async def receive(self):
        """Only the Runtime IPC socket is awaited; the app FD belongs to Runtime."""
        try:
            self.connection.setblocking(False)
            loop = asyncio.get_running_loop(); payload = bytearray()
            async with asyncio.timeout(self.timeout_seconds + 1):
                while len(payload) < REPLY_BYTES:
                    chunk = await loop.sock_recv(self.connection, min(65536, REPLY_BYTES-len(payload)))
                    if not chunk: break
                    payload.extend(chunk)
                    if b"\n" in chunk:
                        frame, _, tail = payload.partition(b"\n")
                        if tail: raise ApplicationResponseError('response_invalid')
                        answer = decode_frame(frame)
                        if (type(answer.get("application_response_contract")) is not int
                                or answer.get("application_response_contract") != CONTRACT
                                or answer.get("reserved") != self.nonce):
                            raise ApplicationResponseError('response_invalid')
                        common = {'application_response_contract', 'reserved'}
                        if set(answer) == common | {'response'}:
                            return answer['response']
                        if (set(answer) == common | {'failure'} and type(answer['failure']) is str
                                and answer['failure'] in {'deadline_exceeded', 'response_unconfirmed'}):
                            raise ApplicationResponseError(answer['failure'])
                        raise ApplicationResponseError('response_invalid')
            raise ApplicationResponseError('response_unconfirmed')
        except ApplicationResponseError:
            raise
        except TimeoutError:
            raise ApplicationResponseError('deadline_exceeded') from None
        except OSError:
            raise ApplicationResponseError('transport_unavailable') from None
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ApplicationResponseError('response_invalid') from None


# Core-owned lifecycle binding shared by health and admitted HTTP callbacks.
# These types never cross the Runtime IPC boundary.
_BINDING_FIELDS = ("instance_id", "authority_incarnation", "authority_epoch", "authority_mode",
    "module_id", "module_package_id", "active_version", "enabled", "status", "socket_path")


@dataclass(frozen=True)
class ApplicationResponseBinding:
    installation_id: int
    snapshot: tuple
    secret: bytes
    request_id: str
    operation_id: str

    @property
    def authority_mode(self):
        return self.snapshot[_BINDING_FIELDS.index('authority_mode')]


def application_snapshot(installation, package):
    return tuple(getattr(installation, field) for field in _BINDING_FIELDS) + (package.sha256,)


def application_fence(binding):
    from sqlalchemy import select
    from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
    values = dict(zip(_BINDING_FIELDS, binding.snapshot))
    return (Installation.id == binding.installation_id,
        *(getattr(Installation, field) == value for field, value in values.items()),
        Installation.module_package_id.in_(select(ModulePackage.id).where(
            ModulePackage.id == values["module_package_id"], ModulePackage.sha256 == binding.snapshot[-1],
            ModulePackage.module_id == values["module_id"], ModulePackage.version == values["active_version"])))
