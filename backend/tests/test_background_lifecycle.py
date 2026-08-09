import asyncio

from backend.utils.extension_monitoring import ExtensionPerformanceMonitor
from backend.utils.extension_updates import ExtensionUpdateManager


def test_update_worker_has_managed_lifecycle():
    async def scenario():
        manager = ExtensionUpdateManager()

        await manager.start_update_worker()
        first_task = manager._worker_task
        assert first_task is not None
        assert not first_task.done()

        await manager.start_update_worker()
        assert manager._worker_task is first_task

        await manager.stop_update_worker()
        assert manager._worker_task is None
        assert first_task.cancelled()

    asyncio.run(scenario())


def test_performance_monitor_has_managed_lifecycle():
    async def scenario():
        monitor = ExtensionPerformanceMonitor()

        await monitor.start_monitoring()
        first_task = monitor._monitoring_task
        assert first_task is not None
        assert not first_task.done()

        await monitor.start_monitoring()
        assert monitor._monitoring_task is first_task

        await monitor.stop_monitoring()
        assert monitor._monitoring_task is None
        assert first_task.cancelled()

    asyncio.run(scenario())
