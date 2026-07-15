"""Daten-Export & -Import (Datenkontrolle, siehe Konzept Kap. 12).

Export: alle eigenen Daten (Stufe 1–3) als ein JSON-Dokument.
Import: dasselbe Format zurückspielen — idempotent (vorhandene IDs werden
übersprungen), alles landet beim angemeldeten Nutzer. Funktioniert damit
als Backup/Restore und für Umzüge zwischen Instanzen.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dateutil import parser as dateparser
from fastapi import APIRouter, Body, Depends
from sqlalchemy import DateTime
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Entity,
    Event,
    EventEntityLink,
    Fragment,
    Location,
    MediaRef,
    Metric,
    Track,
    User,
)

router = APIRouter(prefix="/api/data", tags=["Export & Import"])

EXPORT_VERSION = 1


def _row_to_dict(obj) -> dict:
    """ORM-Zeile -> JSON-fähiges Dict (Datetimes als ISO-Strings)."""
    out: dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, "value"):  # Enum
            val = val.value
        out[col.name] = val
    return out


def _dict_to_kwargs(model, data: dict) -> dict:
    """JSON-Dict -> Spalten-Werte (ISO-Strings zurück zu Datetimes)."""
    kwargs: dict[str, Any] = {}
    for col in model.__table__.columns:
        if col.name not in data:
            continue
        val = data[col.name]
        if val is not None and isinstance(col.type, DateTime):
            val = dateparser.parse(str(val))
        kwargs[col.name] = val
    return kwargs


@router.get("/export")
def export_data(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """Vollständiger Export der eigenen Daten (Stufe 1–3) als JSON."""
    fragments = db.query(Fragment).filter(Fragment.user_id == user.id).all()
    locations = db.query(Location).filter(Location.user_id == user.id).all()
    entities = db.query(Entity).filter(Entity.user_id == user.id).all()
    events = db.query(Event).filter(Event.user_id == user.id).all()
    tracks = db.query(Track).filter(Track.user_id == user.id).all()
    event_ids = {e.id for e in events}
    links = [
        l for l in db.query(EventEntityLink).all() if l.event_id in event_ids
    ]
    media = [m for m in db.query(MediaRef).all() if m.event_id in event_ids]
    metrics = [m for m in db.query(Metric).all() if m.event_id in event_ids]

    return {
        "format": "lifedash-export",
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "fragments": [_row_to_dict(x) for x in fragments],
        "locations": [_row_to_dict(x) for x in locations],
        "entities": [_row_to_dict(x) for x in entities],
        "events": [_row_to_dict(x) for x in events],
        "event_entity_links": [_row_to_dict(x) for x in links],
        "media_refs": [_row_to_dict(x) for x in media],
        "metrics": [_row_to_dict(x) for x in metrics],
        "tracks": [_row_to_dict(x) for x in tracks],
    }


@router.post("/import")
def import_data(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Spielt einen Life-Dash-Export zurück. Vorhandene IDs werden übersprungen
    (idempotent); alle importierten Zeilen gehören dem angemeldeten Nutzer."""
    if payload.get("format") != "lifedash-export":
        return {"error": "Kein Life-Dash-Export (format-Feld fehlt/falsch)"}

    # Reihenfolge beachtet Fremdschlüssel (Eltern zuerst)
    plan = [
        ("locations", Location, True),
        ("fragments", Fragment, True),
        ("entities", Entity, True),
        ("events", Event, True),
        ("event_entity_links", EventEntityLink, False),
        ("media_refs", MediaRef, False),
        ("metrics", Metric, False),
        ("tracks", Track, True),
    ]
    imported: dict[str, int] = {}
    skipped = 0
    for key, model, has_user in plan:
        count = 0
        for row in payload.get(key, []):
            if not row.get("id") or db.get(model, row["id"]) is not None:
                skipped += 1
                continue
            kwargs = _dict_to_kwargs(model, row)
            if has_user:
                kwargs["user_id"] = user.id
            db.add(model(**kwargs))
            count += 1
        db.flush()
        imported[key] = count
    db.commit()
    return {"imported": imported, "skipped_existing": skipped,
            "total": sum(imported.values())}
