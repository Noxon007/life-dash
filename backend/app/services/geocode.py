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
import time
import urllib.error
import urllib.parse
import urllib.request

from app.config import settings

log = logging.getLogger("lifedash.geocode")

USER_AGENT = "life-dash/0.1 (self-hosted life database)"
ACCEPT_LANGUAGE = "de,en"  # Fallback-Kette: Deutsch -> englische Umschrift


def _base() -> str:
    """Basis-URL des Geocoders (OSM-Nominatim oder z. B. LocationIQ)."""
    return settings.geocoder_base_url.rstrip("/")


def _with_key(params: dict) -> dict:
    """API-Key anhängen, falls ein Key-Dienst (LocationIQ) konfiguriert ist."""
    if settings.geocoder_api_key:
        params["key"] = settings.geocoder_api_key
    return params


def _fetch_json(url: str, what: str):
    """GET + JSON mit 429-Behandlung (0.15.2): Drosselt der Dienst, wird
    Retry-After respektiert (Deckel 30 s) und EINMAL erneut versucht —
    statt im Sekundentakt gegen die Sperre weiterzufeuern."""
    for attempt in (1, 2):
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 1:
                try:
                    wait = min(float(exc.headers.get("Retry-After") or 5), 30)
                except ValueError:
                    wait = 5.0
                log.warning("%s: Geocoder drosselt (429) — warte %.0f s", what, wait)
                time.sleep(wait)
                continue
            log.warning("%s fehlgeschlagen: %s", what, exc)
            return None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            log.warning("%s fehlgeschlagen: %s", what, exc)
            return None
    return None

# Nicht-lateinische Schriften (Griechisch, Kyrillisch, Hebräisch, Arabisch,
# Devanagari, Thai, Kana, CJK, Hangul) — zum Erkennen von Fremdschrift-Namen
NON_LATIN_RE = re.compile(
    "[\\u0370-\\u03ff\\u0400-\\u04ff\\u0590-\\u05ff\\u0600-\\u06ff"
    "\\u0900-\\u097f\\u0e00-\\u0e7f\\u3040-\\u30ff\\u4e00-\\u9fff\\uac00-\\ud7af]"
)

# --------------------------------------------------------------------------- #
# Kompakter Anzeige-Name (statt des langen display_name)
#
# Nominatims display_name enthält die komplette Verwaltungskette („…, Gemeinde
# Korfu-Mitte und Inseln, Regionalbezirk Korfu, …, 491 00, Griechenland").
# Für die Anzeige wird der Name stattdessen aus den strukturierten
# addressdetails-Feldern zusammengesetzt. Welche Bausteine einfließen, ist
# pro Nutzer wählbar (User.settings["place_name_parts"], Reihenfolge fix).
# --------------------------------------------------------------------------- #
PLACE_NAME_PARTS = ("road", "suburb", "city", "country")
# Baustein -> OSM-Adressfelder (erstes gefülltes gewinnt)
_PART_KEYS = {
    "road": ("road", "pedestrian", "footway", "path", "square"),
    "suburb": ("suburb", "neighbourhood", "quarter", "borough", "hamlet"),
    "city": ("city", "town", "village", "municipality"),
    "country": ("country",),
}


def sanitize_parts(parts) -> list[str]:
    """Whitelist + kanonische Reihenfolge; leere/ungültige Auswahl -> alle."""
    chosen = [p for p in PLACE_NAME_PARTS if parts and p in parts]
    return chosen or list(PLACE_NAME_PARTS)


def parts_for(user) -> list[str]:
    """Gewählte Bausteine aus den Nutzer-Einstellungen (oder Default)."""
    prefs = getattr(user, "settings", None) or {}
    return sanitize_parts(prefs.get("place_name_parts"))


def _poi_name(namedetails: dict | None) -> str | None:
    """Eigenname des Treffers (name:de -> name:en -> name) — z. B. ein
    POI-Name („Adlerwarte Berlebeck"), der in keinem Adress-Baustein steckt."""
    nd = namedetails or {}
    for key in ("name:de", "name:en", "name"):
        if nd.get(key):
            return str(nd[key])
    return None


def short_name(hit: dict | None, parts: list[str] | None = None) -> str:
    """Kompakter Anzeige-Name aus den addressdetails eines Treffers,
    z. B. "Ελευθερίου Βενιζέλου, Mantouki, Korfu, Griechenland".

    Ist der Treffer ein benanntes Objekt (POI wie Restaurant, Museum,
    Aussichtspunkt), steht dessen Eigenname immer vorn — er ist in den
    Adress-Bausteinen nicht enthalten. Trägt das Objekt selbst einen
    Baustein-Namen (Straße, Stadt …), wird nichts doppelt ausgegeben.
    Fällt ohne Adressfelder auf die ersten zwei display_name-Segmente zurück."""
    addr = (hit or {}).get("address") or {}
    out: list[str] = []
    poi = (hit or {}).get("poi")
    # Baustein-Werte (roh): dient dem Dubletten-Check — ist der Eigenname
    # z. B. der Straßen- oder Stadtname selbst, ist er kein POI-Zusatz
    part_vals = {str(addr[k]) for keys in _PART_KEYS.values() for k in keys if addr.get(k)}
    if poi and poi not in part_vals:
        out.append(str(poi))
    for part in sanitize_parts(parts):
        val = next((addr[k] for k in _PART_KEYS[part] if addr.get(k)), None)
        if part == "road" and val and addr.get("house_number"):
            val = f"{val} {addr['house_number']}"
        if val and val not in out:
            out.append(str(val))
    if out:
        return ", ".join(out)
    name = (hit or {}).get("name") or ""
    return ", ".join(s.strip() for s in name.split(",")[:2])


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
    params = urllib.parse.urlencode(_with_key(
        {"q": query.strip(), "format": "json", "limit": 1,
         "addressdetails": 1, "namedetails": 1}
    ))
    data = _fetch_json(f"{_base()}/search?{params}", f"Nominatim-Suche ({query!r})")
    if data is None:
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
            # strukturierte Felder für den kompakten Anzeige-Namen (short_name)
            "address": hit.get("address") or {},
            "poi": _poi_name(hit.get("namedetails")),
        }
    except (KeyError, ValueError, TypeError):
        return None


def reverse_geocode(lat: float, lng: float) -> dict | None:
    """Koordinate -> Adresse ({name, type}) — für importierte Timeline-Besuche,
    deren Geräte-Export keine Ortsnamen enthält. zoom=17 ≈ Gebäude/Straße.

    Achtung Nominatim-Policy: max. 1 Anfrage/Sekunde — Aufrufer drosselt.
    """
    # LocationIQ kennt kein "jsonv2" — mit Key schlicht "json" (die genutzten
    # Felder display_name/address/namedetails sind in beiden identisch)
    fmt = "json" if settings.geocoder_api_key else "jsonv2"
    params = urllib.parse.urlencode(_with_key(
        {"lat": lat, "lon": lng, "format": fmt, "zoom": 17,
         "addressdetails": 1, "namedetails": 1}
    ))
    data = _fetch_json(f"{_base()}/reverse?{params}",
                       f"Reverse-Geocoding ({lat}, {lng})")
    if not data or not isinstance(data, dict):
        return None
    name = data.get("display_name")
    if not name:
        return None
    return {"name": _prefer_latin(name, data.get("namedetails")),
            "type": data.get("type"),
            "address": data.get("address") or {},
            "poi": _poi_name(data.get("namedetails"))}
