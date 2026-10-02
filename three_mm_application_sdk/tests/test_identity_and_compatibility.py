import sqlite3

import pytest

from three_mm_application_sdk import (
    ApplicationMigration,
    ApplicationPlatformClient,
    ApplicationStorage,
)


def test_sdk_rejects_malformed_identity_responses_and_proof_inputs(monkeypatch):
    client = ApplicationPlatformClient(None, "test", b"s" * 32)
    calls = []

    def invalid_response(action, payload):
        calls.append(action)
        return {"identity": {"installation_id": "dev_not-an-installation"}}

    monkeypatch.setattr(client, "_call", invalid_response)
    with pytest.raises(ValueError):
        client.get_installation_identity()
    with pytest.raises(ValueError):
        client.prove_installation_identity({"payload": "arbitrary-signing"})
    assert calls == ["installation.identity.get"]


@pytest.mark.parametrize("fail", [False, True])
def test_initial_migration_metadata_connection_is_closed(tmp_path, monkeypatch, fail):
    opened = []

    class Connection(sqlite3.Connection):
        closed = False

        def execute(self, statement, *args, **kwargs):
            if fail and statement.startswith("PRAGMA table_info"):
                raise RuntimeError("fixture metadata failure")
            return super().execute(statement, *args, **kwargs)

        def close(self):
            self.closed = True
            super().close()

    storage = ApplicationStorage(tmp_path)

    def connect():
        connection = sqlite3.connect(storage.database_path, factory=Connection)
        opened.append(connection)
        return connection

    monkeypatch.setattr(storage, "_connect", connect)
    migration = ApplicationMigration("0001", lambda _connection: None)
    if fail:
        with pytest.raises(RuntimeError, match="metadata failure"):
            storage.migrate([migration], "0001")
    else:
        storage.migrate([migration], "0001")
    assert opened and all(connection.closed for connection in opened)
