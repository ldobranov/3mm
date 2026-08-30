from pathlib import Path

import pytest

from deployment.factory_reset import (
    FactoryResetError,
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
