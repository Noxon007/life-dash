"""Anmerkung 140 — die Bestandskennung, an der eine Ansicht ihren Abruf spart.

Gemeldet als „Kann man Anzeigen vorrechnen? Warum muss er beim Starten alles
laden?". **Gemessen an 20.000 Ereignissen lädt der Start gar nicht alles**:
neun Anfragen, 86 ms, 11 kB — das ist A37, und daran war nichts zu verbessern.
Teuer ist die KARTE mit 631 ms und 6,1 MB, und zwar bei jedem Öffnen des
Reiters, auch wenn sich nichts geändert hat.

`revision` ist der Riegel davor. Er muss zwei Dinge können, und beide sind
leicht zu verlieren:

* **gleich bleiben**, solange sich nichts ändert — sonst spart er nie etwas,
* **sich ändern**, sobald sich etwas ändert — sonst zeigt die Karte alte
  Titel, und das ist schlimmer als ein langsamer Abruf.

Der zweite Fall ist der, an dem eine naheliegende Fassung scheitert: `total`
allein bliebe bei einer Umbenennung gleich.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Event, Location, Source,
                        User, UserRole)
from app.routers.events import events_index


def _event(db, user, title="Konzert", day=12) -> Event:
    ev = Event(user_id=user.id, title=title, category="event",
               date_start=datetime(2024, 7, day), date_precision=DatePrecision.day,
               source=Source.manual, confirmed=ConfirmState.confirmed)
    db.add(ev)
    db.commit()
    return ev


def _rev(db, user) -> str:
    return events_index(db=db, user=user).revision


def test_the_revision_is_stable_while_nothing_changes(db, user):
    _event(db, user)
    first = _rev(db, user)
    assert first
    assert _rev(db, user) == first, (
        "eine Kennung, die sich von selbst ändert, spart nie einen Abruf")


def test_a_new_event_changes_it(db, user):
    _event(db, user)
    before = _rev(db, user)
    _event(db, user, title="Zweites")
    assert _rev(db, user) != before


def test_a_deleted_event_changes_it(db, user):
    ev = _event(db, user)
    _event(db, user, title="Bleibt")
    before = _rev(db, user)
    db.delete(ev)
    db.commit()
    assert _rev(db, user) != before


def test_a_RENAMED_event_changes_it(db, user):
    """**Der Fall, an dem `total` allein scheitert.**

    Die Zahl bleibt gleich, der Titel nicht — und genau der steht auf der
    Karte. Eine Ansicht, die hier nicht neu lädt, zeigt einen Namen, den es
    nicht mehr gibt, und zwar bis zum nächsten Neustart.
    """
    ev = _event(db, user)
    before = _rev(db, user)
    ev.title = "Anders"
    db.commit()
    assert _rev(db, user) != before, (
        "`updated_at` muss mitzählen — sonst bleibt eine Umbenennung unsichtbar")


def test_a_moved_event_changes_it(db, user):
    """Auch der Ort steht auf der Karte."""
    loc = Location(user_id=user.id, name="Detmold", lat=51.9, lng=8.8)
    db.add(loc)
    db.flush()
    ev = _event(db, user)
    before = _rev(db, user)
    ev.location = loc
    db.commit()
    assert _rev(db, user) != before


def test_an_empty_database_still_answers(db, user):
    """Ohne Ereignisse gibt es keine Kennung zu bilden — aber eine Antwort.

    `max(updated_at)` ist dann NULL, und eine Kennung, die daran stirbt, macht
    aus einem leeren Konto einen Fehler beim Start.
    """
    rev = _rev(db, user)
    assert isinstance(rev, str) and rev


def test_other_accounts_do_not_move_it(db, user):
    """Sonst lädt die Karte bei jedem fremden Schreibvorgang neu — auf einer
    Instanz mit zwei Konten wäre der Riegel damit wirkungslos (A12)."""
    other = User(oidc_subject="other", email="o@example.org",
                 display_name="Andere", role=UserRole.user)
    db.add(other)
    db.commit()
    _event(db, user)
    before = _rev(db, user)
    _event(db, other, title="Fremdes")
    assert _rev(db, user) == before
