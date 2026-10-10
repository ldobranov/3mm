"""Exercise the real host's authenticated machine-context path without Linux sockets."""

import copy
import json
import time

import pytest

from three_mm_runtime import application_host as host
from three_mm_runtime.application_transport import sign_message, verify_message


@pytest.mark.parametrize("audience", ["installation_peer", "installation_bootstrap"])
def test_host_authenticates_before_delivering_machine_context(
    tmp_path, monkeypatch, audience
):
    from three_mm_protocol.installation_peer_v2 import enrollment_metadata

    instance = "a" * 24
    root = tmp_path / "apps"
    instance_root = root / instance
    (instance_root / "run").mkdir(parents=True)
    (instance_root / "data").mkdir()
    key_root = tmp_path / "keys"
    key_root.mkdir()
    secret = b"s" * 32
    (key_root / f"{instance}.key").write_bytes(secret)
    (instance_root / "active.json").write_text(
        json.dumps(
            {
                "instance_id": instance,
                "storage": {
                    "engine": "sqlite",
                    "schema_revision": "0001",
                    "migration_entrypoint": "fixture:migrations",
                },
                "operations": [
                    {
                        "operation_id": "report",
                        "audiences": [audience],
                        "idempotency": "required",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    machine = {
        "installation_id": "inst_" + "a" * 32,
        "key_id": "b" * 64,
        "binding_id": "peer_" + "c" * 32,
        "generation": 1,
        "scopes": (
            ["installation.status.report"] if audience == "installation_peer" else []
        ),
    }
    request = {
        "version": 1,
        "request_id": "valid",
        "timestamp": int(time.time()),
        "operation_id": "report",
        "payload": (
            {
                "enrollment_metadata": enrollment_metadata(
                    "fixture_intent", {}
                ).model_dump(mode="json")
            }
            if audience == "installation_bootstrap"
            else {}
        ),
        "context": {
            "audience": audience,
            "correlation_id": "fixture",
            "idempotency_key": "report_fixture",
            "machine": machine,
        },
    }
    signed = sign_message(request, secret)
    tampered = copy.deepcopy(signed)
    if audience == "installation_bootstrap":
        tampered["payload"]["enrollment_metadata"][
            "application_intent"
        ] = "substituted_intent"
    else:
        tampered["context"]["machine"]["scopes"] = ["capabilities.invoke"]
    mixed = copy.deepcopy(request)
    mixed["request_id"] = "mixed"
    mixed["context"]["user_id"] = 1

    class Connection:
        def __init__(self, value):
            self.message = json.dumps(value).encode() + b"\n"
            self.response = b""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def recv(self, _size):
            result, self.message = self.message, b""
            return result

        def sendall(self, value):
            self.response += value

    connections = [
        Connection(value) for value in (signed, tampered, sign_message(mixed, secret))
    ]
    accepted = iter(connections)

    class StopHost(BaseException):
        pass

    class Server:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def bind(self, _path):
            (instance_root / "run/service.sock").touch()

        def listen(self, _count):
            pass

        def accept(self):
            try:
                return next(accepted), None
            except StopIteration:
                raise StopHost()

    delivered = []

    class Service:
        def handle(self, operation_id, payload, context):
            delivered.append((payload, context))
            return {}

    monkeypatch.setattr(host, "_load_service", lambda *_args: Service())
    monkeypatch.setattr(host.socket, "socket", lambda *_args: Server())
    monkeypatch.setattr(host.socket, "AF_UNIX", 1, raising=False)
    with pytest.raises(StopHost):
        host.serve(instance, root, key_root)
    responses = [
        verify_message(json.loads(connection.response), secret)
        for connection in connections
    ]
    assert [response["ok"] for response in responses] == [True, False, False]
    assert len(delivered) == 1 and delivered[0][1].user_id is None
    assert delivered[0][1].machine.installation_id == machine["installation_id"]
    assert delivered[0][1].machine.scopes == tuple(machine["scopes"])
    assert delivered[0][0] == request["payload"]
