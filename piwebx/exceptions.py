from __future__ import annotations

from typing import TYPE_CHECKING

from httpx import HTTPError


__all__ = ("APIResponseError",)

if TYPE_CHECKING:
    from httpx import Request, Response


class APIResponseError(HTTPError):
    """Raised when the HTTP request was successful but the response was invalid."""

    def __init__(
        self, message: str, *, errors: list[str], request: Request, response: Response
    ):
        super().__init__(message)
        self.errors = errors
        self.request = request
        self.response = response
