from __future__ import annotations

import datetime as dt
from datetime import datetime
from typing import TYPE_CHECKING

import dateutil.parser
import pendulum
import pendulum.tz
from dateparser.date import DateDataParser


__all__ = (
    "LOCAL_TZ",
    "to_utc",
    "from_utc",
    "fuzzy_parse",
    "to_zulu_format",
)

if TYPE_CHECKING:
    from pendulum.datetime import DateTime


# Order of parsers is important here. If absolute-time is first, some relative
# formats that we want to support (ex. *-3h) will be interpreted by the absolute-time
# parser and not parsed correctly
DDP = DateDataParser(
    languages=["en"],
    settings={
        "PARSERS": [
            "relative-time",
            "absolute-time",
        ]
    },
)
LOCAL_TZ = pendulum.now().timezone_name


def to_utc(timestamp: datetime | str) -> DateTime:
    """Convert a datetime to a timezone aware datetime in UTC.

    If the input datetime is not timezone aware it will be interpreted as local
    time.
    """
    if isinstance(timestamp, str):
        timestamp = dateutil.parser.isoparse(timestamp)
    tz = None if timestamp.tzinfo is not None else LOCAL_TZ
    return pendulum.instance(timestamp, tz=tz).in_timezone("UTC")


def from_utc(timestamp: datetime | str, timezone: str | None = None) -> DateTime:
    """Convert a UTC datetime to a timezone aware datetime in the target timezone.

    If the timezone is not specified this will convert to the local timezone.
    """
    if isinstance(timestamp, str):
        timestamp = dateutil.parser.isoparse(timestamp)
    timezone = timezone or LOCAL_TZ
    tz = None if timestamp.tzinfo is not None else "UTC"
    return pendulum.instance(timestamp, tz=tz).in_timezone(timezone)


def fuzzy_parse(timestamp: str) -> DateTime:
    """Fuzzy timestamp parsing. Supports relative dates. The object returned is
    timezone aware in UTC."""
    parsed = DDP.get_date_data(timestamp)["date_obj"]
    if not parsed:
        raise dateutil.parser.ParserError("Invalid timestamp format %s", timestamp)

    if parsed.tzinfo is not None:
        offset = parsed.tzinfo.utcoffset(datetime.now(dt.UTC))
        tzinfo = pendulum.tz.fixed_timezone(offset.total_seconds())
        parsed = parsed.replace(tzinfo=tzinfo)

    return to_utc(parsed)


def to_zulu_format(timestamp: datetime) -> str:
    """Return a timezone aware timestamp in UTC to zulu format.

    This is required due to a bug in the PI Web API...
    https://support.sas.com/kb/63/049.html
    """
    return timestamp.isoformat().replace("+00:00", "Z")
