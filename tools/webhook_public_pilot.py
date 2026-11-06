"""Opt-in CAP12 ingress for a disposable local Public Web pilot."""

import base64
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import socketserver
import sqlite3
import stat
import sys
import tempfile
from threading import Thread
import time

from three_mm_platform_wire import peer_identity, read_frame, remaining, socket_identity, unlink_owned_socket
from three_mm_protocol.public_webhooks import MAX_WEBHOOK_BYTES, WebhookRejected, validate_webhook_endpoint, verify_webhook
from three_mm_public_web.webhook_pilot import (
    PILOT_FRAME_BYTES, PILOT_ID, PILOT_SECONDS, PILOT_VERSION, WebhookPilotClient, valid_signed_fields,
)
from tools.webhook_delivery_lab import _private_root
from tools.webhook_lab import WebhookInbox


@contextmanager
def _exclusive_inbox(directory):
    import fcntl

    descriptor = os.open(directory / 'pilot.lock', os.O_CREAT | os.O_RDONLY | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('Webhook pilot lock must be private')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Stop the active webhook pilot before changing its key') from None
        yield
    finally:
        os.close(descriptor)


def _shared_directory(path):
    directory = Path(path)
    if not directory.is_absolute() or directory.resolve(strict=True) != directory:
        raise ValueError('Use an exact, pre-provisioned pilot socket directory')
    info = directory.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o2710):
        raise ValueError('Split-principal pilot requires an owner-only setgid socket directory with group traversal')
    return directory


@contextmanager
def pilot_ingress(state_dir, admission, secret, *, public_uid=None, socket_dir=None):
    """Own one private local broker, never an installed service or public socket."""
    if sys.platform != 'linux':
        raise ValueError('Webhook pilot requires Linux peer credentials')
    validate_webhook_endpoint(admission.audience, secret)
    uid = os.geteuid()
    split = socket_dir is not None
    if split != (public_uid is not None) or (split and (type(public_uid) is not int or public_uid <= 0 or public_uid == uid)):
        raise ValueError('Split-principal pilot requires a different unprivileged Public Web UID and socket directory')
    expected_uid = public_uid if split else uid
    private_dir = _private_root(state_dir)
    shared_directory = _shared_directory(socket_dir) if split else None

    class Ingress(socketserver.BaseRequestHandler):
        def handle(self):
            deadline = time.monotonic() + PILOT_SECONDS
            connection = self.request
            try:
                if peer_identity(connection)[1] != expected_uid:
                    return
                request = read_frame(connection, deadline, max_bytes=PILOT_FRAME_BYTES)
                if (set(request) != {'version', 'request_id', 'path', 'signed', 'body_base64'}
                        or type(request['version']) is not int or request['version'] != PILOT_VERSION
                        or not isinstance(request['request_id'], str) or not PILOT_ID.fullmatch(request['request_id'])
                        or request['path'] != admission.path):
                    return
                signed, encoded = request['signed'], request['body_base64']
                if (not valid_signed_fields(signed) or not isinstance(encoded, str)
                        or len(encoded) > ((MAX_WEBHOOK_BYTES + 2) // 3) * 4):
                    return
                body = base64.b64decode(encoded, validate=True)
                status, receipt = self.accept(signed, body)
                response = json.dumps({'version': PILOT_VERSION, 'request_id': request['request_id'],
                    'status': status, 'receipt_id': receipt}, separators=(',', ':')).encode('ascii') + b'\n'
                connection.settimeout(remaining(deadline))
                connection.sendall(response)
            except (OSError, ValueError):
                pass  # No echoed input, and a committed receipt is never undone.

        def accept(self, signed, body):
            event_id, timestamp, signature = signed
            try:
                proof = verify_webhook(body, audience=admission.audience, event_id=event_id,
                                       timestamp=timestamp, signature=signature, secret=secret, now=int(time.time()))
                with admission.hold():
                    return inbox.accept(proof, body)
            except WebhookRejected:
                return 403, None
            except sqlite3.Error:
                return 503, None

    with _exclusive_inbox(private_dir), ExitStack() as stack:
        admission.check_route_ownership()
        inbox = WebhookInbox(private_dir, admission.audience, admission.binding_sha256)
        socket_root = (shared_directory if shared_directory is not None else
                       stack.enter_context(tempfile.TemporaryDirectory(prefix='cap12-pilot-', dir='/tmp')))
        path = Path(socket_root) / 'ingress.sock'
        with socketserver.UnixStreamServer(str(path), Ingress) as server:
            identity = socket_identity(path)
            try:
                path.chmod(0o660 if split else 0o600)
                worker = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05})
                worker.start()
                try:
                    yield WebhookPilotClient(admission.path, path, broker_uid=uid), inbox
                finally:
                    server.shutdown()
                    worker.join()
            finally:
                unlink_owned_socket(path, identity)
