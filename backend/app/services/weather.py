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

# --------------------------------------------------------------------------- #
# Anmerkung 119 — derselbe Tag am selben Ort wird EINMAL gefragt
# --------------------------------------------------------------------------- #
# Wetter ist eine Eigenschaft von (Tag, Ort); gespeichert wird es je EREIGNIS.
# Nach einem Timeline-Import hat ein Tag dutzende Besuche, viele davon an
# derselben Adresse — der Anreicherungslauf stellte dieselbe Frage dutzendfach
# und bekam dutzendfach dieselbe Antwort. Gemessen an einem gewöhnlichen
# Importtag: fünf Besuche, vier davon am selben Ort, fünf Abrufe.
#
# `_QUANT` ist der Preis dafür, dass der Schlüssel gröber ist als die Frage:
# zwei Nachkommastellen sind ~1,1 km. Das liegt weit UNTER der Auflösung der
# Quelle (Open-Meteos Archiv rechnet auf einem 9–25-km-Gitter), es kann also
# keinen Wert verändern, den die Daten überhaupt unterscheiden könnten.
# Deshalb wird auch die ANFRAGE mit den gerundeten Koordinaten gestellt: sonst
# läge unter dem Schlüssel eine Antwort, die für einen anderen Punkt geholt
# wurde — ein Cache darf nur ausliefern, wonach er gefragt wurde.
#
# **Fehlschläge werden bewusst NICHT gemerkt.** Das ist die Gegenrichtung zur
# Endlos-Abruf-Falle (F12 `weather_rev`, A39, A42): dort geht es um eine
# DAUERHAFT gespeicherte Marke, hier um einen Prozess-Cache. Ein einzelner
# Netzaussetzer würde sonst den Ort für die Laufzeit des Servers vergiften,
# und die dauerhafte Marke am Ereignis verhindert das Nachfragen ohnehin.
_QUANT = 2
_CACHE: dict[tuple[float, float, str], dict] = {}
_CACHE_MAX = 4096


def reset_cache() -> None:
    """Cache leeren — für Tests und für den Fall, dass jemand einen Lauf
    wiederholen will, ohne den Server neu zu starten."""
    _CACHE.clear()

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
    """Liefert Tageswetter für Ort+Tag oder None (F3, Entscheidung 2026-07-19:
    reine TAGESWERTE statt abgeleiteter Logik):
    {temp_min_c, temp_max_c, sun_h, rain_mm, snow_cm, wind_max_kmh,
     condition, code} — dazu temp_c (Tagesmittel) für Bestands-Kompatibilität.

    F12 ergänzt: gefühlte Temperatur (apparent_*), Regenstunden, Sonnenauf-
    und -untergang samt Tageslichtdauer, Windböen und UV-Index. Alles aus
    DEMSELBEN Aufruf — die Felder waren immer verfügbar und wurden bisher
    nur nicht abgefragt. Stundenwerte bleiben bewusst außen vor
    (Entscheidung F3, siehe KONZEPT Anmerkung 49)."""
    if isinstance(day, datetime):
        day = day.date()
    iso = day.isoformat()
    lat, lng = round(lat, _QUANT), round(lng, _QUANT)
    cached = _CACHE.get((lat, lng, iso))
    if cached is not None:
        # Kopie: der Aufrufer hängt die Werte an ein Ereignis, und ein
        # gemeinsam benutztes Dict wäre ein Weg, den Cache zu verändern.
        return dict(cached)
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lng,
        "start_date": iso,
        "end_date": iso,
        "daily": ("temperature_2m_max,temperature_2m_min,weathercode,"
                  "rain_sum,snowfall_sum,sunshine_duration,windspeed_10m_max,"
                  # F12
                  "apparent_temperature_max,apparent_temperature_min,"
                  "precipitation_hours,sunrise,sunset,daylight_duration,"
                  "windgusts_10m_max,uv_index_max"),
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
    first = lambda key: (daily.get(key) or [None])[0]  # noqa: E731
    tmax, tmin = first("temperature_2m_max"), first("temperature_2m_min")
    code = first("weathercode")
    sun_s = first("sunshine_duration")
    if tmax is None and code is None:
        return None
    temp = None
    if tmax is not None and tmin is not None:
        temp = round((tmax + tmin) / 2, 1)
    elif tmax is not None:
        temp = tmax
    daylight_s = first("daylight_duration")
    # Sonnenauf-/-untergang kommen als ISO-Zeitstempel in Ortszeit
    # ("2024-07-12T05:14"); gespeichert wird nur die Uhrzeit — das Datum
    # steht ohnehin am Event.
    clock = lambda v: v.split("T")[1][:5] if isinstance(v, str) and "T" in v else None  # noqa: E731
    result = {
        "temp_c": temp,
        "temp_min_c": tmin,
        "temp_max_c": tmax,
        "sun_h": round(sun_s / 3600, 1) if sun_s is not None else None,
        "rain_mm": first("rain_sum"),
        "snow_cm": first("snowfall_sum"),
        "wind_max_kmh": first("windspeed_10m_max"),
        "condition": WMO.get(code, "unbekannt") if code is not None else None,
        "code": code,
        # --- F12 ---
        "apparent_max_c": first("apparent_temperature_max"),
        "apparent_min_c": first("apparent_temperature_min"),
        "rain_h": first("precipitation_hours"),
        "daylight_h": round(daylight_s / 3600, 1) if daylight_s is not None else None,
        "gust_max_kmh": first("windgusts_10m_max"),
        "uv_max": first("uv_index_max"),
        "sunrise": clock(first("sunrise")),
        "sunset": clock(first("sunset")),
    }
    # Ältestes zuerst hinaus (Dicts halten die Einfügereihenfolge). Ein Lauf
    # arbeitet die Zeit entlang, der Deckel schneidet also das ab, was am
    # wenigsten wahrscheinlich noch einmal drankommt.
    if len(_CACHE) >= _CACHE_MAX:
        del _CACHE[next(iter(_CACHE))]
    _CACHE[(lat, lng, iso)] = result
    return dict(result)
