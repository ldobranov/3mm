"""TLS possession of the EXISTING Hub installation key; no new enrollment/key.

Private key material stays inside the trusted Core process. Node receives only
its existing Hub public identity's self-signed certificate. No certificate or
credential validation is disabled by the transport. Relay cannot terminate TLS.
"""
from datetime import timedelta
from pathlib import Path
import os
import ssl
import tempfile

from sqlalchemy.orm import Session
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

from backend.db.installation_identity import CoreInstallationIdentity
from backend.services.installation_identity import (
    _decode_identity, _cipher, read_existing_installation_identity,
)


def installation_certificate(identity, private):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, identity.installation_id)])
    start = identity.created_at.replace(tzinfo=None) - timedelta(minutes=1)
    key = private.public_key()
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key).serial_number(int(identity.key_id[:32], 16) or 1)
        .not_valid_before(start).not_valid_after(start + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key), critical=False)
        .sign(private, algorithm=None))
    return certificate.public_bytes(serialization.Encoding.PEM)


def installation_client_context(engine, peer_certificate):
    with Session(engine) as db:
        existing = read_existing_installation_identity(db)  # Missing means refusal, never lazy enrollment.
        row = db.get(CoreInstallationIdentity, 1)
        if row is None:
            raise ValueError("Existing installation signing identity unavailable")
        identity, private = _decode_identity(row, _cipher())
        if identity != existing:
            raise ValueError("Installation identity changed")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_verify_locations(cadata=peer_certificate)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    certificate = installation_certificate(identity, private)
    with tempfile.TemporaryDirectory(prefix="3mm-session-tls-") as directory:
        root = Path(directory)
        for name, value in (("certificate.pem", certificate), ("key.pem", private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))):
            fd = os.open(root / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(value)
        context.load_cert_chain(str(root / "certificate.pem"), str(root / "key.pem"))
    return context, identity


def current_installation_identity(engine, expected):
    try:
        with Session(engine) as db:
            return read_existing_installation_identity(db) == expected
    except Exception:
        return False
