"""In-process wake-up channel for authenticated device command long polling."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict


class DeviceCommandNotifier:
    """Wake async waiters without making the database the polling clock.

    Commands remain durable in the database. This notifier only shortens the
    time between a committed command and the next authenticated Agent fetch.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._revisions: dict[int, int] = defaultdict(int)
        self._waiters: dict[
            int,
            set[tuple[asyncio.AbstractEventLoop, asyncio.Future[int]]],
        ] = defaultdict(set)

    def revision(self, device_id: int) -> int:
        with self._lock:
            return self._revisions[device_id]

    def notify(self, device_id: int) -> int:
        with self._lock:
            revision = self._revisions[device_id] + 1
            self._revisions[device_id] = revision
            waiters = tuple(self._waiters.pop(device_id, ()))
        for loop, future in waiters:
            try:
                loop.call_soon_threadsafe(self._resolve, future, revision)
            except RuntimeError:
                # A request loop may close while a response is being cancelled.
                continue
        return revision

    async def wait(self, device_id: int, *, after: int, timeout: float) -> bool:
        if timeout <= 0:
            return self.revision(device_id) > after
        loop = asyncio.get_running_loop()
        future: asyncio.Future[int] = loop.create_future()
        waiter = (loop, future)
        with self._lock:
            if self._revisions[device_id] > after:
                return True
            self._waiters[device_id].add(waiter)
        try:
            await asyncio.wait_for(future, timeout=timeout)
            return True
        except TimeoutError:
            return False
        finally:
            with self._lock:
                device_waiters = self._waiters.get(device_id)
                if device_waiters is not None:
                    device_waiters.discard(waiter)
                    if not device_waiters:
                        self._waiters.pop(device_id, None)

    @staticmethod
    def _resolve(future: asyncio.Future[int], revision: int) -> None:
        if not future.done():
            future.set_result(revision)


device_command_notifier = DeviceCommandNotifier()
