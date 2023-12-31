from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, TypeVar, cast, TYPE_CHECKING

from piwebx.util.time import from_utc

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Sequence
    from piwebx.types import JSONPrimitive, TimeseriesRow

    T = TypeVar("T")


async def locf(stream: AsyncIterator[TimeseriesRow]) -> AsyncIterator[TimeseriesRow]:
    """For recorded data, carries the last observation forward."""
    try:
        last_timestamp, last_data = await stream.__anext__()
    except StopAsyncIteration:
        return
    else:
        yield last_timestamp, last_data

    while True:
        try:
            new_timestamp, new_data = await stream.__anext__()
        except StopAsyncIteration:
            return
        else:
            next_data = [
                val if val is not None else last_data[i]
                for i, val in enumerate(new_data)
            ]
            last_data = next_data
            yield new_timestamp, next_data


def split_range(
    start_time: datetime, end_time: datetime, dt: timedelta
) -> tuple[list[datetime], list[datetime]]:
    """Split a time range into smaller ranges."""
    start_times = []
    end_times = []

    while start_time < end_time:
        start_times.append(start_time)
        next_timestamp = start_time + dt

        if next_timestamp >= end_time:
            start_time = end_time

        else:
            start_time = next_timestamp
        end_times.append(start_time)

    return start_times, end_times


def split_range_on_interval(
    start_time: datetime,
    end_time: datetime,
    interval: timedelta,
    request_chunk_size: int = 5000,
) -> tuple[list[datetime], list[datetime]]:
    """Split a time range into smaller ranges based on a time interval."""
    td = end_time - start_time
    request_time_range = td.total_seconds()
    items_requested = math.ceil(request_time_range / interval.total_seconds())

    if items_requested <= request_chunk_size:
        return [start_time], [end_time]

    dt = timedelta(seconds=math.floor(interval.total_seconds() * request_chunk_size))
    return split_range(start_time, end_time, dt)


def split_range_on_frequency(
    start_time: datetime,
    end_time: datetime,
    request_chunk_size: int = 5000,
    scan_rate: float = 5,
) -> tuple[list[datetime], list[datetime]]:
    """Split a time range into smaller ranges based on the relative update
    frequency of the data.
    """
    td = end_time - start_time
    request_time_range = td.total_seconds()
    items_requested = math.ceil(request_time_range / scan_rate)

    if items_requested <= request_chunk_size:
        return [start_time], [end_time]

    dt = timedelta(seconds=math.floor(request_chunk_size * scan_rate))
    return split_range(start_time, end_time, dt)


def get_timestamp_index(data: list[dict[str, Any]]) -> list[str]:
    """Create a single, sorted timestamp index from a chunk of timeseries data
    potentially containing duplicate timestamps.

    Duplicate timestamps are removed.
    """
    index = set()
    for datum in data:
        index.update(datum["timestamp"])
    return sorted(index)


def iter_timeseries_rows(
    index: list[str],
    data: list[dict[str, list[Any]]],
    timezone: str | None = None,
) -> Iterator[TimeseriesRow]:
    """Iterate a collection of timeseries data row by row and produce rows
    which have data aligned on a common timestamp.

    This will also handle timezone conversion. Timestamps from the PI Web API are
    always UTC. If a timezone is specified, this will handle the conversion from
    UTC to the desired timezone. The returned timestamps are always timezone aware.

    Note: The timestamps must be in ascending order for this to work correctly.
    If the start time of a 'streams' or 'streamsets' query is greater than the
    end time, the timestamps will be sorted in descending order and this will
    implementation will not work.
    """
    timezone = timezone or "UTC"
    for timestamp in index:
        row = []
        for datum in data:
            try:
                if datum["timestamp"][0] == timestamp:
                    row.append(datum["value"].pop(0))
                    datum["timestamp"].pop(0)
                else:
                    # Most recent data point is later than current timestamp
                    row.append(None)
            except IndexError:
                # No more data for that column
                row.append(None)
        yield from_utc(timestamp, timezone), row


def format_streams_content(
    content: dict[str, list[dict[str, JSONPrimitive]]] | None
) -> dict[str, list[JSONPrimitive]]:
    """Extract timestamp and value for each item in a multi-value stream response."""
    formatted = cast("dict[str, list[JSONPrimitive]]", {"timestamp": [], "value": []})
    items = content.get("Items", []) if content is not None else []

    for item in items:
        timestamp = item["Timestamp"]
        good = item["Good"]
        if not good:
            value = None
        else:
            # If a stream item returned an error, the value will be `None`
            # and we're not particularly interested in the errors
            # https://docs.osisoft.com/bundle/pi-web-api-reference/page/help/topics/error-handling.html
            value = item["Value"]
            if isinstance(value, dict):
                value = value["Name"]
        formatted["timestamp"].append(timestamp)
        formatted["value"].append(value)

    return formatted


def paginate(seq: Sequence[T], page_size: int) -> Iterator[Sequence[T]]:
    """Consume an iterable and return it in chunks.

    Every chunk is at most `page_size`. Never return an empty chunk.
    """
    page = []
    it = iter(seq)
    while True:
        try:
            for _ in range(page_size):
                page.append(next(it))
            yield page
            page = []
        except StopIteration:
            if page:
                yield page
            return
