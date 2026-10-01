import json
import tarfile
from pathlib import Path

import pytest

from deployment.build_node_release import build
from deployment.prepare_node_wheels import digest
from deployment.tests.test_node_installer import BASH, run, section

ROOT = Path(__file__).resolve().parents[2]


def test_node_update_files_are_in_minimal_reproducible_archive(tmp_path):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    name = "fixture-1-py3-none-any.whl"
    (wheels / name).write_bytes(b"fixture")
    (wheels / "provenance.json").write_text(json.dumps({
        "architecture": "armv6l", "python": "3.13", "wheels": [{
            "filename": name, "sha256": digest(b"fixture")
        }]
    }))
    kwargs = dict(version=(ROOT / "VERSION").read_text().strip(), commit="a" * 40,
                  repository="example/3mm", epoch=1700000000)
    first = build(ROOT, wheels, tmp_path / "first", **kwargs)
    assert "openssl" in first["dependencies"]["apt_packages"]
    assert build(ROOT, wheels, tmp_path / "second", **kwargs) == first
    with tarfile.open(tmp_path / "first" / first["artifacts"][0]["filename"]) as archive:
        names = set(archive.getnames())
        assert {
            "agent/node_update_client.py", "three_mm_protocol/node_updates.py",
            "agent/node_update_execution.py",
            "three_mm_runtime/node_update_helper.py", "deployment/apply_node_update.py",
            "three_mm_runtime/node_update_trust.py", "deployment/trust_node_update_hub.py",
            "deployment/systemd/3mm-node-update-helper.service",
        } <= names
        assert not any(name.startswith(("backend/", "frontend/")) for name in names)
        unit = archive.extractfile("deployment/systemd/3mm-node-update-helper.service").read().decode()
        assert "StateDirectory=3mm-node-update" in unit
        assert "RuntimeDirectory=3mm-node-update" in unit
        assert "RestrictAddressFamilies=AF_UNIX" in unit


@pytest.mark.skipif(BASH is None, reason="Bash is required")
def test_rollback_to_older_node_removes_helper_from_required_services(tmp_path):
    old_release = tmp_path / "old"
    definitions = old_release / "deployment/systemd"
    definitions.mkdir(parents=True)
    (definitions / "3mm-node-recovery.service").write_text("fixture")
    source = f'source_release="{old_release.as_posix()}"\n' + '''
installed_units=(3mm-node-recovery.service 3mm-node-update-helper.service)
always_on_services=(3mm-node-recovery.service 3mm-node-update-helper.service)
systemctl_calls=()
systemctl() { systemctl_calls+=("$*"); }
install() { :; }
rm() { printf 'remove %s\\n' "$*"; }
fail() { return 1; }
''' + section("install_units() {", "release_python() {") + '''
install_units "$source_release" 0
printf 'systemctl %s\\n' "${systemctl_calls[@]}"
printf 'remaining: %s\\n' "${always_on_services[@]}"
'''
    result = run(source)
    assert result.returncode == 0, result.stderr
    assert "disable --now 3mm-node-update-helper.service" in result.stdout
    assert "remaining: 3mm-node-recovery.service" in result.stdout
    assert "remaining: 3mm-node-update-helper.service" not in result.stdout
