"""Geocoding über Nominatim (OpenStreetMap).

Löst Ortsnamen/Adressen -> Koordinaten + genaue Adresse auf. Damit sind
präzise Angaben bis Straße/Hausnummer möglich, wenn der Text sie enthält.

Sprache (A10): Angefragt wird mit `Accept-Language: de,en` — fehlt ein
deutscher OSM-Name, liefert Nominatim die englische/lateinische Umschrift
statt der Lokalschrift (z. B. Griechisch). Zusätzlich wird über
`namedetails` der beste lateinische Name (`name:de` -> `name:en`) bevorzugt,
falls der Hauptname trotzdem in Fremdschrift kommt.

MVP: öffentlicher Nominatim-Endpoint. Fürs Homelab später self-hosted
Nominatim (gleiche API) -> nur base_url tauschen. Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request

log = logging.getLogger("lifedash.geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "life-dash/0.1 (self-hosted life database)"
ACCEPT_LANGUAGE = "de,en"  # Fallback-Kette: Deutsch -> englische Umschrift

# Nicht-lateinische Schriften (Griechisch, Kyrillisch, Hebräisch, Arabisch,
# Devanagari, Thai, Kana, CJK, Hangul) — zum Erkennen von Fremdschrift-Namen
NON_LATIN_RE = re.compile(
    "[\\u0370-\\u03ff\\u0400-\\u04ff\\u0590-\\u05ff\\u0600-\\u06ff"
    "\\u0900-\\u097f\\u0e00-\\u0e7f\\u3040-\\u30ff\\u4e00-\\u9fff\\uac00-\\ud7af]"
)


def _prefer_latin(display_name: str, namedetails: dict | None) -> str:
    """Ersetzt einen fremdschriftlichen Hauptnamen (erstes Adress-Segment)
    durch `name:de`/`name:en` aus den namedetails, falls vorhanden."""
    if not namedetails or not display_name:
        return display_name
    first, sep, rest = display_name.partition(",")
    if not NON_LATIN_RE.search(first):
        return display_name
    best = namedetails.get("name:de") or namedetails.get("name:en")
    if not best or NON_LATIN_RE.search(best):
        return display_name
    return f"{best}{sep}{rest}"


def geocode(query: str) -> dict | None:
    """Gibt {name, lat, lng, type} für den besten Treffer zurück oder None."""
    if not query or not query.strip():
        return None
    params = urllib.parse.urlencode(
        {"q": query.strip(), "format": "json", "limit": 1,
         "addressdetails": 1, "namedetails": 1}
    )
    req = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        log.warning("Nominatim-Suche fehlgeschlagen (%r): %s", query, exc)
        return None
    if not data:
        log.debug("Nominatim-Suche ohne Treffer: %r", query)
        return None
    hit = data[0]
    try:
        return {
            "name": _prefer_latin(hit.get("display_name", query), hit.get("namedetails")),
            "lat": float(hit["lat"]),
            "lng": float(hit["lon"]),
            "type": hit.get("type"),
        }
    except (KeyError, ValueError, TypeError):
        return None


def reverse_geocode(lat: float, lng: float) -> dict | None:
    """Koordinate -> Adresse ({name, type}) — für importierte Timeline-Besuche,
    deren Geräte-Export keine Ortsnamen enthält. zoom=17 ≈ Gebäude/Straße.

    Achtung Nominatim-Policy: max. 1 Anfrage/Sekunde — Aufrufer drosselt.
    """
    params = urllib.parse.urlencode(
        {"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 17,
         "addressdetails": 1, "namedetails": 1}
    )
    req = urllib.request.Request(
        f"{NOMINATIM_REVERSE_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        log.warning("Reverse-Geocoding fehlgeschlagen (%s, %s): %s", lat, lng, exc)
        return None
    name = data.get("display_name")
    if not name:
        return None
    return {"name": _prefer_latin(name, data.get("namedetails")),
            "type": data.get("type")}
