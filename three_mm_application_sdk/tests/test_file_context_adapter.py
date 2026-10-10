"""Host adapter injection keeps SDK 1.3 compatibility and context ownership."""

from pathlib import Path

import pytest

from three_mm_application_sdk import (
    ApplicationContext,
    ApplicationFileLimits,
    ApplicationFileStorage,
    ApplicationStorage,
    SDK_VERSION,
)


def test_host_file_adapter_keeps_old_clock_position_and_is_not_replaced(tmp_path):
    data = tmp_path / "data"
    adapter = ApplicationFileStorage(
        data, mode="read", limits=ApplicationFileLimits(8, 12, 2)
    )
    clock = object()
    context = ApplicationContext(
        "org.example.files",
        "1.0.0",
        data,
        {},
        ApplicationStorage(data),
        None,
        clock,
        file_storage=adapter,
    )
    assert context.files is adapter and context.clock is clock
    assert context.files.mode == "read" and context.files.limits == adapter.limits
    assert SDK_VERSION == "1.3"
    assert not data.exists()  # Context/adapter selection performs no file I/O.


@pytest.mark.parametrize(
    "adapter",
    [False, "approved", {"grant": True}, ApplicationFileStorage(Path("foreign"))],
)
def test_context_cannot_select_foreign_or_fake_file_adapter(tmp_path, adapter):
    with pytest.raises(ValueError, match="belong to this context"):
        ApplicationContext(
            "org.example.files",
            "1.0.0",
            tmp_path,
            {},
            ApplicationStorage(tmp_path),
            file_storage=adapter,
        )
    assert list(tmp_path.iterdir()) == []
