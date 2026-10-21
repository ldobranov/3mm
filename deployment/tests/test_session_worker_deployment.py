"""Release invariants; live OS behaviour is a separate explicit acceptance."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_worker_profile_has_per_connection_identity_bounds_and_core_lifecycle():
    unit = (ROOT / "deployment/systemd/3mm-session-worker@.service").read_text()
    for setting in (
        "DynamicUser=yes",
        "NoNewPrivileges=yes",
        "CapabilityBoundingSet=",
        "PrivateDevices=yes",
        "PrivateNetwork=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "RestrictAddressFamilies=AF_UNIX",
        "RestrictNamespaces=yes",
        "MemoryMax=128M",
        "TasksMax=16",
        "LimitNOFILE=64",
        "RuntimeMaxSec=900",
        "KillMode=control-group",
        "Restart=no",
        "BindsTo=3mm-core.service",
        "StandardInput=socket",
        "StandardOutput=null",
        "StandardError=null",
        "/tmp:rw,nosuid,nodev,size=64M",
        "/var/tmp:rw,nosuid,nodev,size=16M",
    ):
        assert setting in unit
    assert "EnvironmentFile=" not in unit  # Never inherit Core keys/DB credentials.
    assert "\nUser=" not in unit  # systemd derives a DISTINCT hashed dynamic UID.
    assert all(
        path in unit for path in ("/etc/3mm", "/var/lib/3mm", "/run/3mm", "/mnt")
    )


def test_socket_is_core_group_only_and_never_globally_started_by_install():
    unit = (ROOT / "deployment/systemd/3mm-session-worker.socket").read_text()
    for setting in (
        "SocketUser=root",
        "SocketGroup=3mm",
        "SocketMode=0660",
        "Accept=yes",
        "MaxConnections=4",
        "RemoveOnStop=yes",
        "PartOf=3mm-core.service",
        "WantedBy=3mm-core.service",
    ):
        assert setting in unit
    installer = (ROOT / "deployment/install-systemd.sh").read_text()
    assert "3mm-session-worker@*.service" in installer
    assert "systemctl enable --now 3mm-session-worker" not in installer
    assert "upsert_environment THREE_MM_LOCAL_SESSIONS" not in installer


def test_real_websocket_dependency_and_inbound_limits_are_released():
    dependencies = (ROOT / "backend/requirements.txt").read_text()
    unit = (ROOT / "deployment/systemd/3mm-core.service").read_text()
    assert "websockets==17.2" in dependencies
    for setting in (
        "--ws websockets-sansio",
        "--ws-max-size 65536",
        "--ws-max-queue 4",
        "--ws-per-message-deflate false",
    ):
        assert setting in unit
