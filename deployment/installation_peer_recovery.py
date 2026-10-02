"""Fence backed-up peer trust before restored services can start."""

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
import sqlite3


def quarantine_restored_installation_peers(database: Path) -> None:
    """Only use on the already validated staging database, never on live state.

    The installation signing identity is preserved, but neither consent nor a
    restored pre-revocation credential may reactivate a peer automatically.
    Legacy backups without the peer tables require no additional migration.
    """
    with closing(sqlite3.connect(database)) as connection, connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        now = datetime.now(UTC).isoformat()
        if "installation_peer_inbound" in tables:
            connection.execute(
                "UPDATE installation_peer_inbound SET state='revoked', credential=NULL, completed_digest=NULL, rotation_digest=NULL, generation=generation+1, updated_at=?",
                (now,),
            )
        if "installation_peer_outbound" in tables:
            connection.execute(
                "UPDATE installation_peer_outbound SET state='revoked', credential=NULL, complete_request=NULL, rotation_request=NULL, report_id=NULL, report_projection=NULL, report_result=NULL, consent_revision=consent_revision+1, updated_at=?",
                (now,),
            )
        if "installation_peer_nonces" in tables:
            connection.execute("DELETE FROM installation_peer_nonces")
