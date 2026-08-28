from pathlib import Path

SYSTEMD_DIR = Path(__file__).parents[2] / "deployment" / "systemd"
INSTALLER = SYSTEMD_DIR.parent / "install-systemd.sh"
BOOTSTRAP_INSTALLER = SYSTEMD_DIR.parents[1] / "install.sh"
UNITS = {
    "core": SYSTEMD_DIR / "3mm-core.service",
    "web": SYSTEMD_DIR / "3mm-web.service",
    "agent": SYSTEMD_DIR / "3mm-agent.service",
    "setup": SYSTEMD_DIR / "3mm-setup.service",
}
PRIVILEGED_UNITS = {
    "helper": SYSTEMD_DIR / "3mm-network-helper.service",
    "setup_ap": SYSTEMD_DIR / "3mm-setup-ap.service",
    "update_helper": SYSTEMD_DIR / "3mm-update-helper.service",
}
CAPTIVE_DNS_CONFIG = SYSTEMD_DIR / "3mm-captive-portal-dnsmasq.conf"


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
        assert unit["ExecStart"].startswith("/opt/3mm/current/.venv/bin/python")
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
    assert "--alias-port 80" in web_command
    assert "--host 127.0.0.1 --port 8890" in agent_command
    assert "--host 0.0.0.0 --port 8895" in setup_command
    assert "--captive-port 80" in setup_command
    assert "--captive-url http://10.42.0.1:8895/setup" in setup_command


def test_setup_unit_has_no_network_mutation_privileges() -> None:
    unit = _directives(UNITS["setup"])

    assert unit["User"] != "root"
    assert unit["AmbientCapabilities"] == "CAP_NET_BIND_SERVICE"
    assert unit["CapabilityBoundingSet"] == "CAP_NET_BIND_SERVICE"
    assert "--network-helper-socket /run/3mm/network-helper.sock" in unit["ExecStart"]


def test_web_uses_only_the_low_port_bind_capability() -> None:
    unit = _directives(UNITS["web"])

    assert unit["CapabilityBoundingSet"] == "CAP_NET_BIND_SERVICE"
    assert unit["AmbientCapabilities"] == "CAP_NET_BIND_SERVICE"


def test_privileged_network_units_are_narrowly_scoped() -> None:
    helper = _directives(PRIVILEGED_UNITS["helper"])
    setup_ap = _directives(PRIVILEGED_UNITS["setup_ap"])

    assert helper["User"] == "root"
    assert helper["Group"] == "3mm"
    assert setup_ap["User"] == "root"
    assert "network_helper" in helper["ExecStart"]
    assert "setup_access_point start" in setup_ap["ExecStart"]
    assert setup_ap["RemainAfterExit"] == "true"
    assert helper["ProtectSystem"] == "strict"
    assert setup_ap["ProtectSystem"] == "strict"
    assert setup_ap["ReadWritePaths"] == (
        "/etc/NetworkManager/dnsmasq-shared.d /var/lib/3mm/provisioning"
    )


def test_setup_ap_owns_the_captive_dns_lifecycle() -> None:
    setup_ap = _directives(PRIVILEGED_UNITS["setup_ap"])

    assert "3mm-captive-portal-dnsmasq.conf" in setup_ap["ExecStartPre"]
    assert "/etc/NetworkManager/dnsmasq-shared.d/3mm-captive-portal.conf" in (
        setup_ap["ExecStartPre"]
    )
    assert setup_ap["ExecStopPost"] == (
        "/usr/bin/rm -f " "/etc/NetworkManager/dnsmasq-shared.d/3mm-captive-portal.conf"
    )
    assert CAPTIVE_DNS_CONFIG.read_text(encoding="utf-8").splitlines()[-1] == (
        "address=/#/10.42.0.1"
    )


def test_update_helper_exposes_only_a_local_hardened_scheduler() -> None:
    helper = _directives(PRIVILEGED_UNITS["update_helper"])

    assert helper["User"] == "root"
    assert "three_mm_runtime.update_helper" in helper["ExecStart"]
    assert "/run/3mm/update-helper.sock" in helper["ExecStart"]
    assert helper["ProtectSystem"] == "strict"
    assert helper["ProtectHome"] == "true"
    assert helper["RestrictAddressFamilies"] == "AF_UNIX"
    assert helper["RuntimeDirectoryPreserve"] == "yes"
    assert helper["ReadWritePaths"] == (
        "/var/lib/3mm/backups /var/lib/3mm/core/backup-imports /etc/3mm"
    )
    assert (
        "--network-recovery-policy /var/lib/3mm/core/network-recovery-policy.json"
        in helper["ExecStart"]
    )
    assert "--provisioning-data-dir /var/lib/3mm/provisioning" in helper["ExecStart"]


def test_only_helpers_own_the_shared_runtime_socket_directory() -> None:
    setup = _directives(UNITS["setup"])
    network_helper = _directives(PRIVILEGED_UNITS["helper"])

    assert "RuntimeDirectory" not in setup
    for name in ("core", "web", "agent"):
        assert "RuntimeDirectory" not in _directives(UNITS[name])
    assert network_helper["RuntimeDirectory"] == "3mm"
    assert network_helper["RuntimeDirectoryPreserve"] == "yes"


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
    assert "3mm-update-helper.service" in installer
    assert "3mm-captive-portal-dnsmasq.conf" in installer
    assert "THREE_MM_NETWORK_RECOVERY_POLICY_FILE" in installer
    assert "THREE_MM_NETWORK_RECOVERY_MARKER_FILE" in installer
    assert "THREE_MM_BACKUP_IMPORT_DIR" in installer
    assert "deployment/portable_backup.py" in installer
    assert "http://$device_hostname.local" in installer
    assert "frontend_primary_origin=$frontend_scheme://$frontend_host" in installer
    assert "frontend_compat_origin=$frontend_scheme://$frontend_host:8080" in installer
    assert "NetworkManager" not in installer
    assert "nmcli" not in installer
    assert "iptables" not in installer
    assert "nft" not in installer


def test_first_install_creates_but_updates_do_not_reset_the_test_admin() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "database_existed_before_deploy=0" in installer
    assert "--create-development-default-if-empty" in installer
    assert "if [[ $database_existed_before_deploy -eq 0 ]]" in installer
    assert 'rm -f -- "$database" "${database}-wal" "${database}-shm"' in installer


def test_installer_owns_the_atomic_release_and_rollback_boundary() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    launcher = (SYSTEMD_DIR.parents[1] / "deploy.ps1").read_text(encoding="utf-8")

    assert 'python3 -m venv "$release_dir/.venv"' in installer
    assert 'ln -sfnT "$release_dir" "$current_link"' in installer
    assert "trap rollback ERR" in installer
    assert "source.backup(backup)" in installer
    assert "venv_dir=$install_root/venv" not in installer
    assert "deployment\\install-systemd.sh" in launcher
    assert "remote-deploy.sh" not in launcher


def test_installer_uses_a_root_owned_cache_outside_protected_home() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "deploy_cache_root=/var/cache/3mm/deploy" in installer
    assert "install -d -o root -g root -m 0700" in installer
    assert 'HOME="$deploy_home" npm_config_cache="$npm_cache"' in installer


def test_installer_restarts_always_on_services_after_link_activation() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    activation = installer.index('ln -sfnT "$release_dir" "$current_link"')
    restart = installer.index("restart_always_on_services", activation)

    assert activation < restart
    assert 'systemctl restart "${always_on_services[@]}"' in installer
    assert "restart_always_on_services || true" in installer


def test_deploy_accepts_setup_or_application_runtime() -> None:
    launcher = (SYSTEMD_DIR.parents[1] / "deploy.ps1").read_text(encoding="utf-8")

    assert "systemctl is-active --quiet 3mm-setup.service" in launcher
    assert "$runtimeMode -eq 'setup'" in launcher
    assert "$runtimeMode -eq 'application'" in launcher
    assert "http://$($originUri.Host):8895/ready" in launcher
    assert "http://10.42.0.1:8895/setup" in launcher


def test_deploy_records_the_validated_project_version() -> None:
    launcher = (SYSTEMD_DIR.parents[1] / "deploy.ps1").read_text(encoding="utf-8")

    assert "Join-Path $repoRoot 'VERSION'" in launcher
    assert "$projectVersion -notmatch" in launcher
    assert "version = $projectVersion" in launcher


def test_public_bootstrap_uses_verified_release_and_detached_installation() -> None:
    bootstrap = BOOTSTRAP_INSTALLER.read_text(encoding="utf-8")

    assert "api.github.com/repos/$THREE_MM_REPOSITORY/releases" in bootstrap
    assert "3mm-update-manifest.json" in bootstrap
    assert "sha256sum --check --status" in bootstrap
    assert "deployment/first_boot_preflight.py" in bootstrap
    assert "deployment/install-systemd.sh" in bootstrap
    assert "systemd-run" in bootstrap
    assert "--no-block" in bootstrap
    assert "--property=UMask=0022" in bootstrap
    assert "--property=UMask=0077" not in bootstrap
    assert "THREE_MM_BOOTSTRAP_PACKAGES" in bootstrap
    assert "network-manager" in bootstrap
    assert "dnsmasq-base" in bootstrap
    assert "3mm Setup XXXX" in bootstrap
    assert "git clone" not in bootstrap
