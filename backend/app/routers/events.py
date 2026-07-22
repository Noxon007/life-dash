"""Event-Read-Endpoints (Stufe-3-Ansichten: Timeline & Karte)."""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import (ConfirmState, DatePrecision, Event, EventEntityLink,
                        Location, Metric, Source, User)
from app.routers._serialize import event_to_read
from app.schemas import (EventGeo, EventManualCreate, EventRead, EventsIndex,
                         LocationGeo, OnThisDayGroup, YearCount)
from app.services.ingestion import create_manual_event
from app.services.stats_overview import find_birth

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


# A37: Datierungen, die der Nutzer selbst als „unscharf" sieht. Die Liste
# „Unscharfe Zeiten" filterte das bisher im Browser über ALLE Ereignisse.
_VAGUE_PRECISIONS = (DatePrecision.month, DatePrecision.season,
                     DatePrecision.year, DatePrecision.decade)


@router.get("", response_model=list[EventRead])
def list_events(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    # Annotated statt Query-als-Default (wie bei on_this_day): so bleiben es
    # echte Python-Defaults, die auch beim direkten Aufruf gelten. Mit
    # `= Query(None)` bekäme ein Direktaufruf das Query-Objekt selbst als Wert
    # in den Filter — die Abfrage bricht dann erst in der DB-Schicht.
    category: Annotated[str | None, Query(description="Nach Kategorie filtern")] = None,
    confirmed_only: Annotated[bool, Query(description="Nur bestätigte Events")] = False,
    q: Annotated[str | None, Query(description="Volltextsuche in Titel/Beschreibung")] = None,
    slim: Annotated[bool, Query(description="A36: schlanke Liste ohne Metrik-Zeilen "
                                "(Wetter kompakt) — für Zeitstrahl/Karte/Heute")] = False,
    # A37 — serverseitiges Zeitfenster
    date_from: Annotated[datetime | None, Query(
        alias="from", description="A37: nur Ereignisse ab diesem Zeitpunkt")] = None,
    date_to: Annotated[datetime | None, Query(
        alias="to", description="A37: nur Ereignisse bis zu diesem Zeitpunkt")] = None,
    limit: Annotated[int | None, Query(
        ge=1, le=5000, description="A37: Seitengröße (ohne Angabe: alles)")] = None,
    offset: Annotated[int, Query(ge=0, description="A37: Seitenversatz")] = 0,
    parent: Annotated[str | None, Query(
        description="A37/F7: nur die Tages-Kinder dieses Ereignisses")] = None,
    vague: Annotated[bool, Query(
        description="A37: nur undatierte und unscharf datierte Ereignisse")] = False,
    visits: Annotated[bool | None, Query(
        description="A37: importierte Standort-Besuche einschließen (Default: "
                    "alles). visits=0 lässt sie weg — der Zeitstrahl blendet "
                    "sie standardmäßig aus.")] = None,
    condense: Annotated[bool, Query(
        description="A39: importierte Besuche desselben Tages und derselben "
                    "Stadt zu einem Eintrag zusammenfassen")] = False,
    city: Annotated[str | None, Query(
        description="A39: nur Ereignisse in dieser Stadt — löst eine "
                    "zusammengefasste Gruppe wieder auf")] = None,
) -> list[EventRead]:
    """Liste der eigenen Events, optional gefiltert (für Timeline & Karte).

    slim (A36): ohne die Roh-Metriken (67 % der Nutzlast) — das Wetter kommt
    kompakt im Feld `weather`. Der Zeitstrahl braucht die Rohzeilen nicht; das
    macht das erste Laden (v. a. mobil, Anmerkung 61) deutlich kleiner.

    A37: `from`/`to` schneiden ein Zeitfenster heraus, `limit`/`offset` blättern
    darin. Ohne beides verhält sich der Endpunkt wie bisher (alles auf einmal) —
    Export, Tests und Altpfade bleiben damit gültig. Undatierte Ereignisse haben
    in einem Zeitfenster keinen Platz und fallen bei gesetztem `from`/`to` weg;
    erreichbar bleiben sie über `vague=1`."""
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
    if date_from is not None:
        query = query.filter(Event.date_start.isnot(None), Event.date_start >= date_from)
    if date_to is not None:
        query = query.filter(Event.date_start.isnot(None), Event.date_start <= date_to)
    if parent is not None:
        query = query.filter(Event.parent_event_id == parent)
    if vague:
        query = query.filter(Event.date_start.is_(None)
                             | Event.date_precision.in_(_VAGUE_PRECISIONS))
    # A37: Der Zeitstrahl blendet importierte Besuche standardmäßig aus. Filtert
    # erst der Browser, besteht eine Seite nach einem Timeline-Import fast nur
    # aus Unsichtbarem — gemessen an einer 12.000er-Datenbank: sechs Seiten
    # nachgeladen für ein paar sichtbare Karten. Also hier filtern.
    if visits is False:
        query = query.filter(Event.source != Source.google_timeline)
    if city:
        query = query.filter(Event.location_id.in_(
            db.query(Location.id).filter(Location.user_id == user.id,
                                         Location.city == city)))
    # A39: Verdichtung. Entscheidend ist, dass sie VOR dem Blättern greift —
    # würde erst die fertige Seite gruppiert, zerschnitte die Seitengrenze eine
    # Gruppe, und beide Hälften zeigten eine zu kleine Zahl. Deshalb wird die
    # Menge selbst reduziert: von jeder (Tag, Stadt)-Gruppe bleibt genau ein
    # Vertreter übrig, und über diese Vertreter wird paginiert.
    if condense:
        query = query.filter(Event.id.in_(_visit_group_reps(db, user.id))
                             | Event.id.notin_(_condensable_visits(db, user.id)))

    # A37: Die Sortierung MUSS eindeutig sein, sonst blättert man an
    # Datums-Gleichständen an Einträgen vorbei oder sieht sie doppelt — bei
    # Timeline-Importen haben dutzende Besuche denselben Zeitstempel.
    query = query.order_by(Event.date_start.desc().nullslast(), Event.id.desc())
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    events = query.all()
    if not slim:
        return [event_to_read(e) for e in events]

    kids = _child_counts(db, user.id, events)
    groups = _visit_group_info(db, user.id, events) if condense else {}
    return [event_to_read(e, slim=True, weather=w, child_count=kids.get(e.id),
                          group=groups.get(e.id))
            for e, w in zip(events, _weather_for(db, user.id, events))]


# --------------------------------------------------------------------------- #
# A39 — Verdichtung importierter Besuche (Anmerkung 88)
#
# Nach einem Timeline-Import hat ein einzelner Tag dutzende Besuche, jeder eine
# eigene Zeile, jeder bis zur Straße benannt. Zusammengefasst wird nach (Tag,
# Stadt): der Tag, weil der Zeitstrahl ohnehin nach Tagen gliedert, die Stadt,
# weil sie seit A39 ein echtes Feld ist und nicht mehr davon abhängt, welche
# Namensbausteine der Nutzer gewählt hat.
# --------------------------------------------------------------------------- #
def _day_parts(col):
    """Jahr/Monat/Tag eines Zeitstempels — dialektneutral.

    `date(x)` gibt es so nur in SQLite, `x::date` nur in Postgres; `extract`
    können beide. Der Test-Lauf ist SQLite, die Anlage des Autors Postgres —
    ein Unterschied, den `test_a37_postgres_dialect.py` schon einmal teuer
    gemacht hat.
    """
    return (func.extract("year", col), func.extract("month", col),
            func.extract("day", col))


def _condensable_base(db: Session, user_id: str):
    """Die Menge, um die es geht: importierte Besuche mit bekannter Stadt.

    Alles andere bleibt unangetastet — von Hand erfasste Ereignisse werden nie
    zusammengefasst, auch wenn zwei am selben Tag in derselben Stadt liegen.
    Sie sind einzeln eingetragen worden, also sind sie einzeln gemeint.
    """
    return (db.query(Event)
            .join(Location, Event.location_id == Location.id)
            .filter(Event.user_id == user_id,
                    Event.source == Source.google_timeline,
                    Event.date_start.isnot(None),
                    Location.city.isnot(None), Location.city != ""))


def _condensable_visits(db: Session, user_id: str):
    """IDs aller Besuche, die überhaupt zusammengefasst werden können."""
    return _condensable_base(db, user_id).with_entities(Event.id)


def _visit_group_reps(db: Session, user_id: str):
    """Je (Tag, Stadt) genau eine ID — der Vertreter der Gruppe.

    `min(id)` ist ein willkürlicher, aber stabiler Vertreter. Stabil ist das
    Entscheidende: derselbe Aufruf muss zweimal dieselbe Zeile liefern, sonst
    springen beim Blättern Einträge. Dass er nicht unbedingt der zeitlich
    erste Besuch ist, fällt nicht auf — Zeitspanne und Anzahl der Gruppe kommen
    aus dem Aggregat, nicht aus dem Vertreter.
    """
    y, m, d = _day_parts(Event.date_start)
    return (_condensable_base(db, user_id)
            .with_entities(func.min(Event.id))
            .group_by(y, m, d, Location.city))


def _visit_group_info(db: Session, user_id: str,
                      events: list[Event]) -> dict[str, dict]:
    """Anzahl und Zeitspanne der Gruppe, die ein Vertreter auf dieser Seite
    vertritt — eine Abfrage für die ganze Seite, eingegrenzt auf deren
    Zeitraum, damit nicht über den gesamten Bestand aggregiert wird.
    """
    reps = [e for e in events if e.date_start and e.source == Source.google_timeline]
    if not reps:
        return {}
    lo = min(e.date_start for e in reps)
    hi = max(e.date_start for e in reps)
    y, m, d = _day_parts(Event.date_start)
    rows = (_condensable_base(db, user_id)
            .with_entities(y.label("y"), m.label("m"), d.label("d"),
                           Location.city.label("city"), func.count(Event.id),
                           func.min(Event.date_start), func.max(Event.date_start))
            .filter(Event.date_start >= lo.replace(hour=0, minute=0, second=0),
                    Event.date_start <= hi.replace(hour=23, minute=59, second=59))
            .group_by(y, m, d, Location.city).all())
    by_key = {(int(r[0]), int(r[1]), int(r[2]), r[3]): r for r in rows}
    out: dict[str, dict] = {}
    for e in reps:
        loc = e.location
        if not loc or not loc.city:
            continue
        key = (e.date_start.year, e.date_start.month, e.date_start.day, loc.city)
        row = by_key.get(key)
        # Eine Gruppe von genau einem Besuch ist keine Gruppe — dann bleibt es
        # eine gewöhnliche Karte ohne Chip und ohne Aufklappen.
        if not row or row[4] < 2:
            continue
        out[e.id] = {"city": loc.city, "count": row[4],
                     "first": row[5], "last": row[6]}
    return out


def _child_counts(db: Session, user_id: str, events: list[Event]) -> dict[str, int]:
    """F7: Zahl der Tages-Kinder je Ereignis der Seite — eine Abfrage.

    Der Chip „📅 N Tages-Einträge" zählte bisher in der geladenen Liste. Mit
    dem Zeitfenster kann ein Kind auf einer anderen Seite liegen; der Chip
    hätte zu wenig gezeigt, ohne dass es jemandem auffällt.

    `user_id` steht hier, obwohl die IDs schon aus den eigenen Ereignissen
    stammen: „jede Abfrage ist auf den Nutzer eingeschränkt" (A12) ist eine
    Regel ohne Ausnahmen — sonst muss man bei jeder Änderung neu begründen,
    warum diese eine Stelle sicher ist."""
    if not events:
        return {}
    ids = [e.id for e in events]
    out: dict[str, int] = {}
    for i in range(0, len(ids), 500):
        rows = (db.query(Event.parent_event_id, func.count(Event.id))
                .filter(Event.user_id == user_id,
                        Event.parent_event_id.in_(ids[i:i + 500]))
                .group_by(Event.parent_event_id).all())
        out.update({pid: n for pid, n in rows})
    return out


def _weather_for(db: Session, user_id: str, events: list[Event]) -> list[dict | None]:
    """Kompaktes Wetter je Ereignis in EINER Tupel-Abfrage (kein ORM je Metrik).

    A36 holte das Wetter für alle Ereignisse des Nutzers auf einmal — bei einer
    Seite von 300 Einträgen wären das weiterhin 190.000 Zeilen. A37 fragt nur
    die Ereignisse der Seite ab. `weather_rev` ist ein interner Marker.

    Der Join auf `Event` bleibt trotz der ID-Einschränkung stehen: A12 verlangt
    die Nutzer-Einschränkung in JEDER Abfrage, ohne Ausnahme (siehe
    `_child_counts`)."""
    if not events:
        return []
    ids = [e.id for e in events]
    wx: dict[str, dict] = {}
    # In Blöcken, damit die IN-Liste keine Parameter-Grenze reißt (SQLite: 999)
    for i in range(0, len(ids), 500):
        rows = (db.query(Metric.event_id, Metric.key, Metric.value, Metric.value_text)
                .join(Event, Event.id == Metric.event_id)
                .filter(Event.user_id == user_id,
                        Metric.event_id.in_(ids[i:i + 500]),
                        Metric.source == Source.weather,
                        Metric.key != "weather_rev")
                .all())
        for eid, key, value, value_text in rows:
            wx.setdefault(eid, {})[key] = value_text if value_text is not None else value
    return [wx.get(e.id) for e in events]


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
    # A37 (zweite Runde): Vorauswahl in SQL statt „alles laden und in Python
    # aussieben". Gemessen bei 3.000 eigenen Einträgen: 660 ms — auf der
    # STARTANSICHT, und mit dem Bestand wachsend. Ursache war dieselbe wie in
    # Anmerkung 80: jedes Ereignis samt seiner vierzehn Metrik-Zeilen als
    # ORM-Objekt, nur um am Ende ein Dutzend davon zu zeigen.
    #
    # Die Auswahl ist EXAKT dieselbe wie vorher, nur früher: Eintägiges kann
    # den Kalendertag nur treffen, wenn Tag und Monat passen; alles mit einem
    # Enddatum kann ihn überspannen und wird weiterhin vollständig geprüft
    # (die Python-Schleife unten entscheidet unverändert).
    query = query.filter(
        Event.date_end.isnot(None)
        | ((func.extract("month", Event.date_start) == today.month)
           & (func.extract("day", Event.date_start) == today.day))
    )
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


@router.get("/index", response_model=EventsIndex)
def events_index(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventsIndex:
    """A37: Die Verteilung der eigenen Ereignisse über die Jahre — als Zahlen.

    Der Zeitstrahl blättert (limit/offset), braucht aber trotzdem zu wissen,
    wie weit seine Geschichte reicht und wie viel in welchem Jahr liegt. Das
    hier kostet drei Aggregat-Abfragen statt einer vollen Liste; der Heute-
    Reiter holt seine drei Kacheln aus derselben Antwort."""
    year = func.extract("year", Event.date_start)
    rows = (db.query(year.label("y"), func.count(Event.id))
            .filter(Event.user_id == user.id, Event.date_start.isnot(None))
            .group_by("y").order_by("y").all())
    years = [YearCount(year=int(y), count=n) for y, n in rows]
    dated = sum(y.count for y in years)
    total = (db.query(func.count(Event.id))
             .filter(Event.user_id == user.id).scalar() or 0)
    unconfirmed = (db.query(func.count(Event.id))
                   .filter(Event.user_id == user.id,
                           Event.confirmed != ConfirmState.confirmed).scalar() or 0)
    # Der Schalter „🛰️ N Besuche" nannte die Zahl der Besuche in der geladenen
    # Liste. Mit dem Zeitfenster wäre das eine beliebige Zahl gewesen — hier
    # steht die echte.
    visits = (db.query(func.count(Event.id))
              .filter(Event.user_id == user.id,
                      Event.source == Source.google_timeline).scalar() or 0)
    return EventsIndex(
        total=total, dated=dated, undated=total - dated, unconfirmed=unconfirmed,
        visits=visits,
        year_min=years[0].year if years else None,
        year_max=years[-1].year if years else None,
        years=years,
        # F17 fährt hier mit: das Geburtsdatum kommt aus einem Meilenstein, der
        # in aller Regel außerhalb der geladenen Seiten liegt. Der Zeitstrahl
        # holt den Index ohnehin — so bleibt es bei einer Anfrage.
        birth=find_birth(db, user.id),
    )


@router.get("/map", response_model=list[EventGeo])
def list_map_events(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    weather: Annotated[bool, Query(
        description="Wetter mitschicken — nur für den angezeigten Zeitraum")] = False,
) -> list[EventGeo]:
    """Nur verortete eigene Events (mit Koordinaten) — für die Karte.

    A37: Antwortet in der schlanken Geo-Form (siehe `EventGeo`) statt mit
    vollen Ereignissen — und erst dann, wenn ihr Reiter geöffnet wird; bis A36
    hing sie am selben Aufruf wie der Zeitstrahl und verlängerte den Start.

    `weather` ist bewusst abschaltbar und standardmäßig AUS: gemessen bei
    12.000 Punkten macht es aus 205 Byte je Punkt 799 — es ist der größte
    Einzelposten der Antwort. Die Karte holt deshalb erst alle Punkte ohne
    Wetter (Zeitraum-Regler, Bündelung, Marker) und danach das Wetter nur für
    den angezeigten Zeitraum, wo Popup und Stopp-Liste es wirklich zeigen."""
    query = (db.query(Event).options(selectinload(Event.location))
             .filter(Event.user_id == user.id, Event.location_id.isnot(None))
             .join(Event.location).filter(Location.lat.isnot(None),
                                          Event.date_start.isnot(None)))
    if date_from is not None:
        query = query.filter(Event.date_start >= date_from)
    if date_to is not None:
        query = query.filter(Event.date_start <= date_to)
    events = query.order_by(Event.date_start.asc(), Event.id.asc()).all()
    wx = _weather_for(db, user.id, events) if weather else [None] * len(events)
    return [
        EventGeo(
            id=e.id, title=e.title, category=e.category, date_start=e.date_start,
            date_precision=e.date_precision, source=e.source,
            location=LocationGeo.model_validate(e.location), weather=w,
        )
        for e, w in zip(events, wx)
    ]


@router.get("/{event_id}", response_model=EventRead)
def get_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventRead:
    """A37: Ein einzelnes Ereignis, vollständig.

    Solange das Frontend alles im Speicher hatte, brauchte es das nie. Mit dem
    Zeitfenster kann ein Ereignis außerhalb der geladenen Seiten liegen — eine
    Statistik-Kachel oder ein Suchtreffer verweist darauf — und dann muss es
    einzeln nachladbar sein. Muss ZULETZT stehen: `/{event_id}` würde sonst
    auch `/map` und `/index` schlucken."""
    event = (db.query(Event).options(*_EAGER)
             .filter(Event.id == event_id, Event.user_id == user.id).first())
    if not event:
        raise HTTPException(404, "Event nicht gefunden")
    return event_to_read(event)
