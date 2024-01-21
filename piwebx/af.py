from __future__ import annotations

import asyncio
import logging
from typing import cast, TYPE_CHECKING

from piwebx.exceptions import APIResponseError
from piwebx.servers import find_assetserver_web_id
from piwebx.util.response import handle_json_response


__all__ = (
    "find_assetdatabase_web_id",
    "find_elements_web_id",
    "find_attributes_web_id",
    "find_attributes_web_id_from_element",
    "find_attributes_type",
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from httpx import AsyncClient

_LOGGER = logging.getLogger("piwebx")


async def find_assetdatabase_web_id(
    client: AsyncClient,
    assetdatabase: str,
    assetserver: str | None = None
) -> str:
    """Get the asset database WebId.

    If ``assetserver`` is not provided, this will attempt to discover the asset server.

    Args:
        client: The client used to retrieve the data
        assetdatbase: The asset database name to search for
        assetserver: The name of the asset server. Will attempt to search
            for the WebId using :function: `abcpi.search.server.find_asseterver_web_id`

    Raises:
        piwebx.APIResponseError: If ``assetserver`` is not ``None`` and not found
            or the server retuned no items
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request
    """
    assetserver_web_id = await find_assetserver_web_id(client, assetserver=assetserver)

    response = await client.get(
        f"/assetservers/{assetserver_web_id}/assetdatabases",
        params={"selectedFields": "Items.Name;Items.WebId"}
    )
    data = cast("dict[str, list[dict[str, str]]]", await handle_json_response(response))

    items = data.get("Items")
    if not items or not isinstance(items, list):
        raise APIResponseError(
            "Unable to select asset database WebID. No items returned from server",
            errors=[],
            request=response.request,
            response=response
        )

    for item in items:
        if item["Name"] == assetdatabase:
            return item["WebId"]
    else:
        raise APIResponseError(
            f"Unable to select asset database WebID. '{assetdatabase}' not found",
            errors=[],
            request=response.request,
            response=response
        )


async def find_elements_web_id(
    client: AsyncClient, paths: Sequence[str]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Get the WebId for a sequence of elements.

    The elements must be referenced by their absolute paths. The search semantics
    for elements can get pretty complex with parent and child elements. The element
    path is the AF equivalent to a PI tag so they are unique. This allows the
    API to be very simialar for finding points, elements, and attributes.

    Args:
        client: The client used to retrieve the data
        paths: The sequence of element paths to search for WebId's

    Raises:
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request
    """
    paths = [path.upper() for path in paths]

    requests = [
        client.get(f"/elements", params={"path": path, "selectedFields": "Path;WebId"})
        for path in paths
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

    num_found = 0
    found = []
    not_found = []
    for path, result in zip(paths, results):
        if not result:
            _LOGGER.info("'%s' search failed", path)
            not_found.append(path)
            continue
        else:
            assert result["Path"].upper() == path
            found.append((path, result["WebId"]))
            num_found += 1

    _LOGGER.debug("Found %i of %i elements", num_found, len(paths))
    return found, not_found


async def find_attributes_web_id(
    client: AsyncClient, paths: Sequence[str]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Get the WebId for a sequence of attributes.

    The attributes must be referenced by their absolute paths. The search semantics
    for attributes can get pretty complex. The attribute path is the AF
    equivalent to a PI tag so they are unique. This allows the
    API to be very simialar for finding points, elements, and attributes.

    Args:
        client: The client used to retrieve the data
        paths: The sequence of attribute paths to search for WebId's

    Raises:
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request
    """
    paths = [path.upper() for path in paths]

    requests = [
        client.get(
            f"/attributes", params={"path": path, "selectedFields": "Path;WebId"}
        )
        for path in paths
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

    num_found = 0
    found = []
    not_found = []
    for path, result in zip(paths, results):
        if not result:
            _LOGGER.info("'%s' search failed", path)
            not_found.append(path)
            continue
        else:
            assert result["Path"].upper() == path
            found.append((path, result["WebId"]))
            num_found += 1

    _LOGGER.debug("Found %i of %i attributes", num_found, len(paths))
    return found, not_found


async def find_attributes_web_id_from_element(
    client: AsyncClient, element_web_id: str
) -> dict[str, str]:
    """Get the WebId's for all attributes associated to an element.

    This only retrieves parent attributes directly beneath the element. It does
    not recursively retrieve child attributes.

    Args:
        client: The client used to retrieve the data
        element_web_id: The WebId for the parent element

    Raises:
        piwebx.APIResponseError: If ``element_web_id`` does not point to a valid
            element or an internal server occurred on the Web API server
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request
    """
    # Check if this is a valid element
    response = await client.get(f"/elements/{element_web_id}")
    await handle_json_response(response)

    response = await client.get(
        f"/elements/{element_web_id}/attributes",
        params={"selectedFields": "Items.Path;Items.WebId"},
    )
    # This shouldn't raise APIResponseError unless there is an internal server
    # error
    data = cast("dict[str, list[dict[str, str]]]", await handle_json_response(response))

    items = data.get("Items")
    assert isinstance(
        items, list
    ), "Expected list for 'Items' property. Has PI Web API schema changed?"
    if not items:
        _LOGGER.info("No attributes are associated to the element (%s)", element_web_id)
    return {item["Path"]: item["WebId"] for item in items}


async def find_attributes_type(
    client: AsyncClient, web_ids: Sequence[str]
) -> dict[str, str | None]:
    """Get the data type for a sequence of PI attributes.

    Args:
        client: The client used to retrieve the data
        web_ids: The sequence of WebId's to search for

    Raises:
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request
    """
    requests = [
        client.get(f"/attributes/{web_id}", params={"selectedFields": "Type"})
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

    attribute_types = {}
    for web_id, result in zip(web_ids, results):
        if not result:
            _LOGGER.warning("'%s' search failed", web_id)
            attribute_types[web_id] = None
        else:
            attribute_types[web_id] = result["Type"]
    return cast("dict[str, str | None]", attribute_types)
