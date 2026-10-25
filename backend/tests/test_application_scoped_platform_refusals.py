"""Actual signed IPC cannot revive legacy peer/proof operations in scoped mode."""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS

import os
from pathlib import Path
import tempfile

import pytest
from sqlalchemy.orm import sessionmaker

import backend.database
from backend.services import installation_identity, installation_peers
from backend.services.application_platform import ApplicationPlatformServer
from backend.tests.test_application_authority_management import (
    installed as managed_installed,
    source_subject,
    source_installed,
    activate_grant,
)
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual POSIX review keys and signed Unix IPC"
)


def test_all_legacy_peer_and_proof_actions_refuse_before_private_or_network_access(
    managed_installed, monkeypatch
):
    state = managed_installed
    activate_grant(state)
    monkeypatch.setattr(backend.database, "SessionLocal", sessionmaker(state.engine))
    effects = []

    def forbidden(*_args, **_kwargs):
        effects.append("legacy_private_or_network_effect")
        raise RuntimeError("Legacy path reached")

    monkeypatch.setattr(installation_identity, "prove_installation_identity", forbidden)
    for name in (
        "list_peers",
        "peer_capabilities",
        "enroll_outbound",
        "rotate_outbound",
        "approve_inbound",
        "revoke_peer",
        "report_outbound",
    ):
        monkeypatch.setattr(installation_peers, name, forbidden)
    with tempfile.TemporaryDirectory(prefix="denied-", dir="/tmp") as temporary:
        root = Path(temporary)
        secret = b"s" * 32
        (root / ("a" * 24 + ".key")).write_bytes(secret)
        server = ApplicationPlatformServer(
            root / "p.sock", root, group="missing-test-group"
        , allowed_actions=COMPATIBILITY_ACTIONS)
        server.start()
        client = ApplicationPlatformClient(server.socket_path, "a" * 24, secret)
        try:
            for action in (
                "installation.identity.prove",
                "installation.peers.list",
                "installation.peers.capabilities",
                "installation.peers.enroll",
                "installation.peers.rotate",
                "installation.peers.approve",
                "installation.peers.revoke",
                "installation.peers.report",
            ):
                # Penetration frame deliberately bypasses client-side parameter
                # validation. The signed server, not an SDK helper, must refuse.
                with pytest.raises(
                    ApplicationPlatformError, match="no supported resource grant"
                ):
                    client._call(action, {})
            assert effects == []
            assert state.manager.inspect(1)["grant_effective"] is True
        finally:
            server.stop()
