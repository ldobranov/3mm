"""Bounded, metadata-only observations of trusted local executor principals.

Never contact a connector destination, remote peer, application handler or task.
Filesystem paths and operating-system principals come from host configuration.
"""
import hashlib
import json
import re
import socket
import time
import uuid

from three_mm_platform_wire import peer_identity, process_generation, read_frame


def _uid(name):
    import pwd
    return pwd.getpwnam(name).pw_uid


def observe(kind, settings):
    try:
        if kind == 'connector':
            from three_mm_platform_runtime.connector_worker import probe_worker
            value = probe_worker(settings.connector_worker_socket, expected_uid=_uid(settings.connector_worker_user))
            if type(value.get('connector_contract')) is not int: raise ValueError('Invalid connector contract')
        elif kind == 'event':
            from three_mm_platform_runtime.server import probe_runtime
            value = probe_runtime(settings.runtime_socket, expected_uid=_uid(settings.runtime_user),
                require_events=True, require_connectors=False)
            if any(type(value.get(key)) is not int for key in ('authority_contract','event_delivery_contract')):
                raise ValueError('Invalid event contract')
        elif kind == 'task':
            nonce = uuid.uuid4().hex
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                connection.settimeout(2); connection.connect(str(settings.task_worker_socket))
                pid, uid, _ = peer_identity(connection)
                if uid != _uid(settings.runtime_user): raise ValueError('Unexpected task principal')
                generation = process_generation(pid, uid)
                connection.sendall(json.dumps({'task_probe':nonce}).encode()+b'\n')
                value = read_frame(connection, time.monotonic()+2, max_bytes=1024)
                if (set(value) != {'task_probe','task_execution_contract','pid','ready'}
                        or value['task_probe'] != nonce or type(value['task_execution_contract']) is not int
                        or value['task_execution_contract'] != 1 or type(value['pid']) is not int
                        or value['pid'] != pid or type(value['ready']) is not bool
                        or process_generation(pid,uid) != generation): raise ValueError('Invalid task probe')
                if not value['ready']: return 'unavailable'
        else: raise ValueError('Unsupported provider profile')
        return 'ready'
    except (FileNotFoundError, ConnectionRefusedError): return 'unavailable'
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, ImportError): return 'unknown'


def observe_host(runtime, secret, prepared, configuration):
    try:
        from deployment.application_host_component import _host_call
        from three_mm_runtime.application_host_identity import HOST_CONTRACT
        pid, uid, value = _host_call(runtime[1].with_name('service.sock'), secret,
            'three_mm.task.info', _uid('3mm-app'))
        if (set(value) != {'host_contract','build_id','task_execution_contract','artifact_sha256',
                'module_id','configuration_sha256','pid','uid','instance_id','metadata_sha256'}
                or type(value['host_contract']) is not int or value['host_contract'] != HOST_CONTRACT
                or type(value['task_execution_contract']) is not int or value['task_execution_contract'] != 1
                or value['pid'] != pid or value['uid'] != uid or value['instance_id'] != runtime[0]
                or value['artifact_sha256'] != prepared.pin.sha256
                or value['module_id'] != prepared.pin.module_id
                or value['configuration_sha256'] != hashlib.sha256(json.dumps(configuration,
                    sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
                or not re.fullmatch('[0-9a-f]{64}', value['metadata_sha256'])):
            raise ValueError('Unconfirmed host metadata')
        return 'ready'
    except (FileNotFoundError, ConnectionRefusedError): return 'unavailable'
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, ImportError): return 'unknown'
