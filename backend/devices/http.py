"""HTTP adapter boundaries; logical device operations live in services."""

import asyncio

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from packages.protocol.transport import DeviceProtocolError


async def database_phase(operation, *args, **kwargs):
    """Do not block the event loop or close a dependency's Session mid-worker.

    Cancelling an asyncio caller can bypass AnyIO cancellation shielding. Join
    the original bounded DB phase, including on repeated cancellation, before
    propagating cancellation so get_db cannot close its Session concurrently.
    Never repeat the phase or change its commit/outcome after an uncertain reply.
    """
    worker = asyncio.create_task(run_in_threadpool(operation, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not worker.cancelled():
            worker.exception()  # Consume the original outcome; no automatic replay.
        raise


def call(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except DeviceProtocolError as exc:
        status = {
            "unauthorized": 401,
            "forbidden": 403,
            "conflict": 409,
            "capacity": 429,
        }[exc.kind]
        headers = {"WWW-Authenticate": "Device"} if exc.kind == "unauthorized" else None
        raise HTTPException(status, detail=exc.detail, headers=headers) from exc
