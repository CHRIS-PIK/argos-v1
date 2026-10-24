"""USGS Earthquake Hazards Program: terremotos em tempo real (GeoJSON, sem autenticação)."""
from __future__ import annotations

import os

import requests

EVENT_TYPE = "earthquakes"
SOURCE = "usgs"
URL = os.getenv(
    "USGS_FEED_URL",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
)


def parse(document: dict) -> list[dict]:
    """Cada feature do GeoJSON é um item; o formato original é preservado."""
    features = document.get("features", [])
    return [f for f in features if isinstance(f, dict) and f.get("id")]


def fetch(session: requests.Session) -> list[dict]:
    response = session.get(URL, timeout=30)
    response.raise_for_status()
    return parse(response.json())
