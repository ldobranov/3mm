from pathlib import Path

SYSTEMD_DIR = Path(__file__).parents[2] / "deployment" / "systemd"
INSTALLER = SYSTEMD_DIR.parent / "install-systemd.sh"
UNITS = {
    "core": SYSTEMD_DIR / "3mm-core.service",
    "web": SYSTEMD_DIR / "3mm-web.service",
    "agent": SYSTEMD_DIR / "3mm-agent.service",
    "setup": SYSTEMD_DIR / "3mm-setup.service",
}
PRIVILEGED_UNITS = {
    "helper": SYSTEMD_DIR / "3mm-network-helper.service",
    "setup_ap": SYSTEMD_DIR / "3mm-setup-ap.service",
}


def _directives(path: Path) -> dict[str, str]:
    directives: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            directives[key] = value
    return directives


def test_units_run_unprivileged_with_common_layout_and_hardening() -> None:
    for name, path in UNITS.items():
        unit = _directives(path)
        assert unit["User"] == "3mm"
        assert unit["Group"] == "3mm"
        assert unit["WorkingDirectory"] == "/opt/3mm/current"
        assert unit["EnvironmentFile"] == "-/etc/3mm/3mm.env"
        assert unit["NoNewPrivileges"] == "true"
        assert unit["PrivateTmp"] == "true"
        assert unit["ProtectSystem"] == "strict"
        assert unit["ProtectHome"] == "true"
        assert unit["Restart"] == "on-failure"
        if name != "web":
            assert unit["StateDirectory"].startswith("3mm/")


def test_core_is_lan_accessible_while_device_services_stay_on_loopback() -> None:
    core_command = _directives(UNITS["core"])["ExecStart"]
    web_command = _directives(UNITS["web"])["ExecStart"]
    agent_command = _directives(UNITS["agent"])["ExecStart"]
    setup_command = _directives(UNITS["setup"])["ExecStart"]

    assert "--host 0.0.0.0 --port 8887" in core_command
    assert "--host 0.0.0.0 --port 8080" in web_command
    assert "--host 127.0.0.1 --port 8890" in agent_command
    assert "--host 0.0.0.0 --port 8895" in setup_command


def test_setup_unit_has_no_network_mutation_privileges() -> None:
    unit = _directives(UNITS["setup"])

    assert unit["User"] != "root"
    assert "AmbientCapabilities" not in unit
    assert "CapabilityBoundingSet" not in unit
    assert "--network-helper-socket /run/3mm/network-helper.sock" in unit["ExecStart"]


def test_privileged_network_units_are_narrowly_scoped() -> None:
    helper = _directives(PRIVILEGED_UNITS["helper"])
    setup_ap = _directives(PRIVILEGED_UNITS["setup_ap"])

    assert helper["User"] == "root"
    assert setup_ap["User"] == "root"
    assert "network_helper" in helper["ExecStart"]
    assert "setup_access_point start" in setup_ap["ExecStart"]
    assert setup_ap["RemainAfterExit"] == "true"
    assert helper["ProtectSystem"] == "strict"
    assert setup_ap["ProtectSystem"] == "strict"


def test_units_use_the_shared_provisioning_directory() -> None:
    agent_command = _directives(UNITS["agent"])["ExecStart"]
    setup_command = _directives(UNITS["setup"])["ExecStart"]

    assert "--provisioning-data-dir /var/lib/3mm/provisioning" in agent_command
    assert "--data-dir /var/lib/3mm/provisioning" in setup_command


def test_example_environment_contains_no_secret_values() -> None:
    example = (SYSTEMD_DIR / "3mm.env.example").read_text(encoding="utf-8")
    forbidden = ("PASSWORD=", "PASSPHRASE=", "TOKEN=", "SECRET=", "PRIVATE_KEY=")

    assert not any(marker in example.upper() for marker in forbidden)


def test_installer_preserves_identity_and_delegates_network_mutation() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "identity.json" in installer
    assert "install -o 3mm -g 3mm -m 0600" in installer
    assert "three_mm_runtime.activate" in installer
    assert "3mm-network-helper.service" in installer
    assert "3mm-setup-ap.service" in installer
    assert "NetworkManager" not in installer
    assert "nmcli" not in installer
    assert "iptables" not in installer
    assert "nft" not in installer
