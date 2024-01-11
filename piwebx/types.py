from typing import Any, Dict, List, Tuple, Union
from typing_extensions import TypeAlias

from pendulum.datetime import DateTime


__all__ = ("JSONContent", "JSONPrimitive", "TimeseriesRow")


JSONPrimitive: TypeAlias = Union[str, int, float, bool, None]
JSONContent: TypeAlias = Union[
    JSONPrimitive, List["JSONContent"], Dict[str, "JSONContent"]
]

TimeseriesRow: TypeAlias = Tuple[DateTime, List[Any]]
