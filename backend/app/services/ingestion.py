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
from datetime import datetime, timezone

from sqlalchemy.orm import Session


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

from app.ai import get_provider
from app.ai.base import ExtractedEvent, ProviderUnavailable

log = logging.getLogger("lifedash.ingestion")
from app.config import settings
from app.services.geocode import geocode, parts_for, reverse_geocode, short_name
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
    User,
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
        extracted = provider.extract(fragment.raw_text,
                                     tracked_modules(db, fragment.user_id))
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
        # F2: Nennt der Text KEINEN Ort, aber der Nutzer hat seinen
        # Gerätestandort mitgegeben, wird der zum Ortsvorschlag
        # (Text hat immer Vorrang; Roh-Koordinaten liegen im Fragment).
        if (event.location_id is None and event.location is None
                and fragment.capture_lat is not None
                and fragment.capture_lng is not None):
            event.location = _location_from_capture(db, fragment)
        if event.confidence < settings.confidence_review_threshold:
            needs_review = True
        events.append(event)

    fragment.status = (
        FragmentStatus.needs_review if needs_review else FragmentStatus.processed
    )
    db.flush()
    return events


# Import-Fragmente (Timeline/Fitness) enthalten nur Zusammenfassungen — eine
# KI-Extraktion darüber würde Unsinn erzeugen. Nur Text-Quellen neu berechnen.
_TEXT_SOURCES = (Source.manual, Source.ai, Source.api)


def reset_reprocess(db: Session) -> int:
    """Markiert alle neu zu berechnenden Fragmente (status -> pending).

    Fragmente mit mindestens einem bestätigten Event bleiben unangetastet
    (moderierte Wahrheit wird geschützt); ihre unbestätigten Geschwister-Events
    ebenso. Bei den übrigen werden die alten (unbestätigten) Events verworfen.
    Gibt die Anzahl der zu verarbeitenden Fragmente zurück.
    """
    count = 0
    for fragment in db.query(Fragment).filter(
        Fragment.source.in_(_TEXT_SOURCES),
        Fragment.status != FragmentStatus.discarded,
    ).all():
        if any(e.confirmed == ConfirmState.confirmed for e in fragment.events):
            continue
        for event in list(fragment.events):
            db.delete(event)
        fragment.status = FragmentStatus.pending
        count += 1
    db.commit()
    return count


def reprocess_pending(db: Session, limit: int = 5) -> tuple[int, int, bool]:
    """Verarbeitet bis zu `limit` pending-Fragmente neu (Batch für das Admin-UI).

    Gibt (verarbeitet, verbleibend, abgebrochen) zurück. Ist der KI-Provider
    nicht erreichbar (z. B. Quota erschöpft), bricht der Batch ab: bereits
    Berechnetes bleibt (Commit je Fragment), das aktuelle behält den Altbestand.
    """
    pending = (db.query(Fragment)
               .filter(Fragment.source.in_(_TEXT_SOURCES),
                       Fragment.status == FragmentStatus.pending)
               .order_by(Fragment.created_at)
               .limit(limit).all())
    count, aborted = 0, False
    for fragment in pending:
        try:
            ingest_fragment(db, fragment, fallback_on_error=False)
        except ProviderUnavailable as err:
            db.rollback()
            log.warning("Neuberechnung nach %d Fragmenten abgebrochen: %s", count, err)
            aborted = True
            break
        db.commit()
        count += 1
    remaining = (db.query(Fragment)
                 .filter(Fragment.source.in_(_TEXT_SOURCES),
                         Fragment.status == FragmentStatus.pending)
                 .count())
    return count, remaining, aborted


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
        confirmed_at=_utcnow(),
        confirmed_by="manual",  # Provenienz (P2.7): der Nutzer IST die Quelle
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


def _location_from_capture(db: Session, fragment: Fragment) -> Location | None:
    """F2: Gerätestandort -> Location (Reverse-Geocoding im Anzeige-Format;
    ohne Treffer bleibt ein Koordinaten-Name, den „Ortsnamen auflösen" später
    nachzieht)."""
    lat, lng = fragment.capture_lat, fragment.capture_lng
    name, ltype, country = f"Ort ({lat:.4f}, {lng:.4f})", None, None
    if settings.geocoding_enabled:
        hit = reverse_geocode(lat, lng)
        if hit:
            user = db.get(User, fragment.user_id) if fragment.user_id else None
            name = short_name(hit, parts_for(user)) or name
            ltype = hit.get("type")
            country = (hit.get("address") or {}).get("country")
    existing = (db.query(Location)
                .filter(Location.user_id == fragment.user_id,
                        Location.name.ilike(name))
                .first())
    if existing:
        return existing
    location = Location(user_id=fragment.user_id, name=name[:255], lat=lat,
                        lng=lng, type=ltype, country=country)
    db.add(location)
    db.flush()
    return location


def tracked_modules(db: Session, user_id: str | None) -> list[str] | None:
    """A15: Gewählte Module des Nutzers (None = alle — Standard)."""
    user = db.get(User, user_id) if user_id else None
    tracked = ((user.settings or {}).get("tracked_modules")) if user else None
    return tracked if isinstance(tracked, list) else None


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
    geo = None
    # Präzise Adresse per Geocoding auflösen (bis Straße/Hausnummer)
    if settings.geocoding_enabled:
        geo = geocode(ex.location_name)
        if geo:
            lat, lng, ltype = geo["lat"], geo["lng"], geo.get("type")
            # Kompakter Anzeige-Name aus den gewählten Bausteinen statt der
            # vollen Nominatim-Adresse mit Verwaltungskette
            user = db.get(User, user_id) if user_id else None
            name = short_name(geo, parts_for(user)) or geo["name"]

    country = (geo.get("address") or {}).get("country") if geo else None
    location = Location(user_id=user_id, name=name, lat=lat, lng=lng, type=ltype,
                        country=country)
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
