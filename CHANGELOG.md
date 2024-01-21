# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## 0.0.2 (12 Jan 2024)

- Added WebId search functions for

  - Points (`find_points_web_id`)
  - Attributes (`find_attributes_web_id`)

  The resolved WebId's can be used directly in all streams data collection functions

- Added data type search for

  - Points (`find_points_type`)
  - Attributes (`find_attributes_type`)

- Added `get_current` , `get_recorded_at_time` and `get_interpolated_at_time` streams functions

## 0.0.3 (16 Jan 2024)

- Added WebId search functions for

  - Assetservers (`find_assetserver_web_id`)
  - Assetdatabase (`find_assetdatabase_web_id`)
  - Dataservers (`find_dataserver_web_id`)

## 0.0.4 (21 Jan 2024)

- Fixed a bug in all `streams` functions that would allow them to exceed the `max_concurrency` parameter
