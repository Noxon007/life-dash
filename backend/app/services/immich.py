"""P2.1 — Immich-Konnektor: Fotos zu Ereignissen finden.

**Verweise, keine Kopien** (KONZEPT Kap. 9). Die Bilder bleiben in Immich;
Life-Dash merkt sich nur die Asset-ID und reicht Vorschaubilder durch. Damit
sind Immich-Verknüpfungen eine **Ableitung** (Schicht 4, Anmerkung 57): sie
dürfen jederzeit verworfen und neu berechnet werden — anders als die
hochgeladenen Dateien aus F15, die zur Lebensdatenbank gehören.

Der Konnektor ist bewusst isoliert und defensiv: Immich ist ein fremder
Dienst, der nicht läuft, langsam antworten oder seine API ändern kann. Nichts
davon darf die App mitreißen — im Zweifel gibt es einfach keine Fotos.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

log = logging.getLogger("lifedash.immich")

TIMEOUT = 15
# Immich deckelt die Trefferzahl je Seite; mehr als das braucht ein einzelnes
# Ereignis ohnehin nicht.
PAGE_SIZE = 250


class ImmichError(RuntimeError):
    """Immich nicht erreichbar oder Antwort unbrauchbar — Text geht an den Nutzer."""


def config_for(user) -> tuple[str, str] | None:
    """(Basis-URL, API-Schlüssel) aus den Nutzereinstellungen — oder None.

    Pro Nutzer, nicht global: in einem Mehrpersonen-Setup hat jeder seine
    eigene Immich-Bibliothek (Kap. 9)."""
    prefs = (user.settings or {}).get("immich") or {}
    url, key = (prefs.get("url") or "").strip().rstrip("/"), (prefs.get("api_key") or "").strip()
    return (url, key) if url and key else None


# Ein Reverse-Proxy vor Immich (Nginx, Traefik …) liefert bei Last oder einem
# kurzen Neustart gern ein 502/503/504. Das ist vorübergehend — einmal kurz
# warten und erneut versuchen, statt den ganzen Foto-Lauf abzubrechen.
_TRANSIENT = (502, 503, 504)
_RETRIES = 2
_RETRY_WAIT = 1.5


def _request(url: str, key: str, path: str, *, payload: dict | None = None,
             raw: bool = False):
    """Ein Aufruf gegen Immich. `payload` -> POST (JSON), sonst GET."""

    target = f"{url}/api{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    last: ImmichError | None = None
    for attempt in range(_RETRIES + 1):
        req = urllib.request.Request(target, data=data, method="POST" if data else "GET")
        req.add_header("x-api-key", key)
        req.add_header("Accept", "application/octet-stream" if raw else "application/json")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = resp.read()
                return body if raw else json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ImmichError("Immich lehnt den API-Schlüssel ab (401/403)") from exc
            if exc.code == 404:
                raise ImmichError(f"Immich kennt {path} nicht (404) — "
                                  "passt die URL und die Immich-Version?") from exc
            if exc.code in _TRANSIENT and attempt < _RETRIES:
                last = ImmichError(f"Immich vorübergehend nicht bereit ({exc.code})")
                log.info("Immich %d bei %s — erneuter Versuch %d/%d",
                         exc.code, path, attempt + 1, _RETRIES)
                time.sleep(_RETRY_WAIT)
                continue
            raise ImmichError(f"Immich antwortet mit {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < _RETRIES:
                last = ImmichError(f"Immich nicht erreichbar: {exc}")
                time.sleep(_RETRY_WAIT)
                continue
            raise ImmichError(f"Immich nicht erreichbar: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ImmichError("Immich liefert keine gültige JSON-Antwort — "
                              "zeigt die URL wirklich auf Immich?") from exc
    raise last or ImmichError("Immich nicht erreichbar")


def check(url: str, key: str) -> dict:
    """Verbindungstest für die Einstellungen.

    Gibt es diesen Knopf nicht, merkt der Nutzer einen Tippfehler erst daran,
    dass ein Foto-Lauf nichts findet — und sucht die Ursache an der falschen
    Stelle.

    Bewusst `/server/about` und NICHT `/server/ping`: ping antwortet ohne
    jede Authentifizierung und würde einen falschen API-Schlüssel als Erfolg
    melden — also genau den Fehler verschweigen, den der Test finden soll.
    """
    info = _request(url.rstrip("/"), key, "/server/about")
    return {"ok": True, "version": (info or {}).get("version") or "unbekannt"}


def _stamp(when: datetime) -> str:
    """Zeitstempel im Format, das Immich akzeptiert.

    Wichtig: Immich validiert `takenAfter`/`takenBefore` gegen ein Muster, das
    eine **Zeitzone verlangt** (`Z` oder `±hh:mm`). Ein nacktes
    `2024-05-01T00:00:00` wird mit 400 abgelehnt. Life-Dash speichert Zeiten
    als lokale Wanduhrzeit (A13), also wird genau die lokale Zone angehängt —
    `Z` würde das Fenster um den UTC-Versatz verschieben und an Tagesgrenzen
    die falschen Fotos einsammeln.
    """
    return (when if when.tzinfo else when.astimezone()).isoformat()


def search_assets(url: str, key: str, start: datetime, end: datetime) -> list[dict]:
    """Assets in einem Zeitfenster (Aufnahmezeit), neueste zuerst."""
    body = {
        "takenAfter": _stamp(start),
        "takenBefore": _stamp(end),
        "size": PAGE_SIZE,
        "page": 1,
        "withExif": True,
    }
    data = _request(url, key, "/search/metadata", payload=body)
    items = (((data or {}).get("assets") or {}).get("items")) or []
    # Nur Bilder und Videos mit Aufnahmezeit — alles andere lässt sich einem
    # Ereignis nicht sinnvoll zuordnen.
    return [a for a in items if a.get("id")]


def thumbnail(url: str, key: str, asset_id: str) -> bytes:
    """Vorschaubild eines Assets — durchgereicht, nie zwischengespeichert."""
    return _request(url, key, f"/assets/{asset_id}/thumbnail?size=preview", raw=True)


# --------------------------------------------------------------------------- #
# Zuordnung Asset -> Ereignis
# --------------------------------------------------------------------------- #
def asset_time(asset: dict) -> datetime | None:
    raw = (asset.get("exifInfo") or {}).get("dateTimeOriginal") or asset.get("fileCreatedAt")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def asset_geo(asset: dict) -> tuple[float, float] | None:
    exif = asset.get("exifInfo") or {}
    lat, lng = exif.get("latitude"), exif.get("longitude")
    if lat is None or lng is None:
        return None
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Grobe Entfernung in km. Bewusst ohne Haversine: für „war das Foto in
    der Nähe?" reicht die flache Näherung, und sie kostet keine Bibliothek."""
    from math import cos, radians, sqrt

    dlat = (a[0] - b[0]) * 111.0
    dlng = (a[1] - b[1]) * 111.0 * cos(radians((a[0] + b[0]) / 2))
    return sqrt(dlat * dlat + dlng * dlng)


def window_for(event, *, pad_hours: int = 6) -> tuple[datetime, datetime] | None:
    """Zeitfenster, in dem Fotos zu diesem Ereignis passen könnten.

    Die Genauigkeit des Ereignisses entscheidet: bei `exact` sind es Stunden
    um den Zeitpunkt, bei einem Tag der ganze Tag, bei einer Reise die ganze
    Spanne. Vage Angaben (Monat, Jahreszeit, Jahr, Jahrzehnt) bekommen KEIN
    Fenster — „Sommer 2002" würde sonst wahllos Fotos einsammeln, und ein
    falsches Foto am Eintrag ist schlimmer als gar keins.
    """
    from app.models import DatePrecision

    if event.date_start is None:
        return None
    if event.date_precision not in (DatePrecision.exact, DatePrecision.day):
        return None
    start = event.date_start
    end = event.date_end or event.date_start
    if event.date_precision == DatePrecision.exact:
        return start - timedelta(hours=pad_hours), end + timedelta(hours=pad_hours)
    # Tagesgenau: vom Beginn des ersten bis zum Ende des letzten Tages
    return (start.replace(hour=0, minute=0, second=0, microsecond=0),
            end.replace(hour=23, minute=59, second=59, microsecond=999999))


def matches(event, asset: dict, *, max_km: float = 25.0) -> bool:
    """Passt dieses Asset zu diesem Ereignis?

    Die Zeit hat der Suchaufruf schon geprüft. Bleibt der Ort: hat sowohl das
    Ereignis als auch das Foto Koordinaten, müssen sie zusammenpassen — sonst
    landen die Urlaubsfotos anderer Leute am selben Tag im eigenen Eintrag.
    Fehlt einem von beiden die Position, entscheidet allein die Zeit; das ist
    absichtlich großzügig, denn ungetaggte Fotos sind häufig.
    """
    loc = getattr(event, "location", None)
    if not loc or loc.lat is None or loc.lng is None:
        return True
    geo = asset_geo(asset)
    if geo is None:
        return True
    return _km(geo, (loc.lat, loc.lng)) <= max_km
