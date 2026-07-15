"""Wetter-Enrichment über Open-Meteo (kostenlos, kein API-Key).

Holt historisches Tageswetter für Koordinaten + Datum und liefert
Temperatur + Bedingung zurück. Als Stufe-3-`Metric` an Events gehängt.
Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# WMO-Wettercodes -> deutsche Kurzbeschreibung
WMO = {
    0: "klar", 1: "überwiegend klar", 2: "teils bewölkt", 3: "bewölkt",
    45: "Nebel", 48: "Reifnebel",
    51: "leichter Nieselregen", 53: "Nieselregen", 55: "starker Nieselregen",
    56: "gefrierender Niesel", 57: "gefrierender Niesel",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen",
    66: "gefrierender Regen", 67: "gefrierender Regen",
    71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall",
    77: "Schneegriesel",
    80: "leichte Schauer", 81: "Schauer", 82: "heftige Schauer",
    85: "Schneeschauer", 86: "starke Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "schweres Gewitter mit Hagel",
}


def fetch_weather(lat: float, lng: float, day: datetime | date) -> dict | None:
    """Liefert {temp_c, condition, code} für Ort+Tag, oder None wenn nicht verfügbar."""
    if isinstance(day, datetime):
        day = day.date()
    iso = day.isoformat()
    params = urllib.parse.urlencode({
        "latitude": round(lat, 4),
        "longitude": round(lng, 4),
        "start_date": iso,
        "end_date": iso,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode",
        "timezone": "auto",
    })
    req = urllib.request.Request(f"{ARCHIVE_URL}?{params}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    daily = data.get("daily") or {}
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    code = (daily.get("weathercode") or [None])[0]
    if tmax is None and code is None:
        return None
    temp = None
    if tmax is not None and tmin is not None:
        temp = round((tmax + tmin) / 2, 1)
    elif tmax is not None:
        temp = tmax
    return {
        "temp_c": temp,
        "condition": WMO.get(code, "unbekannt") if code is not None else None,
        "code": code,
    }
