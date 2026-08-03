"""Anmerkung 148 — im Kompendium führen die TAGE.

Die Sammlung zählte bis hierher Einträge. Nach einem Timeline-Import ist das
eine Aussage über den Import: „Deutschland — 11.203 Einträge" heißt, dass
Google 11.203 Besuche geliefert hat, nicht, dass jemand 11.203 mal dort war.
Dieselbe Umstellung hat Anmerkung 143 für Welt, Top-Orte und Städte gemacht;
hier zieht der Rest der Sammlung nach, damit nicht zwei Kacheln derselben Wand
zwei verschiedene Dinge zählen (Anmerkung 106).

Beide Zahlen bleiben stehen. „47 Tage · 312 Einträge" beantwortet beide Fragen;
nur die Tage zu liefern hieße, die andere unbeantwortbar zu machen.

Geprüft werden die drei Stellen, an denen so eine Zahl still falsch wird:
die Verdichtung über mehrere Ereignisse desselben Tages, der äußere Join (eine
Entity ohne Ereignisse muss in der Liste BLEIBEN) und der Besitzfilter.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Entity, Event,
                        EventEntityLink, Source, User, UserRole)
from app.routers.modules import compendium


@pytest.fixture()
def other_user(db):
    u = User(oidc_subject="other-sub", email="other@example.org",
             display_name="Zweitnutzer", role=UserRole.user)
    db.add(u)
    db.commit()
    return u


def _entity(db, user, name, type_="country"):
    e = Entity(user_id=user.id, type=type_, name=name)
    db.add(e)
    db.flush()
    return e


def _linked(db, user, entity, when, title="Besuch"):
    ev = Event(user_id=user.id, title=title, category="event",
               date_start=when, date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.google_timeline)
    db.add(ev)
    db.flush()
    db.add(EventEntityLink(event_id=ev.id, entity_id=entity.id))
    db.flush()
    return ev


def _by_name(rows):
    return {r.name: r for r in rows}


def test_days_condense_several_entries_of_one_day(db, user):
    """**Der eigentliche Punkt.** Zwölf importierte Besuche an einem Tag sind
    EIN Tag — dieselbe Regel wie A31/Anmerkung 64 beim Wetter und Anmerkung 143
    bei den Städten."""
    land = _entity(db, user, "Deutschland")
    for hour in range(12):
        _linked(db, user, land, datetime(2024, 7, 12, hour))
    _linked(db, user, land, datetime(2024, 7, 13, 9))
    db.commit()

    row = _by_name(compendium("country", db=db, user=user))["Deutschland"]
    assert row.day_count == 2
    assert row.event_count == 13, "die Einträge müssen daneben stehen bleiben"


def test_an_entity_without_events_stays_in_the_list(db, user):
    """Der äußere Join ist die Falle: wird der Besitzfilter als WHERE-Bedingung
    geschrieben statt in die JOIN-Bedingung, verschwinden genau die Einträge,
    an denen noch nichts hängt — und das sind die, die man bestätigen will."""
    _entity(db, user, "Andorra")
    db.commit()

    rows = _by_name(compendium("country", db=db, user=user))
    assert "Andorra" in rows
    assert rows["Andorra"].day_count == 0
    assert rows["Andorra"].event_count == 0


def test_undated_events_count_as_entries_but_not_as_days(db, user):
    """„Irgendwann in den Neunzigern" ist ein Eintrag und kein Kalendertag.
    Deshalb gibt es zwei Zahlen und nicht eine."""
    land = _entity(db, user, "Peru")
    ev = Event(user_id=user.id, title="Irgendwann", category="event",
               date_start=None, date_precision=DatePrecision.year,
               confirmed=ConfirmState.confirmed, source=Source.manual)
    db.add(ev)
    db.flush()
    db.add(EventEntityLink(event_id=ev.id, entity_id=land.id))
    # Ein datiertes daneben — sonst wäre die Zusicherung „0 Tage" auch dann
    # grün, wenn gar keine Tage gezählt werden (Anmerkung 108).
    _linked(db, user, land, datetime(2019, 8, 4))
    db.commit()

    row = _by_name(compendium("country", db=db, user=user))["Peru"]
    assert row.event_count == 2
    assert row.day_count == 1


def test_other_accounts_do_not_add_days(db, user, other_user):
    """Der Zugriffsschutz sitzt an der Entity — aber gezählt werden Ereignisse,
    und die haben ihren eigenen Besitzer. Ohne den Filter in der JOIN-Bedingung
    zählten fremde Zeilen mit."""
    land = _entity(db, user, "Island")
    _linked(db, user, land, datetime(2024, 3, 1))
    # Ein fremdes Ereignis, das auf dieselbe Entity zeigt.
    ev = Event(user_id=other_user.id, title="Fremd", category="event",
               date_start=datetime(2024, 6, 1), date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.manual)
    db.add(ev)
    db.flush()
    db.add(EventEntityLink(event_id=ev.id, entity_id=land.id))
    db.commit()

    row = _by_name(compendium("country", db=db, user=user))["Island"]
    assert row.day_count == 1
    assert row.event_count == 1


def test_the_same_day_through_two_links_counts_once(db, user):
    """Zwei Verknüpfungen auf dasselbe Ereignis (z. B. `subject` und
    `location`) sind ein Ereignis. `count(EventEntityLink.id)` hätte hier zwei
    gezählt — eine Zahl, die mit der Rolle wächst statt mit dem Leben."""
    land = _entity(db, user, "Malta")
    ev = _linked(db, user, land, datetime(2024, 5, 5))
    db.add(EventEntityLink(event_id=ev.id, entity_id=land.id, role="location"))
    db.commit()

    row = _by_name(compendium("country", db=db, user=user))["Malta"]
    assert row.day_count == 1
    assert row.event_count == 1


def test_days_are_counted_per_entity_not_across_the_type(db, user):
    """Eine Gruppierung, die aus Versehen über den ganzen Typ zählt, sieht bei
    einem Eintrag richtig aus und bei zweien nie wieder."""
    a = _entity(db, user, "Nepal")
    b = _entity(db, user, "Bhutan")
    _linked(db, user, a, datetime(2024, 1, 1))
    _linked(db, user, a, datetime(2024, 1, 2))
    _linked(db, user, b, datetime(2024, 1, 3))
    db.commit()

    rows = _by_name(compendium("country", db=db, user=user))
    assert rows["Nepal"].day_count == 2
    assert rows["Bhutan"].day_count == 1
