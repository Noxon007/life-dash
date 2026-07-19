"""Wetter-Enrichment über Open-Meteo (kostenlos, kein API-Key).

Holt historisches Tageswetter für Koordinaten + Datum und liefert
Temperatur + Bedingung zurück. Als Stufe-3-`Metric` an Events gehängt.
Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime

log = logging.getLogger("lifedash.weather")

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


def _dominant_daytime_code(hourly: dict) -> int | None:
    """F3: Häufigster Wettercode tagsüber (8–20 Uhr lokal) — das „gefühlte"
    Tagwetter, statt des schwersten Codes des ganzen Tages (1 Std. Morgenregen
    überdeckte vorher einen sonnigen Tag). Gleichstand: schwererer Code."""
    times = hourly.get("time") or []
    codes = hourly.get("weathercode") or []
    day_codes = [c for t, c in zip(times, codes)
                 if c is not None and 8 <= int(str(t)[11:13] or 0) < 20]
    if not day_codes:
        return None
    counts: dict[int, int] = {}
    for c in day_codes:
        counts[c] = counts.get(c, 0) + 1
    return max(counts, key=lambda c: (counts[c], c))


def fetch_weather(lat: float, lng: float, day: datetime | date) -> dict | None:
    """Liefert Tageswetter für Ort+Tag oder None:
    {temp_c (Mittel), temp_min_c, temp_max_c, condition, code, precip_mm}.
    F3: Bedingung kommt aus den STUNDEN-Daten (dominantes Tagwetter 8–20 Uhr),
    Min/Max getrennt, Niederschlagssumme dazu."""
    if isinstance(day, datetime):
        day = day.date()
    iso = day.isoformat()
    params = urllib.parse.urlencode({
        "latitude": round(lat, 4),
        "longitude": round(lng, 4),
        "start_date": iso,
        "end_date": iso,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_sum",
        "hourly": "weathercode",
        "timezone": "auto",
    })
    req = urllib.request.Request(f"{ARCHIVE_URL}?{params}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        log.warning("Open-Meteo nicht erreichbar (%s, %s): %s", iso, (lat, lng), exc)
        return None

    daily = data.get("daily") or {}
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    precip = (daily.get("precipitation_sum") or [None])[0]
    code = _dominant_daytime_code(data.get("hourly") or {})
    if code is None:  # keine Stundendaten -> Tagescode als Rückfall
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
        "temp_min_c": tmin,
        "temp_max_c": tmax,
        "precip_mm": precip,
        "condition": WMO.get(code, "unbekannt") if code is not None else None,
        "code": code,
    }
