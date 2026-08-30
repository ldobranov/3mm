#!/usr/bin/env python3
"""Rebuild active application service releases after a full-state restore."""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from three_mm_runtime.application_activation import activate_application_package


DATABASE = Path("/var/lib/3mm/core/3mm.db")
UPLOAD_ROOT = Path("/var/lib/3mm/core/uploads/modules")
APPLICATION_ROOT = Path("/var/lib/3mm/application-extensions")
KEY_ROOT = Path("/etc/3mm/application-extensions")
WANTS_ROOT = Path("/etc/systemd/system/multi-user.target.wants")


def _service_ids() -> tuple[int, int]:
    import grp
    import pwd

    return pwd.getpwnam("3mm-app").pw_uid, grp.getgrnam("3mm-app").gr_gid


def restore_application_extensions(
    database: Path = DATABASE,
    *,
    upload_root: Path = UPLOAD_ROOT,
    application_root: Path = APPLICATION_ROOT,
    key_root: Path = KEY_ROOT,
    service_ids: tuple[int, int] | None = None,
) -> tuple[str, ...]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = list(
            connection.execute(
                """
                SELECT i.module_id, p.version, p.sha256
                FROM application_extension_installations AS i
                JOIN module_packages AS p ON p.id = i.module_package_id
                WHERE i.enabled = 1 AND i.status = 'active'
                ORDER BY i.module_id
                """
            )
        )
        uid, gid = service_ids or _service_ids()
        desired: set[str] = set()
        restored: list[str] = []
        for row in rows:
            activated = activate_application_package(
                upload_root / f"{row['sha256']}.zip",
                row["sha256"],
                root=application_root,
                key_root=key_root,
                service_uid=uid,
                service_gid=gid,
            )
            if (
                activated.module_id != row["module_id"]
                or activated.version != row["version"]
            ):
                raise RuntimeError("Restored application package identity changed")
            desired.add(activated.instance_id)
            connection.execute(
                """
                UPDATE application_extension_installations
                SET instance_id = ?, socket_path = ?, health_checked_at = ?, error = NULL
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
        connection.commit()
    finally:
        connection.close()

    if WANTS_ROOT.is_dir():
        for link in WANTS_ROOT.glob("3mm-application-extension@*.service"):
            match = re.fullmatch(
                r"3mm-application-extension@([0-9a-f]{24})\.service", link.name
            )
            if match and match.group(1) not in desired:
                subprocess.run(
                    ["/usr/bin/systemctl", "disable", "--now", link.name],
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
