"""Event-Read-Endpoints (Stufe-3-Ansichten: Timeline & Karte)."""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import (ConfirmState, DatePrecision, Event, EventEntityLink,
                        Metric, Source, User)
from app.routers._serialize import event_to_read
from app.schemas import EventManualCreate, EventRead, OnThisDayGroup
from app.services.ingestion import create_manual_event

router = APIRouter(prefix="/api/events", tags=["Events"])

# Verknüpfungen in wenigen Sammel-Queries vorladen statt lazy pro Event
# (bei 10k+ importierten Events wird das N+1-Lazy-Loading sonst zur Bremse)
_EAGER = (
    selectinload(Event.entity_links).selectinload(EventEntityLink.entity),
    selectinload(Event.metrics),
    selectinload(Event.location),
    selectinload(Event.media),
)
# A36: slim lädt die Metriken NICHT (Wetter kommt separat als Tupel-Abfrage);
# Medien bleiben eager, damit die Fotostreifen ohne N+1 rendern.
_EAGER_SLIM = (
    selectinload(Event.entity_links).selectinload(EventEntityLink.entity),
    selectinload(Event.location),
    selectinload(Event.media),
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
    slim: bool = Query(False, description="A36: schlanke Liste ohne Metrik-Zeilen "
                       "(Wetter kompakt) — für Zeitstrahl/Karte/Heute"),
) -> list[EventRead]:
    """Liste der eigenen Events, optional gefiltert (für Timeline & Karte).

    slim (A36): ohne die Roh-Metriken (67 % der Nutzlast) — das Wetter kommt
    kompakt im Feld `weather`. Der Zeitstrahl braucht die Rohzeilen nicht; das
    macht das erste Laden (v. a. mobil, Anmerkung 61) deutlich kleiner."""
    # A36-Performance: im slim-Modus die Metriken NICHT eager laden — 16 Zeilen
    # je Ereignis als ORM-Objekte waren der Flaschenhals (bei 12.000 Ereignissen
    # ~3 s). Stattdessen unten das Wetter in EINER schlanken Abfrage holen.
    eager = _EAGER_SLIM if slim else _EAGER
    query = db.query(Event).options(*eager).filter(Event.user_id == user.id)
    if category:
        query = query.filter(Event.category == category)
    if confirmed_only:
        from app.models import ConfirmState

        query = query.filter(Event.confirmed == ConfirmState.confirmed)
    if q:
        like = f"%{q}%"
        query = query.filter(Event.title.ilike(like) | Event.description.ilike(like))

    events = query.order_by(Event.date_start.desc().nullslast()).all()
    if not slim:
        return [event_to_read(e) for e in events]

    # Kompaktes Wetter für alle Ereignisse in einer einzigen Tupel-Abfrage
    # (kein ORM-Objekt je Metrik). weather_rev ist ein interner Marker.
    wx: dict[str, dict] = {}
    rows = (db.query(Metric.event_id, Metric.key, Metric.value, Metric.value_text)
            .join(Event, Event.id == Metric.event_id)
            .filter(Event.user_id == user.id,
                    Metric.source == Source.weather,
                    Metric.key != "weather_rev")
            .all())
    for eid, key, value, value_text in rows:
        wx.setdefault(eid, {})[key] = value_text if value_text is not None else value
    return [event_to_read(e, slim=True, weather=wx.get(e.id)) for e in events]


# --------------------------------------------------------------------------- #
# F14 — „An diesem Tag"
# --------------------------------------------------------------------------- #
# Reine Schicht-4-Ableitung: speichert nichts, rechnet bei jedem Aufruf neu.
#
# Nur `exact` und `day` zählen. `month` wurde bewusst ausgeschlossen, obwohl
# das Konzept es zunächst mitnannte: bei Monatsgenauigkeit ist der Tag
# unbekannt, „heute vor 5 Jahren" wäre also eine Behauptung, die die Daten
# nicht hergeben — und Genauigkeit nicht zu überzeichnen ist die Grundregel
# dieses Projekts (Kap. 3.1). Ein eigener „in diesem Monat"-Block kann das
# später ehrlich nachholen.
_ON_THIS_DAY_PRECISIONS = (DatePrecision.exact, DatePrecision.day)


@router.get("/on-this-day", response_model=list[OnThisDayGroup])
def on_this_day(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    # Annotated statt Query-als-Default: so bleiben es echte Python-Defaults,
    # die auch beim direkten Aufruf gelten (Jobs, Tests) — nicht nur über HTTP.
    date: Annotated[date_type | None, Query(description="Bezugstag (Default: heute)")] = None,
    max_years: Annotated[int, Query(ge=1, le=200, description="Wie weit zurück")] = 50,
    # F16: Ein Tag vor fünf Jahren kann dreißig importierte Besuche enthalten.
    # Ungedeckelt wird aus dem Rückblick eine Liste, und die Erinnerung geht
    # darin unter — genau der Grund, warum der Block aus dem Zeitstrahl musste.
    max_per_year: Annotated[int, Query(ge=1, le=50, description="Einträge je Jahrgang")] = 3,
    include_imported: Annotated[bool, Query(
        description="Importierte Standort-Besuche mitzeigen")] = False,
) -> list[OnThisDayGroup]:
    """Was ist an diesem Kalendertag in früheren Jahren passiert?

    Trifft auch mehrtägige Events, die den Tag *überspannen* („du warst an
    diesem Tag vor 5 Jahren auf Mallorca") — nicht nur solche, die an ihm
    beginnen. Existiert zu einem Mehrtages-Event ein Tages-Kind (F7) im selben
    Jahrgang, gewinnt das Kind: es ist der genauere Eintrag, und beide
    nebeneinander wären dieselbe Erinnerung doppelt.
    """
    today = date or datetime.now().date()
    query = (db.query(Event).options(*_EAGER)
             .filter(Event.user_id == user.id,
                     Event.date_start.isnot(None),
                     Event.date_precision.in_(_ON_THIS_DAY_PRECISIONS)))
    if not include_imported:
        query = query.filter(Event.source != Source.google_timeline)
    events = query.all()

    by_year: dict[int, list[Event]] = {}
    for e in events:
        start = e.date_start.date()
        end = (e.date_end or e.date_start).date()
        if end < start:
            start, end = end, start
        # Jahrgänge, in denen dieser Event den Kalendertag berührt. Über die
        # Spanne laufen statt zu rechnen: sie ist praktisch immer kurz, und
        # Schaltjahre sowie Jahreswechsel erledigen sich damit von selbst.
        if (end - start).days > 366:
            continue
        d = start
        while d <= end:
            years_ago = today.year - d.year
            if d.month == today.month and d.day == today.day and 1 <= years_ago <= max_years:
                by_year.setdefault(years_ago, []).append(e)
                break
            d += timedelta(days=1)

    groups: list[OnThisDayGroup] = []
    for years_ago in sorted(by_year):
        chosen = by_year[years_ago]
        # F7: Eltern verwerfen, deren Tages-Kind schon in diesem Jahrgang steht
        child_parents = {e.parent_event_id for e in chosen if e.parent_event_id}
        chosen = [e for e in chosen if e.id not in child_parents]
        chosen.sort(key=lambda e: (e.date_start, e.title or ""))
        total = len(chosen)
        groups.append(OnThisDayGroup(
            years_ago=years_ago,
            date=today.replace(year=today.year - years_ago),
            events=[event_to_read(e) for e in chosen[:max_per_year]],
            total=total,
        ))
    return groups


@router.get("/map", response_model=list[EventRead])
def list_map_events(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[EventRead]:
    """Nur verortete eigene Events (mit Koordinaten) — für die Karte."""
    events = (db.query(Event).options(*_EAGER)
              .filter(Event.user_id == user.id).join(Event.location).all())
    result = [event_to_read(e) for e in events if e.location and e.location.lat is not None]
    return result
