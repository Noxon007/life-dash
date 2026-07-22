"""Modul- & Kompendium-Endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Entity, Event, EventEntityLink, Location, User
from app.modules.registry import registry
from app.routers._serialize import event_to_read
from app.schemas import CityRead, EntityRead, EventRead, ModuleRead

router = APIRouter(prefix="/api", tags=["Module & Kompendium"])


@router.get("/modules", response_model=list[ModuleRead])
def list_modules() -> list[ModuleRead]:
    """Alle registrierten Trackable-Module (aus YAML geladen)."""
    return [
        ModuleRead(
            key=m.key,
            label=m.label,
            icon=m.icon,
            color=m.color,
            emoji=m.emoji,
            compendium=m.compendium,
            category_labels=m.category_labels or {},
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


@router.get("/cities", response_model=list[CityRead])
def cities(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CityRead]:
    """A41: Die besuchten Städte als Kompendium-Tab.

    Städte sind KEINE `Entity` — sie stehen als `Location.city` (A39) und
    werden hier aggregiert statt gespiegelt. Eine zweite Wahrheit für dieselbe
    Tatsache wäre teurer als diese Abfrage: die Stadt kommt aus dem
    Ortsnamen-Lauf und ändert sich, wenn er sie korrigiert.

    Warum es Städte gibt und Orte nicht (Anmerkung 95): ein Kompendium
    beantwortet „welche habe ich?" und setzt damit eine Menge mit Horizont
    voraus. Ein Leben hat vielleicht 100–300 Städte; Orte sind ein
    Koordinaten-Index, der mit jedem Import um hunderte wächst — dafür ist die
    Karte da.

    Der Leerstring bedeutet „nachgesehen, keine Stadt" (A39) und ist keine
    Stadt — er fällt hier genauso weg wie NULL.
    """
    rows = (db.query(Location.city,
                     func.min(Location.country),
                     func.count(Event.id),
                     func.count(func.distinct(Location.id)),
                     func.min(Event.date_start),
                     func.max(Event.date_start))
            .join(Event, Event.location_id == Location.id)
            .filter(Location.user_id == user.id,
                    Event.user_id == user.id,
                    Location.city.isnot(None), Location.city != "")
            .group_by(Location.city)
            .order_by(Location.city)
            .all())
    return [CityRead(name=name, country=country, event_count=events,
                     place_count=places, first_visit=first, last_visit=last)
            for name, country, events, places, first, last in rows]


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
