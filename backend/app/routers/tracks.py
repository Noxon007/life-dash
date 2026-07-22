"""Google-Timeline-Import (P2.2) + Track-Abfrage für den Karten-Layer.

Unterstützte Formate:
- Geräte-Export (Android/iOS, 2024+): {"semanticSegments": [...]} mit
  visit / activity / timelinePath — Koordinaten als "51.22°, 6.77°"-Strings.
- Alter Takeout-Export (Semantic Location History): {"timelineObjects": [...]}
  mit placeVisit / activitySegment — Koordinaten als latitudeE7/longitudeE7.

Besuche werden zu Events (source google_timeline, sofort confirmed — das Gerät
ist die Quelle), Bewegungen zu Tracks (Stufe 3, Punkte unvereinfacht).
Jedes Segment trägt einen stabilen Hash als external_id -> Re-Import ist
idempotent (Dubletten werden übersprungen).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from datetime import datetime, timezone

from dateutil import parser as dateparser
from fastapi import APIRouter, Body, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import (
    ConfirmState,
    DatePrecision,
    Entity,
    Event,
    EventEntityLink,
    Fragment,
    FragmentStatus,
    Location,
    Source,
    Track,
    User,
)
from app.schemas import PlaceNameResolveResult, TimelineImportResult, TrackRead
from app.services import geocode as geocode_svc

log = logging.getLogger("lifedash.timeline")

# Nominatim-Policy: max. 1 Anfrage/Sekunde — 1,2 s lässt Luft, damit der
# öffentliche Endpoint nicht mit 429 drosselt (Modul-Konstante -> in Tests
# patchbar). Mit konfiguriertem Key-Dienst (LocationIQ, 2/s) geht es schneller.
NOMINATIM_DELAY_S = 1.2


def _geo_delay() -> float:
    return min(NOMINATIM_DELAY_S, 0.6) if settings.geocoder_api_key else NOMINATIM_DELAY_S
# Beim Import nur kleine Mengen NEUER Orte direkt auflösen — große Erstimporte
# laufen über den Admin-Button „Ortsnamen auflösen" (sonst dauert der Upload Minuten)
AUTO_RESOLVE_MAX = 30

router = APIRouter(prefix="/api", tags=["Tracks & Timeline-Import"])

# Google-Aktivitätstyp -> Track.activity_type (beide Formate, normalisiert)
_ACTIVITY_MAP = {
    "walking": "walk", "on foot": "walk",
    "running": "run",
    "cycling": "cycle", "on bicycle": "cycle",
    "in passenger vehicle": "drive", "driving": "drive", "in vehicle": "drive",
    "motorcycling": "drive", "in taxi": "drive",
    "in bus": "transit", "in train": "transit", "in subway": "transit",
    "in tram": "transit", "in ferry": "transit", "flying": "transit",
}

# semanticType -> deutscher Ortsname (Geräte-Export kennt keine Ortsnamen).
# A19: "searched address" bekommt bewusst KEIN Label mehr — es beschreibt nur,
# wie Google den Aufenthalt erkannt hat, und stiftet keinen Mehrwert. Solche
# Besuche laufen als unbenannte Orte ("Ort (lat, lng)") in die normale
# Adress-Auflösung und enden als reine Adresse.
_SEMANTIC_NAMES = {
    "home": "Zuhause", "inferred home": "Zuhause (vermutet)",
    "work": "Arbeit", "inferred work": "Arbeit (vermutet)",
    "aliased location": "Gespeicherter Ort",
}
# A12: Semantische Labels sind KEINE echten Ortsnamen — sie zählen wie
# Koordinaten-Namen als "unaufgelöst" und werden reverse-geocodet; das Label
# bleibt dabei als Präfix erhalten ("Zuhause — Musterstraße 1, Detmold").
SEMANTIC_LABELS = frozenset(_SEMANTIC_NAMES.values())
# A19: Alt-Label aus früheren Importen — bleibt Auflösungs-Kandidat, wird beim
# Auflösen aber ERSETZT statt als Präfix behalten (Migration räumt Rest auf).
DROP_LABELS = frozenset({"Gesuchte Adresse"})

_LATLNG_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*°?\s*,\s*(-?\d+(?:\.\d+)?)")


# --------------------------------------------------------------------------- #
# Parse-Helfer
# --------------------------------------------------------------------------- #
def _latlng(value) -> tuple[float, float] | None:
    """Koordinate aus "51.22°, 6.77°", {"latLng": "..."} oder E7-Dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        if "latLng" in value:
            return _latlng(value["latLng"])
        if "latitudeE7" in value and "longitudeE7" in value:
            return value["latitudeE7"] / 1e7, value["longitudeE7"] / 1e7
        if "latE7" in value and "lngE7" in value:
            return value["latE7"] / 1e7, value["lngE7"] / 1e7
        return None
    m = _LATLNG_RE.search(str(value))
    if not m:
        return None
    lat, lng = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def _time(value) -> datetime | None:
    """ISO-Zeit -> naive lokale Wanduhrzeit (Tageszuordnung wie erlebt)."""
    if not value:
        return None
    try:
        return dateparser.isoparse(str(value)).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def _activity_type(raw: str | None) -> str:
    if not raw:
        return "unknown"
    return _ACTIVITY_MAP.get(str(raw).replace("_", " ").strip().lower(), "unknown")


def _seg_hash(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:40]


def _haversine_m(points: list) -> float:
    total = 0.0
    for (lat1, lng1), (lat2, lng2) in zip(points, points[1:]):
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        total += 6371000 * 2 * math.asin(math.sqrt(a))
    return round(total, 1)


# --------------------------------------------------------------------------- #
# Normalisierung: beide Google-Formate -> einheitliche Zwischenform
# --------------------------------------------------------------------------- #
def _normalize(payload: dict) -> tuple[list[dict], list[dict]]:
    """Liefert (visits, moves) als normalisierte Dicts.

    visit: {start, end, latlng, place_id, name, probability, hash}
    move:  {start, end, points, activity_type, distance_m, hash}
    """
    visits: list[dict] = []
    moves: list[dict] = []

    # ---- Geräte-Export (semanticSegments) ----
    for seg in payload.get("semanticSegments") or []:
        start, end = _time(seg.get("startTime")), _time(seg.get("endTime"))
        if not start or not end:
            continue
        base = (seg.get("startTime"), seg.get("endTime"))

        if "visit" in seg:
            v = seg["visit"] or {}
            top = v.get("topCandidate") or {}
            ll = _latlng(top.get("placeLocation"))
            if not ll:
                continue
            sem = str(top.get("semanticType") or "").replace("_", " ").strip().lower()
            name = _SEMANTIC_NAMES.get(sem)
            try:
                prob = float(v.get("probability") or 1.0)
            except (TypeError, ValueError):
                prob = 1.0
            visits.append({
                "start": start, "end": end, "latlng": ll,
                "place_id": top.get("placeId") or top.get("placeID"),
                "name": name, "probability": prob,
                "hash": _seg_hash("visit", *base, ll),
            })
        elif "timelinePath" in seg:
            points = [p for p in (_latlng(x.get("point")) for x in seg["timelinePath"] or []) if p]
            if len(points) < 2:
                continue
            moves.append({
                "start": start, "end": end, "points": points,
                "activity_type": None,  # wird ggf. aus activity-Segmenten annotiert
                "distance_m": _haversine_m(points),
                "hash": _seg_hash("path", *base, points[0], points[-1], len(points)),
            })
        elif "activity" in seg:
            a = seg["activity"] or {}
            p_start, p_end = _latlng(a.get("start")), _latlng(a.get("end"))
            points = [p for p in (p_start, p_end) if p]
            if len(points) < 2:
                continue
            try:
                dist = float(a.get("distanceMeters") or 0) or None
            except (TypeError, ValueError):
                dist = None
            moves.append({
                "start": start, "end": end, "points": points,
                "activity_type": _activity_type((a.get("topCandidate") or {}).get("type")),
                "distance_m": dist,
                "hash": _seg_hash("activity", *base, points[0], points[-1]),
                "_annotation_only": True,  # 2-Punkt-Linie: nur nutzen, wenn kein Pfad da ist
            })

    # ---- Alter Takeout-Export (timelineObjects) ----
    for obj in payload.get("timelineObjects") or []:
        if "placeVisit" in obj:
            pv = obj["placeVisit"] or {}
            loc, dur = pv.get("location") or {}, pv.get("duration") or {}
            start, end = _time(dur.get("startTimestamp")), _time(dur.get("endTimestamp"))
            ll = _latlng(loc)
            if not start or not end or not ll:
                continue
            visits.append({
                "start": start, "end": end, "latlng": ll,
                "place_id": loc.get("placeId"),
                "name": loc.get("name") or loc.get("address"),
                "probability": (pv.get("visitConfidence") or 100) / 100,
                "hash": _seg_hash("visit", dur.get("startTimestamp"), dur.get("endTimestamp"), ll),
            })
        elif "activitySegment" in obj:
            seg = obj["activitySegment"] or {}
            dur = seg.get("duration") or {}
            start, end = _time(dur.get("startTimestamp")), _time(dur.get("endTimestamp"))
            if not start or not end:
                continue
            points = []
            for wp in ((seg.get("waypointPath") or {}).get("waypoints")
                       or (seg.get("simplifiedRawPath") or {}).get("points") or []):
                ll = _latlng(wp)
                if ll:
                    points.append(ll)
            if len(points) < 2:
                points = [p for p in (_latlng(seg.get("startLocation")), _latlng(seg.get("endLocation"))) if p]
            if len(points) < 2:
                continue
            moves.append({
                "start": start, "end": end, "points": points,
                "activity_type": _activity_type(seg.get("activityType")),
                "distance_m": float(seg.get("distance") or 0) or _haversine_m(points),
                "hash": _seg_hash("activity", dur.get("startTimestamp"), dur.get("endTimestamp"),
                                  points[0], points[-1]),
            })

    return visits, moves


def _annotate_paths(moves: list[dict]) -> list[dict]:
    """Geräte-Export: timelinePath-Tracks bekommen den Typ des überlappenden
    activity-Segments; reine 2-Punkt-activity-Tracks entfallen dann."""
    paths = [m for m in moves if not m.get("_annotation_only")]
    activities = [m for m in moves if m.get("_annotation_only")]
    used = set()
    for p in paths:
        if p["activity_type"]:
            continue
        mid = p["start"] + (p["end"] - p["start"]) / 2
        for i, a in enumerate(activities):
            if a["start"] <= mid <= a["end"]:
                p["activity_type"] = a["activity_type"]
                # Googles gemessene Distanz ist genauer als die Haversine-Summe
                # über den (grob gesampelten) Pfad
                if a["distance_m"]:
                    p["distance_m"] = a["distance_m"]
                used.add(i)
                break
        p["activity_type"] = p["activity_type"] or "unknown"
    # activity-Segmente ohne zugehörigen Pfad bleiben als 2-Punkt-Track erhalten
    remaining = [a for i, a in enumerate(activities) if i not in used]
    for a in remaining:
        a.pop("_annotation_only", None)
    return paths + remaining


def _semantic_label(name: str | None) -> str | None:
    """Semantisches Label eines Ortsnamens ("Zuhause", "Arbeit — Musterstr. 1"
    -> "Arbeit"), sonst None. Erkennt auch bereits aufgelöste Namen mit
    Label-Präfix, damit z. B. die Fremdschrift-Auflösung das Label behält."""
    if not name:
        return None
    first = name.split(" — ", 1)[0].strip()
    if first in DROP_LABELS:  # A19: Label fällt bei der Auflösung weg
        return None
    return first if first in SEMANTIC_LABELS else None


def _apply_resolved_name(db: Session, loc: Location, user_id: str,
                         parts: list[str] | None = None,
                         lang: str | None = None) -> bool:
    """Reverse-geocodet eine Location und zieht die Titel der verknüpften
    Besuchs-Events („Besuch: …") nach — deckt Koordinaten-Namen („Ort (lat,
    lng)"), semantische Labels („Zuhause", A12) und Fremdschrift-Namen (A10)
    ab. Gespeichert wird der kompakte Anzeige-Name aus den gewählten
    Bausteinen (`parts`, z. B. Straße/Ortsteil/Stadt/Land) statt der langen
    Nominatim-Adresse. Semantische Labels bleiben als Präfix erhalten
    („Zuhause — Adresse"); der Location-Typ (z. B. home) bleibt dabei
    unverändert, und getrennte place_ids (z. B. mehrere Wohnorte im
    Lebenslauf) bleiben getrennte Orte. Manuell umbenannte Events (title in
    field_overrides) bleiben unangetastet."""
    label = _semantic_label(loc.name)
    hit = geocode_svc.reverse_geocode(loc.lat, loc.lng, lang)
    if not hit:
        return False
    short = geocode_svc.short_name(hit, parts)
    if not short:
        return False
    if label:
        short = f"{label} — {short}"
    loc.name = short[:255]
    if not label and hit.get("type"):
        loc.type = hit["type"]
    linked = (
        db.query(Event)
        .filter(Event.user_id == user_id, Event.location_id == loc.id,
                Event.title.like("Besuch:%"))
        .all()
    )
    for ev in linked:
        if (ev.field_overrides or {}).get("title"):
            continue
        ev.title = f"Besuch: {short}"[:255]
    # A39: Stadt aus denselben addressdetails — trägt Städte-Statistik und
    # Zeitstrahl-Verdichtung. Nur setzen, wenn etwas da ist: ein bereits
    # bekannter Wert soll nicht von einem Treffer ohne Stadtfeld gelöscht
    # werden (Nominatim liefert nicht bei jeder Abfrage alle Bausteine).
    city = geocode_svc.city_of(hit)
    if city:
        loc.city = city
    elif loc.city is None:
        # A39: Leerstring = „nachgesehen, hier gibt es keine Stadt" (ein Ort
        # im Wald hat keine). NULL heißt dagegen „noch nie nachgesehen".
        # Ohne diese Unterscheidung würde der Rückfüll-Lauf jeden stadtlosen
        # Ort bei JEDEM Durchgang erneut abfragen — derselbe Dauerläufer, den
        # F12 mit `weather_rev` abstellen musste.
        loc.city = ""
    # F4: Land aus den addressdetails mitnehmen -> Länder-Kompendium/-Statistik
    country = (hit.get("address") or {}).get("country")
    if country:
        loc.country = country[:64]
        events_here = (db.query(Event)
                       .filter(Event.user_id == user_id, Event.location_id == loc.id)
                       .all())
        _link_country(db, user_id, loc.country, events_here)
    return True


def _link_country(db: Session, user_id: str, country: str,
                  events: list[Event]) -> int:
    """F4: Legt die country-Entity an (falls neu) und verknüpft die Events —
    idempotent (bestehende Verknüpfungen bleiben einmalig). Import-Daten sind
    Fakten -> Entity ist bestätigt."""
    if not country or not events:
        return 0
    entity = (db.query(Entity)
              .filter(Entity.user_id == user_id, Entity.type == "country",
                      Entity.name.ilike(country))
              .first())
    if not entity:
        entity = Entity(user_id=user_id, type="country", name=country,
                        confirmed=ConfirmState.confirmed)
        db.add(entity)
        db.flush()
    have = {l.event_id for l in db.query(EventEntityLink)
            .filter(EventEntityLink.entity_id == entity.id).all()}
    added = 0
    for ev in events:
        if ev.id not in have:
            db.add(EventEntityLink(event_id=ev.id, entity_id=entity.id,
                                   role="mentioned"))
            added += 1
    return added


def _unresolved_name_filter():
    """SQL-Filter für Orte ohne echten Namen: Koordinaten-Platzhalter
    („Ort (lat, lng)"), semantische Labels ohne Adresse (A12) und
    Alt-Labels aus früheren Importen (A19)."""
    return or_(Location.name.like("Ort (%"),
               Location.name.in_(SEMANTIC_LABELS | DROP_LABELS))


def _nonlatin_locations(db: Session, user_id: str) -> list[Location]:
    """Verortete Locations des Nutzers, deren Name Fremdschrift enthält
    (z. B. Griechisch) — Kandidaten für die Neu-Auflösung auf Deutsch (A10)."""
    rows = (db.query(Location)
            .filter(Location.user_id == user_id, Location.lat.isnot(None))
            .all())
    return [l for l in rows if geocode_svc.NON_LATIN_RE.search(l.name or "")]


def _verbose_locations(db: Session, user_id: str, parts: list[str]) -> list[Location]:
    """Verortete Locations, deren Name länger ist, als das gewählte Format
    zulässt (mehr Komma-Segmente als Bausteine) — alte, voll ausgeschriebene
    Nominatim-Adressen. Kandidaten fürs Nachformatieren (scope=verbose)."""
    max_commas = len(parts) - 1
    rows = (db.query(Location)
            .filter(Location.user_id == user_id, Location.lat.isnot(None))
            .all())
    return [l for l in rows if (l.name or "").count(",") > max_commas]


def _name_defect(name: str | None, parts: list[str]) -> str | None:
    """A28: Welchen Mangel hat dieser Ortsname — oder keinen (None)?

    Die eine Bedingung, die die drei früheren Scopes ersetzt. Reihenfolge ist
    bedeutsam: „unnamed" zuerst, denn ein frisch geholter Name kommt bereits
    im gewählten Format und in der gewählten Sprache — er kann danach weder
    zu lang noch fremdschriftlich sein. Wer hier nichts zurückgibt, ist fertig
    und wird vom Lauf nicht noch einmal angefasst."""
    n = name or ""
    if n.startswith("Ort (") or n in SEMANTIC_LABELS or n in DROP_LABELS:
        return "unnamed"
    if geocode_svc.NON_LATIN_RE.search(n):
        return "nonlatin"
    if n.count(",") > len(parts) - 1:
        return "verbose"
    return None


def _resolve_candidates(db: Session, user_id: str, parts: list[str]) -> list[Location]:
    """A28: Alle Orte mit Namensmangel als EINE entduplizierte Liste,
    „unnamed" zuerst.

    Vorher lief der Job dreimal, einmal je Scope — ein Ort kann aber in
    mehreren Mengen liegen (eine griechische Adresse ist meist auch zu lang)
    und wurde dann bis zu dreimal geocodiert. Bei Nominatims 1,2-s-Drossel
    ist das der eigentliche Gewinn, nicht der eine Klick."""
    rows = (db.query(Location)
            .filter(Location.user_id == user_id, Location.lat.isnot(None))
            .all())
    order = {"unnamed": 0, "nonlatin": 1, "verbose": 2}
    scored = [(order[d], l) for l in rows
              if (d := _name_defect(l.name, parts)) is not None]
    # A39: Orte, deren Name in Ordnung ist, denen aber die Stadt fehlt. Sie
    # kommen zuletzt — ihr Name stimmt ja, es geht nur um ein Feld, das es vor
    # 0.34 nicht gab. `city IS NULL` heißt „nie nachgesehen"; der Lauf schreibt
    # danach entweder die Stadt oder den Leerstring, sodass jeder Ort genau
    # einmal dafür abgefragt wird.
    seen = {l.id for _, l in scored}
    scored += [(3, l) for l in rows if l.city is None and l.id not in seen]
    scored.sort(key=lambda t: t[0])
    return [l for _, l in scored]


# --------------------------------------------------------------------------- #
# Import-Endpoint
# --------------------------------------------------------------------------- #
@router.post("/import/timeline", response_model=TimelineImportResult)
def import_timeline(
    payload: dict = Body(...),
    auto_resolve: bool = True,
    min_probability: float = 0.0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimelineImportResult:
    """Importiert einen Google-Timeline-Export (Geräte-Export oder Takeout).

    auto_resolve=false unterdrückt das direkte Reverse-Geocoding kleiner
    Ortsmengen — das Frontend setzt es beim Etappen-Import großer Dateien
    (A2), damit nicht jede Etappe an der Nominatim-Drossel (1 req/s) hängt.

    min_probability (0..1, A12): Besuche, deren Ortszuordnung laut Google
    unsicherer ist (häufig bei „Gesuchte Adresse"), werden übersprungen.
    0 = alle importieren (Default)."""
    min_probability = max(0.0, min(min_probability, 1.0))
    visits, moves = _normalize(payload)
    moves = _annotate_paths(moves)
    invalid = (len(payload.get("semanticSegments") or []) + len(payload.get("timelineObjects") or [])
               - len(visits) - len(moves))
    skipped_lowprob = 0
    if min_probability > 0:
        kept = [v for v in visits if v["probability"] >= min_probability]
        skipped_lowprob = len(visits) - len(kept)
        visits = kept

    # Vorhandene Import-Schlüssel des Nutzers -> idempotenter Re-Import
    have_events = {x[0] for x in db.query(Event.external_id)
                   .filter(Event.user_id == user.id, Event.external_id.isnot(None)).all()}
    have_tracks = {x[0] for x in db.query(Track.external_id)
                   .filter(Track.user_id == user.id, Track.external_id.isnot(None)).all()}

    all_dates = [v["start"] for v in visits] + [m["start"] for m in moves]
    fragment = Fragment(
        user_id=user.id,
        raw_text=json.dumps({
            "type": "google_timeline_import",
            "visits": len(visits), "moves": len(moves),
            "range": [min(all_dates).isoformat(), max(all_dates).isoformat()] if all_dates else None,
        }, ensure_ascii=False),
        source=Source.google_timeline,
        status=FragmentStatus.processed,
    )
    db.add(fragment)
    db.flush()

    # Orte wiederverwenden: pro placeId bzw. gerundeter Koordinate eine Location
    loc_cache: dict[str, Location] = {}
    new_locations: list[Location] = []

    def _resolve_visit_location(v: dict) -> Location:
        lat, lng = v["latlng"]
        key = v["place_id"] or f"{lat:.4f},{lng:.4f}"
        if key in loc_cache:
            return loc_cache[key]
        existing = (db.query(Location)
                    .filter(Location.user_id == user.id, Location.external_ref == key)
                    .first())
        if existing:
            loc_cache[key] = existing
            return existing
        name = v["name"] or f"Ort ({lat:.4f}, {lng:.4f})"
        ltype = "home" if v["name"] in ("Zuhause", "Zuhause (vermutet)") else "poi"
        loc = Location(user_id=user.id, name=name, lat=lat, lng=lng,
                       type=ltype, external_ref=key)
        db.add(loc)
        db.flush()
        loc_cache[key] = loc
        new_locations.append(loc)
        return loc

    created_visits = skipped = 0
    for v in visits:
        if v["hash"] in have_events:
            skipped += 1
            continue
        have_events.add(v["hash"])
        loc = _resolve_visit_location(v)
        # Ortsnamen sind kompakt (short_name); alte lange Adressen heilt
        # die Aktion „Adressen kürzen" (scope=verbose) nachträglich mit.
        db.add(Event(
            user_id=user.id,
            title=f"Besuch: {loc.name}"[:255],
            date_start=v["start"], date_end=v["end"],
            date_precision=DatePrecision.exact,
            category="event",
            confidence=round(min(1.0, v["probability"]), 2),
            confirmed=ConfirmState.confirmed,  # Gerätedaten = Fakt, nicht moderierungspflichtig
            confirmed_at=datetime.now(timezone.utc),
            confirmed_by="import",  # Provenienz (P2.7)
            source=Source.google_timeline,
            location=loc,
            origin_fragment=fragment,
            external_id=v["hash"],
        ))
        created_visits += 1

    created_tracks = 0
    for m in moves:
        if m["hash"] in have_tracks:
            skipped += 1
            continue
        have_tracks.add(m["hash"])
        db.add(Track(
            user_id=user.id,
            date_start=m["start"], date_end=m["end"],
            points=m["points"],
            activity_type=m["activity_type"] or "unknown",
            distance_m=m["distance_m"],
            source=Source.google_timeline,
            external_id=m["hash"],
            origin_fragment_id=fragment.id,
        ))
        created_tracks += 1

    # Vorschlag 2: kleine Mengen NEUER Orte direkt reverse-geocoden — Namen
    # statt „Ort (lat, lng)" bzw. echte Adressen hinter semantischen Labels
    # (A12). Große Erstimporte laufen über den Button.
    names_resolved = 0
    unnamed_new = [l for l in new_locations
                   if l.name.startswith("Ort (") or l.name in SEMANTIC_LABELS]
    if auto_resolve and settings.geocoding_enabled and 0 < len(unnamed_new) <= AUTO_RESOLVE_MAX:
        # Neue Events erst in die DB schreiben (autoflush ist aus), sonst
        # findet die Titel-Nachführung in _apply_resolved_name sie nicht
        db.flush()
        parts = geocode_svc.parts_for(user)
        lang = geocode_svc.lang_for(user)   # F10: Ortsnamen in der UI-Sprache
        for i, loc in enumerate(unnamed_new):
            if i:
                time.sleep(_geo_delay())
            if _apply_resolved_name(db, loc, user.id, parts, lang):
                names_resolved += 1

    db.commit()
    locations_unnamed = (db.query(Location)
                         .filter(Location.user_id == user.id, _unresolved_name_filter())
                         .count())
    log.info("Timeline-Import: %d Besuche, %d Tracks, %d Dubletten übersprungen, "
             "%d unsichere Besuche gefiltert (min_probability=%.2f), "
             "%d Ortsnamen aufgelöst (%d offen)",
             created_visits, created_tracks, skipped, skipped_lowprob,
             min_probability, names_resolved, locations_unnamed)
    return TimelineImportResult(
        visits_created=created_visits,
        tracks_created=created_tracks,
        skipped_duplicates=skipped,
        skipped_invalid=max(0, invalid),
        skipped_low_probability=skipped_lowprob,
        date_min=min(all_dates) if all_dates else None,
        date_max=max(all_dates) if all_dates else None,
        names_resolved=names_resolved,
        locations_unnamed=locations_unnamed,
    )


@router.post("/import/timeline/resolve-names", response_model=PlaceNameResolveResult)
def resolve_place_names(
    limit: int = 25,
    scope: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaceNameResolveResult:
    """Löst Ortsnamen per Reverse-Geocoding auf — EIN Lauf für alles (A28).

    Kandidaten sind alle verorteten Orte mit Namensmangel, entdupliziert und
    „unnamed" zuerst: Koordinaten-Namen („Ort (lat, lng)") und semantische
    Labels ohne Adresse (A12, das Label bleibt Präfix), Fremdschrift-Namen
    (A10) und zu lange Nominatim-Adressen. Ein Ort wird dabei höchstens
    einmal geocodiert, auch wenn er mehrere Mängel hat.

    `scope` bleibt als optionaler Parameter erhalten (Werte wie früher:
    unnamed/nonlatin/verbose) — die UI bietet ihn nicht mehr an, aber
    bestehende Job-Einträge und Skripte laufen damit weiter.

    Arbeitet einen Batch (max. `limit`, gedrosselt auf 1 Anfrage/s wegen
    Nominatim-Policy) ab und meldet, wie viele Orte noch offen sind — das
    Frontend ruft so lange nach, bis nichts mehr offen ist. Fortschritt wird
    pro Ort committet.
    """
    limit = max(1, min(limit, 100))
    parts = geocode_svc.parts_for(user)
    lang = geocode_svc.lang_for(user)   # F10: Ortsnamen in der UI-Sprache

    def _candidates() -> list[Location]:
        if scope == "nonlatin":
            return _nonlatin_locations(db, user.id)
        if scope == "verbose":
            return _verbose_locations(db, user.id, parts)
        if scope == "unnamed":
            return (db.query(Location)
                    .filter(Location.user_id == user.id,
                            _unresolved_name_filter(),
                            Location.lat.isnot(None))
                    .all())
        return _resolve_candidates(db, user.id, parts)

    locs = _candidates()[:limit]
    resolved = failed = 0
    for i, loc in enumerate(locs):
        if i:
            time.sleep(_geo_delay())
        ok = _apply_resolved_name(db, loc, user.id, parts, lang)
        if ok:
            db.commit()
        # Eine Bedingung für alle Mängel (A28): hat der Name danach immer noch
        # einen, war der Aufruf kein Fortschritt — sonst liefe der Batch-Lauf
        # endlos über dieselben Orte. Deckt beides ab, was vorher zwei
        # scope-spezifische Prüfungen waren: OSM kennt keinen de/en-Namen,
        # oder addressdetails fehlen und der Name bleibt zu lang.
        if ok and _name_defect(loc.name, parts) is not None:
            ok = False
        if ok:
            resolved += 1
        else:
            failed += 1
    # Fehlschläge nicht als "offen" zählen, sonst dreht das Frontend
    # Endlosrunden über dieselben, unauflösbaren Orte.
    remaining = max(0, len(_candidates()) - failed)
    log.info("Ortsnamen-Auflösung (%s): %d aufgelöst, %d fehlgeschlagen, %d offen",
             scope or "alle", resolved, failed, remaining)
    return PlaceNameResolveResult(resolved=resolved, failed=failed, remaining=remaining)


# --------------------------------------------------------------------------- #
# Track-Abfrage (Karten-Layer)
# --------------------------------------------------------------------------- #
@router.get("/tracks", response_model=list[TrackRead])
def list_tracks(
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TrackRead]:
    """Tracks des Nutzers, optional auf einen Zeitraum eingegrenzt (Überlappung).

    `limit` (Default 1000, hart gedeckelt) schützt vor Riesen-Antworten bei
    weiten Zeiträumen — nach einem Timeline-Import liegen schnell >20k Tracks
    mit vollen Punktlisten in der DB. Neueste zuerst.
    """
    limit = max(1, min(limit, 5000))
    q = db.query(Track).filter(Track.user_id == user.id)
    if start:
        q = q.filter(Track.date_end >= start)
    if end:
        q = q.filter(Track.date_start <= end)
    rows = q.order_by(Track.date_start.desc()).limit(limit).all()
    return [TrackRead.model_validate(t) for t in reversed(rows)]
