"""F7 in Serie — alle mehrtägigen Ereignisse auf einmal aufteilen (Anm. 113).

Aus dem Betrieb: Seit Immich Alben vorschlägt, entstehen mehrtägige Einträge in
Serie, und jeder einzelne wollte von Hand aufgeteilt werden. Der Sammelknopf
schreibt **vervielfacht** in die Lebensdatenbank — deshalb prüft diese Datei
vor allem, was er NICHT tut.
"""
from __future__ import annotations

from datetime import datetime

from app.models import ConfirmState, DatePrecision, Event, Source
from app.routers.events import (BULK_DAY_SPAN, create_day_children,
                                day_children_for_all, day_children_pending)


def _ev(db, user, title, start, end, *, precision=DatePrecision.day,
        confirmed=ConfirmState.confirmed, source=Source.manual) -> Event:
    event = Event(user_id=user.id, title=title, category="trip",
                  date_start=start, date_end=end, date_precision=precision,
                  confirmed=confirmed, source=source, confidence=1.0)
    db.add(event)
    db.commit()
    return event


def test_bulk_split_creates_the_days_it_announced(db, user):
    _ev(db, user, "Urlaub auf Mallorca",
        datetime(2005, 7, 23), datetime(2005, 8, 5))
    _ev(db, user, "Wochenende Kreta", datetime(2019, 8, 3), datetime(2019, 8, 5))

    plan = day_children_pending(db=db, user=user)
    assert (plan["events"], plan["days"]) == (2, 17)     # 14 + 3

    done = day_children_for_all(db=db, user=user)
    assert (done["events"], done["created"]) == (2, 17)
    kids = db.query(Event).filter(Event.parent_event_id.isnot(None)).all()
    assert len(kids) == 17
    assert all(k.date_precision == DatePrecision.day for k in kids)
    assert {k.title for k in kids} >= {"Wochenende Kreta — Tag 1",
                                       "Wochenende Kreta — Tag 3"}


def test_pressing_twice_creates_nothing_twice(db, user):
    _ev(db, user, "Kreta", datetime(2019, 8, 3), datetime(2019, 8, 5))
    day_children_for_all(db=db, user=user)
    again = day_children_for_all(db=db, user=user)
    assert again["created"] == 0
    assert db.query(Event).filter(Event.parent_event_id.isnot(None)).count() == 3


def test_gaps_are_filled_and_the_numbering_survives(db, user):
    """Der Einzelknopf hat schon Tag 1 angelegt. Der Sammellauf füllt den Rest —
    und Tag 3 muss Tag 3 heißen, nicht Tag 1. Die Nummer kommt aus der Spanne,
    nicht aus der Reihenfolge des Anlegens."""
    parent = _ev(db, user, "Kreta", datetime(2019, 8, 3), datetime(2019, 8, 5))
    db.add(Event(user_id=user.id, title="Kreta — Tag 1", category="trip",
                 date_start=datetime(2019, 8, 3), date_end=datetime(2019, 8, 3),
                 date_precision=DatePrecision.day, source=Source.manual,
                 confirmed=ConfirmState.confirmed, parent_event_id=parent.id))
    db.commit()

    assert day_children_pending(db=db, user=user)["days"] == 2
    day_children_for_all(db=db, user=user)
    titles = sorted(e.title for e in db.query(Event)
                    .filter(Event.parent_event_id == parent.id).all())
    assert titles == ["Kreta — Tag 1", "Kreta — Tag 2", "Kreta — Tag 3"]


def test_vague_dates_are_never_split(db, user):
    """„Sommer 2002" trägt eine Spanne über Monate. 92 Tages-Einträge daraus
    behaupteten eine Genauigkeit, die die Angabe selbst dementiert — dieselbe
    Regel wie in F14 und F1."""
    _ev(db, user, "Sommer 2002", datetime(2002, 6, 1), datetime(2002, 8, 31),
        precision=DatePrecision.season)

    plan = day_children_pending(db=db, user=user)
    assert plan["events"] == 0 and plan["vague"] == 1
    assert day_children_for_all(db=db, user=user)["created"] == 0


def test_unconfirmed_proposals_are_never_split(db, user):
    """Kinder erben die Bestätigung. Einen Vorschlag aufzuteilen würde die
    Moderations-Warteschlange vervielfachen, statt sie abzuarbeiten."""
    _ev(db, user, "Mallorca_2005", datetime(2005, 7, 23), datetime(2005, 8, 5),
        confirmed=ConfirmState.unconfirmed, source=Source.immich)

    assert day_children_pending(db=db, user=user)["events"] == 0
    assert day_children_for_all(db=db, user=user)["created"] == 0


def test_long_spans_are_left_to_a_deliberate_single_decision(db, user):
    """Anmerkung 87: Tausende leere Container, die jede Aggregation wieder
    ausfiltern muss. EIN „Auslandsjahr" ergäbe 365 Zeilen — das bleibt eine
    Einzelentscheidung, und der Sammelknopf SAGT, dass er es ausgelassen hat."""
    _ev(db, user, "Auslandsjahr", datetime(2011, 1, 1), datetime(2011, 12, 31))

    plan = day_children_pending(db=db, user=user)
    assert plan["events"] == 0
    assert plan["too_long_count"] == 1
    assert plan["too_long"][0]["title"] == "Auslandsjahr"
    assert day_children_for_all(db=db, user=user)["created"] == 0

    # Ausdrücklich gewollt geht es weiterhin — über den Einzelknopf.
    event = db.query(Event).filter(Event.title == "Auslandsjahr").one()
    assert len(create_day_children(event_id=event.id, db=db, user=user)) == 365


def test_the_run_is_not_capped_by_the_display_limit(db, user):
    """Die Anzeige deckelt bei 60 — der Lauf darf das nicht tun. Ein Knopf,
    der sechzig anlegt und über den Rest schweigt, wäre genau die Stille,
    die dieses Projekt jagt."""
    for i in range(70):
        _ev(db, user, f"Reise {i}", datetime(2020, 1, 1), datetime(2020, 1, 3))

    plan = day_children_pending(db=db, user=user)
    assert plan["events"] == 70 and len(plan["list"]) == 60 and plan["more"] == 10
    assert day_children_for_all(db=db, user=user)["created"] == 210


def test_other_users_events_stay_untouched(db, user):
    """A12: in JEDER Abfrage."""
    from app.models import User, UserRole

    other = User(oidc_subject="other", email="o@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    db.add(Event(user_id=other.id, title="Fremde Reise", category="trip",
                 date_start=datetime(2020, 5, 1), date_end=datetime(2020, 5, 4),
                 date_precision=DatePrecision.day, source=Source.manual,
                 confirmed=ConfirmState.confirmed))
    db.commit()

    assert day_children_pending(db=db, user=user)["events"] == 0
    assert day_children_for_all(db=db, user=user)["created"] == 0


def test_span_limit_is_adjustable(db, user):
    """Der Deckel ist eine Voreinstellung, keine Mauer — wer 90 Tage will,
    stellt 90 ein und sieht vorher, was daraus wird."""
    _ev(db, user, "Interrail", datetime(2018, 6, 1), datetime(2018, 7, 15))
    assert day_children_pending(db=db, user=user)["events"] == 0
    assert day_children_pending(db=db, user=user, max_span=60)["events"] == 1
    assert BULK_DAY_SPAN < 45 <= 60
    assert day_children_for_all(db=db, user=user, max_span=60)["created"] == 45
