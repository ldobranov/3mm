"""Transport-neutral M21 output pump; NOT a production authority connector.

The owning runtime must supply a current-authority checker bound to the exact
authenticated session. There is no allow-by-default checker, device lookup,
provider registration, shell/process launch or route activation here. One
bounded output chunk is held at a time and every send is awaited, never replayed.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from three_mm_protocol.interactive_session import (
    MAX_SESSION_PAYLOAD_BYTES,
    SESSION_ID_PATTERN,
    encode_session_frame,
)

if TYPE_CHECKING:
    from three_mm_application_sdk.session import SessionOutputProvider


class SessionOutputError(RuntimeError):
    """Output stopped; no automatic retry or replacement session is allowed."""


class SessionOutputCleanupError(SessionOutputError):
    """Keep ownership evidence; provider cleanup has not been confirmed."""


async def pump_session_output(
    provider: SessionOutputProvider,
    session_id: str,
    send: Callable[[bytes], Awaitable[None]],
    *,
    authorize: Callable[[], Awaitable[None]],
    check_interval: float = 1.0,
    send_timeout: float = 10.0,
    close_timeout: float = 5.0,
) -> None:
    """Push unsolicited output using ordinary interactive-session.v1 frames.

    ``authorize`` must raise on denial/drift and return None on success. It is
    rechecked while reads/sends wait, not only when bytes arrive. Cancellation,
    denial, invalid output, EOF and transport failure all close this exact
    provider session. Close failure is surfaced, not mislabeled safe cleanup.
    Session limits/expiry and OS isolation remain the owning runtime's duties.
    """
    if (
        not isinstance(session_id, str)
        or re.fullmatch(SESSION_ID_PATTERN, session_id) is None
    ):
        raise ValueError("Session output identity is invalid")
    if (
        not callable(send)
        or not callable(authorize)
        or not callable(getattr(provider, "read_output", None))
    ):
        raise ValueError(
            "Session output requires a provider, transport and authority checker"
        )
    for name, value, minimum, maximum in (
        ("check interval", check_interval, 0.01, 1.0),
        ("send timeout", send_timeout, 0.01, 60.0),
        ("close timeout", close_timeout, 0.01, 60.0),
    ):
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not minimum <= value <= maximum
        ):
            raise ValueError(f"Session {name} is outside bounds")

    async def check() -> None:
        try:
            result = await asyncio.wait_for(authorize(), timeout=check_interval)
            if result is not None:
                raise SessionOutputError("Current session authority was not confirmed")
        except Exception as exc:
            raise SessionOutputError(
                "Current session authority is unavailable"
            ) from exc

    async def guarded(operation: Awaitable, timeout: float | None = None):
        task = asyncio.ensure_future(operation)
        deadline = (
            None if timeout is None else asyncio.get_running_loop().time() + timeout
        )
        try:
            while True:
                remaining = (
                    check_interval
                    if deadline is None
                    else min(
                        check_interval, deadline - asyncio.get_running_loop().time()
                    )
                )
                if remaining <= 0:
                    raise SessionOutputError("Session output transport timed out")
                done, _ = await asyncio.wait((task,), timeout=remaining)
                if done:
                    return task.result()
                await check()
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    reason = "output_failed"
    try:
        seq = 0
        while True:
            await check()
            payload = await guarded(provider.read_output(session_id))
            await check()  # Bytes received after revoke must not reach the browser.
            if payload is None:
                reason = "output_eof"
                return
            if (
                type(payload) is not bytes
                or not 1 <= len(payload) <= MAX_SESSION_PAYLOAD_BYTES
            ):
                raise SessionOutputError(
                    "Session provider output is invalid or exceeds frame bounds"
                )
            if seq == 2**32 - 1:
                raise SessionOutputError("Session output sequence exhausted")
            seq += 1
            frame = encode_session_frame(
                op="data",
                seq=seq,
                session_id=session_id,
                payload=payload,
                payload_kind="binary",
            )
            await guarded(send(frame), timeout=send_timeout)
    except asyncio.CancelledError:
        reason = "output_cancelled"
        raise
    finally:
        cleanup = asyncio.create_task(provider.close(session_id, reason))
        try:
            await asyncio.wait_for(asyncio.shield(cleanup), timeout=close_timeout)
        except asyncio.CancelledError:
            # A second disconnect/cancel must not abandon the already-owned
            # cleanup. Wait within the same bounded cleanup policy, then keep
            # the caller's cancellation rather than reporting a successful use.
            try:
                await asyncio.wait_for(asyncio.shield(cleanup), timeout=close_timeout)
            except BaseException as exc:
                cleanup.cancel()
                cleanup.add_done_callback(_consume_cleanup)
                raise SessionOutputCleanupError(
                    "Session provider cleanup is unconfirmed"
                ) from exc
            raise
        except Exception as exc:
            cleanup.cancel()
            cleanup.add_done_callback(_consume_cleanup)
            raise SessionOutputCleanupError(
                "Session provider cleanup is unconfirmed"
            ) from exc


def _consume_cleanup(task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()
