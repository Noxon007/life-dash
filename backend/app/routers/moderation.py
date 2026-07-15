"""Moderations-Endpoints: unbestätigte Stufe-2-Einträge prüfen."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ConfirmState, Event, User
from app.routers._serialize import event_to_read
from app.schemas import EventRead, EventUpdate

router = APIRouter(prefix="/api/moderation", tags=["Moderation"])


@router.get("/queue", response_model=list[EventRead])
def moderation_queue(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[EventRead]:
    """Alle eigenen unbestätigten Events (Moderations-Warteschlange)."""
    events = (
        db.query(Event)
        .filter(Event.user_id == user.id, Event.confirmed == ConfirmState.unconfirmed)
        .order_by(Event.created_at.desc())
        .all()
    )
    return [event_to_read(e) for e in events]


def _get_event(db: Session, event_id: str, user: User) -> Event:
    event = db.get(Event, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="Event nicht gefunden")
    return event


def _confirm_linked_entities(event: Event) -> None:
    """Bestätigt die mit dem Event verknüpften Entities mit.

    Wer das Event moderiert hat, hat auch dessen Objekte (Tier, Land, ...)
    gesehen — sonst blieben Kompendium-Einträge ewig 'unbestätigt'."""
    for link in event.entity_links:
        link.entity.confirmed = ConfirmState.confirmed


@router.post("/{event_id}/confirm", response_model=EventRead)
def confirm_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventRead:
    """Bestätigt ein Event (Stufe 2: unconfirmed -> confirmed) inkl. verknüpfter Entities."""
    event = _get_event(db, event_id, user)
    event.confirmed = ConfirmState.confirmed
    _confirm_linked_entities(event)
    db.commit()
    db.refresh(event)
    return event_to_read(event)


@router.patch("/{event_id}", response_model=EventRead)
def correct_event(
    event_id: str,
    payload: EventUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventRead:
    """Korrigiert Felder eines Events. Geänderte Felder werden als override markiert
    und damit vor einer späteren KI-Neuberechnung geschützt."""
    event = _get_event(db, event_id, user)
    overrides = dict(event.field_overrides or {})

    data = payload.model_dump(exclude_unset=True)

    # Ort separat behandeln: Name/Adresse -> Geocoding -> Location-Zeile
    if "location_name" in data:
        from app.ai.base import ExtractedEvent
        from app.services.ingestion import _resolve_location

        name = (data.pop("location_name") or "").strip()
        event.location = (
            _resolve_location(db, ExtractedEvent(title=event.title, location_name=name), user.id)
            if name else None
        )
        overrides["location"] = True

    for key, value in data.items():
        setattr(event, key, value)
        overrides[key] = True

    event.field_overrides = overrides
    event.confirmed = ConfirmState.confirmed
    _confirm_linked_entities(event)
    db.commit()
    db.refresh(event)
    return event_to_read(event)


@router.delete("/{event_id}", status_code=204, response_model=None)
def discard_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Verwirft ein Event (löscht die Stufe-2-Ableitung; Fragment bleibt erhalten)."""
    event = _get_event(db, event_id, user)
    db.delete(event)
    db.commit()
