from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from httpx_ws import aconnect_ws

from piwebx.exceptions import BufferClosed,  ChannelGroupException
from piwebx.util.data import format_streamsets_content, iter_timeseries_values, paginate
from piwebx.util.datastructures import Buffer


__all__ = ("ChannelGroup", "open_channel_group",)

if TYPE_CHECKING:
    from httpx import AsyncClient
    
    from piwebx.types import LabeledTimeseriesValue


MAX_HEADER_BYTES = 4096  # 4KB
MAX_BUFFER = 500


@asynccontextmanager
async def open_channel_group(
    client: AsyncClient,
    web_ids: Sequence[str],
    include_initial_values: bool = False,
    maxsize: int = 512,
    keepalive_ping_interval_seconds: float = 20,
    keepalive_ping_timeout_seconds: float = 20,
    subprotocols: list[str] | None = None,
    timezone: str | None = None,
) -> AsyncIterator[ChannelGroup[LabeledTimeseriesValue]]:
    """Subscribe to a sequence of PI tags for near real-time data streaming.

    Wraps N websocket connections and returns a `ChannelGroup` for iterating
    data returned from the PI Web API. The number of websocket connections is
    a function of the number of tags and how long the WebId's are for the tags,
    it is not deterministic.

    Example:
    ```python
    async def iter_channel_group():
        client = ...
        web_ids = [...]
        # Upon exiting the context, all connections in the channel group are closed
        with open_channel_group(client, web_ids) as cg:
            async for val in cg:
                ...

    Args:
        client: The Client to execute requests and create websocket
            connections.
        web_ids: The web_ids to stream data for.
        include_inital_values: If ``True`` once a connection is established, the web API
            will send the current value for the PI tag
        maxsize: The maximum number of timeseries values to buffer. When the buffer fills,
            websocket messages will buffer at the connection level up to 512 messages, at
            which point messages will then buffer at the transport level
        keepalive_ping_interval_seconds: Interval at which the client will automatically
            send a Ping event to keep the connection alive. Set it to `None` to 
            disable this mechanism. Defaults to 20 seconds.
        keepalive_ping_timeout_seconds: Maximum delay the client will wait for an answer
            to its Ping event. If the delay is exceeded, ``httpx_ws.WebSocketNetworkError``
            will be raised and the connection closed. Defaults to 20 seconds.
        subprotocols:
            Optional list of suprotocols to negotiate with the server.
    """
    # Determine how many connections we need to create based on the size of all
    # WebId's so we don't exceed the header size limit on servers. This is not
    # perfect, we set a relatively conservative limit of 4KB to add another
    # connection. This gives a minumum of 4KB (on most servers) for other headers
    # such as cookies, authorization, extensions, etc. Also, we assume the length
    # of each WebId is more or less the same (which is not guarenteed to be true)
    # and we make no attempt to adjust our limit based on the current size of
    # the other headers.
    num_connections = len("&webId=".join(web_ids).encode()) // MAX_HEADER_BYTES + 1
    page_size = math.ceil(len(web_ids) / num_connections)
    buf = Buffer(maxsize=maxsize)
    group = ChannelGroup(client, buf)
    for subset in paginate(web_ids, page_size=page_size):
        group._open_channel(
            web_ids=subset,
            include_initial_values=include_initial_values,
            keepalive_ping_interval_seconds=keepalive_ping_interval_seconds,
            keepalive_ping_timeout_seconds=keepalive_ping_timeout_seconds,
            subprotocols=subprotocols,
            timezone=timezone,
        )
    try:
        yield group
    finally:
        await group.close()


class ChannelGroup(AsyncIterator):
    """Manage and iterate over a group of channel connections."""

    def __init__(self, client: AsyncClient, buf: Buffer) -> None:
        self._client = client
        self._buf = buf
        self._exceptions: list[BaseException] = []
        self._channels: set[asyncio.Task] = set()

    async def close(self) -> None:
        """Close the channel group.
        
        This closes all channels and closes the underlying buffer.
        """
        futs = tuple(self._channels)
        for fut in futs: fut.cancel()
        self._buf.close()
        if futs:
            await asyncio.wait(futs, return_when=asyncio.ALL_COMPLETED)

    def _channel_done(self, fut: asyncio.Future) -> None:
        """Callback after a channel closes. Discard the channel, close the group,
        and note any exceptions.
        """
        self._channels.discard(fut)
        try:
            exc = fut.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            self._exceptions.append(exc)
        self.close()

    def _open_channel(
        self,
        web_ids: Sequence[str],
        include_initial_values: bool = False,
        keepalive_ping_interval_seconds: float = 20,
        keepalive_ping_timeout_seconds: float = 20,
        subprotocols: list[str] | None = None,
        timezone: str | None = None,
    ) -> None:
        """Create a task that opens and manages a single channel."""
        url = (
            f"streamsets/channel?webId={'&webId='.join(web_ids)}"
            f"&includeInitialValues={include_initial_values}"
        )
        task = asyncio.create_task(
            self._run_channel(
                url,
                keepalive_ping_interval_seconds=keepalive_ping_interval_seconds,
                keepalive_ping_timeout_seconds=keepalive_ping_timeout_seconds,
                subprotocols=subprotocols,
                timezone=timezone, 
            )
        )
        task.add_done_callback(self._channel_done)
        self._channels.add(task)

    async def _run_channel(
        self,
        url: str,
        keepalive_ping_interval_seconds: float = 20,
        keepalive_ping_timeout_seconds: float = 20,
        subprotocols: list[str] | None = None,
        timezone: str | None = None,
    ) -> None:
        """Establish a connection to the remote server, parse data, and append the
        data to the buffer.
        """
        async with aconnect_ws(
            url,
            self._client,
            keepalive_ping_interval_seconds=keepalive_ping_interval_seconds,
            keepalive_ping_timeout_seconds=keepalive_ping_timeout_seconds,
            subprotocols=subprotocols,
        ) as ws:
            while True:
                content = await ws.receive_json()
                data = format_streamsets_content(content)
                for value in iter_timeseries_values(data, timezone=timezone):
                    try:
                        await self._buf.append(value)
                    except BufferClosed:
                        break

    async def __anext__(self) -> LabeledTimeseriesValue:
        try:
            return await self._buf.pop()
        except BufferClosed:
            pass

        if self._exceptions:
            raise ChannelGroupException(self._exceptions)
        
        raise StopAsyncIteration()