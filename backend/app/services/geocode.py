"""Geocoding über Nominatim (OpenStreetMap).

Löst Ortsnamen/Adressen -> Koordinaten + genaue Adresse auf. Damit sind
präzise Angaben bis Straße/Hausnummer möglich, wenn der Text sie enthält.

MVP: öffentlicher Nominatim-Endpoint. Fürs Homelab später self-hosted
Nominatim (gleiche API) -> nur base_url tauschen. Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "life-dash/0.1 (self-hosted life database)"


def geocode(query: str) -> dict | None:
    """Gibt {name, lat, lng, type} für den besten Treffer zurück oder None."""
    if not query or not query.strip():
        return None
    params = urllib.parse.urlencode(
        {"q": query.strip(), "format": "json", "limit": 1, "addressdetails": 1}
    )
    req = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    if not data:
        return None
    hit = data[0]
    try:
        return {
            "name": hit.get("display_name", query),
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
        {"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 17, "addressdetails": 1}
    )
    req = urllib.request.Request(
        f"{NOMINATIM_REVERSE_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    name = data.get("display_name")
    if not name:
        return None
    return {"name": name, "type": data.get("type")}
