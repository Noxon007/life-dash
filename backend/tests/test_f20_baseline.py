"""F20 — der Wohnort (Anmerkung 144).

Was hier festgenagelt wird, ist nicht „es gibt eine neue Tabelle", sondern die
fünf Stellen, an denen dieses Paket still falsch wird:

* **Erfasste und abgeleitete Tage sind disjunkt.** Der Wohnort füllt nur
  Lücken. Auf dieser Eigenschaft beruht, dass jede Statistik die beiden Mengen
  einfach ADDIEREN darf und dass die Wetter-Vereinigung keinen Tag doppelt
  sieht. Fällt sie, zählt alles doppelt — und zwar leise.
* **Ein Zeitraum ist EINE Zeile.** Die Korrektur eines Datums darf nichts
  hinterlassen; genau dafür wurde gegen erzeugte Ereignisse entschieden.
* **Abgeleitete Tage zählen voll mit** (Entscheidung des Users) — aber nur als
  TAGE. Ein abgeleiteter Tag ist kein Eintrag und hat keine Kategorie.
* **Der Deckel darf die Antwort nicht entscheiden.** Ein Ort mit 2 000
  abgeleiteten Tagen muss in der Rangliste stehen, auch wenn er ohne sie nicht
  unter die ersten zehn käme.
* **Das Tageswetter merkt sich, dass gefragt wurde.** Sonst fragt derselbe Tag
  bei jedem Lauf erneut — die Endlos-Abruf-Falle, hier in ihrer nächsten
  Auflage.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (BaselineLocation, ConfirmState, DatePrecision, DayMetric,
                        Event, Location, Source, User, UserRole)
from app.services import baseline
from app.services.enrichment import enrich_weather
from app.services.stats_overview import compute_overview
from app.services.stats_toplists import compute_toplists

TODAY = date(2026, 8, 3)


# --------------------------------------------------------------------------- #
# Hilfen
# --------------------------------------------------------------------------- #
def _loc(db, user, name, *, city=None, country=None, lat=53.9, lng=10.3):
    loc = Location(user_id=user.id, name=name, city=city, country=country,
                   lat=lat, lng=lng)
    db.add(loc)
    db.flush()
    return loc


def _base(db, user, loc, start, end=None, label=None):
    row = BaselineLocation(user_id=user.id, location_id=loc.id, label=label,
                           date_start=start, date_end=end)
    db.add(row)
    db.flush()
    return row


def _event(db, user, when, *, loc=None, title="Eintrag", category="event"):
    ev = Event(user_id=user.id, title=title, category=category,
               date_start=when, date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.manual,
               location=loc)
    db.add(ev)
    db.flush()
    return ev


@pytest.fixture()
def client(db, user):
    """Echte HTTP-Aufrufe gegen dieselbe Sitzung wie die Fixtures.

    **Ohne `with`, und das ist der ganze Punkt.** Im `with`-Block fährt der
    TestClient den Lifespan der App — und der öffnet `ensure_schema` und
    `create_all` auf der KONFIGURIERTEN Datenbank (nicht auf der des Tests) und
    startet den Minuten-Ticker des Nachtplans. `test_a35_local_auth.py` hat
    genau das schon einmal aufgeschrieben und deshalb dort auf einen Client
    verzichtet. Ohne den Kontextmanager läuft kein Lifespan; die Anfragen gehen
    trotzdem durch den echten Router-Stapel, und darum geht es hier.

    (Auf SQLite fiel das nicht auf — dort ist die konfigurierte Datenbank eine
    Datei, die niemand ansieht. Auf PostgreSQL hing der Lauf. Wieder ein
    Befund, den nur der zweite Dialekt liefert.)
    """
    app.dependency_overrides[get_db] = lambda: db
    from app.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Die Regel: nur Lücken
# --------------------------------------------------------------------------- #
def test_a_day_with_an_entry_is_not_filled(db, user):
    """Die Eigenschaft, auf der der Rest des Pakets steht.

    Fällt sie, addiert jede Statistik denselben Tag zweimal und das
    Tageswetter bekommt zwei Werte für einen Tag — beides ohne Fehlermeldung.
    """
    loc = _loc(db, user, "Bad Segeberg", city="Bad Segeberg", country="Deutschland")
    _base(db, user, loc, date(2024, 1, 1), date(2024, 1, 10))
    _event(db, user, datetime(2024, 1, 5, 12))
    db.commit()

    days = baseline.inferred_days(db, user.id, today=TODAY)
    assert len(days) == 9
    assert date(2024, 1, 5) not in days
    # …und die beiden Mengen schneiden sich wirklich nicht
    assert not (set(days) & baseline.recorded_days(db, user.id))


def test_several_entries_on_one_day_still_block_only_that_day(db, user):
    loc = _loc(db, user, "Bad Segeberg")
    _base(db, user, loc, date(2024, 3, 1), date(2024, 3, 3))
    for hour in range(5):
        _event(db, user, datetime(2024, 3, 2, hour))
    db.commit()
    assert sorted(baseline.inferred_days(db, user.id, today=TODAY)) == \
        [date(2024, 3, 1), date(2024, 3, 3)]


def test_an_open_period_ends_today_not_in_the_future(db, user):
    """„Seit 2019 wohne ich hier" ist keine Aussage über morgen."""
    loc = _loc(db, user, "Kiel")
    _base(db, user, loc, TODAY - timedelta(days=2), None)
    db.commit()
    days = sorted(baseline.inferred_days(db, user.id, today=TODAY))
    assert days == [TODAY - timedelta(days=2), TODAY - timedelta(days=1), TODAY]


def test_a_period_that_ends_before_it_starts_is_skipped_not_swapped(db, user):
    """Stillschweigend zu tauschen hieße, eine falsche Eingabe unsichtbar zu
    machen — der Nutzer sähe eine Zeile, die etwas anderes tut, als sie sagt."""
    loc = _loc(db, user, "Kiel")
    _base(db, user, loc, date(2024, 5, 10), date(2024, 5, 1))
    db.commit()
    assert baseline.inferred_days(db, user.id, today=TODAY) == {}


# --------------------------------------------------------------------------- #
# Ein Zeitraum ist EINE Zeile
# --------------------------------------------------------------------------- #
def test_correcting_the_period_leaves_nothing_behind(db, user):
    """Der Vorgang, für den F20 überhaupt so gebaut ist (Anmerkung 144).

    Wären die Tage erzeugte, bestätigte Ereignisse, stünden nach dieser einen
    Änderung Zeilen falsch da, die keine Maschine mehr anfassen dürfte.
    """
    loc = _loc(db, user, "Bad Segeberg")
    row = _base(db, user, loc, date(1986, 1, 1), date(1992, 12, 31))
    db.commit()
    before = len(baseline.inferred_days(db, user.id, today=TODAY))

    row.date_end = date(1990, 12, 31)
    db.commit()
    after = baseline.inferred_days(db, user.id, today=TODAY)
    assert len(after) < before
    assert max(after) == date(1990, 12, 31)
    # Nichts ist zurückgeblieben: es gibt keine Zeile je Tag, die man
    # vergessen könnte.
    assert db.query(Event).count() == 0


def test_two_periods_may_not_overlap(client, db, user):
    """Ein Wohnort zur Zeit (Anmerkung 144, Entscheidung 4)."""
    loc = _loc(db, user, "Bad Segeberg")
    _base(db, user, loc, date(2000, 1, 1), date(2005, 12, 31), label="Elternhaus")
    db.commit()

    r = client.post("/api/baselines", json={
        "place": "Bad Segeberg", "date_start": "2004-01-01",
        "date_end": "2008-12-31"})
    assert r.status_code == 409
    # Der Fehler NENNT den Zeitraum, mit dem es sich schneidet — sonst wäre es
    # eine Ablehnung ohne Hinweis, was zu ändern ist.
    assert "Elternhaus" in r.json()["detail"]


def test_a_period_may_be_moved_onto_its_own_old_span(client, db, user):
    """Beim Ändern darf sich der Zeitraum nicht mit SICH SELBST schneiden."""
    loc = _loc(db, user, "Kiel")
    row = _base(db, user, loc, date(2000, 1, 1), date(2005, 12, 31))
    db.commit()
    r = client.patch(f"/api/baselines/{row.id}",
                     json={"date_end": "2006-12-31"})
    assert r.status_code == 200, r.text
    assert r.json()["date_end"] == "2006-12-31"


# --------------------------------------------------------------------------- #
# Zählen: voll mit, aber als TAGE
# --------------------------------------------------------------------------- #
def test_inferred_days_count_in_places_cities_and_countries(db, user):
    loc = _loc(db, user, "Musterweg 1, Bad Segeberg", city="Bad Segeberg",
               country="Deutschland")
    _base(db, user, loc, date(2024, 1, 1), date(2024, 1, 31))
    db.commit()

    ov = compute_overview(db, user.id)
    assert dict(ov["top_places"])["Musterweg 1"] == 31
    assert dict(ov["top_cities"])["Bad Segeberg"] == 31
    assert ov["baseline_days"] == 31

    top = compute_toplists(db, user.id)
    assert top["places"][0] == {"name": "Musterweg 1", "days": 31, "events": 0}
    assert top["cities"][0]["days"] == 31
    assert top["countries"][0] == {"name": "Deutschland", "days": 31, "events": 0}
    assert top["years"][0] == {"name": "2024", "days": 31, "events": 0}


def test_an_inferred_day_is_not_an_entry(db, user):
    """Beide Zahlen bleiben unterscheidbar (Anmerkung 143)."""
    loc = _loc(db, user, "Kiel", city="Kiel", country="Deutschland")
    _base(db, user, loc, date(2024, 2, 1), date(2024, 2, 10))
    _event(db, user, datetime(2024, 2, 20, 9), loc=loc, category="concert")
    db.commit()

    top = compute_toplists(db, user.id)
    city = top["cities"][0]
    assert city["days"] == 11 and city["events"] == 1
    # Kategorien bekommen den Wohnort NICHT — ein abgeleiteter Tag hat keine.
    assert [c["name"] for c in top["categories"]] == ["concert"]
    assert top["categories"][0]["days"] == 1


def test_the_ranking_cap_does_not_decide_the_answer(db, user):
    """Ein Ort mit 2 000 abgeleiteten Tagen muss in der Liste stehen, auch wenn
    er ohne sie nicht unter die ersten zehn käme.

    **Der Fall, der wirklich verlorengeht, ist der Ort mit BEIDEM.** Ein Name,
    den die Abfrage gar nicht kennt, wird beim Zusammenführen ohnehin neu
    angelegt — dieser Test war im ersten Anlauf grün, auch mit
    zurückgebautem `_PRE_N` (Anmerkung 108, und diesmal beim Fahren gegen den
    kaputten Stand gefunden). Verloren geht die ZEILE eines Orts, der ein paar
    Einträge hat und deshalb unterhalb des Deckels liegt: sie kommt dann als
    frische Zeile ohne ihre Einträge zurück, und die Liste behauptet „0
    Einträge" für einen Ort, an dem welche stehen.
    """
    for i in range(20):
        city = _loc(db, user, f"Ort {i:02d}", city=f"Stadt {i:02d}")
        for d in range(5):
            _event(db, user, datetime(2020, 1, 1) + timedelta(days=i * 40 + d),
                   loc=city)
    home = _loc(db, user, "Elternhaus", city="Bad Segeberg")
    _event(db, user, datetime(2019, 5, 5, 9), loc=home)
    _base(db, user, home, date(2000, 1, 1), date(2005, 12, 31))
    db.commit()

    top = compute_toplists(db, user.id)
    assert top["places"][0]["name"] == "Elternhaus"
    assert top["places"][0]["days"] > 2000
    first = top["cities"][0]
    assert first["name"] == "Bad Segeberg"
    # Der eine erfasste Tag ist noch da — und zwar als TAG und als EINTRAG.
    assert first["events"] == 1
    assert first["days"] == baseline.day_counts(db, user.id)["cities"][
        "Bad Segeberg"] + 1


def test_the_streak_counts_baseline_days(db, user):
    """Die Serie fragt „wie lange am Stück weiß ich, wo ich war" — nicht „wie
    lange am Stück habe ich getippt"."""
    loc = _loc(db, user, "Kiel")
    _base(db, user, loc, date(2024, 4, 1), date(2024, 4, 30))
    _event(db, user, datetime(2024, 5, 1, 8))
    db.commit()

    streaks = compute_toplists(db, user.id)["streaks"]
    assert streaks["longest_run"] == {"from": "2024-04-01", "to": "2024-05-01",
                                      "days": 31}
    assert streaks["longest_gap"] is None


def test_a_baseline_colours_the_world_map(client, db, user):
    """Ein Land, in dem jemand sechs Jahre gelebt hat, ist besucht — auch wenn
    aus dieser Zeit kein einziger Eintrag existiert. Genau dafür gibt es F20."""
    loc = _loc(db, user, "Bad Segeberg", country="Deutschland")
    _base(db, user, loc, date(2024, 1, 1), date(2024, 1, 20))
    db.commit()

    world = client.get("/api/world").json()
    de = [c for cont in world["continents"] for c in cont["countries"]
          if c["iso"] == "DE"]
    assert de, "Deutschland fehlt auf der Karte"
    assert de[0]["day_count"] == 20
    # Der Eintrags-Zähler bleibt bei null: ein abgeleiteter Tag ist kein Eintrag.
    assert de[0]["event_count"] == 0


# --------------------------------------------------------------------------- #
# Tageswetter
# --------------------------------------------------------------------------- #
def test_weather_run_fills_baseline_days_and_marks_them(db, user, fake_weather):
    """Und fragt sie beim zweiten Lauf NICHT erneut ab.

    Die Endlos-Abruf-Falle in ihrer nächsten Auflage: ohne Marke fragt jeder
    Lauf dieselben 14 600 Tage erneut bei Open-Meteo an.
    """
    loc = _loc(db, user, "Kiel")
    _base(db, user, loc, TODAY - timedelta(days=4), TODAY)
    db.commit()

    enriched, remaining = enrich_weather(db)
    assert enriched == 5 and remaining == 0
    assert len(fake_weather) == 5
    assert db.query(DayMetric).filter(DayMetric.key == "temp_max_c").count() == 5

    fake_weather.clear()
    enriched, remaining = enrich_weather(db)
    assert (enriched, remaining) == (0, 0)
    assert fake_weather == [], "derselbe Tag wurde ein zweites Mal abgefragt"


def test_the_day_header_shows_baseline_weather(client, db, user, fake_weather):
    """Der Tageskopf liest EINE Funktion (Anmerkung 119) — sie muss beide
    Quellen kennen, sonst hätte ein Wohnort-Tag zwar Wetter und zeigte keins."""
    loc = _loc(db, user, "Kiel")
    _base(db, user, loc, date(2024, 6, 1), date(2024, 6, 2))
    db.commit()
    enrich_weather(db)

    wx = client.get("/api/days/weather",
                    params={"from": "2024-06-01", "to": "2024-06-02"}).json()
    assert wx["2024-06-01"]["values"]["temp_max_c"] == 29.0
    assert wx["2024-06-01"]["values"]["weather"] == "Klar"
    # Ein Tag ohne zweite Region ist eindeutig — der Wohnort hat genau einen Ort.
    assert wx["2024-06-01"]["regions"] == 1


def test_baseline_weather_reaches_the_badge_thresholds(db, user, fake_weather):
    """Die Erfolge zählen über `day_value_query`. Läse die nur die
    Ereignis-Metriken, wären Wohnort-Tage für sie unsichtbar — und ein Nutzer
    mit zwanzig Jahren Wohnort hätte Wetterdaten, die nirgends ankommen."""
    from app.services.weather_day import day_value_query

    loc = _loc(db, user, "Kiel")
    _base(db, user, loc, date(2024, 7, 1), date(2024, 7, 3))
    db.commit()
    enrich_weather(db)

    rows = day_value_query(db, user.id, "sunshine_h", min_value=10).all()
    assert len(rows) == 3


def test_day_weather_survives_a_moved_period_and_can_be_cleared(client, db, user,
                                                               fake_weather):
    """Es ist eine Tatsache über (Tag, Ort), nicht über den Zeitraum — also
    bleibt es stehen und wird nur nicht mehr gelesen. Weg kommt es auf
    ausdrücklichen Knopfdruck, weil Schicht 4 verwerfbar ist."""
    loc = _loc(db, user, "Kiel")
    row = _base(db, user, loc, date(2024, 9, 1), date(2024, 9, 3))
    db.commit()
    enrich_weather(db)
    before = db.query(DayMetric).count()
    assert before > 0

    client.patch(f"/api/baselines/{row.id}", json={"date_end": "2024-09-01"})
    assert db.query(DayMetric).count() == before

    r = client.post("/api/baselines/weather/clear")
    assert r.status_code == 200 and r.json()["removed"] == before
    assert db.query(DayMetric).count() == 0


# --------------------------------------------------------------------------- #
# Endpunkte
# --------------------------------------------------------------------------- #
def test_the_list_reports_the_days_it_really_fills(client, db, user):
    """Die Spanne wäre die einfachere und die unehrlichere Zahl."""
    loc = _loc(db, user, "Bad Segeberg")
    _base(db, user, loc, date(2024, 1, 1), date(2024, 1, 10))
    for d in (3, 4):
        _event(db, user, datetime(2024, 1, d, 10))
    db.commit()

    rows = client.get("/api/baselines").json()
    assert len(rows) == 1 and rows[0]["day_count"] == 8


def test_the_day_endpoint_answers_only_its_window(client, db, user):
    loc = _loc(db, user, "Kiel", city="Kiel")
    _base(db, user, loc, date(2024, 1, 1), date(2024, 12, 31), label="Studium")
    db.commit()

    r = client.get("/api/days/baseline",
                   params={"from": "2024-03-01", "to": "2024-03-05"}).json()
    assert sorted(r["days"]) == ["2024-03-01", "2024-03-02", "2024-03-03",
                                 "2024-03-04", "2024-03-05"]
    # Die Beschreibung steht EINMAL da, je Tag nur ihr Index (Anmerkung 157).
    assert len(r["periods"]) == 1
    assert r["periods"][0]["label"] == "Studium"
    assert r["periods"][0]["place"] == "Kiel"
    assert set(r["days"].values()) == {0}


def test_the_day_endpoint_does_not_repeat_the_description_per_day(client, db, user):
    """Ein Zeitraum über sechs Jahre sind 2 190 Tage — die Beschreibung an
    jedem einzelnen wäre 1,4 MB für eine Auskunft von dreißig Byte
    (Anmerkung 157, hier gleich beim ersten Bau angewandt)."""
    loc = _loc(db, user, "Musterweg 1, Bad Segeberg", city="Bad Segeberg")
    _base(db, user, loc, date(2000, 1, 1), date(2005, 12, 31), label="Elternhaus")
    db.commit()

    r = client.get("/api/days/baseline",
                   params={"from": "2000-01-01", "to": "2005-12-31"}).json()
    assert len(r["days"]) == 2192       # zwei Schaltjahre
    assert len(r["periods"]) == 1
    # Der lange Ortsname kommt genau einmal über die Leitung.
    assert client.get("/api/days/baseline",
                      params={"from": "2000-01-01", "to": "2005-12-31"}
                      ).text.count("Musterweg 1") == 1


def test_the_index_carries_the_baseline_years(client, db, user):
    """Ein Jahr, in dem NUR abgeleitete Tage liegen, muss in der Übersicht
    stehen — sonst ist die Kindheit unsichtbar, obwohl sie gefüllt ist."""
    loc = _loc(db, user, "Bad Segeberg")
    _base(db, user, loc, date(1990, 1, 1), date(1990, 1, 20))
    db.commit()

    idx = client.get("/api/events/index").json()
    assert idx["years"] == []
    assert idx["baseline_days"] == 20
    assert idx["baseline_years"] == [{"year": 1990, "count": 20}]


def test_the_revision_moves_when_a_period_changes(client, db, user):
    """Anmerkung 140 eine Tabelle weiter: eine geänderte Zeile lässt Zahl und
    Zeitstempel der EREIGNISSE unberührt — die Karte zeigte sonst den alten
    Stand weiter."""
    loc = _loc(db, user, "Kiel")
    row = _base(db, user, loc, date(2024, 1, 1), date(2024, 1, 5))
    db.commit()
    first = client.get("/api/events/index").json()["revision"]

    client.patch(f"/api/baselines/{row.id}", json={"date_end": "2024-02-05"})
    assert client.get("/api/events/index").json()["revision"] != first


def test_clearing_the_end_reopens_the_period(client, db, user):
    """Anmerkung 184: `clear_end` ist der Unterschied zwischen „unverändert
    lassen" und „das Ende soll weg".

    In JSON heißt ein fehlendes Feld dasselbe wie `null`, nämlich nichts.
    Ohne das eigene Feld wäre „bis heute" nachträglich nicht mehr einstellbar —
    genau der Fall, der beim Umzug in die aktuelle Wohnung eintritt: das
    Formular zeigte „bis heute" und der Zeitraum behielte sein altes Ende.
    """
    loc = _loc(db, user, "Kiel")
    row = _base(db, user, loc, date(2024, 1, 1), date(2024, 1, 5))
    db.commit()

    # Ohne das Feld bleibt das Ende stehen, auch wenn `date_end: null` kommt.
    client.patch(f"/api/baselines/{row.id}", json={"date_end": None})
    db.refresh(row)
    assert row.date_end == date(2024, 1, 5)

    r = client.patch(f"/api/baselines/{row.id}", json={"clear_end": True})
    assert r.status_code == 200
    db.refresh(row)
    assert row.date_end is None
    # Und ab jetzt füllt er bis heute, nicht bis zum 5. Januar.
    assert max(baseline.inferred_days(db, user.id, today=TODAY)) == TODAY


def test_changing_only_the_label_keeps_the_chosen_point(client, db, user):
    """Anmerkung 184: der Ort bleibt unberührt, wenn er nicht mitkommt.

    „Das Elternhaus" ist oft eine Adresse, die Nominatim nicht kennt — sein
    Punkt kommt aus einem Klick auf die Karte. Würde die Oberfläche den
    unveränderten Namen beim Ändern der BEZEICHNUNG mitschicken, geocodierte
    der Server ihn neu und ersetzte den Punkt durch den Ortsmittelpunkt. Der
    Endpunkt muss das aushalten: kein `place`, keine Berührung.
    """
    loc = _loc(db, user, "Elternhaus", lat=53.93, lng=10.31)
    row = _base(db, user, loc, date(2024, 1, 1), date(2024, 1, 5))
    db.commit()

    client.patch(f"/api/baselines/{row.id}", json={"label": "Zuhause"})
    db.refresh(row)
    assert row.label == "Zuhause"
    assert row.location_id == loc.id
    assert (row.location.lat, row.location.lng) == (53.93, 10.31)

    # Und die leere Bezeichnung ist eine Aussage, kein Auslassen: sie löscht.
    client.patch(f"/api/baselines/{row.id}", json={"label": ""})
    db.refresh(row)
    assert row.label is None


def test_another_account_sees_nothing(client, db, user):
    other = User(oidc_subject="other", email="o@example.org", role=UserRole.user)
    db.add(other)
    db.flush()
    loc = _loc(db, other, "Fremdort")
    _base(db, other, loc, date(2024, 1, 1), date(2024, 1, 10))
    db.commit()

    assert client.get("/api/baselines").json() == []
    assert baseline.inferred_days(db, user.id, today=TODAY) == {}


def test_deleting_a_period_keeps_its_place(client, db, user):
    """Der Ort kann an Ereignissen hängen; ihn mitzulöschen wäre eine Änderung
    an der Lebensdatenbank als Nebenwirkung."""
    loc = _loc(db, user, "Kiel")
    row = _base(db, user, loc, date(2024, 1, 1), date(2024, 1, 5))
    _event(db, user, datetime(2024, 6, 1, 9), loc=loc)
    db.commit()

    assert client.delete(f"/api/baselines/{row.id}").status_code == 204
    assert db.query(BaselineLocation).count() == 0
    assert db.get(Location, loc.id) is not None
