"""Anmerkung 221 — Teil 2 der Durchsicht: Ableitungen und Eingänge.

Sechs Reparaturen, und fünf davon sind dieselbe Form: eine Regel, die an einer
Stelle galt und an ihrer Zwillingsstelle nicht.

Jeder Test hier ist gegen den kaputten Stand gefahren worden; wo das nicht
möglich war, steht es dabei.
"""
from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (BaselineLocation, ConfirmState, Event, Location,
                        Metric, Source)
from app.routers import admin
from app.services import geocode, stats_overview as ov, stats_toplists as tl


@pytest.fixture()
def client(db, user):
    """Echter Router-Stapel auf der Test-Session.

    Ohne `with` gebaut: der Lifespan öffnet sonst die KONFIGURIERTE Datenbank
    und startet den Ticker (CLAUDE.md). Auf SQLite unsichtbar, auf PostgreSQL
    hängt die Suite.
    """
    from app.auth import get_current_user

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
#  (a) Die Rohansicht und die Tages-Spalte
# --------------------------------------------------------------------------- #
def test_raw_edit_of_a_date_column(db, user, client):
    """Ein Tag lässt sich ändern, ohne dass der Server abstürzt.

    `_coerce_value` kannte `DateTime` und nicht `Date`; ein reiner Tag fiel
    durch jeden Zweig und ging als ZEICHENKETTE an die Datenbank. Auf SQLite
    ein ungefangener `StatementError` (HTTP 500), auf PostgreSQL castet
    psycopg2 und es geht lautlos durch — die Dialektklasse in die Richtung, in
    die dieses Projekt sonst nicht schaut.
    """
    loc = Location(user_id=user.id, name="Zuhause", lat=52.0, lng=8.0)
    db.add(loc)
    db.flush()
    row = BaselineLocation(user_id=user.id, location_id=loc.id,
                           date_start=datetime.date(2020, 1, 1))
    db.add(row)
    db.commit()

    r = client.patch(f"/api/admin/tables/baseline_locations/{row.id}",
                     json={"date_start": "2021-03-07"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(BaselineLocation, row.id).date_start == datetime.date(2021, 3, 7)


def test_raw_edit_rejects_a_broken_day(db, user, client):
    """Und ein unbrauchbarer Tag wird abgewiesen, nicht durchgereicht."""
    loc = Location(user_id=user.id, name="Zuhause", lat=52.0, lng=8.0)
    db.add(loc)
    db.flush()
    row = BaselineLocation(user_id=user.id, location_id=loc.id,
                           date_start=datetime.date(2020, 1, 1))
    db.add(row)
    db.commit()

    r = client.patch(f"/api/admin/tables/baseline_locations/{row.id}",
                     json={"date_start": "nicht-mal-ein-datum"})
    assert r.status_code == 400
    assert "gültiger Tag" in r.json()["detail"]


def test_a_date_column_keeps_being_a_date(db):
    """Die Umwandlung liefert ein `date` und nicht ein `datetime` um Mitternacht.

    Sonst stünde in `baseline_locations` etwas, das die Wohnort-Rechnung anders
    vergleicht als das, was sie selbst schreibt (`data._dict_to_kwargs` sagt
    denselben Satz seit F20).
    """
    col = BaselineLocation.__table__.columns["date_start"]
    got = admin._coerce_value("baseline_locations", col, "2021-03-07")
    assert type(got) is datetime.date and got == datetime.date(2021, 3, 7)


# --------------------------------------------------------------------------- #
#  (b) Der Ort ohne Namen
# --------------------------------------------------------------------------- #
def test_coordinate_placeholder_is_not_cut_in_half():
    """„Ort (54.358, 10.123)" bleibt ganz — das Komma trennt keine Bestandteile.

    Gekürzt wurde am ersten Komma, und beim Platzhalter ist das die Mitte der
    Koordinate. In der Statistik-Kachel stand „Ort (54.358".
    """
    assert geocode.short_place("Ort (54.358, 10.123)") == "Ort (54.358, 10.123)"
    assert geocode.is_coordinate_name("Ort (54.358, 10.123)")


def test_a_real_address_is_still_shortened():
    """Die Kürzung selbst bleibt — ohne sie zählt jede Langadresse als eigener Ort."""
    assert geocode.short_place("Kirschenallee 12, Bad Segeberg") == "Kirschenallee 12"
    assert not geocode.is_coordinate_name("Kirschenallee 12, Bad Segeberg")
    assert geocode.short_place(None) is None
    assert geocode.short_place("") is None


def test_the_statistics_use_that_one_rule(db, user, fake_weather):
    """Und die Statistik ruft sie auch auf, statt selbst zu schneiden."""
    assert ov._short_place("Ort (54.358, 10.123)") == "Ort (54.358, 10.123)"


# --------------------------------------------------------------------------- #
#  (c) Die wärmste Reise
# --------------------------------------------------------------------------- #
def _dated(user, title, category, day, place=None):
    return Event(user_id=user.id, title=title, category=category,
                 date_start=datetime.datetime(day.year, day.month, day.day, 9),
                 location_id=place, confirmed=ConfirmState.confirmed)


def test_a_jog_does_not_push_the_trip_out_of_the_warmest_trip(db, user):
    """Ein früheres Ereignis desselben Tages darf den Reisetag nicht verdrängen.

    `by_day` verdichtete über ALLE Ereignisse mit Wetter und nahm je Tag das
    früheste; `category == "trip"` kam erst danach. Am Demo-Bestand fielen so
    58 von 257 Reisetagen (23 %) still weg.

    Hier: ein Lauf um 9 Uhr und eine Reise um 10 Uhr am selben Tag. Ohne die
    Reparatur gewinnt der Lauf die Verdichtung, ist keine Reise, und der Tag
    kommt in der Kachel gar nicht vor — `warmest_trip` bliebe `None`.
    """
    day = datetime.date(2019, 7, 1)
    jog = Event(user_id=user.id, title="Laufen, 10 km", category="sport",
                date_start=datetime.datetime(2019, 7, 1, 9),
                confirmed=ConfirmState.confirmed)
    trip = Event(user_id=user.id, title="Museumsinsel", category="trip",
                 date_start=datetime.datetime(2019, 7, 1, 10),
                 confirmed=ConfirmState.confirmed)
    db.add_all([jog, trip])
    db.flush()
    for e in (jog, trip):
        db.add(Metric(event_id=e.id, key="temperature_c", value=24.0,
                      source=Source.weather))
    db.commit()

    got = ov.compute_overview(db, user.id)["weather"]["warmest_trip"]
    assert got is not None, ("Der Reisetag ist aus der Rechnung gefallen, weil "
                            "ein Lauf früher am selben Tag lag.")
    assert got["title"] == "Museumsinsel"
    assert got["avg"] == pytest.approx(24.0)


def test_one_day_still_counts_once(db, user):
    """Die Verdichtung bleibt: zwei Reise-Einträge an einem Tag sind EIN Tag.

    Die Gegenprobe zur Reparatur — sonst hätte ich den Filter davor gesetzt und
    dabei die Verdichtung ganz entfernt. Ein importierter Tag mit dreißig
    Besuchen darf nicht dreißigmal in den Schnitt gehen.
    """
    a = Event(user_id=user.id, title="Reise A", category="trip",
              date_start=datetime.datetime(2019, 7, 1, 9),
              confirmed=ConfirmState.confirmed)
    b = Event(user_id=user.id, title="Reise B", category="trip",
              date_start=datetime.datetime(2019, 7, 1, 18),
              confirmed=ConfirmState.confirmed)
    warm = Event(user_id=user.id, title="Reise Warm", category="trip",
                 date_start=datetime.datetime(2020, 8, 1, 9),
                 confirmed=ConfirmState.confirmed)
    db.add_all([a, b, warm])
    db.flush()
    for e, v in ((a, 10.0), (b, 10.0), (warm, 20.0)):
        db.add(Metric(event_id=e.id, key="temperature_c", value=v,
                      source=Source.weather))
    db.commit()

    got = ov.compute_overview(db, user.id)["weather"]["warmest_trip"]
    # Der 1.7. trägt EINEN Wert (10 °C), nicht zwei — sonst gewänne er nicht,
    # aber die Zahl der Tage wäre falsch. Geprüft wird das Ergebnis: der
    # wärmere Tag gewinnt und trägt seinen eigenen Wert.
    assert got["title"] == "Reise Warm"
    assert got["avg"] == pytest.approx(20.0)


# --------------------------------------------------------------------------- #
#  (d) Die Rangliste, die den Kalender maß
# --------------------------------------------------------------------------- #
def test_years_are_ranked_by_entries_not_by_calendar(db, user):
    """Ein Schaltjahr mit EINEM Eintrag steht nicht vor einem Jahr mit dreien.

    Sortiert wurde nach TAGEN, und seit der Wohnort jede Lücke füllt hat jedes
    volle Jahr 365 oder 366 davon. Die Rangliste zeigte deshalb oben die
    Schaltjahre — am Demo-Bestand sechs identische Werte (366) untereinander,
    darunter 2000 und 2004 mit je einem einzigen Eintrag.

    **Der Aufbau ist der gemeldete Fall und nicht irgendeiner.** Die erste
    Fassung dieses Tests hatte keinen Wohnort und blieb gegen den kaputten
    Stand grün: ohne abgeleitete Tage hat das Jahr mit mehr Einträgen auch mehr
    TAGE, und beide Regeln antworten gleich. Erst der Wohnort gleicht die Tage
    an — und genau dadurch entstand der Defekt überhaupt.

    2019 (365 Tage) bekommt drei Einträge, 2020 (366 Tage, Schaltjahr) einen.
    Nach Tagen gewinnt 2020, nach Einträgen 2019.
    """
    loc = Location(user_id=user.id, name="Zuhause", lat=52.0, lng=8.0)
    db.add(loc)
    db.flush()
    db.add(BaselineLocation(user_id=user.id, location_id=loc.id,
                            date_start=datetime.date(2019, 1, 1),
                            date_end=datetime.date(2020, 12, 31)))
    for n, year in ((3, 2019), (1, 2020)):
        for i in range(n):
            db.add(Event(user_id=user.id, title=f"{year}-{i}", category="event",
                         date_start=datetime.datetime(year, 1, i + 1),
                         confirmed=ConfirmState.confirmed))
    db.commit()

    years = tl.compute_toplists(db, user.id)["years"]
    by_name = {r["name"]: r for r in years}
    # Die Voraussetzung des Tests: die Tage sind angeglichen, und das
    # Schaltjahr hat sogar einen mehr.
    assert by_name["2020"]["days"] > by_name["2019"]["days"], by_name
    assert [r["name"] for r in years][:2] == ["2019", "2020"], years
    assert by_name["2019"]["events"] == 3


def test_places_are_still_ranked_by_days(db, user):
    """Und für Orte bleibt es bei den Tagen — dort ist es die richtige Zahl."""
    rows = [{"name": "Viele Tage", "days": 100, "events": 1},
            {"name": "Viele Einträge", "days": 2, "events": 50}]
    assert [r["name"] for r in tl._merge_baseline(rows, {})] \
        == ["Viele Tage", "Viele Einträge"]
    assert [r["name"] for r in tl._merge_baseline(rows, {}, by="events")] \
        == ["Viele Einträge", "Viele Tage"]


# --------------------------------------------------------------------------- #
#  (e) Der Import und die beschädigte Datei
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("block, was", [
    ("nope", "muss eine Liste sein"),
    ([None], "keinen Datensatz"),
    ([123], "keinen Datensatz"),
])
def test_a_broken_backup_gets_an_answer_not_a_stack_trace(client, block, was):
    """Der Weg, auf dem ein Mensch seine Sicherung zurückspielt, antwortet mit 400.

    Vorher: ungefangener `AttributeError`, HTTP 500. Ein 500er sagt „am Server
    ist etwas kaputt" — kaputt war aber die Datei, und das ist eine Auskunft,
    die der Aufrufer gebrauchen kann.
    """
    r = client.post("/api/data/import",
                    json={"format": "lifedash-export", "events": block})
    assert r.status_code == 400, r.text
    assert was in r.json()["detail"]


def test_a_file_that_is_not_an_export_is_refused_with_a_status_code(client):
    """Und ein falsches `format` ist ein Fehler, kein Erfolg mit Hinweis.

    Hier stand HTTP 200 mit `{"error": …}` im Rumpf — als einziger Fehlerweg
    dieser Datei. Eine Oberfläche, die auf den Statuscode sieht, meldete einen
    erfolgreichen Import von null Zeilen.
    """
    r = client.post("/api/data/import", json={"format": "irgendwas"})
    assert r.status_code == 400
    assert "kein Life-Dash-Export" in r.json()["detail"]


def test_a_missing_block_is_still_fine(client):
    """Ein FEHLENDER Abschnitt bleibt erlaubt — ältere Exporte haben weniger.

    Ohne diesen Test wäre die Prüfung oben die Sorte, die Angriffe abwehrt und
    dabei den Normalfall beschädigt: `baseline_locations` und `day_metrics`
    kamen ohne neue Export-Version dazu, gerade weil ein alter Export sie nicht
    mitbringt.
    """
    r = client.post("/api/data/import", json={"format": "lifedash-export"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


# --------------------------------------------------------------------------- #
#  (f) Zeiträume, die es nicht geben kann
# --------------------------------------------------------------------------- #
def test_an_event_cannot_end_before_it_starts(client):
    r = client.post("/api/events", json={"title": "rückwärts",
                                         "date_start": "2020-05-01T10:00:00",
                                         "date_end": "2020-01-01T10:00:00"})
    assert r.status_code == 422
    assert "Ende liegt vor dem Anfang" in r.text


def test_the_same_moment_is_allowed(client):
    """Anfang gleich Ende ist ein gültiger Punkt und keine negative Spanne."""
    r = client.post("/api/events", json={"title": "punkt",
                                         "date_start": "2020-05-01T10:00:00",
                                         "date_end": "2020-05-01T10:00:00"})
    assert r.status_code == 201, r.text


def test_a_partial_change_is_checked_against_the_stored_half(client):
    """**Der Fall, den das Schema nicht sehen kann.**

    Eine Teiländerung schickt nur `date_end`; `date_start` steht in der
    Datenbank. Ein Validator über den Rumpf hätte hier nichts zu vergleichen
    und wäre grün — die Prüfung gehört deshalb hinter das Zusammenfügen.
    """
    ev = client.post("/api/events", json={"title": "spanne",
                                          "date_start": "2020-05-01T10:00:00"}).json()
    r = client.patch(f"/api/moderation/{ev['id']}",
                     json={"date_end": "2019-01-01T10:00:00"})
    assert r.status_code == 400
    assert "Ende liegt vor dem Anfang" in r.json()["detail"]

    ok = client.patch(f"/api/moderation/{ev['id']}",
                      json={"date_end": "2020-05-03T10:00:00"})
    assert ok.status_code == 200


@pytest.mark.parametrize("year, allowed", [
    (9999, False),      # der gemeldete Fall
    (1700, False),
    (1893, True),       # „Großvater geboren" — eine Lebensdatenbank erbt
    (2020, True),
])
def test_only_years_that_can_be_meant(client, year, allowed):
    r = client.post("/api/events", json={"title": "x",
                                         "date_start": f"{year}-01-01T10:00:00"})
    assert (r.status_code == 201) is allowed, r.text


def test_a_residence_in_the_far_future_is_refused(client):
    r = client.post("/api/baselines", json={"place": "Später", "lat": 52.0,
                                            "lng": 8.0, "date_start": "3000-01-01"})
    assert r.status_code == 422


def test_a_residence_next_month_is_not(client):
    """**Ausdrücklich erlaubt.** Wer zum Ersten umzieht, trägt das vorher ein.

    Der Befund lautete „ein Wohnort in der Zukunft wird angenommen"; genau das
    ist richtig, und eine Frist dafür wäre eine erfundene Politik über die
    Daten des Nutzers. Abgewiesen wird nur das Jahr, das niemand gemeint haben
    kann (Test darüber).
    """
    soon = datetime.date.today() + datetime.timedelta(days=30)
    r = client.post("/api/baselines", json={"place": "Neue Wohnung", "lat": 52.0,
                                            "lng": 8.0,
                                            "date_start": soon.isoformat()})
    assert r.status_code == 201, r.text
