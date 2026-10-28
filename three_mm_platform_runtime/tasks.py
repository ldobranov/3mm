"""Optional bounded task/calendar worker; no Core imports, DB or signing keys."""
from datetime import UTC, datetime
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import threading
import time
from contextlib import contextmanager
import re

from three_mm_platform_wire import (read_frame, remaining, send_authority_frame, peer_identity,
    prepare_socket_path, socket_identity, unlink_owned_socket)
from three_mm_platform_runtime.server import _core_connection
from three_mm_platform_wire.task_time import instant, latest_occurrence


class TaskWorker:
    def __init__(self, authority_path, *, core_uid):
        self.authority_path = Path(authority_path)
        self.core_uid = core_uid
        self.stop_event = threading.Event()
        self.last_exchange = 0
        self.runner = None

    def exchange(self, request):
        deadline = time.monotonic() + 3
        connection, _, _ = _core_connection(self.authority_path, self.core_uid, deadline)
        with connection:
            send_authority_frame(connection, {"task_execution_contract": 1, **request})
            result = read_frame(connection, deadline, max_bytes=64 * 1024)
        if result.get("task_execution_contract") != 1 or set(result) != {"task_execution_contract", "task"}:
            raise ValueError("Task authority response is invalid")
        self.last_exchange = time.monotonic()
        return result["task"]

    def run_once(self):
        plan = self.exchange({"action": "claim"})
        if plan is None:
            return False
        # The signed request is already durably marked running. Neither a lost
        # reply nor a worker restart may open this application dispatch again.
        completion = {"failure": "execution_unconfirmed"}
        try:
            metadata = self.invoke(plan)
            execution = self.exchange({"action": "dispatch", "task_run_id": plan["task_run_id"],
                "lease_token": plan["lease_token"], "response": metadata})
            if not self.stop_event.is_set():
                completion = {"response": self.invoke(execution)}
        except (OSError, ValueError, TypeError, KeyError):
            pass
        if not self.stop_event.is_set():
            # One completion transmission. Its loss is resolved through SDK
            # lookup, not another handler invocation or a fabricated success.
            self.exchange({"action": "complete", "task_run_id": plan["task_run_id"],
                "lease_token": plan["lease_token"], **completion})
        return True

    @staticmethod
    def invoke(plan):
        if (set(plan) != {"task_run_id", "lease_token", "socket_path", "timeout_seconds", "request"}
                or type(plan["timeout_seconds"]) not in (int, float) or not 0 < plan["timeout_seconds"] <= 10):
            raise ValueError("Task plan exceeds its execution budget")
        deadline = time.monotonic() + plan["timeout_seconds"]
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as service:
            service.settimeout(remaining(deadline)); service.connect(plan["socket_path"])
            service.sendall(json.dumps(plan["request"], separators=(",", ":")).encode() + b"\n")
            return read_frame(service, deadline, max_bytes=64 * 1024)

    def run(self):
        self.runner = threading.current_thread()
        while not self.stop_event.is_set():
            try:
                self.poll_schedules()
                worked = self.run_once()
            except (OSError, ValueError, TypeError, KeyError):
                self.last_exchange = 0
                worked = False
            if not worked:
                self.stop_event.wait(.2)

    @contextmanager
    def readiness_socket(self, path):
        """Metadata only; a probe cannot claim, dispatch or tick a task."""
        path = Path(path)
        prepare_socket_path(path)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        identity = None
        stopped = threading.Event()
        def serve():
            while not stopped.is_set():
                try:
                    connection, _ = server.accept()
                except TimeoutError: continue
                except OSError: return
                try:
                    with connection:
                        if peer_identity(connection)[1] not in {0, self.core_uid}: continue
                        request = read_frame(connection, time.monotonic()+1, max_bytes=1024)
                        nonce = request.get('task_probe')
                        if set(request) != {'task_probe'} or type(nonce) is not str or not re.fullmatch('[0-9a-f]{32}', nonce): continue
                        result = {'task_probe':nonce, 'task_execution_contract':1, 'pid':os.getpid(),
                            'ready':bool(self.runner and self.runner.is_alive() and not self.stop_event.is_set()
                                and 0 <= time.monotonic()-self.last_exchange <= 15)}
                        connection.settimeout(1)
                        connection.sendall(json.dumps(result,separators=(',',':')).encode()+b'\n')
                except (OSError, ValueError, TypeError): pass
        try:
            server.bind(str(path)); identity = socket_identity(path)
            path.chmod(0o660); server.listen(4); server.settimeout(.2)
            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            yield
        finally:
            stopped.set(); server.close()
            if 'thread' in locals(): thread.join(timeout=1.5)
            if identity is not None: unlink_owned_socket(path, identity)

    def poll_schedules(self):
        plans = self.exchange({"action": "schedule.poll"})
        if not isinstance(plans, list) or len(plans) > 32:
            raise ValueError("Schedule plan exceeds its budget")
        for plan in plans:
            if self.stop_event.is_set():
                return
            try:
                if set(plan) != {"schedule_id", "request_hash", "rule", "start_at", "end_at", "cursor_at"}:
                    raise ValueError("Schedule plan is invalid")
                due = latest_occurrence(plan["rule"], plan["start_at"], plan["end_at"], datetime.now(UTC))
                if due is not None and (plan["cursor_at"] is None or due > instant(plan["cursor_at"])):
                    # No mutation replay after a lost reply. The next poll reads
                    # Core's durable cursor before proposing another occurrence.
                    self.exchange({"action": "schedule.tick", "schedule_id": plan["schedule_id"],
                        "request_hash": plan["request_hash"], "due_at": due.isoformat()})
            except (OSError, ValueError, TypeError, KeyError):
                continue  # An unavailable owner/calendar must not block others.


def main(argv=None):
    import pwd
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-socket", type=Path, default=Path("/run/3mm-core-authority/authority.sock"))
    parser.add_argument('--readiness-socket', type=Path, default=Path('/run/3mm-tasks/worker.sock'))
    principal = parser.add_mutually_exclusive_group()
    principal.add_argument("--core-user", default="3mm")
    principal.add_argument("--core-uid", type=int)
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        raise ValueError("Task worker must not run as root")
    uid = args.core_uid if args.core_uid is not None else pwd.getpwnam(args.core_user).pw_uid
    worker = TaskWorker(args.authority_socket, core_uid=uid)
    signal.signal(signal.SIGTERM, lambda *_: worker.stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: worker.stop_event.set())
    with worker.readiness_socket(args.readiness_socket): worker.run()
    return 0
