from pathlib import Path

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
