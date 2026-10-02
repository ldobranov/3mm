"""Opt-in Linux acceptance: two isolated Cores, verified TLS and real SDK/host sockets.

Run with THREE_MM_RUN_PEER_HTTPS_TEST=1. Never imports backend.main or calls
deployment/systemd helpers; all databases, keys and listeners are temporary.
The private test CA is trusted only inside the fixture worker processes.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
import uuid
import zipfile

import pytest

MODULE = "org.3mm.workflow-reference"  # Fixture only; not a Core registration.
INSTANCE = "a" * 24
NODE = "dev_" + "a" * 32
OTHER_NODE = "dev_" + "b" * 32
REPO = Path(__file__).resolve().parents[2]

SERVICE = """
import json
from three_mm_application_sdk import ApplicationMigration

def get_migrations():
    def create(connection):
        connection.execute("CREATE TABLE receipts (operation TEXT, binding TEXT, key TEXT, audience TEXT, actor TEXT, payload TEXT, PRIMARY KEY(operation, binding, key))")
    return [ApplicationMigration("0001", create)]

def create_service(application):
    class Service:
        def handle(self, operation, payload, context):
            if operation == "health":
                return {"status": "ready"}
            assert context.user_id is None and context.machine is not None
            machine = context.machine
            expected = () if operation == "peer_enroll" else ("installation.status.report",)
            assert machine.scopes == expected
            assert context.audience == ("installation_bootstrap" if operation == "peer_enroll" else "installation_peer")
            actor = {"installation_id": machine.installation_id, "generation": machine.generation, "scopes": list(machine.scopes)}
            with application.storage.transaction() as connection:
                connection.execute("INSERT OR IGNORE INTO receipts VALUES (?, ?, ?, ?, ?, ?)",
                    (operation, machine.binding_id, context.idempotency_key, context.audience, json.dumps(actor), json.dumps(payload)))
            return {}
    return Service()
"""


def create_test_certificate(root):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "3mm isolated test CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    (root / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (root / "cert.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    (root / "tls.key").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    os.chmod(root / "tls.key", 0o600)


def fixture_package(root):
    from backend.tests.test_installation_peers import peer_package
    from backend.services.module_packages import validate_module_package

    original, definition, manifest = peer_package()
    wheel_buffer = io.BytesIO()
    with zipfile.ZipFile(wheel_buffer, "w") as archive:
        archive.writestr("peer_fixture.py", SERVICE)
    wheel = wheel_buffer.getvalue()
    definition["service"]["entrypoint"] = "peer_fixture:create_service"
    definition["service"]["artifact_sha256"] = hashlib.sha256(wheel).hexdigest()
    definition["storage"]["migration_entrypoint"] = "peer_fixture:get_migrations"
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original)) as source,
        zipfile.ZipFile(output, "w") as archive,
    ):
        for name in source.namelist():
            value = (
                json.dumps(definition).encode()
                if name == "application-extension.json"
                else (
                    wheel
                    if name == definition["service"]["artifact"]
                    else source.read(name)
                )
            )
            archive.writestr(name, value)
    blob = output.getvalue()
    validated = validate_module_package(blob)
    (root / "peer.zip").write_bytes(blob)
    release = root / "apps" / INSTANCE / "releases" / validated.sha256
    (release / "service").mkdir(parents=True)
    (release / definition["service"]["artifact"]).write_bytes(wheel)
    (root / "apps" / INSTANCE / "run").mkdir()
    (root / "keys").mkdir()
    (root / "keys" / f"{INSTANCE}.key").write_bytes(secrets.token_bytes(32))
    os.chmod(root / "keys" / f"{INSTANCE}.key", 0o600)
    metadata = {
        "instance_id": INSTANCE,
        "module_id": MODULE,
        "version": "1.0.0",
        "sha256": validated.sha256,
        "wheel": definition["service"]["artifact"],
        "entrypoint": definition["service"]["entrypoint"],
        "configuration": {},
        "storage": definition["storage"],
        "operations": definition["operations"],
        "platform_socket": str(root / "platform.sock"),
    }
    (root / "apps" / INSTANCE / "active.json").write_text(json.dumps(metadata))
    return blob, validated, manifest


def prepare_database(root, origin):
    from backend.database import engine, Base, SessionLocal
    from backend.db.device import Device, DeviceHeartbeat, DeviceInventorySnapshot
    from backend.db.module import ModulePackage, ApplicationExtensionInstallation
    from backend.db.user import User
    from backend.services.installation_identity import installation_identity
    from backend.services.installation_peers import configure_origin

    if (root / "core.db").is_file():
        return
    blob, validated, manifest = fixture_package(root)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(
            User(
                id=1,
                username="fixture-admin",
                email="fixture@example.invalid",
                role="admin",
            )
        )
        package = ModulePackage(
            module_id=MODULE,
            version="1.0.0",
            manifest=manifest,
            sha256=validated.sha256,
            size_bytes=len(blob),
            file_path=str(root / "peer.zip"),
            registrations=[],
        )
        db.add(package)
        db.flush()
        db.add(
            ApplicationExtensionInstallation(
                module_id=MODULE,
                module_package_id=package.id,
                instance_id=INSTANCE,
                active_version="1.0.0",
                status="active",
                enabled=True,
                socket_path=str(root / "apps" / INSTANCE / "run" / "service.sock"),
            )
        )
        now = datetime.now(UTC)
        for device_id in (NODE, OTHER_NODE):
            device = Device(
                device_id=device_id,
                display_name="fixture-node",
                role="node",
                protocol_version="1.0",
                approved_at=now,
            )
            db.add(device)
            db.flush()
            db.add(
                DeviceHeartbeat(
                    device_id=device.id,
                    protocol_version="1.0",
                    payload={"sent_at": now.isoformat()},
                    received_at=now,
                )
            )
            db.add(
                DeviceInventorySnapshot(
                    device_id=device.id,
                    inventory={
                        "captured_at": now.isoformat(),
                        "system": {"architecture": "armv6l"},
                        "private_fixture": "must-not-be-projected",
                    },
                    received_at=now,
                )
            )
        db.commit()
        identity = installation_identity(db).identity
        configure_origin(db, origin, user_id=1)
        (root / "identity.json").write_text(identity.model_dump_json())


class DropResponse:
    """Fault injection after real HTTP processing: close without a complete body."""

    def __init__(self, app, root):
        self.app, self.root = app, root

    async def __call__(self, scope, receive, send):
        marker = self.root / ("drop-" + scope.get("path", "").rsplit("/", 1)[-1])
        drop = False

        async def intercept(message):
            nonlocal drop
            if (
                message["type"] == "http.response.start"
                and message["status"] == 200
                and marker.is_file()
            ):
                marker.unlink()
                drop = True
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [(b"content-length", b"1")],
                    }
                )
            elif drop and message["type"] == "http.response.body":
                raise RuntimeError("fixture: lost response after processing")
            else:
                await send(message)

        await self.app(scope, receive, intercept)


def core_worker(root, port):
    # Production peer_http remains verify=True/trust_env=False. Its default
    # certifi trust bundle is overridden only in this temporary worker process.
    import certifi

    certifi.where = lambda: str(root.parent / "ca.pem")
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    import uvicorn
    from backend.routes.installation_peers import router
    from backend.services.application_platform import ApplicationPlatformServer
    from backend.services import installation_peers as peers

    class FixtureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            offset = root / "clock-offset"
            return datetime.now(tz) + timedelta(
                seconds=int(offset.read_text()) if offset.is_file() else 0
            )

    peers.datetime = FixtureClock  # Test-only clock, not a production time change.
    prepare_database(root, f"https://localhost:{port}")
    platform = ApplicationPlatformServer(
        root / "platform.sock", root / "keys", group="fixture-only"
    )

    @asynccontextmanager
    async def lifespan(_app):
        platform.start()
        try:
            yield
        finally:
            platform.stop()

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    uvicorn.run(
        DropResponse(app, root),
        host="127.0.0.1",
        port=port,
        ssl_certfile=str(root.parent / "cert.pem"),
        ssl_keyfile=str(root.parent / "tls.key"),
        proxy_headers=False,
        access_log=False,
        log_level="warning",
        lifespan="on",
    )


class CoreFixture:
    def __init__(self, root, ca, master_key, jwt_key):
        self.root = root
        root.mkdir()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.origin = f"https://localhost:{self.port}"
        self.ca = ca
        self.processes = []
        self.logs = []
        self.env = dict(
            os.environ,
            DATABASE_URL=f"sqlite:///{root / 'core.db'}",
            AI_SETTINGS_MASTER_KEY=master_key,
            JWT_SECRET=jwt_key,
            APP_CONFIG_FILE=str(root / "no-config.json"),
            THREE_MM_APPLICATION_ROOT=str(root / "apps"),
            THREE_MM_APPLICATION_KEY_ROOT=str(root / "keys"),
            THREE_MM_APPLICATION_PLATFORM_SOCKET=str(root / "platform.sock"),
        )
        import jwt

        self.token = jwt.encode(
            {"sub": "1", "exp": datetime.now(UTC) + timedelta(minutes=15)},
            jwt_key,
            algorithm="HS256",
        )

    def spawn(self, arguments, name):
        log = (self.root / (name + ".log")).open("ab")
        self.logs.append(log)
        child = subprocess.Popen(
            [sys.executable, "-m", *arguments],
            cwd=REPO,
            env=self.env,
            stdout=log,
            stderr=log,
        )
        self.processes.append(child)
        return child

    def start(self):
        self.core = self.spawn(
            [
                "backend.tests.test_installation_peer_https",
                "--worker",
                str(self.root),
                str(self.port),
            ],
            "core",
        )
        self.wait(
            lambda: self.http(
                "GET", "/api/v1/installation-peers/v1/identity"
            ).status_code
            == 200
        )
        self.host = self.spawn(
            [
                "three_mm_runtime.application_host",
                "--instance",
                INSTANCE,
                "--root",
                str(self.root / "apps"),
                "--key-root",
                str(self.root / "keys"),
            ],
            "host",
        )
        self.wait(
            lambda: (self.root / "apps" / INSTANCE / "run" / "service.sock").is_socket()
        )
        from three_mm_application_sdk import ApplicationPlatformClient

        self.sdk = ApplicationPlatformClient(
            self.root / "platform.sock",
            INSTANCE,
            (self.root / "keys" / f"{INSTANCE}.key").read_bytes(),
        )
        return self

    def wait(self, predicate):
        import httpx

        deadline = time.monotonic() + 35
        last_error = None
        while time.monotonic() < deadline:
            if any(child.poll() is not None for child in self.processes):
                raise AssertionError(
                    "Isolated process exited; inspect fixture core/host log"
                )
            try:
                if predicate():
                    return
            except (OSError, RuntimeError, httpx.HTTPError) as exc:
                last_error = exc
            time.sleep(0.15)
        raise AssertionError("Isolated process did not become ready") from last_error

    def http(self, method, path, *, admin=False, **kwargs):
        import httpx

        headers = dict(kwargs.pop("headers", {}))
        if admin:
            headers["Authorization"] = "Bearer " + self.token
        with httpx.Client(
            verify=ssl.create_default_context(cafile=str(self.ca)),
            trust_env=False,
            timeout=15,
        ) as client:
            return client.request(method, self.origin + path, headers=headers, **kwargs)

    def restart(self):
        self.core.terminate()
        self.core.wait(timeout=10)
        self.processes.remove(self.core)
        self.core = self.spawn(
            [
                "backend.tests.test_installation_peer_https",
                "--worker",
                str(self.root),
                str(self.port),
            ],
            "core",
        )
        self.wait(
            lambda: self.http(
                "GET", "/api/v1/installation-peers/v1/identity"
            ).status_code
            == 200
        )

    def close(self):
        for child in reversed(self.processes):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        for log in self.logs:
            log.close()

    @contextmanager
    def database(self):
        with sqlite3.connect(self.root / "core.db") as connection:
            yield connection

    def row(self, table, key, value):
        assert (table, key) in {
            ("installation_peer_outbound", "link_id"),
            ("installation_peer_inbound", "binding_id"),
        }
        with self.database() as connection:
            connection.row_factory = sqlite3.Row
            return dict(
                connection.execute(
                    f"SELECT * FROM {table} WHERE {key} = ?", (value,)
                ).fetchone()
            )

    def receipts(self):
        with sqlite3.connect(
            self.root / "apps" / INSTANCE / "data" / "state.sqlite3"
        ) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute("SELECT * FROM receipts")]


@pytest.mark.parametrize(
    "module_id",
    ["org.3mm.workflow-reference", "org.3mm.cloud-manager", "com.example.9device"],
)
def test_local_consent_accepts_manifest_module_ids(module_id):
    from backend.routes.installation_peers import OutboundConsentRequest

    public = bytes(32)
    value = {
        "origin": "https://center.test",
        "receiver_identity": {
            "installation_id": "inst_" + "1" * 32,
            "key_id": hashlib.sha256(public).hexdigest(),
            "public_key": base64.b64encode(public).decode(),
            "created_at": datetime.now(UTC).isoformat(),
        },
        "target_module_id": module_id,
        "consent": {},
    }
    assert OutboundConsentRequest.model_validate(value).target_module_id == module_id
    value["target_module_id"] = "org..invalid"
    with pytest.raises(ValueError):
        OutboundConsentRequest.model_validate(value)


def signed_request(sender, row, path, payload, *, expired=False):
    """Fixture signing only: reconstruct the isolated Core's encrypted test key."""
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from three_mm_protocol.installation_peer import PeerRequestV1, request_bytes

    with sender.database() as connection:
        encrypted = connection.execute(
            "SELECT encrypted_private_key FROM core_installation_identity"
        ).fetchone()[0]
    private = Ed25519PrivateKey.from_private_bytes(
        Fernet(sender.env["AI_SETTINGS_MASTER_KEY"].encode()).decrypt(
            encrypted.encode()
        )
    )
    now = datetime.now(UTC) - (timedelta(minutes=3) if expired else timedelta())
    request = PeerRequestV1(
        credential=json.loads(row["credential"]),
        path=path,
        nonce=secrets.token_urlsafe(32),
        created_at=now,
        expires_at=now + timedelta(seconds=120),
        payload=payload,
        signature=base64.b64encode(bytes(64)).decode(),
    )
    return request.model_copy(
        update={
            "signature": base64.b64encode(private.sign(request_bytes(request))).decode()
        }
    ).model_dump(mode="json")


@pytest.mark.skipif(
    os.name != "posix" or os.getenv("THREE_MM_RUN_PEER_HTTPS_TEST") != "1",
    reason="Opt-in Linux HTTPS/Unix-socket acceptance",
)
def test_two_cores_verified_https_and_real_application_sockets(tmp_path):
    import httpx
    from cryptography.fernet import Fernet
    from three_mm_application_sdk import ApplicationPlatformError
    from three_mm_protocol.installation_peer import PEER_PREFIX

    # Unix socket names have a short Linux limit; pytest's default deep tmp_path
    # may be too long. Keep every fixture under an independent /tmp directory.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="3mm-peer-") as directory:
        root = Path(directory)
        os.chmod(root, 0o700)
        create_test_certificate(root)
        master_key, jwt_key = Fernet.generate_key().decode(), secrets.token_hex(32)
        sender = CoreFixture(root / "s", root / "ca.pem", master_key, jwt_key)
        receiver = CoreFixture(root / "r", root / "ca.pem", master_key, jwt_key)
        try:
            sender.start()
            receiver.start()
            identity_path = PEER_PREFIX + "/identity"
            with httpx.Client(verify=True, trust_env=False) as untrusted:
                with pytest.raises(httpx.ConnectError):
                    untrusted.get(receiver.origin + identity_path)
            wrong_host = receiver.origin.replace("localhost", "127.0.0.1")
            with httpx.Client(
                verify=ssl.create_default_context(cafile=str(root / "ca.pem")),
                trust_env=False,
            ) as verified:
                with pytest.raises(httpx.ConnectError):
                    verified.get(wrong_host + identity_path)
            receiver_identity = receiver.http("GET", identity_path).json()["identity"]
            assert (
                receiver_identity
                != sender.http("GET", identity_path).json()["identity"]
            )
            base = "/api/v1/installation-peers/applications/" + MODULE
            consent = {
                "summary_fields": ["core_version", "sdk_version"],
                "node_ids": [NODE],
                "node_fields": ["online", "agent_version", "architecture"],
            }
            grant = {
                "origin": receiver.origin,
                "receiver_identity": receiver_identity,
                "target_module_id": MODULE,
                "consent": consent,
            }
            assert (
                sender.http("POST", base + "/outbound", json=grant).status_code == 401
            )
            created = sender.http("POST", base + "/outbound", json=grant, admin=True)
            assert created.status_code == 201, created.text
            link = created.json()["link_id"]
            changed = sender.http(
                "PUT",
                base + "/outbound/" + link + "/consent",
                json={"expected_revision": 1, "consent": consent},
                admin=True,
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["consent_revision"] == 2
            (receiver.root / "drop-complete").touch()
            with pytest.raises(ApplicationPlatformError, match="transport failed"):
                sender.sdk.enroll_installation_peer(link)
            pending = sender.sdk.enroll_installation_peer(link)
            assert pending["state"] == "pending"
            binding = pending["remote_binding_id"]
            assert (
                len(receiver.receipts()) == 1
            )  # Bootstrap retry deduplicated by actual service.
            with pytest.raises(ApplicationPlatformError, match="not active"):
                sender.sdk.report_installation_status(
                    link, report_id="report_" + uuid.uuid4().hex
                )
            receiver.sdk.approve_installation_peer(binding, expected_generation=1)
            assert sender.sdk.enroll_installation_peer(link)["state"] == "active"
            projection = sender.sdk.get_installation_status(link)
            assert set(projection["summary"]) == set(consent["summary_fields"])
            assert [node["device_id"] for node in projection["nodes"]] == [NODE]
            fields = projection["nodes"][0]["fields"]
            assert set(fields) == set(consent["node_fields"])
            assert fields["online"]["value"] is True
            assert fields["agent_version"]["status"] == "unknown"
            assert OTHER_NODE not in json.dumps(projection)
            assert "must-not-be-projected" not in json.dumps(projection)
            report_id = "report_" + uuid.uuid4().hex
            (receiver.root / "drop-report").touch()
            with pytest.raises(ApplicationPlatformError, match="transport failed"):
                sender.sdk.report_installation_status(link, report_id=report_id)
            receiver.restart()
            accepted = sender.sdk.report_installation_status(link, report_id=report_id)
            assert accepted["status"] == "accepted"
            assert (
                sender.sdk.report_installation_status(link, report_id=report_id)
                == accepted
            )
            reports = [
                row for row in receiver.receipts() if row["operation"] == "peer_report"
            ]
            assert len(reports) == 1 and reports[0]["key"] == report_id
            actor = json.loads(reports[0]["actor"])
            assert (
                actor["scopes"] == ["installation.status.report"]
                and actor["generation"] == 1
            )

            payload = {
                "report_id": "report_" + uuid.uuid4().hex,
                "projection": projection,
            }
            row = sender.row("installation_peer_outbound", "link_id", link)
            raw = signed_request(sender, row, PEER_PREFIX + "/report", payload)
            assert (
                receiver.http(
                    "POST",
                    PEER_PREFIX + "/report",
                    json=raw,
                    headers={"Authorization": "Bearer " + receiver.token},
                ).status_code
                == 401
            )
            assert (
                receiver.http(
                    "POST",
                    PEER_PREFIX + "/report",
                    json=raw,
                    headers={"Authorization": "ThreeMM-Peer"},
                ).status_code
                == 200
            )
            receiver.restart()
            assert (
                receiver.http(
                    "POST",
                    PEER_PREFIX + "/report",
                    json=raw,
                    headers={"Authorization": "ThreeMM-Peer"},
                ).status_code
                == 409
            )
            expired = signed_request(
                sender, row, PEER_PREFIX + "/report", payload, expired=True
            )
            assert (
                receiver.http(
                    "POST",
                    PEER_PREFIX + "/report",
                    json=expired,
                    headers={"Authorization": "ThreeMM-Peer"},
                ).status_code
                == 409
            )
            old_generation = signed_request(
                sender, row, PEER_PREFIX + "/report", payload
            )
            (receiver.root / "drop-rotate").touch()
            with pytest.raises(ApplicationPlatformError, match="transport failed"):
                sender.sdk.rotate_installation_peer(link)
            receiver.restart()
            assert sender.sdk.rotate_installation_peer(link)["state"] == "active"
            assert (
                receiver.row("installation_peer_inbound", "binding_id", binding)[
                    "generation"
                ]
                == 2
            )
            assert (
                receiver.http(
                    "POST",
                    PEER_PREFIX + "/report",
                    json=old_generation,
                    headers={"Authorization": "ThreeMM-Peer"},
                ).status_code
                == 409
            )
            current = sender.row("installation_peer_outbound", "link_id", link)
            valid = signed_request(sender, current, PEER_PREFIX + "/report", payload)
            (receiver.root / "clock-offset").write_text(str(25 * 3600))
            assert (
                receiver.http(
                    "POST",
                    PEER_PREFIX + "/report",
                    json=valid,
                    headers={"Authorization": "ThreeMM-Peer"},
                ).status_code
                == 409
            )
            (receiver.root / "clock-offset").unlink()
            receiver.sdk.revoke_installation_peer(binding, direction="inbound")
            with pytest.raises(ApplicationPlatformError, match="HTTP 409"):
                sender.sdk.report_installation_status(
                    link, report_id="report_" + uuid.uuid4().hex
                )
            with pytest.raises(ApplicationPlatformError):
                receiver.sdk.approve_installation_peer(binding, expected_generation=3)
            with pytest.raises(ApplicationPlatformError, match="HTTP 409"):
                sender.sdk.rotate_installation_peer(link)
            sender.sdk.revoke_installation_peer(link, direction="outbound")
            with pytest.raises(ApplicationPlatformError):
                sender.sdk.get_installation_status(link)
            print(
                "PASS: verified TLS/hostname, dual approval, scoped projection, real SDK/host sockets,"
            )
            print(
                "      lost responses + restart, persistent replay rejection, rotation, expiry, revoke."
            )
        finally:
            sender.close()
            receiver.close()
            # Keep only diagnostic logs on failure; no databases or private keys.
            for core in (sender, receiver):
                for name in ("core", "host"):
                    source = core.root / (name + ".log")
                    if source.is_file():
                        (tmp_path / (core.root.name + "-" + name + ".log")).write_bytes(
                            source.read_bytes()
                        )


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        core_worker(Path(sys.argv[2]), int(sys.argv[3]))
    else:
        raise SystemExit("Use pytest with THREE_MM_RUN_PEER_HTTPS_TEST=1 on Linux")
