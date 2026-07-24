"""Tests für Anmerkung 135: unbestätigte Vorschläge aus Google/Immich
(MACHINE_SOURCES) sind Beleg, kein Ereignis — sie tauchen im Zeitstrahl und
auf der Karte erst nach der Bestätigung in der Moderation auf.

Zwei Dinge müssen bewiesen werden:
1. `machine_proposals=0` blendet genau diese Zeilen aus /api/events UND
   /api/events/map aus — ohne Angabe bleibt alles drin (Export, Moderation,
   Altpfade unberührt).
2. Unbestätigte Einträge aus NICHT-maschinellen Quellen (P5.1/F1: eigene,
   KI-geparste Erfassung) bleiben davon unberührt — das ist eine andere
   Frage ("stimmt das, was ich diktiert habe?" statt "ist das überhaupt ein
   Ereignis?").
"""
from __future__ import annotations

from datetime import datetime

from app.models import ConfirmState, DatePrecision, Event, Location, Source
from app.routers.events import events_index, list_events, list_map_events


def _event(db, user, title="x", *, when=None, loc=None, confirmed=True,
           source=Source.manual) -> Event:
    e = Event(user_id=user.id, title=title, category="event",
              date_start=when, date_precision=DatePrecision.day,
              location=loc, source=source,
              confirmed=ConfirmState.confirmed if confirmed
              else ConfirmState.unconfirmed)
    db.add(e)
    db.commit()
    return e


def _loc(db, user, name="Ort", lat=53.5, lng=10.0) -> Location:
    loc = Location(user_id=user.id, name=name, lat=lat, lng=lng)
    db.add(loc)
    db.commit()
    return loc


def test_unconfirmed_machine_proposals_are_filtered_in_timeline(db, user):
    _event(db, user, "34 Fotos in Detmold", when=datetime(2024, 6, 1),
           confirmed=False, source=Source.immich)
    _event(db, user, "Besuch: Zuhause", when=datetime(2024, 6, 1),
           confirmed=False, source=Source.google_timeline)
    _event(db, user, "Konzert", when=datetime(2024, 6, 2), confirmed=True)

    page = list_events(db=db, user=user, slim=True, limit=10,
                       machine_proposals=False)
    assert [e.title for e in page] == ["Konzert"]
    # Ohne Angabe bleibt alles drin — Export, Moderation und Altpfade
    # unberührt.
    assert len(list_events(db=db, user=user, slim=True)) == 3
    assert len(list_events(db=db, user=user, slim=True,
                           machine_proposals=True)) == 3


def test_own_unconfirmed_entries_stay_visible(db, user):
    """P5.1/F1: eine KI-geparste, noch ungeprüfte eigene Erfassung ist kein
    maschineller Fund — sie bleibt inline sichtbar, auch mit
    machine_proposals=0."""
    _event(db, user, "Vielleicht Zahnarzt", when=datetime(2024, 6, 1),
           confirmed=False, source=Source.ai)

    page = list_events(db=db, user=user, slim=True,
                       machine_proposals=False)
    assert [e.title for e in page] == ["Vielleicht Zahnarzt"]


def test_map_filters_unconfirmed_machine_proposals_too(db, user):
    loc = _loc(db, user)
    _event(db, user, "Fototag", when=datetime(2024, 6, 1), loc=loc,
           confirmed=False, source=Source.immich)
    _event(db, user, "Konzert", when=datetime(2024, 6, 2), loc=loc,
           confirmed=True)

    points = list_map_events(db=db, user=user, machine_proposals=False)
    assert [p.title for p in points] == ["Konzert"]
    assert len(list_map_events(db=db, user=user)) == 2


def test_index_counts_pending_machine_proposals(db, user):
    _event(db, user, "Fototag 1", when=datetime(2024, 6, 1),
           confirmed=False, source=Source.immich)
    _event(db, user, "Fototag 2", when=datetime(2024, 6, 2),
           confirmed=False, source=Source.immich)
    _event(db, user, "Besuch", when=datetime(2024, 6, 3),
           confirmed=False, source=Source.google_timeline)
    # zählt nicht mit: weder maschinell noch unbestätigt
    _event(db, user, "Eigene Notiz", when=datetime(2024, 6, 4),
           confirmed=False, source=Source.ai)
    _event(db, user, "Konzert", when=datetime(2024, 6, 5), confirmed=True,
           source=Source.immich)

    assert events_index(db=db, user=user).machine_proposals == 3
