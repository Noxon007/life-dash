"""A41 — die Städte werden aufmachbar (Anmerkungen 94/95).

A39 hat `Location.city` geliefert, die Statistik und die Verdichtung. Was
fehlte, war die Auswahl: man konnte „87 Städte" sehen und keine einzige davon
öffnen. Hier steht der serverseitige Teil davon — die Städte-Liste des
Kompendiums und der Stadtfilter, der aus ihr heraus gerufen wird.

Der Filter selbst gibt es seit A39 (zum Aufklappen einer Sammelkarte); geprüft
wird hier, dass er auch als eigenständige Auswahl trägt. Warum serverseitig:
A37 — wer über den GESAMTEN Bestand auswählt, fragt den Server; ein Filter über
das geladene Fenster fände nur, was zufällig schon da ist.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Event, Location, Source,
                        User, UserRole)
from app.routers.events import list_events
from app.routers.modules import cities


@pytest.fixture()
def other_user(db):
    u = User(oidc_subject="other-sub", email="other@example.org",
             display_name="Zweitnutzer", role=UserRole.user)
    db.add(u)
    db.commit()
    return u


def _loc(db, user, name, city, country=None, lat=51.2, lng=6.7):
    loc = Location(user_id=user.id, name=name, lat=lat, lng=lng,
                   city=city, country=country)
    db.add(loc)
    db.flush()
    return loc


def _visit(db, user, loc, when, title="Besuch"):
    ev = Event(user_id=user.id, title=title, category="event",
               date_start=when, date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, confirmed_by="import",
               source=Source.google_timeline, location=loc)
    db.add(ev)
    db.flush()
    return ev


# --------------------------------------------------------------------------- #
# Die Liste
# --------------------------------------------------------------------------- #
def test_cities_aggregate_across_places(db, user):
    """Der Kern: drei Straßen einer Stadt sind EIN Kompendium-Eintrag — genau
    die Zusammenfassung, die über `Location.name` nicht möglich war."""
    for i, street in enumerate(["Kaiserstraße", "Bilker Allee", "Ratinger Str."]):
        loc = _loc(db, user, f"{street}, Düsseldorf", "Düsseldorf",
                   country="Deutschland", lat=51.2 + i / 100)
        _visit(db, user, loc, datetime(2020 + i, 7, 1))
    db.commit()

    rows = cities(db=db, user=user)
    assert len(rows) == 1
    c = rows[0]
    assert c.name == "Düsseldorf"
    assert c.event_count == 3
    assert c.place_count == 3        # drei Orte, eine Stadt
    assert c.country == "Deutschland"
    assert c.first_visit.year == 2020 and c.last_visit.year == 2022


def test_cityless_places_are_not_a_city(db, user):
    """NULL heißt „nie nachgesehen", "" heißt „nachgesehen, keine da" (A39) —
    keines von beidem ist eine Stadt, und ein leerer Eintrag im Kompendium wäre
    schlimmer als gar keiner."""
    _visit(db, user, _loc(db, user, "Waldweg", ""), datetime(2021, 5, 1))
    _visit(db, user, _loc(db, user, "Ort (1,2)", None, lat=1, lng=2),
           datetime(2021, 5, 2))
    _visit(db, user, _loc(db, user, "Markt, Detmold", "Detmold", lat=51.9),
           datetime(2021, 5, 3))
    db.commit()

    assert [c.name for c in cities(db=db, user=user)] == ["Detmold"]


def test_cities_are_sorted_and_placeless_cities_absent(db, user):
    """Eine Stadt ohne ein einziges Ereignis ist keine besuchte Stadt — der
    Ortsnamen-Lauf legt Orte an, die (noch) an nichts hängen."""
    _loc(db, user, "Straße, Aachen", "Aachen", lat=50.7, lng=6.0)   # ohne Event
    _visit(db, user, _loc(db, user, "Markt, Zwickau", "Zwickau", lat=50.7),
           datetime(2021, 1, 1))
    _visit(db, user, _loc(db, user, "Markt, Bonn", "Bonn", lat=50.7, lng=7.1),
           datetime(2021, 1, 2))
    db.commit()

    assert [c.name for c in cities(db=db, user=user)] == ["Bonn", "Zwickau"]


def test_cities_are_per_user(db, user, other_user):
    _visit(db, user, _loc(db, user, "Markt, Detmold", "Detmold"),
           datetime(2021, 1, 1))
    foreign = Location(user_id=other_user.id, name="Markt, Kyoto",
                       lat=35.0, lng=135.7, city="Kyoto")
    db.add(foreign)
    db.flush()
    db.add(Event(user_id=other_user.id, title="Besuch", category="event",
                 date_start=datetime(2021, 1, 1), date_precision=DatePrecision.day,
                 confirmed=ConfirmState.confirmed, location=foreign))
    db.commit()

    assert [c.name for c in cities(db=db, user=user)] == ["Detmold"]


# --------------------------------------------------------------------------- #
# Der Filter, in den die Liste führt
# --------------------------------------------------------------------------- #
def test_city_filter_selects_across_the_whole_holding(db, user):
    """Der Punkt des serverseitigen Filters (A37): er trifft auch, was weit
    hinten liegt — hier über eine Seitengrenze hinweg."""
    for day in range(1, 21):
        _visit(db, user, _loc(db, user, f"Straße {day}, Detmold", "Detmold",
                              lat=51.9 + day / 100, lng=8.8),
               datetime(2021, 1, day))
    _visit(db, user, _loc(db, user, "Kaiserstraße, Düsseldorf", "Düsseldorf"),
           datetime(2020, 1, 1))   # älter, läge auf einer späteren Seite
    db.commit()

    page = list_events(db=db, user=user, slim=True, city="Düsseldorf", limit=5)
    assert len(page) == 1
    assert page[0].location.city == "Düsseldorf"


def test_city_filter_does_not_leak_across_users(db, user, other_user):
    """Städtenamen sind global — „Detmold" darf nicht die Besuche eines
    anderen Kontos einsammeln, nur weil der Name gleich ist."""
    _visit(db, user, _loc(db, user, "Markt, Detmold", "Detmold"),
           datetime(2021, 1, 1))
    foreign = Location(user_id=other_user.id, name="Markt, Detmold",
                       lat=51.9, lng=8.8, city="Detmold")
    db.add(foreign)
    db.flush()
    db.add(Event(user_id=other_user.id, title="Fremd", category="event",
                 date_start=datetime(2021, 1, 2), date_precision=DatePrecision.day,
                 confirmed=ConfirmState.confirmed, location=foreign))
    db.commit()

    rows = list_events(db=db, user=user, slim=True, city="Detmold")
    assert [r.title for r in rows] == ["Besuch"]
