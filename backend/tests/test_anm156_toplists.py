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

from datetime import date, datetime

import pytest

from app.models import (BaselineLocation, ConfirmState, DatePrecision, Event,
                        Location, MediaRef, Metric,
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


def test_one_day_appears_once_in_a_record_list(db, user):
    """Anmerkung 161 — der gemeldete Fall: „Kältester Tag" listete zehnmal
    denselben 11.1.2026, einmal je Foto dieses Tages.

    Seit Anmerkung 139 ist jedes Foto ein Ereignis; an der Rangfolge hat sich
    nichts geändert, wohl aber an dem, was sie zählt. Ein Rekord ist eine
    Auskunft über einen TAG — die Kachel heißt so, und der Klick führt seit
    Anmerkung 142 dorthin.
    """
    cold_day = datetime(2026, 1, 11)
    for i in range(10):
        ev = _event(db, user, cold_day.replace(hour=i),
                    title="Foto in Ehestorf", loc=_loc(db, user, "Ehestorf"))
        db.add(Metric(event_id=ev.id, key="temp_min_c", value=-14.3 - i * 0.2,
                      source=Source.weather))
    ev = _event(db, user, datetime(2026, 1, 12), loc=_loc(db, user, "Kiel"))
    db.add(Metric(event_id=ev.id, key="temp_min_c", value=-3.0,
                  source=Source.weather))
    db.commit()

    rows = compute_toplists(db, user.id)["weather"]["cold"]
    assert [r["date_start"].date().isoformat() for r in rows] == \
        ["2026-01-11", "2026-01-12"]
    # Und der Tag steht mit seinem KÄLTESTEN Ort da, nicht mit einem beliebigen.
    assert rows[0]["value"] == -16.1
    # Die Kachel bleibt Platz 1 der Liste — auch mit der Verdichtung.
    assert compute_overview(db, user.id)["extremes"]["cold"] == rows[0]


def test_the_direction_of_the_record_picks_the_place_of_the_day(db, user):
    """Der heißeste Tag wird am heißesten seiner Orte gemessen, der kälteste am
    kältesten. Das ist keine zweite Regel neben Anmerkung 119 („der Tageswert
    ist der vorsichtige"), sondern eine andere Frage: dort geht es darum, was
    ein Tag beisteuert, hier darum, wie extrem es an ihm wurde.
    """
    day = datetime(2024, 7, 20)
    for hour, (name, warm, cold) in enumerate([
            ("Hamburg", 26.0, 14.0), ("Sevilla", 41.0, 22.0)]):
        ev = _event(db, user, day.replace(hour=hour), loc=_loc(db, user, name))
        db.add_all([
            Metric(event_id=ev.id, key="temp_max_c", value=warm,
                   source=Source.weather),
            Metric(event_id=ev.id, key="temp_min_c", value=cold,
                   source=Source.weather),
        ])
    db.commit()

    wx = compute_toplists(db, user.id)["weather"]
    assert len(wx["hot"]) == 1 and len(wx["cold"]) == 1
    assert wx["hot"][0]["place"] == "Sevilla" and wx["hot"][0]["value"] == 41.0
    assert wx["cold"][0]["place"] == "Hamburg" and wx["cold"][0]["value"] == 14.0


def test_a_zero_is_no_record_for_rain_but_is_one_for_the_felt_cold(db, user):
    """Die Sonderfälle aus `_EXTREMES` gelten auch in der Liste — sonst wären
    sie beim ersten Blick daneben widerlegt (Anmerkung 104).

    **Anmerkung 216: vorgeführt am Tageslicht ging nicht mehr**, denn die
    beiden Tageslicht-Kacheln sind weg (die Tageslänge nennt die Sonnenwende,
    egal was an dem Tag war). Die Regel selbst ist unverändert und braucht
    weiterhin beide Seiten: 0 mm Regen ist KEIN Rekord, 0 °C gefühlte Kälte
    schon — sonst verschwände jeder Tag um den Gefrierpunkt aus der Liste.
    """
    dry = _event(db, user, datetime(2024, 1, 1))
    wet = _event(db, user, datetime(2024, 1, 2))
    db.add_all([
        Metric(event_id=dry.id, key="rain_mm", value=0.0, source=Source.weather),
        Metric(event_id=wet.id, key="rain_mm", value=14.0, source=Source.weather),
        Metric(event_id=dry.id, key="apparent_temp_min_c", value=0.0,
               source=Source.weather),
        Metric(event_id=wet.id, key="apparent_temp_min_c", value=8.0,
               source=Source.weather),
    ])
    db.commit()

    wx = compute_toplists(db, user.id)["weather"]
    assert [r["value"] for r in wx["rainy"]] == [14.0]
    assert wx["felt_cold"][0]["value"] == 0.0


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


# --------------------------------------------------------------------------- #
# Anmerkung 189 — was bisher ungenutzt in der Datenbank lag
# --------------------------------------------------------------------------- #
def test_photos_count_the_day_from_both_anchors(db, user):
    """Ein Bild hängt an einem EREIGNIS oder an einem TAG (F18) — beides kommt
    vor, und nur eines zu lesen ließe die halbe Sammlung aus einer Statistik
    verschwinden, die vollständig aussieht.

    Und: hochgeladen und verknüpft bleiben getrennt (Anmerkung 57). Das eine
    ist Lebensdatenbank, das andere ein Verweis in ein fremdes System.
    """
    ev = _event(db, user, datetime(2024, 5, 4))
    _event(db, user, datetime(2024, 5, 5))          # ohne Bild — der Nenner
    # am Ereignis, ohne eigenen Zeitstempel
    db.add(MediaRef(user_id=user.id, event_id=ev.id, provider="local",
                    external_id="a.jpg", bytes=2048))
    # am TAG, ohne Ereignis
    for i in range(3):
        db.add(MediaRef(user_id=user.id, provider="immich",
                        external_id=f"i{i}",
                        captured_at=datetime(2024, 5, 4, 12 + i)))
    db.commit()

    p = compute_toplists(db, user.id)["photos"]
    assert p["total"] == 4
    assert (p["uploads"], p["linked"]) == (1, 3)
    assert p["bytes"] == 2048, "nur Hochgeladenes belegt DIESE Platte"
    assert p["events_with_photo"] == 1 and p["events_total"] == 2
    # Beide Anker zählen mit: der Zeitraum reicht bis zu dem Tag, an dem die
    # drei Immich-Bilder liegen — sie hängen an KEINEM Ereignis.
    assert p["first"] == "2024-05-04"
    assert [(y["year"], y["count"]) for y in p["years"]] == [(2024, 4)]
    # **Anmerkung 216: „Tage mit den meisten Fotos" gibt es nicht mehr.** Die
    # Zahl war der Zwölfer-Deckel der Tagesleiste, nicht der Bestand des Tages.
    # Geprüft wird das Feld und nicht die Anzeige: solange der Server es
    # liefert, baut die Oberfläche früher oder später wieder eine Kachel daraus.
    assert "days" not in p


def test_farthest_is_measured_against_the_home_of_that_time(db, user):
    """**Ein Lebensmittelpunkt wandert.** Gemessen wird gegen den Wohnort, der
    AN DEM TAG galt — sonst wäre die Kindheit an der Ostsee eine Fernreise,
    sobald jemand nach München zieht.

    **Anmerkung 216: eine Gruppe JE WOHNORT.** Bis dahin kam von hier genau
    eine Zeile zurück, das globale Maximum — obwohl die Schleife schon immer
    über alle Zeiträume lief. Derselbe Ort, zwei Zeiten: von Kiel aus sind es
    90 km nach Hamburg, von München aus 600. Beide Zahlen sind eine Auskunft,
    und die eine ist nicht der Vorentwurf der anderen.
    """
    kiel = _loc(db, user, "Kiel", city="Kiel", country="Deutschland")
    kiel.lat, kiel.lng = 54.32, 10.14
    muenchen = _loc(db, user, "München", city="München", country="Deutschland")
    muenchen.lat, muenchen.lng = 48.14, 11.58
    hamburg = _loc(db, user, "Hamburg", city="Hamburg", country="Deutschland")
    hamburg.lat, hamburg.lng = 53.55, 10.00
    db.add_all([
        BaselineLocation(user_id=user.id, location_id=kiel.id,
                         date_start=date(2000, 1, 1), date_end=date(2009, 12, 31)),
        BaselineLocation(user_id=user.id, location_id=muenchen.id,
                         date_start=date(2010, 1, 1), date_end=date(2019, 12, 31)),
    ])
    _event(db, user, datetime(2005, 6, 1), loc=hamburg, title="damals")
    _event(db, user, datetime(2015, 6, 1), loc=hamburg, title="später")
    db.commit()

    groups = compute_toplists(db, user.id)["farthest"]
    # Chronologisch, wie `baseline.spans` sie liefert.
    assert [g["home"] for g in groups] == ["Kiel", "München"], groups
    assert [g["from"] for g in groups] == ["2000-01-01", "2010-01-01"]
    near, far = groups[0]["tops"][0], groups[1]["tops"][0]
    assert 80 < near["km"] < 110, near
    assert far["km"] > 500 and far["date"] == "2015-06-01", far


def test_farthest_keeps_three_per_residence_and_sorts_them(db, user):
    """Drei Ziele je Wohnort, absteigend — der vierte fällt weg.

    Der Deckel steht in `FAR_PER_HOME` und nicht als Zahl in der Schleife: er
    entscheidet, WAS zu sehen ist, und das gehört an eine Stelle, die man
    benennen kann.
    """
    kiel = _loc(db, user, "Kiel", city="Kiel", country="Deutschland")
    kiel.lat, kiel.lng = 54.32, 10.14
    db.add(BaselineLocation(user_id=user.id, location_id=kiel.id,
                            date_start=date(2000, 1, 1), date_end=date(2009, 12, 31)))
    # Vier Ziele in steigender Entfernung — Hamburg (~90 km), Berlin (~300),
    # München (~700), Lissabon (~2.600).
    for name, lat, lng in [("Hamburg", 53.55, 10.00), ("Berlin", 52.52, 13.40),
                           ("München", 48.14, 11.58), ("Lissabon", 38.72, -9.14)]:
        place = _loc(db, user, name, city=name, country="X")
        place.lat, place.lng = lat, lng
        _event(db, user, datetime(2005, 6, 1), loc=place, title=name)
    db.commit()

    tops = compute_toplists(db, user.id)["farthest"][0]["tops"]
    assert [r["place"] for r in tops] == ["Lissabon", "München", "Berlin"], tops
    assert tops[0]["km"] > tops[1]["km"] > tops[2]["km"]


def test_a_residence_without_anything_recorded_still_gets_its_group(db, user):
    """**Anmerkung 216: „von hier aus nichts erfasst" ist eine Auskunft.**

    Ein Wohnort, der einfach fehlt, sieht aus wie einer, den es nicht gibt —
    und der Nutzer sucht dann in seinen Wohnort-Zeilen nach dem Fehler.
    """
    kiel = _loc(db, user, "Kiel", city="Kiel", country="Deutschland")
    kiel.lat, kiel.lng = 54.32, 10.14
    db.add(BaselineLocation(user_id=user.id, location_id=kiel.id,
                            date_start=date(2000, 1, 1), date_end=date(2009, 12, 31)))
    db.commit()
    groups = compute_toplists(db, user.id)["farthest"]
    assert len(groups) == 1 and groups[0]["tops"] == [], groups


def test_without_a_residence_there_is_no_far_away(db, user):
    """Eine leere Liste statt einer Null, die wie „war nie weg" aussieht."""
    loc = _loc(db, user, "Hamburg", city="Hamburg", country="Deutschland")
    loc.lat, loc.lng = 53.55, 10.00
    _event(db, user, datetime(2015, 6, 1), loc=loc)
    db.commit()
    assert compute_toplists(db, user.id)["farthest"] == []


def test_reach_counts_the_residence_too(db, user):
    """Ein Jahr ganz zu Hause stünde sonst mit „0 Länder" da — obwohl der
    Mensch in einem war. Dieselbe Regel wie überall seit F20."""
    home = _loc(db, user, "Kiel", city="Kiel", country="Deutschland")
    home.lat, home.lng = 54.32, 10.14
    db.add(BaselineLocation(user_id=user.id, location_id=home.id,
                            date_start=date(2015, 1, 1), date_end=date(2015, 12, 31)))
    db.commit()
    reach = {r["year"]: r for r in compute_toplists(db, user.id)["reach"]}
    assert reach[2015]["countries"] == 1 and reach[2015]["cities"] == 1
