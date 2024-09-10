from __future__ import annotations

from traceback import format_exception
from typing import TYPE_CHECKING

from httpx import HTTPError


__all__ = (
    "APIResponseError",
    "BufferClosed",
    "ChannelGroupException",
)

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


class BufferClosed(Exception):
    """Primarily an internal exception used to signal a buffer is closed."""

    def __str__(self) -> str:
        return "Buffer is closed"


class ChannelGroupException(BaseException):
    """Raised if one or more errors occurs in a ChannelGroup."""

    SEPARATOR = "----------------------------\n"

    def __init__(self, exceptions: list[BaseException]) -> None:
        self.exceptions = exceptions

    def __str__(self) -> str:
        tracebacks = [
            "".join(format_exception(type(exc), exc, exc.__traceback__))
            for exc in self.exceptions
        ]
        return (
            f"{len(self.exceptions)} exceptions were raised in the subscriber:\n"
            f"{self.SEPARATOR}{self.SEPARATOR.join(tracebacks)}"
        )

    def __repr__(self) -> str:
        exception_reprs = ", ".join(repr(exc) for exc in self.exceptions)
        return f"<{self.__class__.__name__}: {exception_reprs}>"
