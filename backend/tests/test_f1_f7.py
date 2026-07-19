"""Tests für 0.15.0: F1 (Reisetagebuch: note-Feld, journal-Kategorie) und
F7 (Mehrtages-Events mit Tages-Unterereignissen). Offline."""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException

from app.models import ConfirmState, DatePrecision, Event, Location, Source
from app.routers.events import create_day_children, create_event
from app.routers.moderation import discard_event
from app.schemas import EventManualCreate


def _trip(db, user, days: int = 3, confirmed: bool = True, location=None) -> Event:
    ev = Event(
        user_id=user.id, title="Mallorca", category="trip",
        date_start=datetime(2026, 7, 5), date_end=datetime(2026, 7, 4 + days),
        date_precision=DatePrecision.day,
        confirmed=ConfirmState.confirmed if confirmed else ConfirmState.unconfirmed,
        confirmed_by="manual" if confirmed else None,
        source=Source.manual, location=location,
    )
    db.add(ev)
    db.commit()
    return ev


# --------------------------------------------------------------------------- #
# F7 — Tages-Unterereignisse
# --------------------------------------------------------------------------- #
def test_day_children_created_with_inheritance(db, user):
    loc = Location(user_id=user.id, name="Mallorca", lat=39.6, lng=2.9)
    db.add(loc)
    db.flush()
    parent = _trip(db, user, days=3, location=loc)

    created = create_day_children(parent.id, db=db, user=user)
    assert len(created) == 3
    assert [c.title for c in created] == [
        "Mallorca — Tag 1", "Mallorca — Tag 2", "Mallorca — Tag 3"]
    for i, c in enumerate(created):
        assert c.parent_event_id == parent.id
        assert c.date_precision == DatePrecision.day
        assert c.date_start.date() == datetime(2026, 7, 5 + i).date()
        assert c.confirmed == ConfirmState.confirmed      # erbt Bestätigung
        assert c.location.id == loc.id                    # erbt den Ort


def test_day_children_idempotent(db, user):
    parent = _trip(db, user, days=3)
    create_day_children(parent.id, db=db, user=user)
    again = create_day_children(parent.id, db=db, user=user)
    assert again == []  # zweiter Lauf legt nichts doppelt an
    assert db.query(Event).filter(Event.parent_event_id == parent.id).count() == 3


def test_day_children_rejects_single_day_and_nesting(db, user):
    single = Event(user_id=user.id, title="Tagesausflug",
                   date_start=datetime(2026, 7, 5), date_end=datetime(2026, 7, 5))
    db.add(single)
    db.commit()
    with pytest.raises(HTTPException):
        create_day_children(single.id, db=db, user=user)

    parent = _trip(db, user, days=2)
    child = create_day_children(parent.id, db=db, user=user)[0]
    with pytest.raises(HTTPException):  # Kinder bekommen keine eigenen Kinder
        create_day_children(child.id, db=db, user=user)


def test_delete_parent_keeps_or_removes_children(db, user):
    parent = _trip(db, user, days=2)
    create_day_children(parent.id, db=db, user=user)

    # Ohne with_children: Kinder werden abgehängt und bleiben erhalten
    discard_event(parent.id, with_children=False, db=db, user=user)
    orphans = db.query(Event).all()
    assert len(orphans) == 2
    assert all(e.parent_event_id is None for e in orphans)

    parent2 = _trip(db, user, days=2)
    create_day_children(parent2.id, db=db, user=user)
    discard_event(parent2.id, with_children=True, db=db, user=user)
    assert db.query(Event).filter(Event.parent_event_id == parent2.id).count() == 0
    assert db.get(Event, parent2.id) is None


# --------------------------------------------------------------------------- #
# F1 — Tagebuch: note wandert bei manueller Eingabe mit (KI-frei)
# --------------------------------------------------------------------------- #
def test_manual_event_stores_journal_note(db, user):
    payload = EventManualCreate(
        title="Tagebuch — 05.07.2026", category="journal",
        date_start=datetime(2026, 7, 5), date_end=datetime(2026, 7, 5),
        note="**Toller Tag** am Meer\n- Schnorcheln\n- Paella",
    )
    result = create_event(payload, db=db, user=user)
    stored = db.get(Event, result.id)
    assert stored.category == "journal"
    assert stored.note.startswith("**Toller Tag**")
    assert stored.confirmed == ConfirmState.confirmed
