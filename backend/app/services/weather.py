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
# Anmerkung 186 — EINE Quelle, ausdrücklich benannt
# --------------------------------------------------------------------------- #
# Bis 0.39 stand hier keine Modellangabe, der Dienst wählte also selbst
# („best_match"). **Und er wählt nach dem ALTER des Tages.** Gemessen am
# 27.06.2026 in Hamburg (Baakenallee), gegen die DWD-Station Fuhlsbüttel mit
# 39,1 °C gemessen:
#
#     best_match (bis hier)      31,3 °C     ← ECMWF IFS
#     ERA5                       37,6 °C
#     ERA5-Land                  36,8 °C
#     ICON-D2 (2,2 km)           38,9 °C
#
# Für den 15.07.1990 und den 17.02.1962 antwortete dasselbe best_match dagegen
# aus ERA5-Land. Ein Archiv über ein ganzes Leben verglich damit die Kindheit
# in einem Modell mit der Gegenwart in einem anderen — an einem Hitzetag sechs
# Kelvin auseinander. **Ein „wärmster Tag deines Lebens" war so keine Aussage
# über das Leben, sondern eine über die Modellwahl des Dienstes.** Und weil
# jeder Tag genau einmal gefragt wird (`weather_rev`), wäre jede spätere
# Änderung dieser Wahl dauerhaft neben den alten Werten liegen geblieben.
#
# **Warum ERA5 und nicht das genaueste.** ICON-D2 träfe die Messung fast, gibt
# es aber nur für Deutschland und erst ab 2021 — die letzten Jahre wären dann
# systematisch heißer als alle davor, und jeder Rekord fiele automatisch in die
# jüngste Zeit. ERA5-Land ist feiner (0,1° statt 0,25°), liefert aber über
# Wasser nichts: geprüft mit `None` für die offene Nordsee UND für Paxos, das
# der Landmaske zu klein ist. Eine Quelle, die bei jeder Insel- und
# Schiffsreise aussetzt, erzwingt eine zweite — und damit genau das Gemisch,
# das hier abgeschafft wird. ERA5 deckt 1940 bis heute ab, weltweit, Land wie
# Wasser.
#
# Der Preis steht in der Oberfläche, statt verschwiegen zu werden: die Werte
# sind ein Modellmittel über ~25 km und kein Thermometer. An einem Rekordtag
# sind das 1,5 K zu wenig — aber gleichmäßig zu wenig, und darauf beruht die
# Vergleichbarkeit, um die es geht.
WEATHER_MODEL = "era5"
# Wie viele Tage ERA5 hinterherhinkt. Geprüft: für vorgestern kam `None`.
# Der Lauf überspringt so junge Tage deshalb, statt sie bei jedem Durchgang
# vergeblich zu fragen — ohne Antwort wird keine Marke gesetzt, sie kommen
# also von selbst dran, sobald sie alt genug sind.
ERA5_LAG_DAYS = 6

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
#
# **Anmerkung 188 — die Gewitter-Codes (95/96/99) kommen hier NIE an.** Nicht
# weil ERA5 gewählt wurde: gemessen über den Sommer 2024 in Hamburg liefert
# KEINES der Archiv-Modelle sie (era5, era5_land, ecmwf_ifs — alle null), und
# über sechs Jahre kamen aus ERA5 genau neun verschiedene Codes, keiner davon
# konvektiv. Eine Reanalyse rechnet auf 25 km; ein Gewitter ist kleiner als
# eine Gitterzelle. Auch `showers_sum` steht im Antwortformat und bleibt in
# ERA5 durchgehend 0,0 (615 Sommertage geprüft), und `cape` gibt es im Archiv
# gar nicht.
#
# Die drei Zeilen bleiben trotzdem stehen: sie sind die Übersetzung eines
# fremden Codes, nicht eine Zusage, dass er vorkommt. **Wer daraus eine
# Auswertung bauen will („Gewittertage", „stärkstes Gewitter"), baut eine, die
# für immer leer bleibt** — und eine Ansicht, die aussieht wie gebaut und immer
# null zeigt, ist genau die Stille, die dieses Projekt teuer bezahlt. Gewitter
# hat nur das Modell-Archiv (`historical-forecast-api`, ICON, 2,2 km), und das
# reicht nur bis ~2021 zurück: für ein Leben wären das die letzten Jahre, und
# eine Rangliste daraus wäre eine Aussage über sie, nicht über das Leben
# (dieselbe Falle wie in Anmerkung 186).
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
    (Entscheidung F3, siehe DECISIONS Anmerkung 49)."""
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
        # Anmerkung 186: ausdrücklich, sonst entscheidet der Dienst — und zwar
        # je nach Alter des Tages verschieden.
        "models": WEATHER_MODEL,
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
