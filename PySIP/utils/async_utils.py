import asyncio
import functools
import logging
from .logger import logger


async def _cancel_and_wait(fut, loop):
    """Cancel the *fut* future or task and wait until it completes."""

    waiter = loop.create_future()
    cb = functools.partial(_release_waiter, waiter)
    fut.add_done_callback(cb)

    try:
        fut.cancel()
        # We cannot wait on *fut* directly to make
        # sure _cancel_and_wait itself is reliably cancellable.
        await waiter
    finally:
        fut.remove_done_callback(cb)

        
def _release_waiter(waiter, *args):
    if not waiter.done():
        waiter.set_result(None)

async def wait_for(fut, timeout, fut_2):
    """Wait for the single Future or coroutine to complete, with timeout.

    Coroutine will be wrapped in Task.

    Returns result of the Future or coroutine.  When a timeout occurs,
    it cancels the task and raises TimeoutError.  To avoid the task
    cancellation, wrap it in shield().

    If the wait is cancelled, the task is also cancelled.

    This function is a coroutine.
    """
    loop = asyncio.events.get_running_loop()

    if timeout is None:
        return await fut

    if timeout <= 0:
        fut = asyncio.ensure_future(fut, loop=loop)

        if fut.done():
            return fut.result()

        await _cancel_and_wait(fut, loop=loop)
        try:
            return fut.result()
        except asyncio.exceptions.CancelledError as exc:
            raise asyncio.exceptions.TimeoutError() from exc

    def start_timeout(waiter, *args):
        nonlocal timeout_handle
        logger.log(logging.DEBUG, "The timeout for DTMF has started right now.")
        timeout_handle = loop.call_later(timeout, _release_waiter, waiter)

    waiter = loop.create_future()
    timeout_handle = None
    cb = functools.partial(_release_waiter, waiter)
    st_cb = functools.partial(start_timeout, waiter)

    fut = asyncio.ensure_future(fut, loop=loop)
    fut.add_done_callback(cb)

    fut_2 = asyncio.ensure_future(fut_2, loop=loop)
    fut_2_cb = functools.partial(_release_waiter, fut_2)
    fut_2.add_done_callback(st_cb)
    fut.add_done_callback(fut_2_cb)

    try:
        # wait until the future completes or the timeout
        try:
            await waiter
        except asyncio.exceptions.CancelledError:
            if fut.done():
                return fut.result()
            else:
                fut.remove_done_callback(cb)
                # We must ensure that the task is not running
                # after wait_for() returns.
                # See https://bugs.python.org/issue32751
                await _cancel_and_wait(fut, loop=loop)
                raise

        if fut.done():
            return fut.result()
        else:
            fut.remove_done_callback(cb)
            # We must ensure that the task is not running
            # after wait_for() returns.
            # See https://bugs.python.org/issue32751
            await _cancel_and_wait(fut, loop=loop)
            # In case task cancellation failed with some
            # exception, we should re-raise it
            # See https://bugs.python.org/issue40607
            try:
                return fut.result()
            except asyncio.exceptions.CancelledError as exc:
                raise asyncio.exceptions.TimeoutError() from exc
    finally:
        if timeout_handle:
            timeout_handle.cancel()

