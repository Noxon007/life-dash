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
from datetime import datetime

from dateutil import parser as dateparser
from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    ConfirmState,
    DatePrecision,
    Event,
    Fragment,
    FragmentStatus,
    Location,
    Source,
    Track,
    User,
)
from app.schemas import TimelineImportResult, TrackRead

log = logging.getLogger("lifedash.timeline")

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

# semanticType -> deutscher Ortsname (Geräte-Export kennt keine Ortsnamen)
_SEMANTIC_NAMES = {
    "home": "Zuhause", "inferred home": "Zuhause (vermutet)",
    "work": "Arbeit", "inferred work": "Arbeit (vermutet)",
    "searched address": "Gesuchte Adresse", "aliased location": "Gespeicherter Ort",
}

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


# --------------------------------------------------------------------------- #
# Import-Endpoint
# --------------------------------------------------------------------------- #
@router.post("/import/timeline", response_model=TimelineImportResult)
def import_timeline(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimelineImportResult:
    """Importiert einen Google-Timeline-Export (Geräte-Export oder Takeout)."""
    visits, moves = _normalize(payload)
    moves = _annotate_paths(moves)
    invalid = (len(payload.get("semanticSegments") or []) + len(payload.get("timelineObjects") or [])
               - len(visits) - len(moves))

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
        return loc

    created_visits = skipped = 0
    for v in visits:
        if v["hash"] in have_events:
            skipped += 1
            continue
        have_events.add(v["hash"])
        loc = _resolve_visit_location(v)
        # Lange Adressen aufs erste Segment kürzen — Koordinaten-Namen ganz lassen
        short = loc.name if loc.name.startswith("Ort (") else loc.name.split(",")[0]
        db.add(Event(
            user_id=user.id,
            title=f"Besuch: {short}",
            date_start=v["start"], date_end=v["end"],
            date_precision=DatePrecision.exact,
            category="event",
            confidence=round(min(1.0, v["probability"]), 2),
            confirmed=ConfirmState.confirmed,  # Gerätedaten = Fakt, nicht moderierungspflichtig
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

    db.commit()
    log.info("Timeline-Import: %d Besuche, %d Tracks, %d Dubletten übersprungen",
             created_visits, created_tracks, skipped)
    return TimelineImportResult(
        visits_created=created_visits,
        tracks_created=created_tracks,
        skipped_duplicates=skipped,
        skipped_invalid=max(0, invalid),
        date_min=min(all_dates) if all_dates else None,
        date_max=max(all_dates) if all_dates else None,
    )


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
