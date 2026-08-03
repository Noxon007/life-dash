"""Anmerkung 156 — die dritte Statistik-Ansicht: Ranglisten.

Was hier festgenagelt wird, ist nicht „die Liste ist da", sondern die vier
Stellen, an denen so eine Liste still falsch wird:

* **Die Kachel ist Platz 1 der Liste.** Kachel und Rangfolge kommen aus
  derselben Funktion; wären es zwei, liefen sie beim ersten Sonderfall
  auseinander — und die Sonderfälle stehen schon in `_EXTREMES` (`0` ist beim
  Regen kein Rekord, beim Tageslicht schon, Anmerkung 104/114).
* **Tage und Einträge sind zwei Zahlen.** Dieselbe Umstellung wie in
  Anmerkung 143/148, hier zum dritten Mal.
* **Die Reihenfolge ist bei Gleichstand stabil.** Eine Rangliste, die bei
  jedem Laden anders aussieht, ist keine.
* **Die Lücke wird nur zwischen erstem und letztem Tag gemessen** — sonst
  meldet sie die Zeit vor dem ersten Eintrag als Befund über ein Leben.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Event, Location, Metric,
                        Source, User, UserRole)
from app.services.stats_overview import compute_overview
from app.services.stats_toplists import compute_toplists


@pytest.fixture()
def other_user(db):
    u = User(oidc_subject="other-sub", email="other@example.org",
             display_name="Zweitnutzer", role=UserRole.user)
    db.add(u)
    db.commit()
    return u


def _loc(db, user, name, city=None, country=None):
    loc = Location(user_id=user.id, name=name, lat=51.2, lng=6.7,
                   city=city, country=country)
    db.add(loc)
    db.flush()
    return loc


def _event(db, user, when, *, title="Eintrag", category="event", loc=None,
           end=None):
    ev = Event(user_id=user.id, title=title, category=category,
               date_start=when, date_end=end, date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.manual,
               location=loc)
    db.add(ev)
    db.flush()
    return ev


def _warm(db, ev, celsius):
    db.add(Metric(event_id=ev.id, key="temp_max_c", value=celsius,
                  source=Source.weather))


# --------------------------------------------------------------------------- #
# Die Kachel ist Platz 1 der Liste
# --------------------------------------------------------------------------- #
def test_the_tile_is_the_first_row_of_the_list(db, user):
    """Wären es zwei Rangfolgen, wäre dies der Test, der sie zusammenhält."""
    for i, c in enumerate([31.5, 38.4, 12.0, 27.3]):
        _warm(db, _event(db, user, datetime(2024, 6, i + 1)), c)
    db.commit()

    tile = compute_overview(db, user.id)["extremes"]["hot"]
    rows = compute_toplists(db, user.id)["weather"]["hot"]
    assert tile is not None and rows
    assert rows[0] == tile
    assert [r["value"] for r in rows] == [38.4, 31.5, 27.3, 12.0]


def test_a_zero_is_no_record_for_rain_but_is_one_for_daylight(db, user):
    """Die Sonderfälle aus `_EXTREMES` gelten auch in der Liste — sonst wären
    sie beim ersten Blick daneben widerlegt (Anmerkung 104)."""
    dry = _event(db, user, datetime(2024, 1, 1))
    wet = _event(db, user, datetime(2024, 1, 2))
    db.add_all([
        Metric(event_id=dry.id, key="rain_mm", value=0.0, source=Source.weather),
        Metric(event_id=wet.id, key="rain_mm", value=14.0, source=Source.weather),
        Metric(event_id=dry.id, key="daylight_h", value=0.0, source=Source.weather),
        Metric(event_id=wet.id, key="daylight_h", value=8.0, source=Source.weather),
    ])
    db.commit()

    wx = compute_toplists(db, user.id)["weather"]
    assert [r["value"] for r in wx["rainy"]] == [14.0]
    # Die Polarnacht IST der kürzeste Tag — und der interessanteste Wert.
    assert wx["shortest_day"][0]["value"] == 0.0


def test_the_order_is_stable_on_ties(db, user):
    """Zwei gleiche Werte dürfen nicht bei jedem Laden die Plätze tauschen."""
    for i in range(6):
        _warm(db, _event(db, user, datetime(2024, 3, i + 1)), 20.0)
    db.commit()

    first = [r["id"] for r in compute_toplists(db, user.id)["weather"]["hot"]]
    second = [r["id"] for r in compute_toplists(db, user.id)["weather"]["hot"]]
    assert first == second and len(first) == 6


def test_the_lists_are_capped_at_ten(db, user):
    for i in range(14):
        _warm(db, _event(db, user, datetime(2024, 5, i + 1)), 10.0 + i)
    db.commit()
    assert len(compute_toplists(db, user.id)["weather"]["hot"]) == 10


# --------------------------------------------------------------------------- #
# Tage und Einträge — zwei Zahlen
# --------------------------------------------------------------------------- #
def test_places_count_days_and_entries_separately(db, user):
    """Zwölf importierte Besuche an einem Tag sind EIN Tag (Anmerkung 143)."""
    loc = _loc(db, user, "Kaiserstraße, Düsseldorf", city="Düsseldorf",
               country="Deutschland")
    for hour in range(12):
        _event(db, user, datetime(2024, 7, 12, hour), loc=loc)
    _event(db, user, datetime(2024, 7, 13, 9), loc=loc)
    db.commit()

    top = compute_toplists(db, user.id)
    assert top["cities"][0] == {"name": "Düsseldorf", "days": 2, "events": 13}
    assert top["countries"][0] == {"name": "Deutschland", "days": 2, "events": 13}
    assert top["places"][0]["days"] == 2 and top["places"][0]["events"] == 13


def test_places_are_shortened_like_the_bars_next_to_them(db, user):
    """Die Langadresse wird auf ihren ersten Bestandteil gekürzt — dieselbe
    Regel wie in `stats_overview`, damit Balken und Liste untereinander nicht
    zwei verschiedene Ortslisten zeigen."""
    for i, name in enumerate(["Kaiserstraße 5, Düsseldorf, Deutschland",
                              "Kaiserstraße 5, Düsseldorf, DE"]):
        _event(db, user, datetime(2024, 8, i + 1), loc=_loc(db, user, name))
    db.commit()

    places = compute_toplists(db, user.id)["places"]
    assert [p["name"] for p in places] == ["Kaiserstraße 5"]
    assert places[0]["events"] == 2 and places[0]["days"] == 2
    # Gegenprobe an derselben Stelle: die Kürzung ist die des Überblicks, also
    # muss der Balken daneben denselben Namen tragen.
    assert compute_overview(db, user.id)["top_places"][0][0] == "Kaiserstraße 5"


def test_the_empty_city_is_not_a_city(db, user):
    """Der Leerstring heißt „nachgesehen, gibt es hier nicht" (A39)."""
    _event(db, user, datetime(2024, 9, 1),
           loc=_loc(db, user, "Wald", city="", country=""))
    _event(db, user, datetime(2024, 9, 2),
           loc=_loc(db, user, "Bremen", city="Bremen", country="Deutschland"))
    db.commit()

    top = compute_toplists(db, user.id)
    assert [c["name"] for c in top["cities"]] == ["Bremen"]
    assert [c["name"] for c in top["countries"]] == ["Deutschland"]


def test_other_accounts_are_not_in_the_lists(db, user, other_user):
    _event(db, user, datetime(2024, 4, 1),
           loc=_loc(db, user, "Bremen", city="Bremen"))
    _event(db, other_user, datetime(2024, 4, 2),
           loc=_loc(db, other_user, "Kiel", city="Kiel"))
    db.commit()
    assert [c["name"] for c in compute_toplists(db, user.id)["cities"]] == ["Bremen"]


def test_years_and_categories_carry_both_numbers(db, user):
    for hour in range(3):
        _event(db, user, datetime(2021, 2, 3, hour), category="meal")
    _event(db, user, datetime(2022, 2, 3), category="concert")
    db.commit()

    top = compute_toplists(db, user.id)
    assert top["years"][0] == {"name": "2021", "days": 1, "events": 3}
    assert top["categories"][0] == {"name": "meal", "days": 1, "events": 3}


# --------------------------------------------------------------------------- #
# Serien
# --------------------------------------------------------------------------- #
def test_the_longest_run_counts_consecutive_days(db, user):
    for d in (1, 2, 3, 4, 7, 8):
        _event(db, user, datetime(2024, 1, d))
    db.commit()

    run = compute_toplists(db, user.id)["streaks"]["longest_run"]
    assert run == {"from": "2024-01-01", "to": "2024-01-04", "days": 4}


def test_several_entries_on_one_day_are_one_day(db, user):
    """Sonst wäre ein Tag mit dreißig importierten Besuchen eine Serie."""
    for hour in range(30):
        _event(db, user, datetime(2024, 1, 1, hour % 24))
    db.commit()
    assert compute_toplists(db, user.id)["streaks"]["longest_run"]["days"] == 1


def test_the_gap_is_measured_only_between_the_first_and_last_day(db, user):
    """Die Zeit VOR dem ersten Eintrag ist keine Lücke, sondern die Zeit vor
    dem ersten Eintrag — sonst meldet die Ansicht den Beginn der Aufzeichnung
    als Befund über ein Leben (offen als Anmerkung 144)."""
    _event(db, user, datetime(2020, 1, 1))
    _event(db, user, datetime(2020, 3, 1))
    db.commit()

    gap = compute_toplists(db, user.id)["streaks"]["longest_gap"]
    assert gap == {"from": "2020-01-02", "to": "2020-02-29", "days": 59}


def test_without_a_gap_there_is_none(db, user):
    _event(db, user, datetime(2020, 1, 1))
    _event(db, user, datetime(2020, 1, 2))
    db.commit()
    assert compute_toplists(db, user.id)["streaks"]["longest_gap"] is None


def test_the_longest_trip_is_the_longest_recorded_one(db, user):
    _event(db, user, datetime(2019, 5, 1), category="trip", title="Kurz",
           end=datetime(2019, 5, 4))
    _event(db, user, datetime(2021, 7, 1), category="trip", title="Lang",
           end=datetime(2021, 7, 20))
    # Ein eintägiger „trip" ist keine Reise am Stück.
    _event(db, user, datetime(2022, 1, 1), category="trip", title="Tagestour",
           end=datetime(2022, 1, 1))
    db.commit()

    trip = compute_toplists(db, user.id)["streaks"]["longest_trip"]
    assert trip["title"] == "Lang" and trip["days"] == 20


def test_an_empty_corpus_answers_with_nothing_not_with_zero(db, user):
    """Kein Bestand heißt „keine Serie", nicht „Serie von 0 Tagen" — eine
    Zahl ohne Grundlage sieht aus wie ein Befund."""
    top = compute_toplists(db, user.id)
    assert top["streaks"] == {"longest_run": None, "longest_gap": None,
                              "longest_trip": None}
    assert top["places"] == [] and top["cities"] == []
    assert all(rows == [] for rows in top["weather"].values())
