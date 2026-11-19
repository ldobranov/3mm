#!/usr/bin/env python3
"""Rebuild active application service releases after a full-state restore."""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
import json

from components.system_runtime.application_activation import activate_application_package
from deployment.authority_recovery import fence_recovered_authority


DATABASE = Path("/var/lib/3mm/core/3mm.db")
UPLOAD_ROOT = Path("/var/lib/3mm/core/uploads/modules")
APPLICATION_ROOT = Path("/var/lib/3mm/application-extensions")
KEY_ROOT = Path("/etc/3mm/application-extensions")
WANTS_ROOT = Path("/etc/systemd/system/multi-user.target.wants")


def _service_ids() -> tuple[int, int]:
    import grp
    import pwd

    return pwd.getpwnam("3mm-app").pw_uid, grp.getgrnam("3mm-app").gr_gid


def _restore_catalog_locations(connection: sqlite3.Connection, upload_root: Path) -> None:
    """Package locations belong to this installation, not the source computer.

    Rebind catalog metadata only. Opening/activating code still requires its
    normal identity and SHA-256 check. A damaged inactive digest gets no file
    target (the package directory itself cannot be used as a ZIP).
    """
    root = str(upload_root.resolve())
    location = """CASE WHEN typeof(sha256)='text' AND length(sha256)=64
                           AND length(CAST(sha256 AS BLOB))=64 AND sha256 NOT GLOB '*[^0-9a-f]*'
                      THEN :prefix || sha256 || '.zip' ELSE :directory END"""
    connection.execute(f"UPDATE module_packages SET file_path={location} WHERE file_path IS NOT ({location})",
                       {"prefix": os.path.join(root, ""), "directory": root})


def restore_application_extensions(
    database: Path = DATABASE,
    *,
    upload_root: Path = UPLOAD_ROOT,
    application_root: Path = APPLICATION_ROOT,
    key_root: Path = KEY_ROOT,
    service_ids: tuple[int, int] | None = None,
) -> tuple[str, ...]:
    # Also fence direct root recovery calls, before any application can start.
    fence_recovered_authority(database, reason="backup_restore")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = list(
            connection.execute(
                """
                SELECT i.module_id, i.configuration, p.module_id AS package_module_id, p.version, p.sha256
                FROM application_extension_installations AS i
                LEFT JOIN module_packages AS p ON p.id = i.module_package_id
                WHERE i.enabled = 1 AND i.status = 'active'
                ORDER BY i.module_id
                """
            )
        )
        # A direct recovery or rollback must not silently skip a dangling active
        # installation and then disable its unit as "not desired".
        if any(row["package_module_id"] != row["module_id"] or not isinstance(row["sha256"], str)
               or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"]) for row in rows):
            raise RuntimeError("An active application has no matching recoverable package")
        uid, gid = service_ids or _service_ids()
        desired: set[str] = set()
        restored: list[str] = []

        for row in rows:
            try:
                configuration = json.loads(row["configuration"] or "{}")
            except (TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    "Stored application configuration is invalid"
                ) from exc

            if not isinstance(configuration, dict):
                raise RuntimeError(
                    "Stored application configuration is invalid"
                )

            activated = activate_application_package(
                upload_root / f"{row['sha256']}.zip",
                row["sha256"],
                configuration=configuration,
                root=application_root,
                key_root=key_root,
                service_uid=uid,
                service_gid=gid,
            )
            if (
                activated.module_id != row["module_id"]
                or activated.version != row["version"]
            ):
                raise RuntimeError(
                    "Restored application package identity changed"
                )

            desired.add(activated.instance_id)
            connection.execute(
                """
                UPDATE application_extension_installations
                SET instance_id = ?, socket_path = ?,
                    health_checked_at = ?, error = NULL
                WHERE module_id = ?
                """,
                (
                    activated.instance_id,
                    str(activated.socket_path),
                    datetime.now(UTC).isoformat(),
                    activated.module_id,
                ),
            )
            restored.append(activated.module_id)
            # No SQLite write transaction across the next external activation.
            connection.commit()
        # Includes staged and disabled versions; do not enable or grant them.
        _restore_catalog_locations(connection, upload_root)
        connection.commit()
    finally:
        connection.close()

    if WANTS_ROOT.is_dir():
        for link in WANTS_ROOT.glob(
            "3mm-application-extension@*.service"
        ):
            match = re.fullmatch(
                r"3mm-application-extension@([0-9a-f]{24})\.service",
                link.name,
            )
            if match and match.group(1) not in desired:
                subprocess.run(
                    [
                        "/usr/bin/systemctl",
                        "disable",
                        "--now",
                        link.name,
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )

    return tuple(restored)

def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Application restore activation must run as root")
    restore_application_extensions()


if __name__ == "__main__":
    main()
