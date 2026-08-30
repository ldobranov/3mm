import sqlite3
from pathlib import Path

from deployment import restore_application_extensions as restore_module


def test_restore_reactivates_only_enabled_application_packages(monkeypatch, tmp_path):
    database = tmp_path / "3mm.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE module_packages (
                id INTEGER PRIMARY KEY,
                module_id TEXT NOT NULL,
                version TEXT NOT NULL,
                sha256 TEXT NOT NULL
            );
            CREATE TABLE application_extension_installations (
                module_id TEXT PRIMARY KEY,
                module_package_id INTEGER NOT NULL,
                instance_id TEXT NOT NULL,
                socket_path TEXT NOT NULL,
                status TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                health_checked_at TEXT,
                error TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO module_packages VALUES (1, ?, ?, ?)",
            ("org.3mm.active", "1.0.0", "a" * 64),
        )
        connection.execute(
            "INSERT INTO module_packages VALUES (2, ?, ?, ?)",
            ("org.3mm.disabled", "1.0.0", "b" * 64),
        )
        connection.execute(
            "INSERT INTO application_extension_installations VALUES (?, 1, ?, ?, 'active', 1, NULL, 'old')",
            ("org.3mm.active", "0" * 24, "old.sock"),
        )
        connection.execute(
            "INSERT INTO application_extension_installations VALUES (?, 2, ?, ?, 'disabled', 0, NULL, NULL)",
            ("org.3mm.disabled", "1" * 24, "disabled.sock"),
        )

    captured = []

    def activate(path, sha256, **kwargs):
        captured.append((path, sha256, kwargs))
        return type(
            "Activated",
            (),
            {
                "module_id": "org.3mm.active",
                "version": "1.0.0",
                "instance_id": "c" * 24,
                "socket_path": tmp_path / "apps" / ("c" * 24) / "run/service.sock",
            },
        )()

    monkeypatch.setattr(restore_module, "activate_application_package", activate)
    monkeypatch.setattr(restore_module, "WANTS_ROOT", tmp_path / "wants")
    upload_root = tmp_path / "uploads"

    restored = restore_module.restore_application_extensions(
        database,
        upload_root=upload_root,
        application_root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        service_ids=(1200, 1201),
    )

    assert restored == ("org.3mm.active",)
    assert captured[0][0] == upload_root / f"{'a' * 64}.zip"
    assert captured[0][2]["service_uid"] == 1200
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT instance_id, socket_path, error FROM application_extension_installations WHERE module_id = ?",
            ("org.3mm.active",),
        ).fetchone()
    assert row == (
        "c" * 24,
        str(tmp_path / "apps" / ("c" * 24) / "run/service.sock"),
        None,
    )
