from __future__ import annotations

import asyncio
from typing import cast, TYPE_CHECKING

import pendulum
from httpx import AsyncClient

from piwebx.util.data import (
    format_streams_content,
    get_timestamp_index,
    iter_timeseries_rows,
    paginate,
    split_range_on_frequency,
)
from piwebx.util.response import handle_json_response
from piwebx.util.time import from_utc, to_utc, to_zulu_format, LOCAL_TZ


__all__ = ("get_recorded",)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from datetime import datetime
    from piwebx.types import JSONPrimitive, TimeseriesRow


async def get_recorded(
    client: AsyncClient,
    web_ids: Sequence[str],
    start_time: datetime,
    end_time: datetime | None = None,
    scan_rate: float | None = None,
    request_chunk_size: int | None = None,
    timezone: str | None = None,
    max_concurrency: int | None = None,
) -> AsyncIterator[TimeseriesRow]:
    """Stream timestamp aligned, recorded data for a sequence of PI tags.

    Args:
        client: The Client used to retrieve the data.
        web_ids: The web_ids to stream data for
        start_time: The start time of the batch. This will be the timestamp
            in the first row of data
        end_time: The end time of the batch. This will be the timestamp in the
            last row. Defaults to now
        scan_rate: The data update frequency (in seconds) for all PI points. A safe
            value is the minimum average update frequency of all PI points in the
            sequence. This does not need to be exact. Defaults to ``5``
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

    timezone = timezone or LOCAL_TZ
    request_chunk_size = request_chunk_size or 5000
    scan_rate = scan_rate or 5

    start_times, end_times = split_range_on_frequency(
        start_time=start_time,
        end_time=end_time,
        request_chunk_size=request_chunk_size,
        scan_rate=scan_rate,
    )

    max_concurrency = max_concurrency or len(web_ids)
    for start_time, end_time in zip(start_times, end_times):
        responses = []
        requests = [
            client.get(
                f"streams/{web_id}/recorded",
                params={
                    "startTime": to_zulu_format(start_time),
                    "endTime": to_zulu_format(end_time),
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

        start_row = await get_recorded_at_time(
            client=client,
            web_ids=web_ids,
            time=start_time,
            timezone=timezone,
            max_concurrency=max_concurrency,
        )
        yield start_row

        # With recorded data we cannot guarentee a value will exist at the start
        # and end times so we always get the recorded at time value for each tag.
        # But, data at that time may exist for some tags so we need to check the
        # timestamps coming out of the iterator and only yield the ones not equal
        # to the start/end time since this would lead to duplicate data.
        for timestamp, row in iter_timeseries_rows(
            index=index, data=data, timezone=timezone
        ):
            if timestamp == start_time:
                continue
            elif timestamp == end_time:
                continue
            yield timestamp, row

        # The next start time is always the last end time, so the only time we
        # need to get the last row is when there are no more time chunks to work
        # through
        else:
            end_row = await get_recorded_at_time(
                client=client,
                web_ids=web_ids,
                time=end_time,
                timezone=timezone,
                max_concurrency=max_concurrency,
            )
            yield end_row


async def get_recorded_at_time(
    client: AsyncClient,
    web_ids: Sequence[str],
    time: datetime,
    timezone: str | None = None,
    max_concurrency: int | None = None,
) -> TimeseriesRow:
    """Returns the recorded value for sequence of PI tags at a specific time.

    Args:
        client: The Client used to retrieve the data
        web_ids: The web_ids to stream data for
        time: The time to get the value at
        timezone: The timezone to convert the returned data into. Defaults to
            the local system timezone
        max_concurrency: The maximum number of concurrent requests made at a time.
            If not specified, the maximum concurrency will be determined by the
            connection pool limit. Defaults to ``None`` (use client limit)

    Raises:
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request.
    """
    time = to_utc(time)

    responses = []
    requests = [
        client.get(
            f"streams/{web_id}/recordedattime",
            params={
                "time": to_zulu_format(time),
                "selectedFields": "Items.Timestamp;Items.Value;Items.Good",
            },
        )
        for web_id in web_ids
    ]

    max_concurrency = max_concurrency or len(web_ids)
    for page in paginate(requests, max_concurrency):
        responses.extend(await asyncio.gather(*page))

    handlers = [
        handle_json_response(
            response, raise_for_status=False, raise_for_content_error=False
        )
        for response in responses
    ]
    results = cast(
        "list[dict[str, JSONPrimitive] | None]", await asyncio.gather(*handlers)
    )

    row: list[JSONPrimitive] = []
    for result in results:
        if not result:
            row.append(None)
            continue
        if result["Good"]:
            value = result["Value"]
            if isinstance(value, dict):
                row.append(value["Name"])
            else:
                row.append(value)
        else:
            row.append(None)

    return from_utc(time, timezone), row
