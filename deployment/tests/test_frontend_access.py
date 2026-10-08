"""Origin policy and actual bounded installer sections; no live mutations."""

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from deployment.frontend_access import (
    LOCAL_ORIGINS,
    MAX_ORIGINS,
    frontend_access_origins,
    normalize_origin,
)
from deployment.tests.test_node_installer import BASH, SCRIPT, run, section

BOOTSTRAP = (Path(__file__).parents[2] / "install.sh").read_text(encoding="utf-8")
SELECT_ORIGIN = BOOTSTRAP[
    BOOTSTRAP.index("select_frontend_origin() {") : BOOTSTRAP.index(
        "select_frontend_origin /etc/3mm/3mm.env"
    )
]


def test_clean_wsl_install_has_explicit_local_and_lan_access(tmp_path):
    origins = frontend_access_origins(
        tmp_path / "absent.env", "http://172.18.196.191", "LAZ-DELL"
    )
    assert set(LOCAL_ORIGINS) <= set(origins)
    assert "http://172.18.196.191" in origins
    assert "http://172.18.196.191:8080" in origins
    assert "http://laz-dell.local" in origins
    assert len(origins) == len(set(origins))


@pytest.mark.parametrize("format", ["json", "quoted_json", "comma"])
def test_updates_preserve_custom_origins_without_executing_environment(
    tmp_path, format
):
    existing = ["https://console.example.com", "http://localhost:8080"]
    value = json.dumps(existing) if format != "comma" else ",".join(existing)
    if format == "quoted_json":
        value = f"'{value}'"
    environment = tmp_path / "3mm.env"
    environment.write_text(
        f"CORS_ORIGINS={value}\nFRONTEND_URL=http://old.example.com\n"
        "SECRET=$(touch should-not-exist)\n"
    )
    original = environment.read_bytes()
    origins = frontend_access_origins(environment, "http://new.example.com", "hub")
    assert set(existing) <= set(origins)
    assert "http://new.example.com" in origins
    assert environment.read_bytes() == original
    assert not (tmp_path / "should-not-exist").exists()
    # Idempotent across subsequent console/UI updates.
    environment.write_text(f"CORS_ORIGINS={json.dumps(origins)}\n")
    assert (
        frontend_access_origins(environment, "http://new.example.com", "hub") == origins
    )


@pytest.mark.parametrize(
    "invalid",
    [
        "*",
        "null",
        "https://*.example.com",
        "http://user:pass@host",
        "http://host/path",
        "http://host?",
        "http://host#",
        "http://host:0",
        "http://host:65536",
        "http://host:",
        "file:///etc/passwd",
        "http://host\\evil",
        "http://host\n",
        "http://host\t",
        7,
        None,
    ],
)
def test_unsafe_origins_rejected(invalid):
    with pytest.raises(ValueError, match="plain HTTP"):
        normalize_origin(invalid)


@pytest.mark.parametrize(
    "value", ["[broken", '["*"]', "[7]", '{"origin":"http://host"}']
)
def test_invalid_stored_policy_fails_closed(tmp_path, value):
    environment = tmp_path / "3mm.env"
    environment.write_text(f"CORS_ORIGINS={value}\n")
    with pytest.raises(ValueError):
        frontend_access_origins(environment, "http://localhost", "host")


def test_policy_bounded_and_origins_canonicalized(tmp_path):
    assert (
        normalize_origin("HTTPS://Console.Example.com:443")
        == "https://console.example.com"
    )
    assert normalize_origin("http://localhost:80") == "http://localhost"
    assert normalize_origin("http://[::1]:8080") == "http://[::1]:8080"
    environment = tmp_path / "3mm.env"
    environment.write_text(
        "CORS_ORIGINS=" + json.dumps([f"http://host{i}" for i in range(MAX_ORIGINS)])
    )
    with pytest.raises(ValueError, match="limit"):
        frontend_access_origins(environment, "http://localhost", "host")


@pytest.mark.skipif(BASH is None, reason="Bash is required")
@pytest.mark.parametrize(
    "stored,override,profile,expected",
    [
        ("http://localhost", "", "full", "http://localhost"),
        ('"https://console.example.com"', "", "full", "https://console.example.com"),
        ("http://old", "http://new:8080", "full", "http://new:8080"),
        ("", "", "full", "http://192.168.1.88"),
        ("http://old", "", "node", "http://192.168.1.88"),
    ],
)
def test_bootstrap_preserves_saved_url_unless_explicitly_overridden(
    tmp_path, stored, override, profile, expected
):
    environment = tmp_path / "3mm.env"
    environment.write_text(f"FRONTEND_URL={stored}\nSECRET=$(false)\n")
    result = run(
        f"frontend_origin={shlex.quote(override)}\ninstall_profile={profile}\n"
        "hostname() { printf '192.168.1.88 10.0.0.2\\n'; }\n"
        "fail() { exit 1; }\n"
        f'python3() {{ {shlex.quote(sys.executable)} "$@"; }}\n'
        + SELECT_ORIGIN
        + f"\nselect_frontend_origin {shlex.quote(str(environment))}\n"
        + 'printf "%s" "$frontend_origin"\n'
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


@pytest.mark.skipif(BASH is None, reason="Bash is required")
def test_invalid_saved_frontend_url_stops_bootstrap(tmp_path):
    environment = tmp_path / "3mm.env"
    environment.write_text("FRONTEND_URL=$(touch should-not-exist)\n")
    result = run(
        "frontend_origin=''\ninstall_profile=full\nfail() { exit 1; }\n"
        f'python3() {{ {shlex.quote(sys.executable)} "$@"; }}\n'
        + SELECT_ORIGIN
        + f"\nselect_frontend_origin {shlex.quote(str(environment))}\n"
        + "echo must-not-continue\n"
    )
    assert result.returncode != 0
    assert "must-not-continue" not in result.stdout


@pytest.mark.skipif(BASH is None, reason="Bash is required")
def test_target_installer_writes_merged_policy_and_keeps_unrelated_state(tmp_path):
    environment = tmp_path / "3mm.env"
    environment.write_text(
        'CORS_ORIGINS=["https://console.example.com"]\n'
        "CUSTOM_SECRET=do-not-replace\nTHREE_MM_GPIO_DRIVER=linux\n"
    )
    origins = frontend_access_origins(environment, "http://localhost", "vm")
    result = run(
        f"environment_file={shlex.quote(str(environment))}\n"
        f"test_root={shlex.quote(str(tmp_path))}\n"
        f"frontend_cors_origins={shlex.quote(json.dumps(origins))}\n"
        "install_profile=full\nenvironment_backup_created=1\n"
        "frontend_origin=http://localhost\n"
        "log() { :; }\n"
        'mktemp() { command mktemp "$test_root/3mm.env.XXXXXX"; }\n'
        + section(
            'log "Updating the persistent service environment"',
            "if [[ -s $ai_master_key_file ]]; then",
        )
        + '\nfi\nprintf "%s" "$environment_tmp"\n'
    )
    assert result.returncode == 0, result.stderr
    written = Path(result.stdout).read_text()
    assert "CUSTOM_SECRET=do-not-replace\n" in written
    assert "THREE_MM_GPIO_DRIVER=linux\n" in written
    assert "FRONTEND_URL=http://localhost\n" in written
    stored = next(
        line.split("=", 1)[1]
        for line in written.splitlines()
        if line.startswith("CORS_ORIGINS=")
    )
    assert json.loads(stored) == origins
    assert SCRIPT.index("frontend_cors_origins=$(") < SCRIPT.index("mutation_started=1")
    # Old rollback units/environments do not have to implement this new health check.
    assert "verify_frontend_access" not in section(
        "rollback() {", "if [[ -L $current_link ]]; then"
    )


@pytest.mark.skipif(BASH is None, reason="Bash is required")
@pytest.mark.parametrize("status", ["200", "400", "000"])
def test_installer_browser_health_detects_cors_rejection(status):
    result = run(
        section("verify_frontend_access() {", "activate_runtime() {")
        + f"\ncurl() {{ printf '{status}'; }}\n"
        + "fail() { return 1; }\nverify_frontend_access\n"
    )
    assert (result.returncode == 0) == (status == "200")


def test_helper_cli_is_standalone_and_required_by_target_artifact(tmp_path):
    helper = Path(__file__).parents[1] / "frontend_access.py"
    result = subprocess.run(
        [
            sys.executable,
            str(helper),
            "--environment",
            str(tmp_path / "absent"),
            "--frontend-origin",
            "http://localhost",
            "--hostname",
            "vm",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert set(LOCAL_ORIGINS) <= set(json.loads(result.stdout))
    contract = json.loads((helper.parent / "deployment-contract.json").read_text())
    assert "deployment/frontend_access.py" in contract["required_files"]
