import sqlite3

import pytest

from packages.application_sdk import (
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
    sqlite_connect = sqlite3.connect

    class Connection(sqlite3.Connection):
        def execute(self, statement, *args, **kwargs):
            if fail and statement.startswith("PRAGMA table_info"):
                raise RuntimeError("fixture metadata failure")
            return super().execute(statement, *args, **kwargs)

    storage = ApplicationStorage(tmp_path)

    def connect(*args, **kwargs):
        connection = sqlite_connect(*args, factory=Connection, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    migration = ApplicationMigration("0001", lambda _connection: None)
    if fail:
        with pytest.raises(RuntimeError, match="metadata failure"):
            storage.migrate([migration], "0001")
    else:
        storage.migrate([migration], "0001")
    assert opened
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
