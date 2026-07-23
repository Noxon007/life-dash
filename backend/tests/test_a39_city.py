"""A39 — die Stadt als eigenes Feld (Anmerkung 88).

Bis 0.33 existierte die Stadt nur als Textbaustein in `Location.name`, und
welche Bausteine dort landen, wählt der Nutzer (`place_name_parts`). Wer
„Stadt" abgewählt hatte, konnte also nicht nach Städten gruppieren — und wer
sie später abwählt, hätte eine Statistik verloren, die es vorher gab. Diese
Tests halten fest, dass das Feld unabhängig vom Namensformat ist.

Der heikelste Teil ist NICHT das Auslesen, sondern die Frage, wann ein Ort als
„nachgesehen" gilt: ohne diese Unterscheidung fragt der Rückfüll-Lauf jeden
stadtlosen Ort bei jedem Durchgang erneut ab, für immer (dieselbe Falle, die
F12 mit `weather_rev` abstellen musste). Offline — kein Netz, keine echten
Nominatim-Aufrufe.
"""
from __future__ import annotations

from datetime import datetime

from app.models import (ConfirmState, DatePrecision, Event, Location, Source)
from app.routers.events import list_events
from app.routers.tracks import _resolve_candidates
from app.services.geocode import city_of, short_name
from app.services.stats_overview import compute_overview


def _hit(**addr) -> dict:
    return {"address": addr, "name": "irgendwo"}


# --------------------------------------------------------------------------- #
# Auslesen: dieselbe Fallback-Kette wie im Anzeigenamen
# --------------------------------------------------------------------------- #
def test_city_falls_back_like_the_name_does():
    assert city_of(_hit(city="Düsseldorf")) == "Düsseldorf"
    assert city_of(_hit(town="Detmold")) == "Detmold"
    assert city_of(_hit(village="Berlebeck")) == "Berlebeck"
    assert city_of(_hit(municipality="Korfu-Mitte")) == "Korfu-Mitte"
    # Reihenfolge zählt: city schlägt town schlägt village
    assert city_of(_hit(city="A", town="B", village="C")) == "A"


def test_no_city_is_an_answer_not_a_gap():
    assert city_of(_hit(road="Waldweg", country="Deutschland")) is None
    assert city_of({}) is None
    assert city_of(None) is None


def test_city_is_independent_of_the_chosen_name_format():
    """Der eigentliche Punkt des Pakets: Wer „Stadt" aus dem Anzeigenamen
    abwählt, verliert die Stadt nicht als Datum."""
    hit = _hit(road="Kaiserstraße", suburb="Bilk", city="Düsseldorf",
               country="Deutschland")
    name_without_city = short_name(hit, ["road", "country"])
    assert "Düsseldorf" not in name_without_city
    assert city_of(hit) == "Düsseldorf"


# --------------------------------------------------------------------------- #
# Rückfüllung: jeder Ort genau einmal
# --------------------------------------------------------------------------- #
# A47 (0.39): „fertig" heißt seither Name, Stadt UND Adress-Bausteine — die
# Stufe „Ortsteil" liest `Location.address`, und die gab es vorher nicht.
# `address={}` heißt hier „nachgesehen, nichts bekommen" und ist genau das
# Gegenstück zum Leerstring bei der Stadt. Ohne diesen Vorgabewert prüften die
# Tests unten einen Ort, an dem noch eine Frage offen ist, und wären zu Recht
# rot. Dass ein Ort ohne Bausteine genau EINMAL geholt wird und nicht bei jedem
# Lauf, steht in `test_a47_levels.py`.
def _loc(db, user, name="Kaiserstraße, Düsseldorf", city=None, lat=51.2, lng=6.7,
         address={}):
    loc = Location(user_id=user.id, name=name, lat=lat, lng=lng, city=city,
                   address=address)
    db.add(loc)
    db.flush()
    return loc


PARTS = ["road", "suburb", "city", "country"]


def test_location_without_city_is_a_candidate(db, user):
    loc = _loc(db, user, city=None)
    assert loc in _resolve_candidates(db, user.id, PARTS)


def test_location_with_city_is_not(db, user):
    loc = _loc(db, user, city="Düsseldorf")
    assert loc not in _resolve_candidates(db, user.id, PARTS)


def test_checked_but_cityless_is_not_asked_again(db, user):
    """Der Leerstring heißt „nachgesehen, gibt es hier nicht". Ohne diese
    Unterscheidung liefe der Lauf für solche Orte endlos weiter."""
    loc = _loc(db, user, name="Waldweg, Deutschland", city="")
    assert loc not in _resolve_candidates(db, user.id, PARTS)


def test_name_defects_still_come_first(db, user):
    """Ein Ort ohne Namen ist dringender als einer, dem nur die Stadt fehlt —
    und er darf nicht doppelt in der Liste stehen."""
    unnamed = _loc(db, user, name="Ort (51.2000, 6.7000)", city=None)
    only_city = _loc(db, user, name="Kaiserstraße, Düsseldorf", city=None,
                     lat=52.0, lng=7.0)
    cands = _resolve_candidates(db, user.id, PARTS)
    assert cands.index(unnamed) < cands.index(only_city)
    assert cands.count(unnamed) == 1


# --------------------------------------------------------------------------- #
# Statistik
# --------------------------------------------------------------------------- #
def _event(db, user, loc, title="Besuch"):
    ev = Event(user_id=user.id, title=title, category="event",
               date_start=datetime(2026, 7, 1), date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, confirmed_by="import",
               source=Source.google_timeline, location=loc)
    db.add(ev)
    db.flush()
    return ev


def test_cities_counted_across_different_places(db, user):
    """Der Gewinn: drei Straßen in einer Stadt sind EINE Stadt — genau das
    konnte die alte Auswertung über `Location.name` nicht sehen."""
    for i, street in enumerate(["Kaiserstraße", "Bilker Allee", "Ratinger Str."]):
        loc = _loc(db, user, name=f"{street}, Düsseldorf", city="Düsseldorf",
                   lat=51.2 + i / 100, lng=6.7)
        _event(db, user, loc)
    loc2 = _loc(db, user, name="Marktplatz, Detmold", city="Detmold",
                lat=51.9, lng=8.8)
    _event(db, user, loc2)
    db.commit()

    ov = compute_overview(db, user.id)
    assert ov["counts"]["cities"] == 2
    assert ov["top_cities"][0] == ["Düsseldorf", 3]
    # Orte bleiben getrennt gezählt — die Städte treten daneben, nicht an ihre Stelle
    assert ov["counts"]["places"] == 4


def test_cityless_places_do_not_become_a_city(db, user):
    """NULL (nie nachgesehen) und "" (keine vorhanden) sind beide keine Stadt
    und dürfen nicht als leerer Eintrag in der Liste auftauchen."""
    _event(db, user, _loc(db, user, name="Waldweg", city=""))
    _event(db, user, _loc(db, user, name="Ort (1,2)", city=None, lat=1, lng=2))
    _event(db, user, _loc(db, user, name="Markt, Detmold", city="Detmold",
                          lat=51.9, lng=8.8))
    db.commit()

    ov = compute_overview(db, user.id)
    assert ov["counts"]["cities"] == 1
    assert [c for c, _ in ov["top_cities"]] == ["Detmold"]


# --------------------------------------------------------------------------- #
# Verdichtung: die Seitengrenze darf keine Gruppe zerschneiden
# --------------------------------------------------------------------------- #
def _visit(db, user, loc, when, title="Besuch: irgendwo"):
    ev = Event(user_id=user.id, title=title, category="event",
               date_start=when, date_precision=DatePrecision.exact,
               confirmed=ConfirmState.confirmed, confirmed_by="import",
               source=Source.google_timeline, location=loc)
    db.add(ev)
    db.flush()
    return ev


def _day_of_visits(db, user, city, day, n, lat=51.2):
    loc = _loc(db, user, name=f"Straße, {city}", city=city, lat=lat, lng=6.7)
    for h in range(n):
        _visit(db, user, loc, datetime(2026, 7, day, 8 + h % 12, 0))
    return loc


def test_condense_collapses_a_day_in_one_city(db, user):
    _day_of_visits(db, user, "Düsseldorf", 5, 12)
    db.commit()

    rows = list_events(db=db, user=user, slim=True, condense=True)
    assert len(rows) == 1
    assert rows[0].group.count == 12
    assert rows[0].group.city == "Düsseldorf"
    assert rows[0].group.first < rows[0].group.last


def test_without_condense_everything_stays(db, user):
    _day_of_visits(db, user, "Düsseldorf", 5, 12)
    db.commit()
    assert len(list_events(db=db, user=user, slim=True)) == 12


def test_two_cities_on_one_day_stay_apart(db, user):
    _day_of_visits(db, user, "Düsseldorf", 5, 4)
    _day_of_visits(db, user, "Detmold", 5, 3, lat=51.9)
    db.commit()

    rows = list_events(db=db, user=user, slim=True, condense=True)
    assert sorted(r.group.count for r in rows) == [3, 4]
    assert {r.group.city for r in rows} == {"Düsseldorf", "Detmold"}


def test_same_city_on_two_days_stays_apart(db, user):
    _day_of_visits(db, user, "Düsseldorf", 5, 4)
    _day_of_visits(db, user, "Düsseldorf", 6, 6, lat=51.3)
    db.commit()

    rows = list_events(db=db, user=user, slim=True, condense=True)
    assert sorted(r.group.count for r in rows) == [4, 6]


def test_page_boundary_does_not_split_a_group(db, user):
    """Die eigentliche Falle: würde erst die fertige Seite gruppiert, zeigte
    eine 40er-Gruppe bei Seitengröße 10 vier Zeilen mit je „10 Besuche“ statt
    einer mit 40. Weil vor dem Blättern reduziert wird, kann das nicht
    passieren — die Gruppe IST hier eine einzige Zeile."""
    for day in (5, 6, 7):
        _day_of_visits(db, user, "Düsseldorf", day, 40, lat=51.2 + day / 100)
    db.commit()

    page1 = list_events(db=db, user=user, slim=True, condense=True, limit=2, offset=0)
    page2 = list_events(db=db, user=user, slim=True, condense=True, limit=2, offset=2)
    assert [r.group.count for r in page1] == [40, 40]
    assert [r.group.count for r in page2] == [40]
    # und keine Zeile taucht auf beiden Seiten auf
    assert not ({r.id for r in page1} & {r.id for r in page2})


def test_manual_events_are_never_condensed(db, user):
    """Von Hand erfasste Einträge sind einzeln gemeint — auch zwei am selben
    Tag in derselben Stadt."""
    loc = _loc(db, user, name="Markt, Detmold", city="Detmold")
    for title in ("Frühstück", "Konzert"):
        ev = Event(user_id=user.id, title=title, category="event",
                   date_start=datetime(2026, 7, 5, 9), date_precision=DatePrecision.exact,
                   confirmed=ConfirmState.confirmed, confirmed_by="manual",
                   source=Source.manual, location=loc)
        db.add(ev)
    db.commit()

    rows = list_events(db=db, user=user, slim=True, condense=True)
    assert len(rows) == 2
    assert all(r.group is None for r in rows)


def test_visits_without_a_city_are_left_alone(db, user):
    """Ohne Stadt gibt es keinen Schlüssel — solche Besuche bleiben einzeln,
    statt in einen Sammeltopf „ohne Stadt“ zu fallen."""
    loc = _loc(db, user, name="Waldweg", city="")
    for h in (9, 10, 11):
        _visit(db, user, loc, datetime(2026, 7, 5, h))
    db.commit()

    rows = list_events(db=db, user=user, slim=True, condense=True)
    assert len(rows) == 3
    assert all(r.group is None for r in rows)


def test_single_visit_is_not_a_group(db, user):
    _day_of_visits(db, user, "Detmold", 5, 1)
    db.commit()
    rows = list_events(db=db, user=user, slim=True, condense=True)
    assert len(rows) == 1 and rows[0].group is None


def test_city_filter_reopens_a_group(db, user):
    """Das Aufklappen: derselbe Tag, nach Stadt gefiltert, liefert wieder alle
    Einzelbesuche."""
    _day_of_visits(db, user, "Düsseldorf", 5, 5)
    _day_of_visits(db, user, "Detmold", 5, 2, lat=51.9)
    db.commit()

    rows = list_events(db=db, user=user, slim=True, city="Düsseldorf",
                       date_from=datetime(2026, 7, 5), date_to=datetime(2026, 7, 5, 23, 59))
    assert len(rows) == 5
    assert {r.location.city for r in rows} == {"Düsseldorf"}
