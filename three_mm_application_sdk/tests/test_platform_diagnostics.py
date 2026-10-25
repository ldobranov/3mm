import json
import socket

import pytest

from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError, SDK_VERSION
from three_mm_protocol.diagnostics import DiagnosticSession


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix application transport")
def test_unavailable_transport_has_a_trace_without_a_ready_core(tmp_path):
    session = DiagnosticSession("sdk", SDK_VERSION)
    session.start()
    client = ApplicationPlatformClient(tmp_path / "missing.sock", "a" * 24,
                                      b"private-secret-must-not-leak!!!!", diagnostics=session)
    with pytest.raises(ApplicationPlatformError, match="unavailable"):
        client.get_installation_identity()
    with session.export() as chunks:
        exported = list(chunks)
    record = json.loads(exported[1])
    assert record["span_id"] == "sdk.call"
    assert record["parent_span_id"] is None
    assert record["result"] == "error"
    assert record["reason"] == "transport_unavailable"
    assert b"private-secret" not in b"".join(exported)
    assert str(tmp_path).encode() not in b"".join(exported)
