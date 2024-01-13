from __future__ import annotations

import asyncio
import logging
from typing import cast, TYPE_CHECKING

from piwebx.exceptions import APIResponseError
from piwebx.util.response import handle_json_response


__all__ = (
    "find_points_web_id",
    "find_points_type",
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from httpx import AsyncClient

_LOGGER = logging.getLogger("piwebx")


async def find_dataserver_web_id(
    client: AsyncClient, dataserver: str | None = None
) -> str:
    """Get the data archive server WebId.

    If not specified, the first data server returned in the list from "/dataservers"
    will be returned.

    Args:
        client: The client used to retrieve the data
        dataserver: The data archive server name to search for

    Raises:
        piwebx.APIResponseError: If ``dataserver`` is not ``None`` and not found
            or the server retuned no items
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request
    """
    response = await client.get(
        "/dataservers", params={"selectedFields": "Items.Name;Items.WebId"}
    )
    data = cast("dict[str, list[dict[str, str]]]", await handle_json_response(response))

    items = data.get("Items")
    if not items or not isinstance(items, list):
        raise APIResponseError(
            "Unable to select data server WebID. No items returned from server",
            errors=[],
            request=response.request,
            response=response,
        )
    if dataserver:
        for item in items:
            if item["Name"] == dataserver:
                return item["WebId"]
        else:
            raise APIResponseError(
                f"Unable to select data server WebID. '{dataserver}' not found",
                errors=[],
                request=response.request,
                response=response,
            )
    else:
        return items[0]["WebId"]


async def find_points_web_id(
    client: AsyncClient, points: Sequence[str], dataserver: str | None = None
) -> tuple[list[tuple[str, str]], list[str]]:
    """Get the WebId for a sequence of PI points.

    If a tag is not found or the query returns multiple results, the query for
    for that tag will fail. Therefore you usually cannot use wild card searches
    for this coroutine (unless the wild card search returns 1 tag).

    If the data archive server is not provided, :function: `abcpi.search.server.find_dataserver_web_id`
    will be used to attempt to discover the archive server.

    Args:
        client: The client used to retrieve the data
        points: The sequence of points to search for WebId's
        dataserver: The name of the data archive server. Will attempt to search
            for the WebId using :function: `abcpi.search.server.find_dataserver_web_id`

    Raises:
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request
    """
    points = [point.upper() for point in points]
    dataserver_web_id = await find_dataserver_web_id(client, dataserver=dataserver)

    # We search directly on the dataserver instead of using the more general
    # "/search" endpoint because of a bug in indexed search for the 2019 and
    # 2019 SP1 versions of the PI Web API. The method we use works for all PI Web
    # API versions. Aveva introduced the "/points/search" endpoint which is the recommended
    # way for all 2021 and newer versions but we need backwards compatability
    requests = [
        client.get(
            f"/dataservers/{dataserver_web_id}/points",
            params={"nameFilter": point, "selectedFields": "Items.Name;Items.WebId"},
        )
        for point in points
    ]
    responses = await asyncio.gather(*requests)

    handlers = [
        handle_json_response(
            response, raise_for_status=False, raise_for_content_error=False
        )
        for response in responses
    ]
    results = cast(
        "list[dict[str, list[dict[str, str]]] | None]",
        await asyncio.gather(*handlers),
    )

    num_found = 0
    found = []
    not_found = []
    for point, result in zip(points, results):
        if not result:
            _LOGGER.info("'%s' search failed", point)
            not_found.append(point)
            continue
        items = result.get("Items")
        assert isinstance(
            items, list
        ), "Expected list for 'Items' property. Has PI Web API schema changed?"
        if not items:
            _LOGGER.info("'%s' search returned no results", point)
            not_found.append(point)
        elif len(items) > 1:
            _LOGGER.info("'%s' search returned more than 1 result", point)
            not_found.append(point)
        else:
            assert items[0]["Name"].upper() == point
            found.append((point, items[0]["WebId"]))
            num_found += 1

    _LOGGER.debug("Found %i of %i points", num_found, len(points))
    return found, not_found


async def find_points_type(
    client: AsyncClient, web_ids: Sequence[str]
) -> dict[str, str | None]:
    """Get the point type for a sequence of PI points.

    Args:
        client: The client used to retrieve the data
        web_ids: The sequence of WebId's to search for

    Raises:
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request
    """
    requests = [
        client.get(f"/points/{web_id}", params={"selectedFields": "PointType"})
        for web_id in web_ids
    ]
    responses = await asyncio.gather(*requests)

    handlers = [
        handle_json_response(
            response, raise_for_status=False, raise_for_content_error=False
        )
        for response in responses
    ]
    results = cast(
        "list[dict[str, str] | None]",
        await asyncio.gather(*handlers),
    )

    point_types = {}
    for web_id, result in zip(web_ids, results):
        if not result:
            _LOGGER.warning("'%s' search failed", web_id)
            point_types[web_id] = None
        else:
            point_types[web_id] = result["PointType"]
    return cast("dict[str, str | None]", point_types)
