"""Modul- & Kompendium-Endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Entity, Event, EventEntityLink, User
from app.modules.registry import registry
from app.routers._serialize import event_to_read
from app.schemas import EntityRead, EventRead, ModuleRead

router = APIRouter(prefix="/api", tags=["Module & Kompendium"])


@router.get("/modules", response_model=list[ModuleRead])
def list_modules() -> list[ModuleRead]:
    """Alle registrierten Trackable-Module (aus YAML geladen)."""
    return [
        ModuleRead(
            key=m.key,
            label=m.label,
            icon=m.icon,
            event_categories=m.event_categories,
        )
        for m in registry.modules
    ]


@router.get("/compendium/{type}", response_model=list[EntityRead])
def compendium(
    type: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EntityRead]:
    """Eigene Entities eines Typs (z. B. 'animal', 'country') fürs Kompendium."""
    rows = (
        db.query(Entity, func.count(EventEntityLink.id))
        .outerjoin(EventEntityLink, EventEntityLink.entity_id == Entity.id)
        .filter(Entity.user_id == user.id, Entity.type == type)
        .group_by(Entity.id)
        .order_by(Entity.name)
        .all()
    )
    out = []
    for entity, count in rows:
        item = EntityRead.model_validate(entity)
        item.event_count = count
        out.append(item)
    return out


@router.post("/entities/{entity_id}/describe", response_model=EntityRead)
def describe_entity(
    entity_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EntityRead:
    """Holt eine Kurzbeschreibung aus der deutschen Wikipedia und speichert sie
    in Entity.attributes (description, wiki_url, thumbnail). Lazy vom
    Kompendium aufgerufen, wenn noch keine Beschreibung vorhanden ist."""
    from app.services.wikipedia import fetch_summary

    entity = db.get(Entity, entity_id)
    if entity is None or entity.user_id != user.id:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")

    attrs = dict(entity.attributes or {})
    if force or not attrs.get("description"):
        info = fetch_summary(entity.name, entity.type)
        # Nur speichern, wenn wirklich etwas gefunden wurde — bei Fehlschlag
        # (z. B. Wikipedia-Drosselung) wird beim nächsten Öffnen neu versucht.
        if info:
            attrs.update({k: v for k, v in info.items() if v})
            entity.attributes = attrs
            db.commit()
            db.refresh(entity)
    return EntityRead.model_validate(entity)


@router.get("/entities/{entity_id}/events", response_model=list[EventRead])
def entity_events(
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EventRead]:
    """Alle eigenen Events, die mit dieser Entity verknüpft sind —
    für die Kompendium-Detailansicht (z. B. alle Fuchs-Sichtungen)."""
    entity = db.get(Entity, entity_id)
    if entity is None or entity.user_id != user.id:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    events = (
        db.query(Event)
        .join(EventEntityLink, EventEntityLink.event_id == Event.id)
        .filter(EventEntityLink.entity_id == entity_id, Event.user_id == user.id)
        .order_by(Event.date_start.desc().nullslast())
        .all()
    )
    return [event_to_read(e) for e in events]
