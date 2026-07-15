"""Ingestion-Pipeline: Fragment (Stufe 1) -> Events/Entities (Stufe 2).

Ablauf:
1. Roh-Fragment speichern (unveränderlich)
2. KI-Extraktion (Provider)
3. Location auflösen/anlegen
4. Events + Entities + Verknüpfungen anlegen (unconfirmed)
5. Review-Gate über Confidence-Schwelle
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.ai import get_provider
from app.ai.base import ExtractedEvent, ProviderUnavailable

log = logging.getLogger("lifedash.ingestion")
from app.config import settings
from app.services.geocode import geocode
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
)


def ingest_fragment(
    db: Session, fragment: Fragment, fallback_on_error: bool = True
) -> list[Event]:
    """Verarbeitet ein bereits gespeichertes Fragment und erzeugt Stufe-2-Events.

    Alle erzeugten Zeilen erben die user_id des Fragments (Mandanten-Trennung).
    fallback_on_error: Bei nicht erreichbarem KI-Provider ein Roh-Event mit
    niedriger Confidence anlegen (Einzel-Ingest, Capture first). Die
    Batch-Neuberechnung setzt False und behandelt den Fehler selbst.
    """
    provider = get_provider()
    try:
        extracted = provider.extract(fragment.raw_text)
    except ProviderUnavailable as err:
        if not fallback_on_error:
            raise
        extracted = [
            ExtractedEvent(
                title=fragment.raw_text[:80],
                description=f"{fragment.raw_text}\n[KI nicht erreichbar: {err}]",
                confidence=0.2,
            )
        ]

    events: list[Event] = []
    needs_review = False

    for ex in extracted:
        event = _build_event(db, ex, fragment, provider)
        if event.confidence < settings.confidence_review_threshold:
            needs_review = True
        events.append(event)

    fragment.status = (
        FragmentStatus.needs_review if needs_review else FragmentStatus.processed
    )
    db.flush()
    return events


def reprocess_all(db: Session) -> int:
    """Berechnet Stufe 2 neu aus den Roh-Fragmenten (Stufe 1).

    Fragmente mit mindestens einem bestätigten Event bleiben unangetastet
    (moderierte Wahrheit wird geschützt). Alle übrigen werden verworfen und
    mit dem aktuellen Provider/Geocoding neu erzeugt.

    Ist der KI-Provider nicht erreichbar (z. B. Tages-Quota erschöpft),
    bricht der Batch ab: bereits neu berechnete Fragmente bleiben (Commit je
    Fragment), das aktuelle behält seinen Altbestand (Rollback).
    """
    count = 0
    for fragment in db.query(Fragment).all():
        has_confirmed = any(
            e.confirmed == ConfirmState.confirmed for e in fragment.events
        )
        if has_confirmed:
            continue
        try:
            for event in list(fragment.events):
                db.delete(event)
            db.flush()
            ingest_fragment(db, fragment, fallback_on_error=False)
        except ProviderUnavailable as err:
            db.rollback()
            log.warning("Neuberechnung nach %d Fragmenten abgebrochen: %s", count, err)
            break
        db.commit()
        count += 1
    return count


def create_manual_event(db: Session, user_id: str, payload) -> Event:
    """Legt ein manuell erfasstes Event an (payload: EventManualCreate).

    Auch hier gilt Capture first: Die Roheingabe wird als Fragment (Stufe 1)
    gesichert. Das Event ist sofort `confirmed` — der Nutzer IST die Quelle.
    Alle Felder sind als override markiert, damit kein Re-Processing sie anfasst.
    """
    import json as _json

    fragment = Fragment(
        user_id=user_id,
        raw_text=_json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
        source=Source.manual,
        status=FragmentStatus.processed,
    )
    db.add(fragment)
    db.flush()

    pseudo = ExtractedEvent(title=payload.title, location_name=payload.location_name)
    location = _resolve_location(db, pseudo, user_id)

    provider = get_provider()
    event = Event(
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        date_start=payload.date_start,
        date_end=payload.date_end,
        date_precision=payload.date_precision,
        category=payload.category,
        confidence=1.0,
        confirmed=ConfirmState.confirmed,
        field_overrides={f: True for f in ("title", "description", "date_start",
                                           "date_end", "date_precision", "category")},
        source=Source.manual,
        location=location,
        origin_fragment=fragment,
        embedding=provider.embed(f"{payload.title}\n{payload.description or ''}"),
    )
    db.add(event)
    db.flush()

    for ent in payload.entities:
        entity = _resolve_entity(db, ent.type, ent.name, ent.attributes, user_id)
        entity.confirmed = ConfirmState.confirmed
        db.add(EventEntityLink(event_id=event.id, entity_id=entity.id, role="subject"))

    db.flush()
    return event


def _build_event(db: Session, ex: ExtractedEvent, fragment: Fragment, provider) -> Event:
    location = _resolve_location(db, ex, fragment.user_id)

    event = Event(
        user_id=fragment.user_id,
        title=ex.title,
        description=ex.description,
        date_start=ex.date_start,
        date_end=ex.date_end,
        date_precision=DatePrecision(ex.date_precision),
        category=ex.category,
        confidence=ex.confidence,
        confirmed=ConfirmState.unconfirmed,
        source=Source.ai,
        location=location,
        origin_fragment=fragment,
        embedding=provider.embed(f"{ex.title}\n{ex.description or ''}"),
    )
    db.add(event)
    db.flush()

    for ent in ex.entities:
        entity = _resolve_entity(db, ent.type, ent.name, ent.attributes, fragment.user_id)
        db.add(EventEntityLink(event_id=event.id, entity_id=entity.id, role="subject"))

    db.flush()
    return event


def _resolve_location(db: Session, ex: ExtractedEvent, user_id: str | None) -> Location | None:
    if not ex.location_name:
        return None
    existing = (
        db.query(Location)
        .filter(Location.user_id == user_id, Location.name.ilike(ex.location_name))
        .first()
    )
    if existing:
        return existing

    lat, lng, ltype, name = ex.location_lat, ex.location_lng, None, ex.location_name
    # Präzise Adresse per Geocoding auflösen (bis Straße/Hausnummer)
    if settings.geocoding_enabled:
        geo = geocode(ex.location_name)
        if geo:
            lat, lng, ltype = geo["lat"], geo["lng"], geo.get("type")
            name = geo["name"]  # vollständige Adresse aus Nominatim

    location = Location(user_id=user_id, name=name, lat=lat, lng=lng, type=ltype)
    db.add(location)
    db.flush()
    return location


def _resolve_entity(
    db: Session, type_: str, name: str, attributes: dict, user_id: str | None
) -> Entity:
    """Einfache Entity-Resolution: gleicher Typ + Name (case-insensitive), pro Nutzer."""
    existing = (
        db.query(Entity)
        .filter(Entity.user_id == user_id, Entity.type == type_, Entity.name.ilike(name))
        .first()
    )
    if existing:
        return existing
    entity = Entity(
        user_id=user_id,
        type=type_,
        name=name,
        attributes=attributes or {},
        confirmed=ConfirmState.unconfirmed,
    )
    db.add(entity)
    db.flush()
    return entity
