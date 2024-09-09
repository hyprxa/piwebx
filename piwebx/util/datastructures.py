from __future__ import annotations

import asyncio
from typing import Any

from piwebx.exceptions import BufferClosed


class Buffer:
    """A FIFO queue-like datastructure which allows multiple producers and multiple consumers
    to send and receive values. A buffer can be closed waking up and signalling any
    blocking producers and consumers.

    Not thread safe.
    """

    def __init__(self, maxsize: int = 0) -> None:
        self.maxsize = maxsize
        self.closed = False

        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=maxsize)
        self._futs: set[asyncio.Future] = set()
        self._loop: asyncio.AbstractEventLoop = None

    def empty(self) -> bool:
        """Returns ``True`` if the buffer is empty."""
        return self._queue.empty()

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Obtain a reference to the event loop."""
        if not self._loop:
            loop = asyncio.get_running_loop()
            self._loop = loop
            return loop
        return self._loop

    async def _pop(self) -> Any:
        """Pop a value from the buffer or block until one becomes available."""
        close = self._get_loop().create_future()
        get = asyncio.create_task(self._queue.get())
        
        self._futs.add(close)
        try:
            try:
                await asyncio.wait([get, close], return_when=asyncio.FIRST_COMPLETED)
            finally:
                close.cancel()
                self._futs.remove(close)
        except asyncio.CancelledError:
            get.cancel()
            raise
        
        if get.done():
            return get.result()
        
        get.cancel()
        assert self.closed
        raise BufferClosed()
        
    async def pop(self, timeout: float | None = None) -> Any:
        """Pop a value from the buffer or block until one becomes available.

        This can be safely canceled.

        Raises:
            BufferClosed: If ``pop`` is called on a closed and empty buffer or
                if ``close`` is called while waiting for a value
        """
        if not self.empty():
            return self._queue.get_nowait()

        if self.closed:
            raise BufferClosed()
        
        return await asyncio.wait_for(self._pop(), timeout=timeout)
    
    async def _append(self, element: Any) -> None:
        """Append a value to the buffer or block until space is available."""
        close = self._get_loop().create_future()
        put = asyncio.create_task(self._queue.put(element))

        self._futs.add(close)
        try:
            try:
                await asyncio.wait([put, close], return_when=asyncio.FIRST_COMPLETED)
            finally:
                close.cancel()
                self._futs.remove(close)
        except asyncio.CancelledError:
            put.cancel()
            raise
        
        if put.done():
            return put.result()
        
        put.cancel()
        assert self.closed
        raise BufferClosed()
    
    async def append(self, element: Any) -> None:
        """Append a value to the buffer or block until space is available.
        
        This can be safely cancelled.

        Raises:
            BufferClosed: If ``append`` is called on a closed buffer or
                if ``close`` is called while waiting to append a value
        """
        if self.closed:
            raise BufferClosed()
        
        await self._append(element)

    def close(self) -> None:
        """Close the buffer. Any coroutines waiting to ``pop`` or ``append`` to the buffer
        will wake up.

        ``close`` is idempotent, multiple calls will have no effect.
        """
        if self.closed:
            return
        
        for fut in self._futs:
            fut.cancel()
            
        self.closed = True