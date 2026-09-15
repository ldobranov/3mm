"""Real Unix transport checks; runnable with unittest on the Linux target."""
from contextlib import contextmanager
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from three_mm_runtime import application_transport as transport
from backend.services import application_extensions as gateway


@unittest.skipUnless(hasattr(socket, 'AF_UNIX'), 'Requires the Linux Unix-socket transport')
class ApplicationDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='3mm-startup-check-')
        self.root = Path(self.temp.name)
        self.path = self.root / 's.sock'
        self.secret = b's'*32
        self.client = transport.ApplicationServiceClient(self.path, self.secret, 0.1)

    def tearDown(self):
        self.temp.cleanup()

    @contextmanager
    def host(self, replies):
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.path)); server.listen(2); server.settimeout(2)
        requests = []
        errors = []
        def run():
            try:
                for result in replies:
                    connection, _ = server.accept()
                    with connection:
                        request = transport.read_message(connection)
                        requests.append(request)
                        if result == 'drop': continue
                        if result == 'timeout': time.sleep(0.2); continue
                        value = {'version': 1, 'timestamp': int(time.time()), 'request_id': request['request_id'],
                            'ok': True, 'result': result}
                        if result == 'extension_error':
                            value.update(ok=False, error='not_dispatched', phase='not_dispatched')
                        signed = transport.sign_message(value, self.secret)
                        if result == 'bad_signature': signed['signature'] = '0'*64
                        transport.send_message(connection, signed)
            except OSError:
                pass  # The tested client may intentionally close after partial send.
            except Exception as exc:
                errors.append(exc)
            finally:
                server.close()
        worker = threading.Thread(target=run)
        worker.start()
        try:
            yield requests
        finally:
            worker.join(timeout=3)
            server.close()
            self.path.unlink(missing_ok=True)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)

    def test_missing_and_stale_socket_are_not_dispatched(self):
        for stale in (False, True):
            if stale:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                    server.bind(str(self.path))
            with self.assertRaises(transport.ApplicationTransportError) as error:
                self.client.invoke('job', {}, {})
            self.assertEqual(error.exception.phase, transport.DispatchPhase.NOT_DISPATCHED)
            self.assertTrue(error.exception.retryable)

    def test_lost_timeout_invalid_and_extension_errors_are_unconfirmed(self):
        for reply in ('drop', 'timeout', 'bad_signature', 'extension_error', []):
            with self.subTest(reply=reply), self.host([reply]):
                with self.assertRaises(transport.ApplicationTransportError) as error:
                    self.client.invoke('job', {}, {})
                self.assertEqual(error.exception.phase, transport.DispatchPhase.EXECUTION_UNCONFIRMED)
                self.assertFalse(error.exception.retryable)

    def test_partial_send_is_unconfirmed(self):
        # Real connect and real bytes sent, then a simulated sendall failure.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.path)); server.listen(1)
            def partial(connection, request):
                connection.sendall(b'{')
                raise BrokenPipeError('partial write')
            with patch.object(transport, 'send_message', partial):
                with self.assertRaises(transport.ApplicationTransportError) as error:
                    self.client.invoke('job', {}, {})
            self.assertEqual(error.exception.phase, transport.DispatchPhase.EXECUTION_UNCONFIRMED)

    def invoke_job(self, *, before_dispatch=None):
        (self.root / ('a'*24 + '.key')).write_bytes(self.secret)
        app = SimpleNamespace(enabled=True, status='active', instance_id='a'*24, socket_path=str(self.path))
        operation = SimpleNamespace(operation_id='job', audiences=['internal'], idempotency='required',
            input_schema={}, output_schema={'properties': {'done': {'type': 'boolean'}}, 'required': ['done']}, timeout_seconds=0.1)
        with patch.object(gateway, 'load_application_definition', return_value=SimpleNamespace(operations=[operation])):
            return gateway.invoke_application(app, object(), SimpleNamespace(key_root=self.root), 'job', {},
                {'idempotency_key': 'stable'}, required_audience='internal', require_ready=True, before_dispatch=before_dispatch)

    def test_start_before_host_then_ready(self):
        with self.assertRaises(gateway.ApplicationGatewayError) as error:
            self.invoke_job()
        self.assertEqual(error.exception.phase, transport.DispatchPhase.NOT_DISPATCHED)
        with self.host([{'revision': '0001', 'outbox': {}}, {'done': True}]) as requests:
            self.assertEqual(self.invoke_job(), {'done': True})
        self.assertEqual([r['operation_id'] for r in requests], ['three_mm.platform.status', 'job'])

    def test_host_stops_after_readiness_before_job_connect(self):
        with self.host([{'revision': '0001', 'outbox': {}}]):
            def gone():
                self.path.unlink(missing_ok=True)
                return True
            with self.assertRaises(gateway.ApplicationGatewayError) as error:
                self.invoke_job(before_dispatch=gone)
            self.assertEqual(error.exception.phase, transport.DispatchPhase.NOT_DISPATCHED)

    def test_output_validation_after_dispatch_is_unconfirmed(self):
        with self.host([{'revision': '0001', 'outbox': {}}, {'done': 'wrong'}]):
            with self.assertRaises(gateway.ApplicationGatewayError) as error:
                self.invoke_job()
            self.assertEqual(error.exception.phase, transport.DispatchPhase.EXECUTION_UNCONFIRMED)


if __name__ == '__main__':
    unittest.main()
