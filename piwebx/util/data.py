from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, TypeVar, cast, TYPE_CHECKING

from piwebx.util.time import from_utc


__all__ = ("locf", "join_on_interpolated")

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Sequence
    from piwebx.types import JSONPrimitive, LabeledTimeseriesValue, TimeseriesRow

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


async def join_on_interpolated(
    interpolated_stream: AsyncIterator[TimeseriesRow],
    recorded_stream: AsyncIterator[TimeseriesRow],
) -> AsyncIterator[TimeseriesRow]:
    """Join a recorded stream on the timestamp index of an interpolated stream.

    This behaves like a "fuzzy" join where the recorded timestamps are aligned by
    the nearest timestamp to the interpolated dataset. Recorded data is filled
    with last observation carried forward, the fuzzy join never involves backdating.
    """
    recorded_stream_ended = False
    try:
        last_recorded_row = await recorded_stream.__anext__()
    except StopAsyncIteration:
        # No data in the recorded stream
        return
    try:
        current_recorded_row = await recorded_stream.__anext__()
    except StopAsyncIteration:
        # The recorded stream only had one row. This shouldnt even be possible
        # if using `get_recorded` but if someone implmented their own stream then
        # we could see this situation
        recorded_stream_ended = True
        current_recorded_row = last_recorded_row

    last_interpolated_row = None
    async for current_interpolated_row in interpolated_stream:
        # Ensure timestamps are in ascending order
        if (
            last_interpolated_row is not None
            and last_interpolated_row[0] > current_interpolated_row[0]
        ):
            raise ValueError(
                "The inteprolated stream must be sorted in ascending "
                "order by timestamp."
            )

        while (
            not recorded_stream_ended
            and current_recorded_row[0] < current_interpolated_row[0]
        ):
            try:
                next_recorded_row = await recorded_stream.__anext__()
            except StopAsyncIteration:
                recorded_stream_ended = True
            else:
                last_recorded_row = current_recorded_row
                current_recorded_row = next_recorded_row

        if last_recorded_row[0] > current_recorded_row[0]:
            raise ValueError(
                "The recorded stream must be sorted in ascending " "order by timestamp"
            )

        if last_recorded_row[0] > current_interpolated_row[0]:
            # Dont back date data, fill with `None`
            yield current_interpolated_row[0], [
                *current_interpolated_row[1],
                *[None] * (len(last_recorded_row) - 1),
            ]

        elif current_recorded_row[0] < current_interpolated_row[0]:
            # We are at the end of the recorded stream. We don't know when the
            # next data update is and what its value is so we fill in `None`
            yield current_interpolated_row[0], [
                *current_interpolated_row[1],
                *[None] * (len(current_recorded_row) - 1),
            ]

        elif current_recorded_row[0] == current_interpolated_row[0]:
            # We had a perfect timestamp alignment
            yield current_interpolated_row[0], [
                *current_interpolated_row[1],
                *current_recorded_row[1],
            ]

        else:
            assert (
                current_recorded_row[0] > current_interpolated_row[0]
                and last_recorded_row[0] <= current_interpolated_row[0]
            )
            # The interpolated timestamp straddles two recorded points.
            # Take the last observation and carry forward
            yield current_interpolated_row[0], [
                *current_interpolated_row[1],
                *last_recorded_row[1],
            ]

        last_interpolated_row = current_interpolated_row


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


def iter_timeseries_values(
    data: list[tuple[str, dict[str, list[Any]]]],
    timezone: str | None = None,
) -> Iterator[LabeledTimeseriesValue]:
    """Iterate a collection of timeseries data and produce labeled timestamped values.

    This will also handle timezone conversion. Timestamps from the PI Web API are
    always UTC. If a timezone is specified, this will handle the conversion from
    UTC to the desired timezone. The returned timestamps are always timezone aware.
    """
    timezone = timezone or "UTC"
    for web_id, values in data:
        for timestamp, value in zip(values["timestamp"], values["value"]):
            yield web_id, from_utc(timestamp, timezone), value


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


def format_streamsets_content(
    content: dict[str, list[dict[str, list[dict[str, JSONPrimitive]]]]] | None
) -> list[tuple[str, dict[str, list[JSONPrimitive]]]]:
    """Extract timestamp and value for each item in a streamset response."""
    formatted = cast("list[tuple[str, dict[str, list[JSONPrimitive]]]]", [])
    items = content.get("Items", []) if content is not None else []

    for item in items:
        web_id = item["WebId"]
        sub_items = item.get("Items", [])
        values = cast("dict[str, list[JSONPrimitive]]", {"timestamp": [], "value": []})
        for sub_item in sub_items:
            timestamp = sub_item["Timestamp"]
            good = sub_item["Good"]
            if not good:
                value = None
            else:
                # If a stream item returned an error, the value will be `None`
                # and we're not particularly interested in the errors
                # https://docs.osisoft.com/bundle/pi-web-api-reference/page/help/topics/error-handling.html
                value = sub_item["Value"]
                if isinstance(value, dict):
                    value = value["Name"]
            values["timestamp"].append(timestamp)
            values["value"].append(value)
        formatted.append((web_id, values))

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
