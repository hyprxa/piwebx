from __future__ import annotations

from typing import cast, TYPE_CHECKING

from piwebx import APIResponseError, handle_json_response


__all__ = (
    "find_assetserver_web_id",
    "find_dataserver_web_id",
)

if TYPE_CHECKING:
    from httpx import AsyncClient


async def find_assetserver_web_id(client: AsyncClient, assetserver: str | None = None) -> str:
    """Get the asset server WebId.

    If not specified, the first asset server returned in the list from "/assetservers"
    will be returned.

    Args:
        client: The client used to retrieve the data
        assetserver: The asset server name to search for

    Raises:
        piwebx.APIResponseError: If ``assetserver`` is not ``None`` and not found
            or the server retuned no items
        httpx.HTTPError: There was an ambiguous exception that occurred while
            handling the request
    """
    response = await client.get("/assetservers", params={"selectedFields": "Items.Name;Items.WebId"})
    data = cast("dict[str, list[dict[str, str]]]", await handle_json_response(response))

    items = data.get("Items")
    if not items or not isinstance(items, list):
        raise APIResponseError(
            "Unable to select asset server WebID. No items returned from server",
            errors=[],
            request=response.request,
            response=response
        )
    if assetserver:
        for item in items:
            if item["Name"] == assetserver:
                return item["WebId"]
        else:
            raise APIResponseError(
                f"Unable to select asset server WebID. '{assetserver}' not found",
                errors=[],
                request=response.request,
                response=response
            )
    else:
        return items[0]["WebId"]


async def find_dataserver_web_id(client: AsyncClient, dataserver: str | None = None) -> str:
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
    response = await client.get("/dataservers", params={"selectedFields": "Items.Name;Items.WebId"})
    data = cast("dict[str, list[dict[str, str]]]", await handle_json_response(response))

    items = data.get("Items")
    if not items or not isinstance(items, list):
        raise APIResponseError(
            "Unable to select data server WebID. No items returned from server",
            errors=[],
            request=response.request,
            response=response
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
                response=response
            )
    else:
        return items[0]["WebId"]