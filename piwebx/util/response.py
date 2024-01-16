from __future__ import annotations

import logging
from typing import cast, TYPE_CHECKING

import orjson
from httpx import HTTPStatusError, Response

from piwebx.exceptions import APIResponseError


__all__ = ("handle_json_response",)

if TYPE_CHECKING:
    from piwebx.types import JSONContent

_LOGGER = logging.getLogger("piwebx")


async def handle_json_response(
    response: Response,
    raise_for_status: bool = True,
    raise_for_content_error: bool = True,
    return_none_for_content_error: bool = True,
) -> JSONContent | None:
    """Primary response handling for all requests to the PI Web API that are
    expected to return a JSON response (i.e all GET methods).

    Args:
        response: The response object returned from the request
        raise_for_status: If ``True`` and the response status is not successful
            or, the 'WebException' property is present and the new status code
            is not successful, raise a :class: `httpx.HTTPStatusError`
        raise_for_content_error: If ``True`` and the 'Errors' property is not
            empty in a successful response raise
            :class: `APIResponseError <piwebx.exceptions.APIResponseError`
        return_none_for_content_error: If ``True`` and ``raise_for_content_error`` is
            ``False`` and the 'Errors' property is not empty in a successful
            response, return ``None``. Otherwise, return the content
    """
    try:
        try:
            response.raise_for_status()
        except HTTPStatusError as e:
            if raise_for_status:
                raise
            _LOGGER.warning(str(e))
            return None
        else:
            content = await response.aread()
    finally:
        await response.aclose()

    data = orjson.loads(content)
    assert isinstance(data, dict), "Unexpected return type from API response."

    # Check for WebException and potentially raise an HTTPError
    # https://docs.aveva.com/bundle/pi-web-api-reference/page/help/topics/error-handling.html
    web_exc = data.get("WebException")
    if web_exc:
        assert isinstance(web_exc, dict)
        status_code = web_exc.get("StatusCode")
        assert isinstance(
            status_code, int
        ), "Unexpected type for status code in WebException."
        response.status_code = status_code
        try:
            response.raise_for_status()
        except HTTPStatusError as e:
            if raise_for_status:
                raise
            _LOGGER.warning(str(e))
            return None

    # Check for Errors property
    # Some controllers can have an errors property on a successful response
    # if invalid/not enough parameters were passed.
    errors = data.get("Errors")
    if errors:
        assert isinstance(errors, list), "Unexpected type for Errors property."
        err_msg = f"API response returned {len(errors)} errors for url: {response.request.url}"
        if raise_for_content_error:
            raise APIResponseError(
                err_msg, errors=errors, request=response.request, response=response
            )
        _LOGGER.warning(err_msg, extra={"piwebx.response.errors": errors})
        if return_none_for_content_error:
            return None

    return cast("JSONContent", data)
