"""Suche: serverseitige Volltextsuche (Entscheidung 2026-07-24, Feedback-Runde).

Die semantische (Embedding-)Suche wurde entfernt — sie kostete einen KI-Dienst,
lud zum Suchen ALLE embeddeten Events in den Prozess und riss bei einem Ausfall
des Embed-Dienstes die ganze Antwort mit (das gemeldete „Server-Suche nicht
erreichbar"). Geprüft wird jetzt: Volltext findet über Titel, Beschreibung,
Ortsname UND Entity-Name, bleibt aufs eigene Konto begrenzt, und braucht
KEINEN KI-Provider.
"""
from __future__ import annotations

from datetime import datetime

from app.models import (ConfirmState, DatePrecision, Entity, Event,
                        EventEntityLink, Location, Source, User, UserRole)
from app.routers.search import search


def _event(db, user, title, *, desc=None, loc_name=None, ent_name=None,
           day=1) -> Event:
    loc = None
    if loc_name:
        loc = Location(user_id=user.id, name=loc_name, lat=53.5, lng=10.0)
        db.add(loc)
        db.flush()
    e = Event(user_id=user.id, title=title, description=desc, category="event",
              location=loc, date_start=datetime(2024, 6, day),
              date_precision=DatePrecision.day, source=Source.manual,
              confirmed=ConfirmState.confirmed)
    db.add(e)
    db.flush()
    if ent_name:
        ent = Entity(user_id=user.id, type="person", name=ent_name,
                     confirmed=ConfirmState.confirmed)
        db.add(ent)
        db.flush()
        db.add(EventEntityLink(event_id=e.id, entity_id=ent.id))
    db.commit()
    return e


def _ids(rows) -> set[str]:
    return {r.id for r in rows}


def test_finds_across_all_four_fields(db, user):
    by_title = _event(db, user, "Konzert in der Elphi", day=1)
    by_desc = _event(db, user, "Abend", desc="Wir hörten ein Konzert", day=2)
    by_loc = _event(db, user, "Spaziergang", loc_name="Konzerthaus", day=3)
    by_ent = _event(db, user, "Treffen", ent_name="Konzertmeister Meyer", day=4)
    _event(db, user, "Frühstück", desc="nichts davon", day=5)

    hits = search(q="konzert", limit=50, db=db, user=user)
    assert _ids(hits) == {by_title.id, by_desc.id, by_loc.id, by_ent.id}


def test_case_insensitive_and_partial(db, user):
    e = _event(db, user, "Geburtstag von Anna")
    assert e.id in _ids(search(q="GEBURT", limit=50, db=db, user=user))


def test_scoped_to_user(db, user):
    mine = _event(db, user, "Mein Konzert")
    other = User(oidc_subject="other-sub", email="other@example.org",
                 display_name="Andere", role=UserRole.user)
    db.add(other)
    db.commit()
    theirs = _event(db, other, "Fremdes Konzert")

    hits = _ids(search(q="konzert", limit=50, db=db, user=user))
    assert mine.id in hits
    assert theirs.id not in hits


def test_works_without_ai_provider(db, user, monkeypatch):
    """Kein KI-Aufruf mehr: würde einer versucht, flöge dieser Test."""
    def _boom(*a, **k):
        raise AssertionError("Suche darf keinen KI-Provider aufrufen")
    monkeypatch.setattr("app.ai.get_provider", _boom)

    e = _event(db, user, "Reise nach Rom")
    assert e.id in _ids(search(q="rom", limit=50, db=db, user=user))


def test_newest_first(db, user):
    old = _event(db, user, "Konzert alt", day=1)
    new = _event(db, user, "Konzert neu", day=28)
    hits = search(q="konzert", limit=50, db=db, user=user)
    assert [h.id for h in hits][:2] == [new.id, old.id]
