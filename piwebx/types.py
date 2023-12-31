from __future__ import annotations

from typing import Any, Tuple, Union
from typing_extensions import TypeAlias

from pendulum.datetime import DateTime


__all__ = ("JSONContent", "JSONPrimitive", "TimeseriesRow")


JSONPrimitive: TypeAlias = Union[str, int, float, bool, None]
JSONContent: TypeAlias = Union[
    JSONPrimitive, list["JSONContent"], dict[str, "JSONContent"]
]

TimeseriesRow: TypeAlias = Tuple[DateTime, list[Any]]
