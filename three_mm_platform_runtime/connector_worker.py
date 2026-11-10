"""Network-only connector executor. No Core imports, DB, keys or replay queue."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time

from three_mm_platform_wire import canonical, peer_identity, read_frame
from three_mm_platform_runtime.connector_execute import failure
from three_mm_platform_runtime.server import PlatformRuntime, _frame, build_identity

CONTRACT = 1


class ConnectorWorker(PlatformRuntime):
    def __init__(self, path, *, core_uid, build_id="source", socket_group=None):
        super().__init__(path, path, core_uid=core_uid, build_id=build_id, socket_group=socket_group)
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(4)
        self.children = set()

    def request_stop(self, *_args):
        super().request_stop()
        with self.lock: children = list(self.children)
        for child in children:
            try: child.kill()
            except ProcessLookupError: pass

    def _serve(self, connection):
        try:
            with connection:
                # Identity before reading any plan or allocating a network child.
                uid = peer_identity(connection)[1]
                if uid not in {0, self.core_uid}: return
                request = read_frame(connection, time.monotonic() + 3)
                if set(request) == {"connector_probe"}:
                    response = {"connector_probe": request["connector_probe"], "connector_contract": CONTRACT,
                        "build_id": self.build_id, "pid": os.getpid(), "ready": True}
                else:
                    if uid != self.core_uid: return
                    if (set(request) != {"connector_contract", "plan", "result_key"}
                            or type(request["connector_contract"]) is not int or request["connector_contract"] != CONTRACT): return
                    plan = request["plan"]
                    key = bytes.fromhex(request["result_key"])
                    if len(key) != 32 or not 0 < plan["timeout_seconds"] <= 30: return
                    command = [sys.executable, "-I", "-S", str(Path(sys.argv[0]).absolute()), "--connector-execute"]
                    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, close_fds=True)
                    with self.lock:
                        self.children.add(child)
                        if self.stop_event.is_set(): child.kill()
                    try:
                        try:
                            output, _ = child.communicate(_frame(plan), timeout=plan["timeout_seconds"])
                            if child.returncode: raise ValueError("Connector child failed")
                            response = json.loads(output)
                        except subprocess.TimeoutExpired:
                            child.kill(); child.communicate()
                            response = failure(plan["method"], "response_timeout")
                        except (ValueError, OSError):
                            response = failure(plan["method"], "worker_failed")
                    finally:
                        if child.poll() is None: child.kill()
                        child.wait()
                        with self.lock: self.children.discard(child)
                    response["signature"] = hmac.new(key, canonical(response), hashlib.sha256).hexdigest()
                connection.settimeout(1); connection.sendall(_frame(response))
        except (OSError, ValueError, TypeError, KeyError, RecursionError): pass
        finally:
            connection.close()
            with self.lock: self.connections.discard(connection); self.workers.discard(threading.current_thread())
            self.slots.release()


def probe_worker(path, *, expected_uid, expected_build=None):
    import uuid
    nonce = uuid.uuid4().hex
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(3); connection.connect(str(path))
        pid, uid, _ = peer_identity(connection)
        if uid != expected_uid: raise ValueError("Connector principal is not trusted")
        connection.sendall(_frame({"connector_probe": nonce}))
        result = read_frame(connection, time.monotonic() + 3)
    if (result.get("connector_probe") != nonce or result.get("connector_contract") != CONTRACT
            or result.get("pid") != pid or result.get("ready") is not True
            or (expected_build is not None and result.get("build_id") != expected_build)):
        raise ValueError("Connector readiness is unconfirmed")
    return result


def main(argv=None):
    import argparse, pwd
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, default=Path("/run/3mm-connectors/worker.sock"))
    parser.add_argument("--core-user", default="3mm")
    parser.add_argument("--core-uid", type=int)
    parser.add_argument("--socket-group")
    args = parser.parse_args(argv)
    if os.geteuid() == 0: raise ValueError("Connector worker must not run as root")
    uid = args.core_uid if args.core_uid is not None else pwd.getpwnam(args.core_user).pw_uid
    worker = ConnectorWorker(args.socket, core_uid=uid, build_id=build_identity(), socket_group=args.socket_group)
    signal.signal(signal.SIGTERM, worker.request_stop); signal.signal(signal.SIGINT, worker.request_stop)
    try: worker.start(); worker.serve_forever()
    finally: worker.close()
    return 0
