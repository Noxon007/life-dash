"""Tests für 0.32.0: A37 — serverseitiges Zeitfenster und Statistik im Server.

Zwei Dinge müssen bewiesen werden, und das zweite ist das wichtigere:

1. Das Blättern liefert jeden Eintrag **genau einmal** — auch bei
   Datums-Gleichständen, die nach einem Timeline-Import der Normalfall sind.
2. Die Statistik zählt weiterhin das **Leben**, nicht das geladene Fenster —
   die Zahlen sind dieselben wie in der alten Client-Rechnung.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException

from app.models import (ConfirmState, DatePrecision, Entity, Event,
                        EventEntityLink, Location, Metric, Source, User,
                        UserRole)
from app.routers.events import (events_index, get_event, list_events,
                                list_map_events)
from app.services.stats_overview import compute_overview


def _event(db, user, title="x", *, category="event", when=None,
           precision=DatePrecision.day, loc=None, confirmed=True,
           parent=None, source=Source.manual, description=None) -> Event:
    e = Event(user_id=user.id, title=title, description=description,
              category=category, date_start=when, date_precision=precision,
              location=loc, parent_event_id=parent, source=source,
              confirmed=ConfirmState.confirmed if confirmed
              else ConfirmState.unconfirmed)
    db.add(e)
    db.commit()
    return e


def _loc(db, user, name, lat=53.5, lng=10.0) -> Location:
    loc = Location(user_id=user.id, name=name, lat=lat, lng=lng)
    db.add(loc)
    db.commit()
    return loc


def _weather(db, event, **values) -> None:
    for key, value in values.items():
        db.add(Metric(event_id=event.id, key=key, value=value,
                      source=Source.weather))
    db.commit()


# --------------------------------------------------------------------------- #
# Blättern
# --------------------------------------------------------------------------- #
def test_paging_returns_every_event_exactly_once(db, user):
    """Der Kern des Pakets: 30 Einträge, alle am SELBEN Zeitstempel.

    Genau so sieht ein importierter Tag aus. Ohne eindeutige Sortierung
    (date_start UND id) blättert man an Einträgen vorbei oder sieht sie
    doppelt — und niemandem fiele es auf."""
    same = datetime(2024, 6, 1, 12, 0)
    ids = {_event(db, user, f"Besuch {i}", when=same).id for i in range(30)}

    seen: list[str] = []
    for offset in range(0, 40, 7):
        page = list_events(db=db, user=user, slim=True, limit=7, offset=offset)
        seen += [e.id for e in page]

    assert len(seen) == len(ids), "Einträge doppelt oder verloren"
    assert set(seen) == ids


def test_page_carries_the_weather_of_its_own_events(db, user):
    """Das Wetter wird je Seite nachgeladen und muss zum Eintrag passen —
    ein Zip-Fehler wäre hier still und würde falsche Werte an Karten hängen."""
    warm = _event(db, user, "warm", when=datetime(2024, 6, 2))
    cold = _event(db, user, "kalt", when=datetime(2024, 6, 1))
    _weather(db, warm, temperature_c=28.0)
    _weather(db, cold, temperature_c=-4.0)

    page = list_events(db=db, user=user, slim=True, limit=1)
    assert len(page) == 1 and page[0].title == "warm"
    assert page[0].weather == {"temperature_c": 28.0}

    page2 = list_events(db=db, user=user, slim=True, limit=1, offset=1)
    assert page2[0].title == "kalt"
    assert page2[0].weather == {"temperature_c": -4.0}


def test_window_filters_by_date_and_drops_undated(db, user):
    _event(db, user, "2023", when=datetime(2023, 5, 1))
    _event(db, user, "2024", when=datetime(2024, 5, 1))
    _event(db, user, "ohne Datum", when=None, precision=DatePrecision.year)

    page = list_events(db=db, user=user, slim=True,
                       date_from=datetime(2024, 1, 1),
                       date_to=datetime(2024, 12, 31))
    assert [e.title for e in page] == ["2024"]

    # Ohne Fenster ist alles da — Altpfade (Export, Tests) bleiben gültig
    assert len(list_events(db=db, user=user, slim=True)) == 3


def test_vague_finds_undated_and_coarsely_dated(db, user):
    _event(db, user, "genau", when=datetime(2024, 5, 1))
    _event(db, user, "irgendwann 2002", when=datetime(2002, 1, 1),
           precision=DatePrecision.year)
    _event(db, user, "gar nicht datiert", when=None)

    titles = {e.title for e in list_events(db=db, user=user, slim=True, vague=True)}
    assert titles == {"irgendwann 2002", "gar nicht datiert"}


def test_parent_returns_only_the_day_children(db, user):
    trip = _event(db, user, "Reise", category="trip", when=datetime(2024, 7, 1))
    _event(db, user, "Tag 1", when=datetime(2024, 7, 1), parent=trip.id)
    _event(db, user, "Tag 2", when=datetime(2024, 7, 2), parent=trip.id)
    _event(db, user, "fremd", when=datetime(2024, 7, 3))

    children = list_events(db=db, user=user, slim=True, parent=trip.id)
    assert {c.title for c in children} == {"Tag 1", "Tag 2"}


def test_paging_is_scoped_to_the_own_user(db, user):
    other = User(oidc_subject="other", email="o@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    _event(db, user, "meins", when=datetime(2024, 1, 1))
    _event(db, other, "fremdes", when=datetime(2024, 1, 2))

    page = list_events(db=db, user=user, slim=True, limit=10)
    assert [e.title for e in page] == ["meins"]


# --------------------------------------------------------------------------- #
# Index, Karte, Einzelabruf
# --------------------------------------------------------------------------- #
def test_index_counts_without_loading_events(db, user):
    _event(db, user, "a", when=datetime(2020, 3, 1))
    _event(db, user, "b", when=datetime(2024, 3, 1))
    _event(db, user, "c", when=datetime(2024, 8, 1), confirmed=False)
    _event(db, user, "undatiert", when=None)

    idx = events_index(db=db, user=user)
    assert idx.total == 4 and idx.dated == 3 and idx.undated == 1
    assert idx.unconfirmed == 1
    assert idx.year_min == 2020 and idx.year_max == 2024
    assert [(y.year, y.count) for y in idx.years] == [(2020, 1), (2024, 2)]


def test_map_returns_only_located_events_in_thin_form(db, user):
    loc = _loc(db, user, "Hamburg, Freie und Hansestadt Hamburg")
    located = _event(db, user, "mit Ort", when=datetime(2024, 6, 1), loc=loc)
    _weather(db, located, temperature_c=19.0)
    _event(db, user, "ohne Ort", when=datetime(2024, 6, 2))

    points = list_map_events(db=db, user=user)
    assert len(points) == 1
    p = points[0]
    assert p.title == "mit Ort" and p.location.lat == 53.5
    # Schlanke Form: was die Karte nicht zeichnet, wird nicht mitgeschickt
    assert not hasattr(p, "description") and not hasattr(p, "media")
    # Gemessen: das Wetter macht aus 205 Byte je Punkt 799. Deshalb ist es im
    # Grundabruf AUS und kommt nur für den angezeigten Zeitraum dazu.
    assert p.weather is None
    assert list_map_events(db=db, user=user, weather=True)[0].weather == {
        "temperature_c": 19.0}


def test_map_accepts_a_time_window(db, user):
    loc = _loc(db, user, "Kiel")
    _event(db, user, "alt", when=datetime(2019, 1, 1), loc=loc)
    _event(db, user, "neu", when=datetime(2024, 1, 1), loc=loc)

    points = list_map_events(db=db, user=user, date_from=datetime(2020, 1, 1))
    assert [p.title for p in points] == ["neu"]


def test_single_event_is_fetchable_and_scoped(db, user):
    other = User(oidc_subject="other2", email="o2@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    mine = _event(db, user, "meins", when=datetime(2024, 1, 1))
    theirs = _event(db, other, "fremdes", when=datetime(2024, 1, 1))

    assert get_event(event_id=mine.id, db=db, user=user).title == "meins"
    with pytest.raises(HTTPException) as err:
        get_event(event_id=theirs.id, db=db, user=user)
    assert err.value.status_code == 404


# --------------------------------------------------------------------------- #
# Statistik: dieselben Zahlen wie vorher im Browser
# --------------------------------------------------------------------------- #
def test_overview_counts_match_the_old_client_rules(db, user):
    berlin = _loc(db, user, "Berlin, Deutschland")
    berlin2 = _loc(db, user, "Berlin, Berlin, Deutschland")  # gleiche Stadt!
    kiel = _loc(db, user, "Kiel")
    _event(db, user, "Konzert A", category="concert", when=datetime(2024, 1, 1),
           loc=berlin)
    _event(db, user, "Konzert B", category="concert", when=datetime(2024, 2, 1),
           loc=berlin2)
    _event(db, user, "Abendessen", category="meal", when=datetime(2024, 3, 1),
           loc=kiel)
    _event(db, user, "Umzug nach Kiel", category="milestone",
           when=datetime(2010, 5, 1))
    _event(db, user, "Geburt", category="milestone", when=datetime(1990, 4, 12))
    _event(db, user, "Vorschlag", when=datetime(2024, 4, 1), confirmed=False)

    ov = compute_overview(db, user.id, today=datetime(2026, 7, 21))
    c = ov["counts"]
    assert c["events"] == 6
    assert c["concerts"] == 2
    assert c["meals"] == 1
    assert c["milestones"] == 2
    assert c["moves"] == 1
    assert c["unconfirmed"] == 1
    # „Berlin, Deutschland" und „Berlin, Berlin, Deutschland" sind EIN Ort —
    # sonst zählt jede Nominatim-Langadresse einzeln (Frontend-Regel placeOf)
    assert c["places"] == 2
    assert ov["birth"]["title"] == "Geburt"
    assert ov["age"] == 36
    assert ov["top_places"][0] == ["Berlin", 2]


def test_overview_move_needs_the_word_not_only_the_category(db, user):
    """Das ILIKE der Vorauswahl ist großzügiger als die Regel — entscheiden
    muss derselbe Ausdruck wie im Frontend."""
    _event(db, user, "Abitur", category="milestone", when=datetime(2009, 6, 1))
    _event(db, user, "Erste Wohnung", category="milestone",
           when=datetime(2011, 9, 1), description="Endlich eingezogen.")

    assert compute_overview(db, user.id)["counts"]["moves"] == 1


def test_overview_weather_counts_days_not_entries(db, user):
    """A31/Anmerkung 64, jetzt im Server: ein importierter Tag trägt dutzende
    Besuche mit demselben Wetter. Gezählt wird der Kalendertag."""
    loc = _loc(db, user, "Hamburg")
    for hour in range(8, 20):
        e = _event(db, user, f"Besuch {hour}", when=datetime(2024, 6, 1, hour),
                   loc=loc, source=Source.google_timeline)
        _weather(db, e, rain_mm=4.0, sunshine_h=2.0, temperature_c=15.0)

    ov = compute_overview(db, user.id)
    assert ov["weather"]["days"] == 1, "zwölf Besuche sind EIN Regentag"
    assert ov["weather"]["rain_days"] == 1
    assert ov["weather"]["sun_hours"] == 2, "nicht 12 × 2 Stunden"
    assert ov["weather"]["rain_days_per_year"] == [[2024, 1]]


def test_overview_extremes_point_at_the_right_event(db, user):
    loc = _loc(db, user, "Sevilla, Andalusien, Spanien")
    hot = _event(db, user, "Hitzetag", when=datetime(2023, 8, 1), loc=loc)
    _weather(db, hot, temp_max_c=41.0, temp_min_c=24.0)
    cold = _event(db, user, "Frosttag", when=datetime(2021, 2, 1))
    _weather(db, cold, temp_max_c=-2.0, temp_min_c=-17.0)
    windy = _event(db, user, "Sturm", when=datetime(2022, 1, 1))
    _weather(db, windy, wind_max_kmh=97.0, temperature_c=6.0)

    ex = compute_overview(db, user.id)["extremes"]
    assert ex["hot"]["value"] == 41.0 and ex["hot"]["title"] == "Hitzetag"
    assert ex["hot"]["place"] == "Sevilla"
    assert ex["cold"]["value"] == -17.0 and ex["cold"]["title"] == "Frosttag"
    assert ex["windy"]["value"] == 97.0
    # Ohne Schnee gibt es keine Kachel — nicht etwa eine mit 0
    assert ex["snowy"] is None


def test_overview_falls_back_to_the_mean_temperature(db, user):
    """Bestandsdaten ohne Min/Max: das Tagesmittel gilt — Frontend-Regel
    metricOf(e, 'temp_max_c', 'temperature_c')."""
    old = _event(db, user, "Altbestand", when=datetime(2015, 7, 1))
    _weather(db, old, temperature_c=26.0)

    ex = compute_overview(db, user.id)["extremes"]
    assert ex["hot"]["value"] == 26.0 and ex["cold"]["value"] == 26.0


def test_overview_warmest_trip_averages_days_not_entries(db, user):
    parent = _event(db, user, "Andalusien", category="trip",
                    when=datetime(2023, 8, 1))
    for day, temp in ((1, 30.0), (2, 34.0)):
        child = _event(db, user, f"Tag {day}", category="trip",
                       when=datetime(2023, 8, day, 9), parent=parent.id)
        _weather(db, child, temperature_c=temp)
        # zweiter Eintrag desselben Tages — darf den Schnitt NICHT verschieben
        extra = _event(db, user, f"Tag {day} abends", category="trip",
                       when=datetime(2023, 8, day, 20), parent=parent.id)
        _weather(db, extra, temperature_c=temp)

    warmest = compute_overview(db, user.id)["weather"]["warmest_trip"]
    assert warmest["avg"] == 32.0


def test_overview_top_animals_and_categories(db, user):
    fuchs = Entity(user_id=user.id, type="animal", name="Fuchs",
                   confirmed=ConfirmState.confirmed)
    reiher = Entity(user_id=user.id, type="animal", name="Graureiher",
                    confirmed=ConfirmState.confirmed)
    db.add_all([fuchs, reiher])
    db.commit()
    for i in range(3):
        e = _event(db, user, f"Sichtung {i}", category="sighting",
                   when=datetime(2024, 5, i + 1))
        db.add(EventEntityLink(event_id=e.id, entity_id=fuchs.id))
    e = _event(db, user, "Reiher", category="sighting", when=datetime(2024, 6, 1))
    db.add(EventEntityLink(event_id=e.id, entity_id=reiher.id))
    db.commit()

    ov = compute_overview(db, user.id)
    assert ov["top_animals"][0][:2] == ["Fuchs", 3]
    assert ov["per_category"][0] == ("sighting", 4)
    assert ov["per_year"] == [[2024, 4]]


def test_overview_is_empty_but_valid_without_data(db, user):
    """Eine frische Installation darf keine Ausnahme werfen."""
    ov = compute_overview(db, user.id)
    assert ov["counts"]["events"] == 0
    assert ov["birth"] is None and ov["age"] is None
    assert ov["extremes"]["hot"] is None
    assert ov["weather"]["days"] == 0


def test_child_count_is_independent_of_the_loaded_page(db, user):
    """F7-Chip: Die Kinder liegen im Zweifel auf einer anderen Seite. Gezählt
    wird deshalb im Server, nicht in der geladenen Liste."""
    trip = _event(db, user, "Reise", category="trip", when=datetime(2024, 6, 30))
    for day in range(1, 6):
        _event(db, user, f"Tag {day}", when=datetime(2024, 7, day), parent=trip.id)

    # Seite von 1, hinter allen Kindern: außer der Reise ist nichts geladen —
    # der Chip muss trotzdem 5 zeigen
    page = list_events(db=db, user=user, slim=True, limit=1, offset=5)
    assert page[0].title == "Reise"
    assert page[0].child_count == 5


def test_index_carries_the_birth_for_the_age_chips(db, user):
    _event(db, user, "Geburt", category="milestone", when=datetime(1990, 4, 12))
    for i in range(5):
        _event(db, user, f"neu {i}", when=datetime(2024, 1, i + 1))

    idx = events_index(db=db, user=user)
    assert idx.birth["date_start"] == datetime(1990, 4, 12)


def test_static_routes_win_over_the_single_event_route():
    """`/api/events/{event_id}` steht am Ende der Datei — mit Absicht.

    Stünde es weiter oben, würde es `/api/events/index`, `/api/events/map` und
    `/api/events/on-this-day` verschlucken: FastAPI nimmt die erste passende
    Route, und `{event_id}` passt auf jedes einzelne Segment. Der Fehler wäre
    ein 404 auf Endpunkte, die es gibt — und niemand würde ihn beim Lesen des
    Codes sehen."""
    from app.routers.events import router

    paths = [r.path for r in router.routes if "GET" in (r.methods or ())]
    single = paths.index("/api/events/{event_id}")
    for static in ("/api/events/index", "/api/events/map", "/api/events/on-this-day"):
        assert paths.index(static) < single, f"{static} steht hinter /{{event_id}}"
