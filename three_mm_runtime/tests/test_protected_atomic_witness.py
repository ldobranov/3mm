"""Production helper runs root with a non-root primary group; no live VM effects."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from three_mm_runtime.application_activation import _write_atomic


def test_application_unit_waits_for_nonroot_exec_before_acknowledging_start():
    template = (
        Path(__file__).resolve().parents[2]
        / "deployment/systemd/3mm-application-extension@.service"
    )
    values = dict(
        line.split("=", 1)
        for line in template.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    assert values["Type"] == "exec"
    assert values["User"] == values["Group"] == "3mm-app"
    assert values["NoNewPrivileges"] == "true"
    assert values["ProtectSystem"] == "strict"


@pytest.mark.parametrize(
    "owner", [{"uid": 0}, {"gid": 0}, {"uid": True, "gid": 0}, {"uid": -1, "gid": 0}]
)
def test_partial_or_invalid_ownership_refuses_before_filesystem_effect(tmp_path, owner):
    target = tmp_path / "witness.json"
    target.write_bytes(b"original")
    with pytest.raises(ValueError, match="ownership"):
        _write_atomic(target, b"changed", 0o600, **owner)
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() != 0,
    reason="Linux root ownership regression",
)
def test_root_witness_replacements_pin_root_group_under_nonroot_primary_group(tmp_path):
    script = r"""
import json, os, stat, sys
from pathlib import Path
from three_mm_runtime.application_activation import _write_atomic
from three_mm_runtime.application_relational_namespace import _exclusive_file
os.setgroups([])
os.setgid(65534)
p = Path(sys.argv[1])
_exclusive_file(p, b'initial', 0o600, 0)
for phase in (b'stopped_unconfirmed', b'stopped_review_required'):
    _write_atomic(p, phase, 0o600, uid=0, gid=0)
    info=p.stat()
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o600)
    assert p.read_bytes() == phase
assert len(list(p.parent.iterdir())) == 1
print(json.dumps({'uid':os.geteuid(), 'helper_gid':os.getegid(), 'witness_gid':p.stat().st_gid}))
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "witness.json")],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert json.loads(process.stdout) == {
        "uid": 0,
        "helper_gid": 65534,
        "witness_gid": 0,
    }
