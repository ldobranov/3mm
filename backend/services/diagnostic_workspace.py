"""Bounded read-only observations. Optional probe contention never queues Core work."""
import json
import socket
import threading
import time
import uuid
from three_mm_protocol.diagnostic_snapshot import component_inventory, DIGEST, ROOTS
from three_mm_protocol.diagnostics import OPERATIONS
from backend.services.operation_diagnostics import core_diagnostics
from three_mm_platform_wire import peer_identity, read_frame
from deployment.service_component import _http_identity

_PROBE = threading.Lock()


def observe(settings, lifecycle):
    rows=[{'component':'core','version':core_diagnostics.version,'build_id':None,'state':'running','health':'ready','reason':'core_management'}]
    result={'schema_version':1,'components':rows,'core_services':lifecycle,'probe_status':'busy','operations':sorted(OPERATIONS)}
    if not _PROBE.acquire(blocking=False):
        rows.extend({'component':role,'build_id':None,'state':'unknown','health':'unknown','reason':'collector_busy'} for role in ROOTS)
        return result
    try:
        rows.extend(component_inventory())
        result['probe_status']='complete'
        for row in rows:
            role=row['component']
            if role not in {'platform-runtime','agent','public-web'}: continue
            try:
                if role=='platform-runtime':
                    import pwd
                    uid=pwd.getpwnam(settings.applications.runtime_user).pw_uid
                    nonce=uuid.uuid4().hex;deadline=time.monotonic()+.4
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                        connection.settimeout(.4);connection.connect(str(settings.applications.runtime_socket))
                        if peer_identity(connection)[1]!=uid: raise ValueError('Foreign runtime principal')
                        connection.sendall(json.dumps({'runtime_probe':nonce}).encode()+b'\n')
                        value=read_frame(connection,deadline,max_bytes=8192)
                    if type(value) is not dict: raise ValueError('Invalid runtime observation')
                    if value.get('runtime_probe')!=nonce or value.get('ready') is not True: raise ValueError('Runtime not ready')
                    build=value.get('build_id')
                else:
                    value=_http_identity('http://127.0.0.1:'+('8890/component-health' if role=='agent' else '8081/__3mm_component__/health'),timeout=.3)
                    if type(value) is not dict: raise ValueError('Invalid component observation')
                    if value.get('component')!=role or type(value.get('pid')) is not int or value['pid']<=0: raise ValueError('Invalid component identity')
                    build=value.get('build_id')
                if type(build) is not str or not DIGEST.fullmatch(build): raise ValueError('Invalid loaded build')
                if row['build_id'] is not None and row['build_id']!=build: raise ValueError('Component pin mismatch')
                row.update(health='ready',reason='live_probe',loaded_build_id=build)
            except (OSError,ValueError,KeyError,ImportError,TypeError,RecursionError):
                row.update(health='unavailable',reason='probe_unavailable')
        return result
    finally: _PROBE.release()
