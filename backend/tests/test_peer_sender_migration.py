"""Legacy permissions never silently acquire signed export permission."""
import subprocess
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import create_engine, text
from backend.tests.test_migration_history import _alembic
from backend.installation.sender_consent import contact_state


def test_historical_contact_is_not_current_reachability():
    now = datetime.now(UTC)
    obs = {"revision": 3, "state": "offline", "at": now.isoformat()}
    assert contact_state(obs, 3, now=now + timedelta(seconds=120)) == "offline"
    assert contact_state(obs, 3, now=now + timedelta(seconds=121)) == "stale"
    assert contact_state(obs, 4, now=now) == "unknown"
    assert contact_state({**obs, "state": "unknown"}, 3, now=now) == "unknown"
    assert contact_state(obs, 3, now=now - timedelta(seconds=1)) == "unknown"


def test_existing_link_requires_explicit_approval_after_upgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'before.db'}"
    _alembic(url, "upgrade", "b096b7e82f86")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("""INSERT INTO installation_peer_outbound
          (link_id,module_id,application_instance_id,sender_identity,receiver_identity,origin,
           target_module_id,consent,consent_revision,state,report_id,created_at,updated_at)
          VALUES ('old','example','instance','{}','{}','https://example.invalid',
           'receiver','{}',2,'active','original',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""))
    _alembic(url, "upgrade", "head")
    _alembic(url, "check")
    with engine.connect() as db:
        assert db.execute(text("SELECT send_revision,send_approval,report_sequence,report_id FROM installation_peer_outbound")).one() == (1,None,1,"original")
    with pytest.raises(subprocess.CalledProcessError) as error:
        _alembic(url, "downgrade", "b096b7e82f86")
    assert "Withdraw live outgoing links" in error.value.stderr
    with engine.begin() as db: db.execute(text("UPDATE installation_peer_outbound SET state='revoked'"))
    _alembic(url, "downgrade", "b096b7e82f86")
    engine.dispose()
