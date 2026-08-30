import os

from agent.hardware.identifier import MockIdentifierAdapter


def test_mock_identifier_sequence_survives_restart(tmp_path):
    state = tmp_path / "identifier-sequence.json"
    first = MockIdentifierAdapter(state).scan("TAG-1")
    second = MockIdentifierAdapter(state).scan("TAG-2")

    assert first["payload"]["sequence"] == 1
    assert second["payload"]["sequence"] == 2
    assert second["payload"]["adapter_kind"] == "mock"
    if os.name != "nt":
        assert state.stat().st_mode & 0o777 == 0o600
