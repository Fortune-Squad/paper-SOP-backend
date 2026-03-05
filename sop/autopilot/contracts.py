from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "v1"


def with_schema_version(payload: dict[str, Any]) -> dict[str, Any]:
    if "schema_version" not in payload:
        payload["schema_version"] = SCHEMA_VERSION
    return payload


def parse_iso8601_utc(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
