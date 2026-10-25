"""Own optional Core services without making them prerequisites for administration.

Only fixed component states and reason codes are exported. Exceptions, paths and
credentials never enter the status projection. This is lifecycle bookkeeping,
not a worker supervisor or a replacement for the process boundary planned in P4.
"""

import asyncio
import inspect
import logging

logger = logging.getLogger(__name__)


class CoreComponents:
    def __init__(self):
        self._states = {}
        self._closers = []
        self._checks = {}
        self._stopping = False

    def _set(self, name, state, reason):
        value = {"state": state, "reason": reason}
        if self._states.get(name) != value and state in {"failed", "degraded"}:
            logger.warning("Optional Core component %s: %s", name, reason)
        self._states[name] = value

    def ready(self, name):
        if not self._stopping:
            self._set(name, "ready", "ok")

    def degraded(self, name):
        if not self._stopping:
            self._set(name, "degraded", "iteration_failed")

    @staticmethod
    async def _invoke(callback):
        result = callback()
        if inspect.isawaitable(result):
            await result

    async def _close(self, name, closer):
        try:
            await self._invoke(closer)
        except Exception:
            self._set(name, "failed", "shutdown_failed")
            return False
        return True

    async def start(self, name, factory, *, start="start", stop="stop", task_attribute=None, check=None):
        self._set(name, "starting", "starting")
        instance = None
        try:
            instance = factory()
            await self._invoke(getattr(instance, start))
        except BaseException as error:
            self._set(name, "failed", "startup_failed")
            if instance is not None:
                closer = getattr(instance, stop)
                if not await self._close(name, closer):
                    self._closers.append((name, closer))
            if not isinstance(error, Exception):
                raise
            return None
        self._closers.append((name, getattr(instance, stop)))
        self.ready(name)
        if check:
            self._checks[name] = lambda: check(instance)
        if task_attribute:
            task = getattr(instance, task_attribute)
            if task is not None:
                task.add_done_callback(lambda done: self._completed(name, done))
            else:
                self._set(name, "failed", "worker_stopped")
        return instance

    def _completed(self, name, task):
        error = None if task.cancelled() else task.exception()
        if not self._stopping:
            self._set(name, "failed", "worker_failed" if error else "worker_stopped")

    def spawn(self, name, work, *, one_shot=False):
        async def run():
            self.ready(name)
            try:
                result = await work()
            except asyncio.CancelledError:
                if not self._stopping:
                    self._set(name, "failed", "worker_stopped")
                raise
            except Exception:
                self._set(name, "failed", "worker_failed")
            else:
                if one_shot:
                    self._set(name, "degraded" if result is False else "ready",
                              "iteration_failed" if result is False else "ok")
                elif not self._stopping:
                    self._set(name, "failed", "worker_stopped")
        self._set(name, "starting", "starting")
        task = asyncio.create_task(run(), name=name)
        async def stop_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._closers.append((name, stop_task))
        return task

    def snapshot(self):
        if not self._stopping:
            for name, check in self._checks.items():
                try:
                    available = check()
                except Exception:
                    available = False
                if not available:
                    self._set(name, "failed", "worker_stopped")
        return {"schema_version": 1,
                "status": "stopped" if self._stopping else
                          "ready" if self._states and all(item["state"] == "ready" for item in self._states.values()) else "degraded",
                "components": {key: dict(value) for key, value in sorted(self._states.items())}}

    async def close(self):
        self._stopping = True
        for name, closer in reversed(self._closers):
            if await self._close(name, closer):
                self._set(name, "stopped", "stopped")
        self._closers.clear()
        self._checks.clear()
