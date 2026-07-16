"""Event-Read-Endpoints (Stufe-3-Ansichten: Timeline & Karte)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, EventEntityLink, User
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
