# Async Utilities for the [AVEVA PI Web API](https://docs.aveva.com/bundle/pi-web-api-reference/page/help.html)
`piwebx` is a collection of utilities for efficiently retrieving data from the PI System via the PI Web API.

## Key Features
- Timestamp aligned interpolated and recorded time series data retrieval
- Iterator based API and chunk requesting allows for unbounded time ranges
- Returns timezone aware data in user defined timezone or local timezone
- Correctly handles timezone aware input data
- Built on [HTTPX](https://www.python-httpx.org/) allowing for rich support of different authentication methods

## WebID Search
Resources in PI Web API are addressed by WebIDs, which are persistent, URL-safe identifiers that encode the GUIDs and/or paths associated with objects in the PI System. There are multiple ways to search for resources in the PI Web API. `piwebx` is geared towards time series data retrieval so rather than cover all the search semantics in the Web API, basic methods to find the WebID for points and attributes, which singularly identify time series streams, are provided.

### Points
Search for points by name.

```python
from httpx import AsyncClient
from piwebx import find_points_web_id


points = [
    "point1",
    "point2",
    "point3",
]

async def main():
    async with AsyncClient(base_url=...) as client:
        found, not_found = await find_points_web_id(client, points)
    if not_found:
        for point in not_found:
            print(f"{point} was not found")
    
    for point, web_id in found:
        print(f"The WebID for {point} is {web_id}")
```

### Attributes
Search for attributes by their fully qualified path.

```python
from httpx import AsyncClient
from piwebx import find_attributes_web_id


attributes = [
    "\\\\server\\database\\element|attribute1",
    "\\\\server\\database\\element|attribute2",
    "\\\\server\\database\\element|attribute3",
]

async def main():
    async with AsyncClient(base_url=...) as client:
        found, not_found = await find_attributes_web_id(client, attributes)
    if not_found:
        for attribute in not_found:
            print(f"{attribute} was not found")
    
    for attribute, web_id in found:
        print(f"The WebID for {attribute} is {web_id}")
```

## Interpolated Data
The PI Web API supports retrieving time series in an interpolated format. `piwebx` makes it easy to get interpolated data for many streams...

```python
import csv
from datetime import datetime, timedelta

from httpx import AsyncClient
from piwebx import get_interpolated


web_ids = ["web_id1", ...]

async def main():
    start = datetime.now() - timedelta(minutes=30)
    with open("interpolate_example.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        async with AsyncClient(base_url=...) as client:
            async for timestamp, data in get_interpolated(client, web_ids, start=start):
                writer.writerow((timestamp.isoformat(), *data))
```

### Join On Interpolated
The PI System usually has a mixture of analog data and discrete points. Analog data is compressed and, with the right compression settings, can be accurately represented by linear interpolation. On the other hand, discrete points are normally not compressed and linear interpolation is not appropriate between values. `piwebx` provides a way to align interpolated and discrete data on a common index.

```python
import csv
from datetime import datetime, timedelta

from httpx import AsyncClient
from piwebx import get_interpolated, get_recorded, join_on_interpolated, locf


analog_data_points = ["web_id1", ...]
discrete_data_points["web_id1", ...]

async def main():
    start = datetime.now() - timedelta(minutes=30)
    with open("joined_example.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        async with AsyncClient(base_url=...) as client:
            interpolated_stream = get_interpolated(client, analog_data_points, start_time=start)
            recorded_stream = locf(get_recorded(client, discrete_data_points, start_time=start))
            async for timestamp, data in join_on_interpolated(interpolated_stream, recorded_stream):
                writer.writerow((timestamp.isoformat(), *data))
```

## Recorded Data
Recorded data, also known as compressed data, is the actual time series data stored in the PI archive. `piwebx` makes it easy to get recorded data for many streams...

```python
import csv
from datetime import datetime, timedelta

from httpx import AsyncClient
from piwebx import get_recorded


web_ids = ["web_id1", ...]

async def main():
    start = datetime.now() - timedelta(minutes=30)
    with open("interpolate_example.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        async with AsyncClient(base_url=...) as client:
            async for timestamp, data in get_recorded(client, web_ids, start=start):
                writer.writerow((timestamp.isoformat(), *data))
```

### Last Observation Carried Forward
By default, `get_recorded` returns a value for every stream for every row. Streams which dont have a value at a given timestamp are assigned `None`. A method for filling values is LOCF (last observation carried forward). This can be used to fill gaps in recorded data streams.

```python
import csv
from datetime import datetime, timedelta

from httpx import AsyncClient
from piwebx import get_recorded, locf


web_ids = ["web_id1", ...]

async def main():
    start = datetime.now() - timedelta(minutes=30)
    with open("interpolate_example.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        async with AsyncClient(base_url=...) as client:
            async for timestamp, data in locf(get_recorded(client, web_ids, start=start)):
                writer.writerow((timestamp.isoformat(), *data))
```