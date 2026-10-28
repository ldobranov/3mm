"""Bounded signed SDK transport; Core alone authenticates and admits operations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import sys
import threading
import time
import uuid
import zipfile

try:
    import grp
    import pwd
except ImportError:  # Artifact construction also runs on the Windows laptop.
    grp = pwd = None

from three_mm_platform_wire import (
    AUTHORITY_CALL_SECONDS, AUTHORITY_CONTRACT, AUTHORITY_MAX_BYTES,
    ENVELOPE_FIELDS, MAX_CONNECTIONS, READ_TIMEOUT_SECONDS, REQUEST_TIMEOUT_SECONDS, RUNTIME_ACTIONS,
    send_authority_frame, receive_authority_frame,
    peer_identity, process_generation, prepare_socket_path, socket_identity,
    unlink_owned_socket, read_frame, remaining,
)


def _frame(value):
    data=json.dumps(value,separators=(",", ":"),allow_nan=False).encode()+b"\n"
    if len(data)>AUTHORITY_MAX_BYTES:
        raise ValueError("Runtime metadata exceeds its budget")
    return data


def _core_connection(path,uid,deadline):
    connection=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        connection.settimeout(remaining(deadline));connection.connect(str(path))
        pid,current,_=peer_identity(connection)
        if current!=uid:
            raise ValueError("Core IPC principal is not trusted")
        generation=process_generation(pid,current)
        return connection,pid,generation
    except BaseException:
        connection.close();raise


def probe_core(path,uid,*,public_web=False,events=False,connectors=True,responses=False):
    nonce=uuid.uuid4().hex;deadline=time.monotonic()+AUTHORITY_CALL_SECONDS
    connection,pid,generation=_core_connection(path,uid,deadline)
    with connection:
        connection.settimeout(remaining(deadline))
        expected={"authority_contract":AUTHORITY_CONTRACT,"authority_probe":nonce}
        if public_web: expected["public_web_contract"]=1
        if events: expected["event_delivery_contract"]=1
        if connectors: expected["connector_execution_contract"]=1
        if responses: expected["application_response_contract"]=1
        send_authority_frame(connection,expected)
        result=read_frame(connection,deadline,max_bytes=AUTHORITY_MAX_BYTES)
    if result!=expected:
        raise ValueError("Core authority contract is unavailable")
    return {"core_pid":pid,"core_process_generation":generation}


def build_identity():
    archive=Path(sys.argv[0])
    if archive.suffix!=".pyz":
        return "source"
    with zipfile.ZipFile(archive) as bundle:
        data=bundle.read("runtime-build.json")
    if len(data)>8192:
        raise ValueError("Runtime build metadata is invalid")
    value=json.loads(data)
    identifier=value.get("build_id")
    if (value.get("authority_contract")!=AUTHORITY_CONTRACT
            or not isinstance(identifier,str) or re.fullmatch(r"[0-9a-f]{64}",identifier) is None):
        raise ValueError("Runtime build contract is unsupported")
    return identifier


class PlatformRuntime:
    def __init__(self,path,authority_path,*,core_uid,socket_group=None,build_id="source"):
        if type(core_uid) is not int or core_uid<=0:
            raise ValueError("Core must have an explicit non-root principal")
        self.path=Path(path);self.authority_path=Path(authority_path)
        self.core_uid=core_uid;self.socket_group=socket_group;self.build_id=build_id
        self.stop_event=threading.Event();self.server=None;self.identity=None
        self.lock=threading.Lock();self.connections=set();self.workers=set()
        self.slots=threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.responses=None
        self.public_web=None
        self.events=None

    def start(self):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        prepare_socket_path(self.path)
        server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.server=server
        try:
            server.bind(str(self.path));self.identity=socket_identity(self.path)
            os.chmod(self.path,0o660)
            if self.socket_group is not None:
                gid=grp.getgrnam(self.socket_group).gr_gid
                # A root-prepared setgid socket directory supplies the client
                # group without adding Runtime to the applications/key group.
                if self.path.stat().st_gid!=gid:os.chown(self.path,-1,gid)
            server.listen(MAX_CONNECTIONS);server.settimeout(.2)
            if self.events is not None:self.events.start()
        except BaseException:
            self.close();raise

    def request_stop(self,*_args):
        self.stop_event.set()
        if self.server is not None:self.server.close()

    def close(self):
        self.request_stop()
        with self.lock:
            connections=list(self.connections);workers=list(self.workers)
        for connection in connections:
            try:connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()
        deadline=time.monotonic()+5
        for worker in workers:
            if worker.ident is not None:worker.join(timeout=max(0,deadline-time.monotonic()))
        unlink_owned_socket(self.path,self.identity)
        self.identity=None;self.server=None

    def serve_forever(self):
        while not self.stop_event.is_set():
            try:connection,_=self.server.accept()
            except TimeoutError:continue
            except OSError:
                if self.stop_event.is_set():return
                raise
            if not self.slots.acquire(blocking=False):connection.close();continue
            worker=None
            try:
                worker=threading.Thread(target=self._serve,args=(connection,),daemon=True)
                with self.lock:self.connections.add(connection);self.workers.add(worker)
                worker.start()
            except Exception:
                with self.lock:self.connections.discard(connection);self.workers.discard(worker)
                connection.close();self.slots.release()

    def _serve(self,connection):
        try:
            with connection:
                deadline=time.monotonic()+REQUEST_TIMEOUT_SECONDS
                request=read_frame(connection,min(deadline,time.monotonic()+READ_TIMEOUT_SECONDS),
                                   max_bytes=AUTHORITY_MAX_BYTES)
                if set(request)=={"runtime_probe"}:
                    nonce=request["runtime_probe"]
                    if not isinstance(nonce,str) or re.fullmatch(r"[0-9a-f]{32}",nonce) is None:return
                    response={"runtime_probe":nonce,"build_id":self.build_id,
                        "authority_contract":AUTHORITY_CONTRACT,"pid":os.getpid(),"ready":False,
                        "connector_execution_contract":1,
                        "application_response_contract":1,"application_responses_ready":bool(self.responses and self.responses.server is not None),
                        "public_web_contract":1,"public_web_ready":bool(self.public_web and self.public_web.server is not None),
                        "event_delivery_contract":1,"event_worker_ready":bool(self.events and self.events.ready)}
                    try:
                        response.update(probe_core(self.authority_path,self.core_uid,public_web=self.public_web is not None,events=self.events is not None,responses=self.responses is not None))
                        response["ready"]=self.events is None or self.events.ready
                    except (OSError,ValueError):pass
                else:
                    if (not ENVELOPE_FIELDS <= request.keys() or not isinstance(request.get("action"),str)
                            or request["action"] not in RUNTIME_ACTIONS):return
                    # Forward exactly one original signed object. No credentials,
                    # authority keys, DB, grants, retries or response synthesis.
                    upstream,_,_=_core_connection(self.authority_path,self.core_uid,deadline)
                    with upstream:
                        upstream.settimeout(remaining(deadline))
                        send_authority_frame(upstream,request,origin=connection if request["action"]=="relational.boot.startup" else None)
                        if request["action"] == "connector.request":
                            response, origin = receive_authority_frame(upstream, deadline)
                        else:
                            origin = None
                            response=read_frame(upstream,deadline,max_bytes=AUTHORITY_MAX_BYTES)
                    if request["action"] == "connector.request" and origin is not None:
                        try:
                            timeout = response.get("timeout_seconds")
                            if (response.get("connector_execution_contract") != 1
                                    or type(timeout) is not int or not 0 < timeout <= 30):
                                raise ValueError("Invalid connector handoff")
                            with self.lock: self.connections.add(origin)
                            try:
                                answer = read_frame(origin, min(deadline-2, time.monotonic()+timeout+1))
                                completion = {"response": answer}
                            except (OSError, ValueError): completion = {"failure": "execution_unconfirmed"}
                        finally:
                            with self.lock: self.connections.discard(origin)
                            origin.close()
                        upstream,_,_=_core_connection(self.authority_path,self.core_uid,deadline)
                        with upstream:
                            upstream.settimeout(remaining(deadline))
                            send_authority_frame(upstream,{"connector_execution_contract":1,
                                "receipt":response["receipt"],**completion})
                            response=read_frame(upstream,deadline,max_bytes=AUTHORITY_MAX_BYTES)
                connection.settimeout(1);connection.sendall(_frame(response))
        except (OSError,ValueError,TypeError,RecursionError):
            pass  # A loss is never a forged signed success or permission to replay.
        finally:
            connection.close()
            with self.lock:self.connections.discard(connection);self.workers.discard(threading.current_thread())
            self.slots.release()


def probe_runtime(path,*,expected_uid,expected_build=None,require_public_web=False,require_events=False,require_connectors=True,require_responses=False):
    nonce=uuid.uuid4().hex;deadline=time.monotonic()+AUTHORITY_CALL_SECONDS+1
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(remaining(deadline));connection.connect(str(path))
        pid,uid,_=peer_identity(connection)
        if uid!=expected_uid:raise ValueError("Runtime principal is not trusted")
        connection.sendall(_frame({"runtime_probe":nonce}))
        result=read_frame(connection,deadline,max_bytes=AUTHORITY_MAX_BYTES)
    if (result.get("runtime_probe")!=nonce or result.get("pid")!=pid or result.get("ready") is not True
            or result.get("authority_contract")!=AUTHORITY_CONTRACT
            or (expected_build is not None and result.get("build_id")!=expected_build)
            or (require_connectors and result.get("connector_execution_contract")!=1)
            or (require_public_web and (result.get("public_web_contract")!=1 or result.get("public_web_ready") is not True))
            or (require_responses and (result.get("application_response_contract")!=1 or result.get("application_responses_ready") is not True))
            or (require_events and (result.get("event_delivery_contract")!=1 or result.get("event_worker_ready") is not True))):
        raise ValueError("Runtime readiness is unconfirmed")
    return result


def main(argv=None):
    if argv is None: argv=sys.argv[1:]
    if argv == ["--connector-execute"]:
        from three_mm_platform_runtime.connector_worker import execute_child
        return execute_child()
    if argv and argv[0] == "--connector-worker":
        from three_mm_platform_runtime.connector_worker import main as worker_main
        return worker_main(argv[1:])
    if argv and argv[0] == "--task-worker":
        from three_mm_platform_runtime.tasks import main as task_main
        return task_main(argv[1:])
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket",type=Path,default=Path("/run/3mm-platform/runtime.sock"))
    parser.add_argument("--authority-socket",type=Path,default=Path("/run/3mm-core-authority/authority.sock"))
    principal=parser.add_mutually_exclusive_group()
    principal.add_argument("--core-user",default="3mm");principal.add_argument("--core-uid",type=int)
    parser.add_argument("--socket-group")
    parser.add_argument("--public-web-socket",type=Path)
    parser.add_argument("--public-web-group")
    parser.add_argument("--events",action="store_true")
    parser.add_argument("--response-socket",type=Path)
    parser.add_argument("--response-group")
    args=parser.parse_args(argv)
    if os.geteuid()==0:raise ValueError("Platform Runtime must not run as root")
    uid=args.core_uid if args.core_uid is not None else pwd.getpwnam(args.core_user).pw_uid
    runtime=PlatformRuntime(args.socket,args.authority_socket,core_uid=uid,
                            socket_group=args.socket_group,build_id=build_identity())
    public=None;public_thread=None
    if args.public_web_socket is not None:
        from three_mm_platform_runtime.public_web import PublicWebRuntime
        public=PublicWebRuntime(args.public_web_socket,args.authority_socket,core_uid=uid,
                                socket_group=args.public_web_group,build_id=runtime.build_id)
        runtime.public_web=public
    response_thread=None
    if args.response_socket is not None:
        from three_mm_platform_runtime.responses import ApplicationResponses
        runtime.responses=ApplicationResponses(args.response_socket,args.authority_socket,core_uid=uid,
            socket_group=args.response_group,build_id=runtime.build_id)
    if args.events:
        from three_mm_platform_runtime.events import EventDeliveryWorker
        runtime.events=EventDeliveryWorker(args.authority_socket,core_uid=uid)
    def stop(*_args):
        runtime.request_stop()
        if runtime.responses is not None: runtime.responses.request_stop()
        if public is not None: public.request_stop()
        if runtime.events is not None: runtime.events.request_stop()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        if runtime.responses is not None:
            runtime.responses.start()
            def serve_responses():
                try: runtime.responses.serve_forever()
                finally: runtime.request_stop()
            response_thread=threading.Thread(target=serve_responses,daemon=True)
            response_thread.start()
        if public is not None:
            public.start()
            def serve_public():
                try: public.serve_forever()
                finally: runtime.request_stop()
            public_thread=threading.Thread(target=serve_public,daemon=True)
            public_thread.start()
        try:runtime.start();runtime.serve_forever()
        finally:runtime.close()
    finally:
        if runtime.events is not None: runtime.events.close()
        if runtime.responses is not None: runtime.responses.close()
        if response_thread is not None: response_thread.join(timeout=5)
        if public is not None: public.close()
        if public_thread is not None: public_thread.join(timeout=5)
    return 0
