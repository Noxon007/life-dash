"""Event-Read-Endpoints (Stufe-3-Ansichten: Timeline & Karte)."""
from __future__ import annotations

import logging
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import false as sa_false
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import (ConfirmState, DatePrecision, Event, EventEntityLink,
                        Location, Metric, Source, User)
from app.routers._serialize import EAGER, EAGER_SLIM, event_to_read
from app.schemas import (EventGeo, EventManualCreate, EventRead, EventsIndex,
                         LocationGeo, OnThisDayGroup, YearCount)
from app.services import visitsplit
from app.services.immich_link import MACHINE_SOURCES
from app.services.photo_points import asset_of as photo_asset_of
from app.services.ingestion import create_manual_event
from app.services.stats_overview import find_birth
from app.sqlutil import DISTRICT_KEYS, addr_part, day_parts, even_spread

router = APIRouter(prefix="/api/events", tags=["Events"])

log = logging.getLogger("lifedash.events")

# Seit 0.35.0 in `_serialize.py` — dort, wo `event_to_read` steht: wer ein
# Ereignis serialisiert, braucht genau diese Beziehungen (A42).
_EAGER, _EAGER_SLIM = EAGER, EAGER_SLIM


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
# Sammelaktion: bis zu welcher Spanne ein Ereignis ohne Rückfrage aufgeteilt
# wird. Bewusst viel kleiner als `MAX_DAY_CHILDREN` (das ist eine Grenze für
# eine EINZELNE, ausdrücklich gewollte Aufteilung). Anmerkung 87 hat ein
# automatisches Tages-Objekt je Tag verworfen, weil Tausende leere Container
# entstehen, die jede Aggregation wieder ausfiltern muss — ein Sammelknopf
# ohne Deckel wäre genau das, nur von Hand ausgelöst: EIN „Auslandsjahr"
# ergäbe 365 Zeilen. Was darüber liegt, bleibt der Einzelentscheidung.
BULK_DAY_SPAN = 31
# Aufgeteilt wird nur, was tagesgenau datiert ist. „Sommer 2002" trägt
# `date_start=2002-06-01` und eine Spanne über Monate — 92 Tages-Einträge
# daraus zu machen behauptete eine Genauigkeit, die die Angabe selbst
# dementiert. Dieselbe Regel wie `_ON_THIS_DAY_PRECISIONS` (F14) und wie im
# Tagebuch-Vorschlag (F1).
_SPLITTABLE_PRECISIONS = (DatePrecision.exact, DatePrecision.day)


def _missing_days(parent: Event) -> list[tuple[int, date_type]]:
    """Welche Tage der Spanne noch KEIN Kind haben — (Nummer, Datum).

    Die Nummer ist der Tag innerhalb der Spanne und steckt im Titel („— Tag
    3"). Sie muss aus der Spanne kommen und nicht aus der Reihenfolge des
    Anlegens: sonst heißt derselbe Tag beim Lückenfüllen anders als beim
    ersten Lauf.
    """
    first, last = parent.date_start.date(), parent.date_end.date()
    have = {c.date_start.date() for c in parent.children if c.date_start}
    return [(offset + 1, first + timedelta(days=offset))
            for offset in range((last - first).days + 1)
            if first + timedelta(days=offset) not in have]


def _new_day_child(user_id: str, parent: Event, number: int,
                   day: date_type) -> Event:
    """Ein Tages-Kind — die EINE Stelle, an der festgelegt ist, wie es aussieht.

    Einzelknopf und Sammelknopf gehen hier durch. Zwei Fassungen wären zwei
    Regeln, und die laufen still auseinander (Anmerkung 106/111) — hier wäre
    der Unterschied besonders teuer, weil er in der Lebensdatenbank landet.
    """
    start = datetime(day.year, day.month, day.day)
    confirmed = parent.confirmed == ConfirmState.confirmed
    return Event(
        user_id=user_id,
        title=f"{parent.title} — Tag {number}",
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

    created: list[Event] = []
    for number, day in _missing_days(parent):
        child = _new_day_child(user.id, parent, number, day)
        db.add(child)
        created.append(child)
    db.flush()
    # Anreicherung (Wetter) hängt an den Kindern = pro Tag (Kern von F7)
    auto_enrich_events(db, created)
    db.commit()
    for c in created:
        db.refresh(c)
    return [event_to_read(c) for c in created]


# --------------------------------------------------------------------------- #
# F7 in Serie — alle mehrtägigen Ereignisse auf einmal aufteilen
# --------------------------------------------------------------------------- #
# Aus dem Betrieb (Anmerkung 113): Seit Immich Alben vorschlägt, entstehen
# mehrtägige Einträge in Serie, und jeder einzelne wollte per Hand aufgeklappt
# und aufgeteilt werden. Ein Knopf pro Ereignis ist richtig, solange es ein
# Ereignis ist; bei zwanzig ist er die Arbeit selbst.
#
# **Erst sehen, dann anlegen** — dasselbe Muster wie bei der Immich-Vorschau
# (P2.5): Diese Aktion schreibt in die Lebensdatenbank, und zwar vervielfacht.
# Wer 12 Ereignisse aufteilt, bekommt vielleicht 200 Zeilen, die er danach
# einzeln wieder löschen müsste.
_BULK_LIST_LIMIT = 60


def _scan_splittable(db: Session, user_id: str, max_span: int):
    """(fällige, zu lange, unscharf) — die EINE Auswahl für Vorschau und Lauf.

    Zwei Auswahlen wären zwei Regeln: die Vorschau zeigte dann etwas anderes,
    als der Knopf tut, und das fiele niemandem auf (Anmerkung 106). Deshalb
    liefert diese Funktion die Ereignis-Objekte mitsamt ihren fehlenden Tagen —
    die Vorschau zählt sie, der Lauf legt sie an.
    """
    rows = (db.query(Event).options(selectinload(Event.children))
            .filter(Event.user_id == user_id,
                    Event.parent_event_id.is_(None),
                    Event.confirmed == ConfirmState.confirmed,
                    Event.date_start.isnot(None),
                    Event.date_end.isnot(None),
                    Event.date_end > Event.date_start)
            .order_by(Event.date_start.desc()).all())
    ready, long_ones, vague = [], [], 0
    for event in rows:
        span = (event.date_end.date() - event.date_start.date()).days + 1
        if span < 2:
            continue
        if event.date_precision not in _SPLITTABLE_PRECISIONS:
            vague += 1
            continue
        missing = _missing_days(event)
        if not missing:
            continue                      # schon aufgeteilt — nichts zu tun
        (ready if span <= max_span else long_ones).append((event, span, missing))
    return ready, long_ones, vague


def _entry(event: Event, span: int, missing: list) -> dict:
    return {"id": event.id, "title": event.title, "span": span,
            "days": len(missing),
            "start": event.date_start.date().isoformat(),
            "end": event.date_end.date().isoformat()}


def _splittable(db: Session, user_id: str, max_span: int) -> dict:
    """Was ein Sammellauf aufteilen würde — und was er auslässt, mit Grund.

    Nur **bestätigte** Ereignisse: Kinder erben die Bestätigung, ein
    aufgeteilter Vorschlag würde also die Moderations-Warteschlange
    vervielfachen statt sie abzuarbeiten.
    """
    ready, long_ones, vague = _scan_splittable(db, user_id, max_span)
    ready = [_entry(*r) for r in ready]
    long_ones = [_entry(*r) for r in long_ones]
    return {
        "max_span": max_span,
        "events": len(ready),
        "days": sum(e["days"] for e in ready),
        "list": ready[:_BULK_LIST_LIMIT],
        "more": max(0, len(ready) - _BULK_LIST_LIMIT),
        # Was NICHT passiert, gehört genauso in die Antwort wie was passiert:
        # ein Ereignis, das stillschweigend ausgelassen wird, ist ein Rätsel.
        "too_long": long_ones[:_BULK_LIST_LIMIT],
        "too_long_count": len(long_ones),
        "vague": vague,
    }


@router.get("/days/pending")
def day_children_pending(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    max_span: Annotated[int, Query(ge=2, le=MAX_DAY_CHILDREN)] = BULK_DAY_SPAN,
) -> dict:
    """Vorschau: welche Ereignisse würden aufgeteilt, in wie viele Tage."""
    return _splittable(db, user.id, max_span)


@router.post("/days/all")
def day_children_for_all(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    max_span: Annotated[int, Query(ge=2, le=MAX_DAY_CHILDREN)] = BULK_DAY_SPAN,
) -> dict:
    """Legt die fehlenden Tages-Einträge für ALLE passenden Ereignisse an.

    **Ohne Wetter.** Der Einzelknopf reichert direkt an (P2.4), weil es um ein
    Ereignis geht; hier wären es hunderte Open-Meteo-Abrufe in EINER Anfrage —
    und ein Endpunkt, dessen Dauer an einem fremden Dienst hängt, überlebt
    keinen umgekehrten Vertreter (Anmerkung 113, der 502). Das Wetter trägt
    der Wetterlauf nach; genau dafür gibt es ihn.

    Idempotent wie der Einzelknopf: vorhandene Tage werden übersprungen, es
    werden nur Lücken gefüllt. Zweimal drücken legt nichts doppelt an.
    """
    # Dieselbe Auswahl wie die Vorschau — und die Anzeige-Deckelung
    # (`_BULK_LIST_LIMIT`) gilt hier NICHT: sie ist eine Eigenschaft der
    # Darstellung, kein Teil der Regel. Ein Lauf, der sechzig anlegt und über
    # den Rest schweigt, wäre genau die Stille, die dieses Projekt jagt.
    ready, long_ones, vague = _scan_splittable(db, user.id, max_span)
    created = 0
    for event, _span, missing in ready:
        for number, day in missing:
            db.add(_new_day_child(user.id, event, number, day))
            created += 1
    db.commit()
    log.info("Tages-Einträge in Serie: %d Ereignisse, %d Tage angelegt "
             "(max_span=%d, %d zu lang, %d unscharf)",
             len(ready), created, max_span, len(long_ones), vague)
    return {"events": len(ready), "created": created, "max_span": max_span,
            "too_long_count": len(long_ones), "vague": vague}


# --------------------------------------------------------------------------- #
# A46 — mehrtägige IMPORTIERTE Besuche nachträglich in Tage schneiden
# --------------------------------------------------------------------------- #
# Der Import legt seit A46 nur noch Tages-Besuche an; der Bestand ist damit
# nicht geheilt. Gemeldet waren über 2.000 Zwei-Tages-Ereignisse, die meisten
# davon Nächte am Wohnort.
#
# **Das hier schneidet BESTÄTIGTES, und das ist der Grund für jede seiner
# Einschränkungen.** Die Kernregel lautet „Maschinen ändern Bestätigtes nie"
# (KONZEPT Kap. 3.1). Erlaubt ist der Lauf trotzdem, aus zwei Gründen, die
# beide genannt sein wollen: Ein MENSCH löst ihn aus — er läuft nie im
# Nachtplan und nie als Nebenwirkung von irgendetwas anderem. Und `date_end`
# war bei diesen Zeilen nie eine Aussage über die Dauer, sondern ein
# Übernahme-Artefakt: Google liefert Anfang und Ende eines Aufenthalts, der
# Import hat sie roh in ein Ereignisfeld geschrieben. Korrigiert wird die
# Übernahme, nicht die Beobachtung — die Zeitpunkte selbst bleiben auf die
# Sekunde erhalten.
#
# Konsequenz daraus: **nur `google_timeline`.** Kein Immich-Vorschlag, kein
# von Hand erfasstes Ereignis, auch dann nicht, wenn es genauso aussieht.
_MULTIDAY_SOURCE = Source.google_timeline


def _scan_multiday_visits(db: Session, user_id: str):
    """(schneidbar, zu lang, hat Kinder) — die EINE Auswahl für Vorschau und Lauf.

    Dasselbe Muster wie `_scan_splittable` direkt darüber: zwei Auswahlen
    wären zwei Regeln, und die Vorschau zeigte dann etwas anderes, als der
    Knopf tut (Anmerkung 106).

    Ereignisse mit F7-Tages-Kindern werden ausgelassen. Ein geschnittener
    Elternteil ließe die Kinder auf einer Spanne sitzen, die es nicht mehr
    gibt — und wer sich für ein importiertes Besuchs-Ereignis Tages-Kinder
    angelegt hat, hat eine Absicht damit, die dieser Lauf nicht kennt.
    """
    rows = (db.query(Event).options(selectinload(Event.children))
            .filter(Event.user_id == user_id,
                    Event.source == _MULTIDAY_SOURCE,
                    Event.date_start.isnot(None),
                    Event.date_end.isnot(None),
                    Event.date_end > Event.date_start)
            .order_by(Event.date_start.desc()).all())
    ready, long_ones, with_kids = [], [], 0
    for event in rows:
        if event.date_start.date() == event.date_end.date():
            continue
        if event.children:
            with_kids += 1
            continue
        pieces = visitsplit.day_pieces(event.date_start, event.date_end)
        if not pieces:
            long_ones.append(event)
            continue
        ready.append((event, pieces))
    return ready, long_ones, with_kids


def _visit_entry(event: Event, pieces: list) -> dict:
    return {"id": event.id, "title": event.title, "days": len(pieces),
            "start": event.date_start.isoformat(),
            "end": event.date_end.isoformat()}


@router.get("/visits/multiday")
def multiday_visits(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Vorschau: welche importierten Besuche würden geschnitten, in wie viele Tage.

    Erst sehen, dann schreiben — dasselbe Muster wie beim F7-Sammellauf und
    bei der Immich-Vorschau (P2.5). Diese Aktion fasst die Lebensdatenbank an,
    und zwar tausendfach.
    """
    ready, long_ones, with_kids = _scan_multiday_visits(db, user.id)
    entries = [_visit_entry(e, p) for e, p in ready]
    return {
        "events": len(entries),
        # Was danach dasteht, ist die eigentliche Zahl: aus 2.000 Zeilen
        # werden 4.000. Wer das erst hinterher sieht, ist überrascht worden.
        "rows_after": sum(e["days"] for e in entries),
        "list": entries[:_BULK_LIST_LIMIT],
        "more": max(0, len(entries) - _BULK_LIST_LIMIT),
        # Was NICHT passiert, gehört genauso in die Antwort wie was passiert.
        "too_long": [_visit_entry(e, [None]) for e in long_ones[:_BULK_LIST_LIMIT]],
        "too_long_count": len(long_ones),
        "max_days": visitsplit.SPLIT_MAX_DAYS,
        "with_children": with_kids,
    }


@router.post("/visits/split")
def split_multiday_visits(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Schneidet die mehrtägigen importierten Besuche an der Tagesgrenze.

    Das erste Stück bleibt die **vorhandene Zeile**. Das ist keine Sparsamkeit,
    sondern der einzige Weg, der nichts verliert: an einem Besuch können
    Fotos, Metriken und Verknüpfungen hängen, und die zeigen auf diese ID.
    Neue Zeilen entstehen nur für die weiteren Tage.

    Idempotent: ein zweiter Lauf findet nichts mehr, weil danach kein Ereignis
    dieser Quelle mehr über eine Tagesgrenze reicht.
    """
    ready, long_ones, with_kids = _scan_multiday_visits(db, user.id)
    created = 0
    for event, pieces in ready:
        base = event.external_id
        ids = visitsplit.piece_ids(base, len(pieces)) if base else [None] * len(pieces)
        # Das erste Stück in die vorhandene Zeile — samt neuem Schlüssel,
        # damit ein späterer Re-Import diesen Besuch wiedererkennt (der
        # Import prüft beide Formen, siehe routers/tracks.py).
        first_lo, first_hi = pieces[0]
        event.date_start, event.date_end = first_lo, first_hi
        event.external_id = ids[0]
        for (lo, hi), ext in zip(pieces[1:], ids[1:]):
            db.add(Event(
                user_id=user.id,
                title=event.title,
                description=event.description,
                date_start=lo, date_end=hi,
                date_precision=event.date_precision,
                category=event.category,
                confidence=event.confidence,
                confirmed=event.confirmed,
                confirmed_at=event.confirmed_at,
                confirmed_by=event.confirmed_by,
                source=event.source,
                location_id=event.location_id,
                origin_fragment_id=event.origin_fragment_id,
                external_id=ext,
            ))
            created += 1
    db.commit()
    log.info("Mehrtägige Besuche geschnitten: %d Ereignisse, %d Zeilen neu "
             "(%d zu lang, %d mit Tages-Kindern übersprungen)",
             len(ready), created, len(long_ones), with_kids)
    return {"events": len(ready), "created": created,
            "too_long_count": len(long_ones), "with_children": with_kids}


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
        description="A37: importierte Standort-Besuche (Google Timeline) "
                    "einschließen (Default: alles). visits=0 lässt sie weg — "
                    "der Zeitstrahl blendet sie standardmäßig aus.")] = None,
    photos: Annotated[bool | None, Query(
        description="Anmerkung 139: Immich-Foto-Ereignisse einschließen "
                    "(Default: alles). Ein EIGENER Schalter neben `visits`, "
                    "weil es in der Oberfläche zwei Schalter sind — 🛰️ Google "
                    "und 📷 Immich sind zwei Sorten Beleg mit zwei Mengen "
                    "(hunderte gegen zehntausende).")] = None,
    machine_proposals: Annotated[bool | None, Query(
        description="Unbestätigte Vorschläge maschineller Quellen (Google/"
                    "Immich, MACHINE_SOURCES) einschließen (Default: alles, "
                    "API-Konsumenten/Export bleiben unverändert). "
                    "machine_proposals=0 lässt sie weg — sie werden erst nach "
                    "Bestätigung in der Moderation zu Ereignissen und tauchen "
                    "vorher nicht als unbestätigte Karte im Zeitstrahl auf; "
                    "die belegende Foto-/Besuchs-Ebene bleibt davon "
                    "unberührt, die zeigt sich unabhängig davon.")] = None,
    condense: Annotated[bool, Query(
        description="A39: importierte Besuche desselben Tages und desselben "
                    "Ortes zu einem Eintrag zusammenfassen")] = False,
    group: Annotated[str, Query(
        description="A47: auf welcher Ebene verdichtet wird — country|city|"
                    "district|point. `point` heißt: gar nicht. Wirkt nur "
                    "zusammen mit condense=1.")] = "city",
    city: Annotated[str | None, Query(
        description="A39: nur Ereignisse in dieser Stadt — löst eine "
                    "zusammengefasste Gruppe wieder auf")] = None,
    place: Annotated[str | None, Query(
        description="Anmerkung 134: nur Ereignisse mit diesem Wert auf der Stufe "
                    "`group` (country|city|district) — löst eine auf DIESER "
                    "Stufe zusammengefasste Gruppe wieder auf, auch beim "
                    "Ortsteil, wo `city` den falschen Wert prüfen würde.")] = None,
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
    # Anmerkung 138: MACHINE_SOURCES statt nur google_timeline — seitdem
    # Immich-Fototage genauso automatisch bestätigt werden wie Google-Besuche,
    # gilt für sie dieselbe Regel. Zwei Quellen mit derselben Beleglage
    # brauchen dieselbe Behandlung, sonst läuft sie still auseinander
    # (Anmerkung 106).
    hidden = _hidden_sources(visits, photos)
    if hidden:
        query = query.filter(Event.source.notin_(hidden))
    # Anmerkung 135: unbestätigte Vorschläge maschineller Quellen sind Beleg,
    # kein Ereignis — sie tauchen erst nach dem bewussten Schritt in der
    # Moderation zwischen den bestätigten Karten auf. Bewusst nur diese
    # beiden Quellen (MACHINE_SOURCES): unbestätigte Einträge aus P5.1/F1
    # (KI-Erfassung aus eigenem Text) bleiben inline sichtbar, das ist eine
    # andere Frage („stimmt das, was ich diktiert habe?" statt „ist das
    # überhaupt ein Ereignis?").
    if machine_proposals is False:
        query = query.filter(~((Event.confirmed != ConfirmState.confirmed)
                               & Event.source.in_(MACHINE_SOURCES)))
    if city:
        query = query.filter(Event.location_id.in_(
            db.query(Location.id).filter(Location.user_id == user.id,
                                         Location.city == city)))
    # A39: Verdichtung. Entscheidend ist, dass sie VOR dem Blättern greift —
    # würde erst die fertige Seite gruppiert, zerschnitte die Seitengrenze eine
    # Gruppe, und beide Hälften zeigten eine zu kleine Zahl. Deshalb wird die
    # Menge selbst reduziert: von jeder (Tag, Stadt)-Gruppe bleibt genau ein
    # Vertreter übrig, und über diese Vertreter wird paginiert.
    # A47: Die Stufe kommt von außen. Ein unbekannter Wert wird abgewiesen und
    # nicht still auf „city" gebogen — sonst bekäme jemand, der sich vertippt,
    # eine plausible Antwort auf eine andere Frage.
    if group not in GROUP_LEVELS:
        raise HTTPException(400, f"Unbekannte Verdichtungsstufe: {group}")
    # Anmerkung 134: eine auf `group` verdichtete Gruppe wieder auflösen. `city`
    # oben prüft immer `Location.city` und fand einen Ortsteil-Wert deshalb nie —
    # „HafenCity · 3 Besuche" klappte nicht auf. `place` prüft die Spalte DIESER
    # Stufe (Land/Stadt/Ortsteil), also denselben Ausdruck, der die Gruppe
    # gebildet hat.
    if place:
        column = _level_column(group)
        if column is not None:
            query = query.filter(Event.location_id.in_(
                db.query(Location.id).filter(Location.user_id == user.id,
                                             column == place)))
    if condense and group != "point":
        query = query.filter(Event.id.in_(_visit_group_reps(db, user.id, group))
                             | Event.id.notin_(_condensable_visits(db, user.id, group)))

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
    groups = (_visit_group_info(db, user.id, events, group)
              if condense and group != "point" else {})
    return [event_to_read(e, slim=True, weather=w, child_count=kids.get(e.id),
                          group=groups.get(e.id))
            for e, w in zip(events, _weather_for(db, user.id,
                                                 [e.id for e in events]))]


# --------------------------------------------------------------------------- #
# A39 — Verdichtung importierter Besuche (Anmerkung 88)
#
# Nach einem Timeline-Import hat ein einzelner Tag dutzende Besuche, jeder eine
# eigene Zeile, jeder bis zur Straße benannt. Zusammengefasst wird nach (Tag,
# Stadt): der Tag, weil der Zeitstrahl ohnehin nach Tagen gliedert, die Stadt,
# weil sie seit A39 ein echtes Feld ist und nicht mehr davon abhängt, welche
# Namensbausteine der Nutzer gewählt hat.
# --------------------------------------------------------------------------- #
# Seit 0.35.0 in `app/sqlutil.py`, weil die Erfolge dieselbe Frage stellen
# (welche Einträge liegen am selben Kalendertag?) und zwei Antworten darauf
# genau die Sorte Abweichung wären, die `test_a37_postgres_dialect.py` prüft.
_day_parts = day_parts


# --------------------------------------------------------------------------- #
# A47 (Anmerkung 116) — die Verdichtungsstufe ist eine FRAGE, keine Eigenschaft
# --------------------------------------------------------------------------- #
# Bis 0.38 war „nach Stadt" fest verdrahtet. Das ist eine gute Voreinstellung
# und eine schlechte Vorgabe: „In welchen Ländern war ich 2019?" und „In
# welchen Stadtteilen von Berlin?" sind beide legitim, und welche Frage gerade
# gilt, weiß nur der, der hinsieht.
#
# Die Stufen liegen absichtlich an EINER Stelle, aus der Filter, Vertreter und
# Aggregat alle drei lesen. Drei Funktionen mit je einer fest genannten Spalte
# wären dieselbe Regel an drei Orten — und die widerspricht sich still
# (Anmerkung 106).
GROUP_LEVELS = ("country", "city", "district", "point")


def _level_column(level: str):
    """Die Spalte (bzw. der JSON-Ausdruck) dieser Stufe — None heißt „gar nicht
    verdichten"."""
    if level == "country":
        return Location.country
    if level == "city":
        return Location.city
    if level == "district":
        # `Location.address` trägt die Roh-Bausteine des Geocoders
        # (Anmerkung 110). Welcher Baustein den Ortsteil benennt, hängt vom
        # Land ab — deshalb die Fallback-Kette aus `sqlutil`.
        return addr_part(Location.address, *DISTRICT_KEYS)
    return None


def _place_of(location, level: str) -> str | None:
    """Derselbe Wert wie `_level_column`, nur in Python statt in SQL.

    Beide müssen dasselbe sagen, sonst findet die Zuordnung ihre Gruppe nicht:
    der Vertreter stünde ohne Chip da, obwohl es die Gruppe gibt. Die
    Fallback-Kette ist deshalb dieselbe Konstante.
    """
    if not location:
        return None
    if level == "country":
        return location.country
    if level == "city":
        return location.city
    if level == "district":
        address = location.address or {}
        for key in DISTRICT_KEYS:
            value = (address.get(key) or "").strip()
            if value:
                return value
    return None


def _hidden_sources(visits: bool | None, photos: bool | None) -> list[Source]:
    """Welche maschinellen Quellen gerade NICHT gezeigt werden (Anmerkung 139).

    Bis 0.39 gab es hierfür einen Schalter für beide zusammen (`visits` gegen
    `MACHINE_SOURCES`). Das war richtig, solange Immich Tagescluster lieferte —
    dieselbe Größenordnung, dieselbe Sorte Zeile. Seit ein Foto ein Ereignis
    ist, stehen hunderten Google-Besuchen zehntausende Foto-Ereignisse
    gegenüber, und wer die Fotos ausblenden will, will die Besuche behalten.

    **Eine Liste an EINER Stelle**, gelesen von Zeitstrahl und Karte. Stünde
    die Bedingung an beiden Orten einzeln, blendete der eine Reiter aus, was
    der andere zeigt — Anmerkung 106 in ihrer gewöhnlichsten Form.
    """
    hidden: list[Source] = []
    if visits is False:
        hidden.append(Source.google_timeline)
    if photos is False:
        hidden.append(Source.immich)
    return hidden


def _condensable_base(db: Session, user_id: str, level: str = "city"):
    """Die Menge, um die es geht: importierte Besuche mit bekanntem Ort.

    Alles andere bleibt unangetastet — von Hand erfasste Ereignisse werden nie
    zusammengefasst, auch wenn zwei am selben Tag in derselben Stadt liegen.
    Sie sind einzeln eingetragen worden, also sind sie einzeln gemeint.

    **Ohne Wert auf der gewählten Stufe wird nicht verdichtet.** Einen Besuch
    ohne Ortsteil in eine Ortsteil-Gruppe zu werfen, die in Wahrheit die Stadt
    ist, wäre eine Zahl mit Anspruch — und sie stünde neben echten Ortsteilen,
    ohne sich zu unterscheiden. Er bleibt dann eine gewöhnliche Karte.
    """
    column = _level_column(level)
    query = (db.query(Event)
             .join(Location, Event.location_id == Location.id)
             .filter(Event.user_id == user_id,
                     # Anmerkung 138: MACHINE_SOURCES statt nur
                     # google_timeline — ein Immich-Fototag ist seitdem
                     # dieselbe Sorte automatisch bestätigter Beleg wie ein
                     # Google-Besuch und wird deshalb genauso gebündelt.
                     Event.source.in_(MACHINE_SOURCES),
                     Event.date_start.isnot(None)))
    if column is None:
        # Stufe „point": es gibt nichts zu gruppieren. Die leere Menge ist die
        # richtige Antwort — `condense` greift dann ohnehin nicht, aber die
        # Funktion muss auch allein aufrufbar bleiben.
        return query.filter(sa_false())
    return query.filter(column.isnot(None), column != "")


def _condensable_visits(db: Session, user_id: str, level: str = "city"):
    """IDs aller Besuche, die überhaupt zusammengefasst werden können."""
    return _condensable_base(db, user_id, level).with_entities(Event.id)


def _visit_group_reps(db: Session, user_id: str, level: str = "city"):
    """Je (Tag, Ort, QUELLE) genau eine ID — der Vertreter der Gruppe.

    `min(id)` ist ein willkürlicher, aber stabiler Vertreter. Stabil ist das
    Entscheidende: derselbe Aufruf muss zweimal dieselbe Zeile liefern, sonst
    springen beim Blättern Einträge. Dass er nicht unbedingt der zeitlich
    erste Besuch ist, fällt nicht auf — Zeitspanne und Anzahl der Gruppe kommen
    aus dem Aggregat, nicht aus dem Vertreter.

    **Die Quelle gehört seit Anmerkung 139 in den Schlüssel.** Vorher fielen
    ein Google-Besuch und dreißig Fotos desselben Tages in dieselbe Gruppe, und
    der Vertreter war eines von beidem — mit zwei getrennten Schaltern wird das
    sofort falsch: „📷 aus" ließe eine Gruppe stehen, deren Vertreter ein Foto
    ist, oder umgekehrt eine verschwinden, in der Besuche steckten. Zwei
    Aussagen („dreimal hier gewesen", „dreißig Fotos gemacht") gehören ohnehin
    nicht in eine Zeile.
    """
    y, m, d = _day_parts(Event.date_start)
    return (_condensable_base(db, user_id, level)
            .with_entities(func.min(Event.id))
            .group_by(y, m, d, _level_column(level), Event.source))


def _visit_group_info(db: Session, user_id: str, events: list[Event],
                      level: str = "city") -> dict[str, dict]:
    """Anzahl und Zeitspanne der Gruppe, die ein Vertreter auf dieser Seite
    vertritt — eine Abfrage für die ganze Seite, eingegrenzt auf deren
    Zeitraum, damit nicht über den gesamten Bestand aggregiert wird.
    """
    column = _level_column(level)
    if column is None:
        return {}
    reps = [e for e in events if e.date_start and e.source in MACHINE_SOURCES]
    if not reps:
        return {}
    lo = min(e.date_start for e in reps)
    hi = max(e.date_start for e in reps)
    y, m, d = _day_parts(Event.date_start)
    # Die Quelle steht auch hier im Schlüssel — dieselbe Gruppierung wie in
    # `_visit_group_reps`. Zwei verschiedene Gruppenschlüssel für dieselbe
    # Gruppe wären eine Zahl, die zum Vertreter nicht passt: die Karte hieße
    # „12× Foto in Detmold" und stünde für drei Fotos und neun Besuche.
    rows = (_condensable_base(db, user_id, level)
            .with_entities(y.label("y"), m.label("m"), d.label("d"),
                           column.label("place"), func.count(Event.id),
                           func.min(Event.date_start), func.max(Event.date_start),
                           Event.source.label("src"))
            .filter(Event.date_start >= lo.replace(hour=0, minute=0, second=0),
                    Event.date_start <= hi.replace(hour=23, minute=59, second=59))
            .group_by(y, m, d, column, Event.source).all())
    by_key = {(int(r[0]), int(r[1]), int(r[2]), r[3], r[7]): r for r in rows}
    out: dict[str, dict] = {}
    for e in reps:
        place = _place_of(e.location, level)
        if not place:
            continue
        key = (e.date_start.year, e.date_start.month, e.date_start.day,
               place, e.source)
        row = by_key.get(key)
        # Eine Gruppe von genau einem Besuch ist keine Gruppe — dann bleibt es
        # eine gewöhnliche Karte ohne Chip und ohne Aufklappen.
        if not row or row[4] < 2:
            continue
        out[e.id] = {"city": place, "count": row[4],
                     "first": row[5], "last": row[6], "level": level}
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


def _weather_for(db: Session, user_id: str, ids: list[str]) -> list[dict | None]:
    """Kompaktes Wetter je Ereignis in EINER Tupel-Abfrage (kein ORM je Metrik).

    A36 holte das Wetter für alle Ereignisse des Nutzers auf einmal — bei einer
    Seite von 300 Einträgen wären das weiterhin 190.000 Zeilen. A37 fragt nur
    die Ereignisse der Seite ab. `weather_rev` ist ein interner Marker.

    Nimmt **Kennungen**, nicht Ereignisse (Anmerkung 157): seit die Karte ihre
    Punkte als Tupel liest, gibt es dort kein `Event`-Objekt mehr, und ein
    Parameter, der eines verlangt, hätte genau das erzwungen, was der Umbau
    abschafft.

    Der Join auf `Event` bleibt trotz der ID-Einschränkung stehen: A12 verlangt
    die Nutzer-Einschränkung in JEDER Abfrage, ohne Ausnahme (siehe
    `_child_counts`)."""
    if not ids:
        return []
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
    return [wx.get(eid) for eid in ids]


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
        # Anmerkung 138: MACHINE_SOURCES statt nur google_timeline (siehe
        # dieselbe Begründung bei `visits` oben).
        query = query.filter(Event.source.notin_(MACHINE_SOURCES))
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
    # Der Schalter „🛰️ N automatisch erfasst" nannte die Zahl der Besuche in
    # der geladenen Liste. Mit dem Zeitfenster wäre das eine beliebige Zahl
    # gewesen — hier steht die echte. Anmerkung 138: MACHINE_SOURCES statt nur
    # google_timeline — Google-Besuche und Immich-Fototage sind dieselbe
    # Sorte automatisch bestätigter Beleg und zählen deshalb zusammen.
    visits = (db.query(func.count(Event.id))
              .filter(Event.user_id == user.id,
                      Event.source == Source.google_timeline).scalar() or 0)
    # Anmerkung 139: eine EIGENE Zahl für die Immich-Foto-Ereignisse, weil es
    # dafür jetzt einen eigenen Schalter gibt. Sie zusammenzuzählen wäre die
    # ältere Antwort auf eine Frage, die seitdem anders gestellt wird — der
    # Schalter „📷 12.481" muss sagen, was ER einblendet, nicht was beide
    # zusammen einblenden.
    photo_events = (db.query(func.count(Event.id))
                    .filter(Event.user_id == user.id,
                            Event.source == Source.immich).scalar() or 0)
    # Anmerkung 135: wie viele unbestätigte Vorschläge aus Google/Immich gerade
    # ausgeblendet sind — der Hinweis, der stattdessen in die Moderation
    # verlinkt, braucht diese Zahl.
    machine_proposals = (db.query(func.count(Event.id))
                         .filter(Event.user_id == user.id,
                                 Event.confirmed != ConfirmState.confirmed,
                                 Event.source.in_(MACHINE_SOURCES)).scalar() or 0)
    # Anmerkung 110: Unscharf datierte Einträge sind ein ZWEITER Rückstand
    # neben den unbestätigten — und er lebte bisher nur im Verwaltungs-Reiter,
    # wo ihn niemand sucht. Bewusst eine eigene Zahl und nicht in `unconfirmed`
    # gemischt: „unbestätigt" heißt „stimmt das?", „unscharf" heißt „wann war
    # das?". Zwei Fragen, zwei Kacheln.
    # Importierte Besuche zählen nicht mit — sie sind immer exakt datiert und
    # würden die Zahl nur verwässern. Anmerkung 138: MACHINE_SOURCES statt nur
    # google_timeline.
    fuzzy = (db.query(func.count(Event.id))
             .filter(Event.user_id == user.id,
                     Event.source.notin_(MACHINE_SOURCES),
                     Event.date_start.is_(None)
                     | Event.date_precision.in_(_VAGUE_PRECISIONS)).scalar() or 0)
    # A47: Wie viele Orte noch nie nach ihren Adress-Bausteinen gefragt wurden.
    # `address IS NULL` heißt „nie nachgesehen", ein gesetztes Dict heißt
    # „nachgesehen" — auch ein leeres. Die Stufe „Ortsteil" hängt daran, und
    # ein Auswahlfeld, das nichts bewirkt, muss das sagen können (A40).
    loc_total = (db.query(func.count(Location.id))
                 .filter(Location.user_id == user.id).scalar() or 0)
    loc_open = (db.query(func.count(Location.id))
                .filter(Location.user_id == user.id,
                        Location.address.is_(None)).scalar() or 0)
    # Anmerkung 140: EINE Zeichenkette, die sich ändert, sobald sich am Bestand
    # etwas ändert. Damit kann eine Ansicht sagen „ich habe genau diesen Stand
    # schon gezeichnet" und einen teuren Abruf ganz weglassen.
    #
    # `total` allein reichte nicht: eine Änderung an einem Titel oder Ort ließe
    # die Zahl gleich, und die Karte zeigte den alten Text weiter. `max(
    # updated_at)` fängt genau das — beide zusammen fangen auch den Fall
    # „gelöscht und neu angelegt in derselben Sekunde", weil sich dann die Zahl
    # bewegt hat.
    #
    # **Bewusst kein Zeitstempel als Ablaufdatum.** Ein Cache, der nach fünf
    # Minuten verfällt, zeigt fünf Minuten lang etwas Falsches und danach etwas
    # Richtiges — beides ohne Anlass. Diese Kennung ist entweder gleich oder
    # nicht.
    touched = (db.query(func.max(Event.updated_at))
               .filter(Event.user_id == user.id).scalar())
    revision = f"{total}:{touched.isoformat() if touched else '-'}"
    return EventsIndex(
        revision=revision,
        total=total, dated=dated, undated=total - dated, unconfirmed=unconfirmed,
        visits=visits, photo_events=photo_events,
        machine_proposals=machine_proposals, fuzzy=fuzzy,
        locations_no_address=loc_open, locations_total=loc_total,
        year_min=years[0].year if years else None,
        year_max=years[-1].year if years else None,
        years=years,
        # F17 fährt hier mit: das Geburtsdatum kommt aus einem Meilenstein, der
        # in aller Regel außerhalb der geladenen Seiten liegt. Der Zeitstrahl
        # holt den Index ohnehin — so bleibt es bei einer Anfrage.
        birth=find_birth(db, user.id),
    )


# Wie viele Kartenpunkte höchstens in EINE Antwort gehen.
#
# Seit Anmerkung 139 ist jedes verortete Foto ein Ereignis — eine gewöhnliche
# Sammlung bringt damit fünfstellig viele Punkte mit, und bis hier hatte dieser
# Endpunkt gar keinen Deckel. Der Wert ist ein **Sicherheitsnetz**, keine
# Betriebsgrenze: gedeckelt wird erst dort, wo es dem Browser weh tut (die
# Zeichenlast trägt seit A45 die Leinwand statt einzelner SVG-Knoten, und das
# verschiebt die Schwelle um eine Größenordnung).
#
# Überschritten wird er nie stillschweigend: die Antwort nennt `total` neben
# `shown`, und gegriffen wird gleichmäßig über den Zeitraum statt vorne
# abzuschneiden (`sqlutil.even_spread`).
MAP_MAX_POINTS = 50000

# Anmerkung 157: die Spalten, die ein Kartenpunkt braucht — und nur die.
#
# Vorher lud der Endpunkt `Event`-OBJEKTE samt `selectinload(location)`. Bei
# 20.000 Punkten sind das 20.000 ORM-Objekte plus 20.000 Ortszeilen, für einen
# Aufruf, der nichts davon behält. Das ist die Lehre aus Anmerkung 80 in ihrer
# zweiten Auflage: der Preis ist das ERZEUGEN jeder Zeile, nicht das Finden —
# ein Index hilft dagegen nichts, eine Tupel-Abfrage alles.
_MAP_COLS = (Event.id, Event.title, Event.category, Event.date_start,
             Event.date_precision, Event.source, Event.external_id,
             Location.id.label("loc_id"), Location.name.label("loc_name"),
             Location.lat, Location.lng)


def _photo_block(rows) -> dict:
    """Foto-Punkte in ihrer kompakten Form (Anmerkung 157).

    **Ein Fotopunkt ist kein Ereignis auf der Leitung, sondern ein Punkt.**
    Gemessen bei 20.000 Ereignissen waren es 6,1 MB, weil jedes Foto sein
    volles Ereignis mitbrachte: Titel („Foto in Detmold" — auf der Karte steht
    er nirgends), Kategorie, Präzision, Quelle und einen verschachtelten Ort
    mit eigener Kennung. Anmerkung 140 hatte das gemessen und ausdrücklich
    liegen lassen; hier ist es abgeräumt.

    Gezeigt wird von einem Foto genau dreierlei: **der Punkt** (Koordinate),
    **das Bild** (Asset-Kennung fürs Vorschaubild) und **die Beschriftung im
    Popup** (Ortsname + Zeit). Dazu kommt die Kategorie, weil die Kartenleiste
    danach filtert.

    Zwei Entscheidungen, die man beim Lesen sonst für Sparsamkeit hielte:

    * **Ortsname und Kategorie werden entdoppelt.** Zwanzigtausend Fotos
      verteilen sich auf einige hundert Orte; der Name ist der längste Wert je
      Punkt und derselbe für hunderte Punkte. Er steht deshalb einmal in
      `places` und je Punkt nur sein Index.
    * **Die Ereignis-Kennung geht NICHT mit.** Sie wäre der größte Einzelposten
      (36 Zeichen je Punkt) für etwas, das die Karte nicht benutzt: das Popup
      eines Fotos zeigt das BILD, nie den Bearbeiten-Dialog (Anmerkung 139 —
      die Karte zeigt das Bild, der Zeitstrahl die Tatsache). Die Identität
      eines Fotos ist ohnehin sein Asset (`external_id` = `immich:photo:<id>`);
      wer das Ereignis dazu braucht, findet es darüber — eine Abfrage für einen
      Klick statt 20.000 Kennungen bei jedem Laden.

    Ebenso fehlt das **Wetter**: ein Foto-Popup zeigt keins, und ein Feld,
    das immer `null` ist, ist ein Versprechen ohne Deckung.
    """
    places: dict[str, int] = {}
    cats: dict[str, int] = {}
    points: list[list] = []
    for r in rows:
        pi = places.setdefault(r.loc_name or "", len(places))
        ci = cats.setdefault(r.category or "", len(cats))
        points.append([r.lat, r.lng, r.date_start.isoformat(),
                       photo_asset_of(r.external_id), pi, ci])
    return {"places": list(places), "cats": list(cats), "points": points}


@router.get("/map")
def list_map_events(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    weather: Annotated[bool, Query(
        description="Wetter mitschicken — nur für den angezeigten Zeitraum")] = False,
    machine_proposals: Annotated[bool | None, Query(
        description="Anmerkung 135: wie beim Zeitstrahl — machine_proposals=0 "
                    "lässt unbestätigte Google-/Immich-Vorschläge weg.")] = None,
    visits: Annotated[bool | None, Query(
        description="Anmerkung 139: Google-Besuche einschließen (Default: ja)")] = None,
    photos: Annotated[bool | None, Query(
        description="Anmerkung 139: Immich-Foto-Ereignisse einschließen "
                    "(Default: ja)")] = None,
    limit: Annotated[int | None, Query(ge=1, le=200000)] = None,
) -> dict:
    """Nur verortete eigene Events (mit Koordinaten) — für die Karte.

    A37: Antwortet in der schlanken Geo-Form (siehe `EventGeo`) statt mit
    vollen Ereignissen — und erst dann, wenn ihr Reiter geöffnet wird; bis A36
    hing sie am selben Aufruf wie der Zeitstrahl und verlängerte den Start.

    `weather` ist bewusst abschaltbar und standardmäßig AUS: gemessen bei
    12.000 Punkten macht es aus 205 Byte je Punkt 799 — es ist der größte
    Einzelposten der Antwort. Die Karte holt deshalb erst alle Punkte ohne
    Wetter (Zeitraum-Regler, Bündelung, Marker) und danach das Wetter nur für
    den angezeigten Zeitraum, wo Popup und Stopp-Liste es wirklich zeigen.

    **Anmerkung 139 — zwei Schalter, zwei Filter, ein Deckel.** `visits` und
    `photos` sind getrennt, weil sie in der Oberfläche getrennte Schalter sind
    (🛰️ Google, 📷 Immich). Sie hier zu beantworten und nicht im Browser ist
    nicht Bequemlichkeit: ein ausgeschalteter Foto-Schalter soll die 20.000
    Punkte gar nicht erst über die Leitung schicken.

    **Anmerkung 157 — zwei Formen in einer Antwort.** `events` sind Pins (Titel,
    Kategorie, Datum, Ort, Wetter — alles davon steht im Popup oder in der
    Stopp-Liste), `photos` sind Punkte in kompakter Form (siehe `_photo_block`).
    Das ist kein Sonderfall, sondern die Trennung aus Anmerkung 139 eine Schicht
    tiefer: Foto und Ereignis sind auf der Karte schon zwei Darstellungen, und
    eine Darstellung, die vier Werte zeigt, muss nicht zwölf holen.
    """
    query = (db.query(*_MAP_COLS)
             .select_from(Event)
             .join(Location, Event.location_id == Location.id)
             .filter(Event.user_id == user.id, Event.location_id.isnot(None),
                     Location.lat.isnot(None), Event.date_start.isnot(None)))
    if date_from is not None:
        query = query.filter(Event.date_start >= date_from)
    if date_to is not None:
        query = query.filter(Event.date_start <= date_to)
    if machine_proposals is False:
        query = query.filter(~((Event.confirmed != ConfirmState.confirmed)
                               & Event.source.in_(MACHINE_SOURCES)))
    hidden = _hidden_sources(visits, photos)
    if hidden:
        query = query.filter(Event.source.notin_(hidden))

    cap = limit or MAP_MAX_POINTS
    total = query.count()
    if total <= cap:
        rows = query.order_by(Event.date_start.asc(), Event.id.asc()).all()
    else:
        # **Deckeln heißt nicht abschneiden.** `LIMIT 50000` über eine
        # Bibliothek von 2009 bis heute lieferte die Jahre bis etwa 2019 und
        # ließe alles danach von der Karte verschwinden, während sie voll
        # aussieht (dieselbe Regel wie bei den Wegen und bei A45).
        #
        # Der Deckel gilt über BEIDE Formen zusammen — er ist eine Aussage über
        # die Karte, nicht über eine Ebene. Zwei getrennte Deckel wären zwei
        # Hinweise, und der Nutzer sieht eine Karte.
        rows = even_spread(db, Event, query, Event.id, Event.date_start,
                           cap, total, selection=_MAP_COLS)
    # Über den NAMEN und nicht über die Position: `Location.id` trägt deshalb
    # ein Label, damit `r.id` eindeutig das Ereignis meint. Ein `r[5]` wäre
    # genau die Zeile, die beim nächsten Spaltenwunsch still das Falsche liest.
    pins = [r for r in rows if r.source != Source.immich]
    photo_rows = [r for r in rows if r.source == Source.immich]
    wx = (_weather_for(db, user.id, [r.id for r in pins]) if weather
          else [None] * len(pins))
    return {
        "total": total,
        "shown": len(rows),
        "events": [
            EventGeo(
                id=r.id, title=r.title, category=r.category,
                date_start=r.date_start, date_precision=r.date_precision,
                source=r.source,
                location=LocationGeo(id=r.loc_id, name=r.loc_name,
                                     lat=r.lat, lng=r.lng),
                weather=w,
            ).model_dump(mode="json")
            for r, w in zip(pins, wx)
        ],
        # Anmerkung 157: die Fotos in kompakter Form. Getrennt und nicht als
        # zwölftes Feld an jedem Punkt — der Unterschied ist 4,0 MB.
        "photos": _photo_block(photo_rows),
    }


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
