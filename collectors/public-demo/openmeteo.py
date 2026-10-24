"""Open-Meteo: clima atual de capitais brasileiras (sem autenticação)."""
from __future__ import annotations

import os

import requests

EVENT_TYPE = "weather"
SOURCE = "open-meteo"
URL = os.getenv("OPENMETEO_URL", "https://api.open-meteo.com/v1/forecast")

# id, nome, estado, região, latitude, longitude
CITIES = [
    ("sao-paulo", "São Paulo", "SP", "Sudeste", -23.55, -46.63),
    ("rio-de-janeiro", "Rio de Janeiro", "RJ", "Sudeste", -22.91, -43.17),
    ("belo-horizonte", "Belo Horizonte", "MG", "Sudeste", -19.92, -43.94),
    ("vitoria", "Vitória", "ES", "Sudeste", -20.32, -40.34),
    ("curitiba", "Curitiba", "PR", "Sul", -25.43, -49.27),
    ("porto-alegre", "Porto Alegre", "RS", "Sul", -30.03, -51.23),
    ("florianopolis", "Florianópolis", "SC", "Sul", -27.60, -48.55),
    ("brasilia", "Brasília", "DF", "Centro-Oeste", -15.78, -47.93),
    ("goiania", "Goiânia", "GO", "Centro-Oeste", -16.68, -49.25),
    ("salvador", "Salvador", "BA", "Nordeste", -12.97, -38.50),
    ("recife", "Recife", "PE", "Nordeste", -8.05, -34.88),
    ("fortaleza", "Fortaleza", "CE", "Nordeste", -3.73, -38.52),
    ("manaus", "Manaus", "AM", "Norte", -3.12, -60.02),
    ("belem", "Belém", "PA", "Norte", -1.46, -48.50),
]

CURRENT = "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,weather_code"


def condition(code: int | None) -> str:
    """Resume o código WMO em uma categoria legível (vira o `status` do evento)."""
    if code is None:
        return "desconhecido"
    if code == 0:
        return "céu limpo"
    if code in (1, 2, 3):
        return "nublado"
    if code in (45, 48):
        return "neblina"
    if 51 <= code <= 57:
        return "garoa"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "chuva"
    if 71 <= code <= 77 or code in (85, 86):
        return "neve"
    if code >= 95:
        return "tempestade"
    return "outro"


def parse(document: list[dict] | dict) -> list[dict]:
    """A API devolve uma lista (uma posição por cidade, na ordem pedida)."""
    locations = document if isinstance(document, list) else [document]
    items = []
    for (city_id, name, state, region, _lat, _lon), loc in zip(CITIES, locations):
        current = loc.get("current") or {}
        items.append({
            "id": city_id,
            "name": name,
            "state": state,
            "region": region,
            "country": "BR",
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "elevation": loc.get("elevation"),
            "observed_at": current.get("time"),
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_kmh": current.get("wind_speed_10m"),
            "precipitation_mm": current.get("precipitation"),
            "weather_code": current.get("weather_code"),
            "condition": condition(current.get("weather_code")),
        })
    return items


def fetch(session: requests.Session) -> list[dict]:
    response = session.get(
        URL,
        params={
            "latitude": ",".join(str(c[4]) for c in CITIES),
            "longitude": ",".join(str(c[5]) for c in CITIES),
            "current": CURRENT,
            "timezone": "UTC",
        },
        timeout=30,
    )
    response.raise_for_status()
    return parse(response.json())
