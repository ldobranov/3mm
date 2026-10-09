from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from deployment.factory_reset import (
    FactoryResetError,
    _prepare_state_directories,
    _remove_application_keys,
    _remove_persistent_children,
    validate_factory_paths,
)


def test_factory_reset_removes_only_named_3mm_state_children(tmp_path: Path) -> None:
    for name in (
        "agent",
        "core",
        "deploy-backups",
        "provisioning",
        "update-helper",
        "application-extensions",
    ):
        child = tmp_path / name
        child.mkdir()
        (child / "state").write_text("test", encoding="utf-8")
    retained = tmp_path / "unrecognized-data"
    retained.mkdir()

    _remove_persistent_children(tmp_path)

    assert retained.is_dir()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["unrecognized-data"]


def test_factory_reset_removes_application_transport_keys(tmp_path: Path) -> None:
    key_root = tmp_path / "application-extensions"
    key_root.mkdir()
    (key_root / "instance.key").write_bytes(b"secret")

    _remove_application_keys(key_root)

    assert not key_root.exists()


def test_factory_reset_rejects_caller_selected_paths(tmp_path: Path) -> None:
    with pytest.raises(FactoryResetError, match="production paths"):
        validate_factory_paths(tmp_path, tmp_path / "current")


def test_factory_reset_recreates_all_runtime_mount_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ownership: dict[Path, tuple[int, int]] = {}
    modes: dict[Path, int] = {}
    monkeypatch.setattr(
        "deployment.factory_reset.os.chown",
        lambda path, uid, gid: ownership.__setitem__(Path(path), (uid, gid)),
        raising=False,
    )
    monkeypatch.setattr(
        "deployment.factory_reset.os.chmod",
        lambda path, mode: modes.__setitem__(Path(path), mode),
    )
    state_root = tmp_path / "state"
    key_root = tmp_path / "keys"

    _prepare_state_directories(
        state_root,
        uid=1001,
        gid=1002,
        application_gid=1003,
        key_root=key_root,
    )

    assert (state_root / "core" / "backup-imports").is_dir()
    assert (state_root / "backups" / "exports").is_dir()
    assert len((key_root.parent / "backup.key").read_bytes()) == 32
    assert (state_root / "application-extensions" / "platform").is_dir()
    assert key_root.is_dir()
    assert ownership[state_root] == (1001, 1003)
    assert modes[state_root] == 0o710
    assert ownership[state_root / "application-extensions"] == (0, 1003)
    assert ownership[state_root / "application-extensions" / "platform"] == (
        1001,
        1003,
    )
    assert modes[state_root / "application-extensions" / "platform"] == 0o750


@pytest.mark.parametrize("fence_fails", [False, True])
def test_reset_fences_fresh_database_before_any_activation(tmp_path, monkeypatch, fence_fails):
    import deployment.factory_reset as reset

    calls = []
    monkeypatch.setitem(sys.modules, "pwd", SimpleNamespace(getpwnam=lambda _name: SimpleNamespace(pw_uid=1)))
    monkeypatch.setitem(sys.modules, "grp", SimpleNamespace(getgrnam=lambda _name: SimpleNamespace(gr_gid=2)))
    monkeypatch.setattr(reset, "_remove_persistent_children", lambda *_a: calls.append("remove-state"))
    monkeypatch.setattr(reset, "_remove_application_keys", lambda: calls.append("remove-keys"))
    monkeypatch.setattr(reset, "_prepare_state_directories", lambda *_a: calls.append("prepare"))

    def fence(path, *, reason):
        assert path == tmp_path / "core/3mm.db" and reason == "factory_reset"
        calls.append("fence")
        if fence_fails:
            raise RuntimeError("fence failed")

    def run(arguments):
        if "stop" in arguments:
            calls.append("stop")
        elif any(str(value).endswith("migrate_database.py") for value in arguments):
            calls.append("migrate")
        elif "backend.scripts.bootstrap_admin" in arguments:
            calls.append("bootstrap")
        elif "three_mm_runtime.activate" in arguments:
            calls.append("activate")
        else:
            calls.append("refresh-helper")

    monkeypatch.setattr(reset, "fence_recovered_authority", fence)
    if fence_fails:
        with pytest.raises(RuntimeError, match="fence failed"):
            reset.perform_factory_reset(release=tmp_path / "release", state_root=tmp_path, runner=SimpleNamespace(run=run))
        assert calls == ["stop", "remove-state", "remove-keys", "prepare", "migrate", "fence"]
    else:
        reset.perform_factory_reset(release=tmp_path / "release", state_root=tmp_path, runner=SimpleNamespace(run=run))
        assert calls == ["stop", "remove-state", "remove-keys", "prepare", "migrate", "fence", "bootstrap", "activate", "refresh-helper"]
