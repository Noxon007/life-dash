"""Moderations-Endpoints: unbestätigte Stufe-2-Einträge prüfen."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Query as OrmQuery, Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ConfirmState, Event, EventEntityLink, User
from app.routers._serialize import event_to_read
from app.schemas import (
    BulkConfirmFilter,
    BulkConfirmPreview,
    BulkConfirmResult,
    EventRead,
    EventUpdate,
)

router = APIRouter(prefix="/api/moderation", tags=["Moderation"])


def mark_confirmed(event: Event, by: str) -> None:
    """Übergang Vorschlagsraum -> Lebensdatenbank inkl. Provenienz (P2.7).

    by: "manual" | "bulk" | "import". Bei bereits bestätigten Events bleibt
    die ursprüngliche Provenienz stehen (erneutes Bestätigen/Bearbeiten
    verfälscht nicht, wann etwas zur Wahrheit wurde)."""
    if event.confirmed != ConfirmState.confirmed:
        event.confirmed_at = datetime.now(timezone.utc)
        event.confirmed_by = by
    event.confirmed = ConfirmState.confirmed


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
    mark_confirmed(event, "manual")
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
    # Ändern sich die Fakten Zeit/Ort, stimmt angehängtes Wetter nicht mehr
    facts_changed = bool({"location_name", "date_start", "date_end"} & data.keys())

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

    # Objekte separat behandeln: Verknüpfungen vollständig ersetzen
    # (Umbenennen = alte Entity abhängen, neue auflösen/anlegen)
    if "entities" in data:
        from app.services.ingestion import _resolve_entity

        wanted = data.pop("entities") or []
        old_entities = [link.entity for link in event.entity_links]
        event.entity_links.clear()  # delete-orphan räumt die Link-Zeilen ab
        db.flush()
        for ent in wanted:
            entity = _resolve_entity(
                db, ent["type"], ent["name"].strip(), ent.get("attributes") or {}, user.id
            )
            entity.confirmed = ConfirmState.confirmed
            db.add(EventEntityLink(event_id=event.id, entity_id=entity.id, role="subject"))
        db.flush()
        # Entities ohne verbleibende Events aufräumen (sonst Karteileichen im Kompendium)
        for entity in old_entities:
            still_linked = (
                db.query(EventEntityLink).filter_by(entity_id=entity.id).count() > 0
            )
            if not still_linked:
                db.delete(entity)
        overrides["entities"] = True

    for key, value in data.items():
        setattr(event, key, value)
        overrides[key] = True

    event.field_overrides = overrides
    mark_confirmed(event, "manual")
    _confirm_linked_entities(event)

    # Der NUTZER hat Zeit/Ort korrigiert -> Wetter folgt den neuen Fakten
    # (keine Maschinen-Änderung an Bestätigtem; vgl. KONZEPT Kap. 3.1).
    if facts_changed:
        from app.models import Source
        from app.services.enrichment import auto_enrich_events

        for m in [m for m in event.metrics if m.source == Source.weather]:
            event.metrics.remove(m)  # delete-orphan räumt die Zeile ab
        db.flush()
        auto_enrich_events(db, [event])

    db.commit()
    db.refresh(event)
    return event_to_read(event)


# --------------------------------------------------------------------------- #
# P2.5 — Bulk-Bestätigen: viele korrekte KI-Vorschläge auf einmal in die
# Lebensdatenbank übernehmen. Immer zweistufig: erst Vorschau, dann Bestätigen
# (beide Endpoints nutzen exakt dieselbe Filter-Query).
# --------------------------------------------------------------------------- #
BULK_PREVIEW_LIMIT = 50


def _bulk_query(db: Session, user: User, f: BulkConfirmFilter) -> OrmQuery:
    query = db.query(Event).filter(
        Event.user_id == user.id, Event.confirmed == ConfirmState.unconfirmed
    )
    if f.category:
        query = query.filter(Event.category == f.category)
    if f.source:
        query = query.filter(Event.source == f.source)
    if f.min_confidence > 0:
        query = query.filter(Event.confidence >= f.min_confidence)
    # Zeitraumfilter greift auf die Ereignis-Zeit; Events ohne Datum fallen
    # dann bewusst raus (die sollen einzeln moderiert werden).
    if f.date_from:
        query = query.filter(Event.date_start >= f.date_from)
    if f.date_to:
        query = query.filter(Event.date_start <= f.date_to)
    return query


@router.post("/bulk-confirm/preview", response_model=BulkConfirmPreview)
def bulk_confirm_preview(
    payload: BulkConfirmFilter,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BulkConfirmPreview:
    """Zeigt, welche Events ein Bulk-Bestätigen mit diesen Filtern träfe."""
    query = _bulk_query(db, user, payload)
    total = query.count()
    sample = query.order_by(Event.created_at.desc()).limit(BULK_PREVIEW_LIMIT).all()
    return BulkConfirmPreview(total=total, events=[event_to_read(e) for e in sample])


@router.post("/bulk-confirm", response_model=BulkConfirmResult)
def bulk_confirm(
    payload: BulkConfirmFilter,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BulkConfirmResult:
    """Bestätigt alle Events, die den Filtern entsprechen (Provenienz: bulk)."""
    events = _bulk_query(db, user, payload).all()
    for event in events:
        mark_confirmed(event, "bulk")
        _confirm_linked_entities(event)
    db.commit()
    return BulkConfirmResult(confirmed=len(events))


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
