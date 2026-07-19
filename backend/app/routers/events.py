"""Event-Read-Endpoints (Stufe-3-Ansichten: Timeline & Karte)."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import ConfirmState, DatePrecision, Event, EventEntityLink, User
from app.routers._serialize import event_to_read
from app.schemas import EventManualCreate, EventRead
from app.services.ingestion import create_manual_event

router = APIRouter(prefix="/api/events", tags=["Events"])

# Verknüpfungen in wenigen Sammel-Queries vorladen statt lazy pro Event
# (bei 10k+ importierten Events wird das N+1-Lazy-Loading sonst zur Bremse)
_EAGER = (
    selectinload(Event.entity_links).selectinload(EventEntityLink.entity),
    selectinload(Event.metrics),
    selectinload(Event.location),
)


@router.post("", response_model=EventRead, status_code=201)
def create_event(
    payload: EventManualCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventRead:
    """Manuell erfasstes Event (ohne KI) — sofort bestätigt."""
    from app.services.enrichment import auto_enrich_events

    event = create_manual_event(db, user.id, payload)
    auto_enrich_events(db, [event])  # P2.4: Wetter direkt ergänzen
    db.commit()
    db.refresh(event)
    return event_to_read(event)


# F7: Aus einem Mehrtages-Event Tages-Unterereignisse erzeugen. Kinder sind
# normale Lebensdatenbank-Events (erben Ort, Kategorie und Bestätigung),
# nur mit parent_event_id als Herkunftsverweis. Idempotent: Tage, die schon
# ein Kind haben, werden übersprungen — der Knopf füllt nur Lücken auf.
MAX_DAY_CHILDREN = 366


@router.post("/{event_id}/days", response_model=list[EventRead], status_code=201)
def create_day_children(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EventRead]:
    """Legt für jeden Tag der Event-Spanne ein Tages-Kind an („… — Tag 3")."""
    from app.services.enrichment import auto_enrich_events

    parent = db.get(Event, event_id)
    if parent is None or parent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Event nicht gefunden")
    if parent.parent_event_id:
        raise HTTPException(status_code=400,
                            detail="Tages-Einträge können keine eigenen Tages-Einträge bekommen")
    if not parent.date_start or not parent.date_end:
        raise HTTPException(status_code=400, detail="Das Event braucht ein Von- und Bis-Datum")
    first = parent.date_start.date()
    last = parent.date_end.date()
    span = (last - first).days + 1
    if span < 2:
        raise HTTPException(status_code=400,
                            detail="Tages-Einträge gibt es nur für mehrtägige Events")
    if span > MAX_DAY_CHILDREN:
        raise HTTPException(status_code=400,
                            detail=f"Spanne zu groß (max. {MAX_DAY_CHILDREN} Tage)")

    have = {c.date_start.date() for c in parent.children if c.date_start}
    confirmed = parent.confirmed == ConfirmState.confirmed
    created: list[Event] = []
    for offset in range(span):
        day = first + timedelta(days=offset)
        if day in have:
            continue
        start = datetime(day.year, day.month, day.day)
        child = Event(
            user_id=user.id,
            title=f"{parent.title} — Tag {offset + 1}",
            date_start=start,
            date_end=start,
            date_precision=DatePrecision.day,
            category=parent.category,
            confidence=1.0,
            confirmed=parent.confirmed,
            confirmed_at=parent.confirmed_at if confirmed else None,
            confirmed_by=parent.confirmed_by if confirmed else None,
            source=parent.source,
            location_id=parent.location_id,
            parent_event_id=parent.id,
        )
        db.add(child)
        created.append(child)
    db.flush()
    # Anreicherung (Wetter) hängt an den Kindern = pro Tag (Kern von F7)
    auto_enrich_events(db, created)
    db.commit()
    for c in created:
        db.refresh(c)
    return [event_to_read(c) for c in created]


@router.get("", response_model=list[EventRead])
def list_events(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    category: str | None = Query(None, description="Nach Kategorie filtern"),
    confirmed_only: bool = Query(False, description="Nur bestätigte Events"),
    q: str | None = Query(None, description="Volltextsuche in Titel/Beschreibung"),
) -> list[EventRead]:
    """Liste der eigenen Events, optional gefiltert (für Timeline & Karte)."""
    query = db.query(Event).options(*_EAGER).filter(Event.user_id == user.id)
    if category:
        query = query.filter(Event.category == category)
    if confirmed_only:
        from app.models import ConfirmState

        query = query.filter(Event.confirmed == ConfirmState.confirmed)
    if q:
        like = f"%{q}%"
        query = query.filter(Event.title.ilike(like) | Event.description.ilike(like))

    events = query.order_by(Event.date_start.desc().nullslast()).all()
    return [event_to_read(e) for e in events]


@router.get("/map", response_model=list[EventRead])
def list_map_events(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[EventRead]:
    """Nur verortete eigene Events (mit Koordinaten) — für die Karte."""
    events = (db.query(Event).options(*_EAGER)
              .filter(Event.user_id == user.id).join(Event.location).all())
    result = [event_to_read(e) for e in events if e.location and e.location.lat is not None]
    return result
