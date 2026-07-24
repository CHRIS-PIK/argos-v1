from __future__ import annotations
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def bucket_10m(dt: datetime | None = None) -> datetime:
    dt = dt or utc_now()
    return dt.replace(minute=(dt.minute // 10) * 10, second=0, microsecond=0)


def parse_dt(value):
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def first(obj: dict, *names, default=None):
    for name in names:
        if obj.get(name) not in (None, ""):
            return obj[name]
    return default
