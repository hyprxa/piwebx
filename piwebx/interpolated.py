from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import cast, TYPE_CHECKING

import pendulum
from httpx import AsyncClient

from piwebx.util.data import (
    format_streams_content,
    get_timestamp_index,
    iter_timeseries_rows,
    paginate,
    split_range_on_interval,
)
from piwebx.util.response import handle_json_response
from piwebx.util.time import to_utc, to_zulu_format, LOCAL_TZ


__all__ = ("get_interpolated",)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from piwebx.types import JSONPrimitive, TimeseriesRow


async def get_interpolated(
    client: AsyncClient,
    web_ids: Sequence[str],
    start_time: datetime,
    end_time: datetime | None = None,
    interval: timedelta | int | None = None,
    request_chunk_size: int | None = None,
    timezone: str | None = None,
    max_concurrency: int | None = None,
) -> AsyncIterator[TimeseriesRow]:
    """Stream timestamp aligned, interpolated data for a WebId's.

    Args:
        client: The Client used to retrieve the data.
        web_ids: The web_ids to stream data for.
        start_time: The start time of the batch. This will be the timestamp
            in the first row of data
        end_time: The end time of the batch. This will be the timestamp in the
            last row. Defaults to :function:`pendulum.now()`
        interval: The time interval (in seconds) between successive rows. Defaults
            to ``60``
        request_chunk_size: The maximum number of rows to be returned from a
            single HTTP request. This splits up the time range into successive
            pieces. Defaults to ``5000``
        timezone: The timezone to convert the returned data into. Defaults to
            the local system timezone
        max_concurrency: The maximum number of concurrent requests made at a time.
            If not specified, the maximum concurrency will be determined by the
            connection pool limit. Defaults to ``None`` (use client limit)

    Yields:
        row: A :type: `TimeseriesRow <piwebx.types.TimeseriesRow>`.

    Raises:
        ValueError: If `start_time` >= `end_time`.
        TypeError: If `interval` is an invalid type.
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request.
    """
    start_time = to_utc(start_time)
    end_time = to_utc(end_time or pendulum.now())

    if start_time >= end_time:
        # The Web API would allow this, it would return the data in descending
        # order but we need the data in ascending order otherwise iter_timeseries_rows
        # will not work
        raise ValueError("'start_time' cannot be greater than or equal to 'end_time'")

    interval = interval or 60
    interval = timedelta(seconds=interval) if isinstance(interval, int) else interval
    if not isinstance(interval, timedelta):
        raise TypeError(f"Interval must be timedelta or int. Got {type(interval)}")

    timezone = timezone or LOCAL_TZ
    request_chunk_size = request_chunk_size or 5000

    start_times, end_times = split_range_on_interval(
        start_time=start_time,
        end_time=end_time,
        interval=interval,
        request_chunk_size=request_chunk_size,
    )
    interval_str = f"{interval.total_seconds()} seconds"

    max_concurrency = max_concurrency or len(web_ids)
    for start_time, end_time in zip(start_times, end_times):
        responses = []
        requests = [
            client.get(
                f"streams/{web_id}/interpolated",
                params={
                    "startTime": to_zulu_format(start_time),
                    "endTime": to_zulu_format(end_time),
                    "interval": interval_str,
                    "selectedFields": "Items.Timestamp;Items.Value;Items.Good",
                },
            )
            for web_id in web_ids
        ]
        for page in paginate(requests, max_concurrency):
            responses.extend(await asyncio.gather(*page))

        handlers = [
            handle_json_response(
                response, raise_for_status=False, raise_for_content_error=False
            )
            for response in responses
        ]
        results = cast(
            "list[dict[str, list[dict[str, JSONPrimitive]]] | None]",
            await asyncio.gather(*handlers),
        )
        data = [format_streams_content(result) for result in results]
        index = get_timestamp_index(data)

        for row in iter_timeseries_rows(index=index, data=data, timezone=timezone):
            yield row
