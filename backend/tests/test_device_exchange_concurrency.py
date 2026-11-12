"""Device long polls must not stall browser streams or retain stale authority."""

import asyncio
import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import backend.database  # noqa: F401 -- register the current ORM relationships
from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.device import Device, DeviceCredential, DevicePlatformState
from backend.devices.commands import api as commands
from backend.devices.platform import api as platform
from packages.protocol.device_platform import challenge


DEVICE_ID = "dev_" + "b" * 32
CREDENTIAL_ID = "cred_" + "c" * 32


class _SessionDouble:
    def rollback(self):
        pass

    def refresh(self, _device):
        pass

    def commit(self):
        pass


@pytest.mark.parametrize("phase", ["management", "signing", "command_poll"])
def test_synchronous_device_work_does_not_block_another_coroutine(monkeypatch, phase):
    """A browser input/output task must run while a device DB phase is waiting.

    The bounded gate is released by the other coroutine, not a fast-machine
    timing assertion. Before the fix the route blocks its own event loop until
    the fallback expires, so that coroutine cannot release the gate in time.
    """
    entered, release = threading.Event(), threading.Event()
    completed_with_other_coroutine = []

    def slow():
        entered.set()
        completed_with_other_coroutine.append(release.wait(2))

    def management(*_args):
        if phase == "management":
            slow()
        return {"command": None}

    proof = object()

    def signing(*_args):
        if phase == "signing":
            slow()
        return proof

    class Operations:
        def __init__(self, *_args):
            pass

        def next_command(self):
            slow()
            return None

    monkeypatch.setattr(platform, "management_payload", management)
    monkeypatch.setattr(platform, "sign_authority", signing)
    monkeypatch.setattr(commands, "DeviceOperations", Operations)
    device = SimpleNamespace(id=1, device_id=DEVICE_ID)
    payload = SimpleNamespace(device_id=DEVICE_ID, operation="command")

    async def run():
        async def browser_progress():
            while not entered.is_set():
                await asyncio.sleep(0)
            release.set()

        if phase == "command_poll":
            operation = commands.next_command(
                DEVICE_ID, Response(), wait_seconds=0, device=device, db=_SessionDouble()
            )
        else:
            operation = platform.exchange(
                DEVICE_ID, payload, wait_seconds=0, device=device, db=_SessionDouble()
            )
        result, _ = await asyncio.gather(operation, browser_progress())
        return result

    result = asyncio.run(run())
    assert completed_with_other_coroutine == [True]
    if phase == "command_poll":
        assert result.status_code == 204
    else:
        assert result is proof


@pytest.mark.parametrize("adapter", ["signed", "unsigned"])
@pytest.mark.parametrize("worker_fails", [False, True])
def test_cancellation_joins_device_worker_before_closing_its_session(
    monkeypatch, adapter, worker_fails
):
    """Even repeated task cancellation cannot close a Session under its worker."""
    entered, release, completed = (
        threading.Event(), threading.Event(), threading.Event()
    )

    class OwnedSession(_SessionDouble):
        closed = False

        def close(self):
            self.closed = True

    db = OwnedSession()

    def slow():
        entered.set()
        try:
            assert release.wait(2), "The test did not release its bounded worker"
            assert not db.closed, "The dependency closed a Session still in use"
            if worker_fails:
                raise RuntimeError("Injected database phase failure")
        finally:
            completed.set()

    def management(*_args):
        slow()
        return {"command": None}

    class Operations:
        def __init__(self, *_args):
            pass

        def next_command(self):
            slow()
            return None

    monkeypatch.setattr(platform, "management_payload", management)
    monkeypatch.setattr(platform, "sign_authority", lambda *_args: {"signed": True})
    monkeypatch.setattr(commands, "DeviceOperations", Operations)
    device = SimpleNamespace(id=1, device_id=DEVICE_ID)
    payload = SimpleNamespace(device_id=DEVICE_ID, operation="command")

    async def run():
        async def request():
            try:
                if adapter == "signed":
                    return await platform.exchange(
                        DEVICE_ID, payload, wait_seconds=0, device=device, db=db
                    )
                return await commands.next_command(
                    DEVICE_ID, Response(), wait_seconds=0, device=device, db=db
                )
            finally:
                db.close()  # FastAPI's dependency teardown after route exit.

        task = asyncio.create_task(request())
        try:
            async def wait_started():
                while not entered.is_set():
                    if task.done():
                        await task
                    await asyncio.sleep(0)

            await asyncio.wait_for(wait_started(), 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done(), "Cancellation abandoned the running database phase"
            assert not db.closed
            assert not completed.is_set()
        finally:
            release.set()
            # Always consume the task, also when the pre-fix assertion fails.
            try:
                await task
            except asyncio.CancelledError:
                pass
        assert task.cancelled()
        assert completed.is_set()
        assert db.closed

    asyncio.run(run())


@pytest.fixture
def device_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'device-poll.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        device = Device(
            device_id=DEVICE_ID, display_name="poll-test", role="standalone",
            protocol_version="1.0", approved_at=datetime.now(UTC),
        )
        db.add(device)
        db.flush()
        db.add_all([
            CoreAuthorityGuard(singleton_id=1),
            DevicePlatformState(device_id=device.id),
            DeviceCredential(
                device_id=device.id, credential_id=CREDENTIAL_ID,
                secret_hash="d" * 64,
            ),
        ])
        db.commit()
    try:
        yield engine
    finally:
        engine.dispose()


def _poll(adapter, db, device):
    if adapter == "signed":
        return platform.exchange(
            DEVICE_ID, challenge(DEVICE_ID, CREDENTIAL_ID, "command"),
            wait_seconds=1, device=device, db=db,
        )
    return commands.next_command(
        DEVICE_ID, Response(), wait_seconds=1, device=device, db=db,
    )


@pytest.mark.parametrize("adapter", ["signed", "unsigned"])
def test_device_poll_releases_its_database_snapshot_before_wait(
    monkeypatch, device_database, adapter
):
    engine = device_database
    with Session(engine) as db:
        device = db.scalar(select(Device).where(Device.device_id == DEVICE_ID))

        async def wait(_device_id, **_kwargs):
            assert not db.in_transaction(), "A long poll retained a database transaction"
            return False

        module = platform if adapter == "signed" else commands
        monkeypatch.setattr(module.device_command_notifier, "wait", wait)
        monkeypatch.setattr(platform, "sign_authority", lambda *_args: {"signed": True})
        result = asyncio.run(_poll(adapter, db, device))
        if adapter == "signed":
            assert result == {"signed": True}
        else:
            assert result.status_code == 204


@pytest.mark.parametrize("adapter", ["signed", "unsigned"])
def test_device_revoked_during_long_poll_is_not_served_from_old_snapshot(
    monkeypatch, device_database, adapter
):
    engine = device_database
    signed = []
    with Session(engine) as db:
        device = db.scalar(select(Device).where(Device.device_id == DEVICE_ID))

        async def wait(_device_id, **_kwargs):
            with Session(engine) as writer:
                current = writer.scalar(select(Device).where(Device.device_id == DEVICE_ID))
                current.revoked_at = datetime.now(UTC)
                writer.commit()
            return True

        def sign(*_args):
            signed.append(True)
            return {"signed": True}

        module = platform if adapter == "signed" else commands
        monkeypatch.setattr(module.device_command_notifier, "wait", wait)
        monkeypatch.setattr(platform, "sign_authority", sign)
        with pytest.raises(HTTPException) as failure:
            asyncio.run(_poll(adapter, db, device))
        assert failure.value.status_code in {401, 409}
        assert signed == []
