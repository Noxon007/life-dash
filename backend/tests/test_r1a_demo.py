"""R1a — der Demo-Bestand: ein erfundenes Leben, das sich nicht widerspricht.

**Was hier geprüft wird, ist nicht „sieht gut aus".** Ein Demo-Bestand ist ein
Schaufenster, und die teuren Fehler eines Schaufensters sind still: eine
Ansicht, die leer bleibt und deshalb kaputt aussieht; ein Knopf, der beim ersten
Klick zehntausend Netzabrufe startet; ein Bestand, der bei jedem Aufbau anders
ist, sodass kein Screenshot zweimal stimmt.

**Der Bestand wird EINMAL je Modul gebaut** (`corpus`), nicht je Test: fünf
Sekunden mal zehn wären die Hälfte der Testzeit dieses Projekts für eine
Sache, die sich zwischen zwei Zusicherungen nicht ändert.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data import countries as ref
from app.database import Base
from app.demo import _Builder, life, seed_demo
from app.demo.weather import daylight_hours, synth_weather
from app.models import (BaselineLocation, ConfirmState, DayMetric, Entity, Event,
                        Fragment, FragmentStatus, Location, Metric, Source, Track,
                        User, UserRole)
from app.services.enrichment import (_WEATHER_METRICS, _WEATHER_TEXT_METRICS,
                                     WEATHER_REVISION, _weather_candidates)


@pytest.fixture(scope="module")
def corpus():
    """Der volle Demo-Bestand in einer eigenen Datenbank.

    **Eigene Engine statt der `db`-Fixture, und zwar auch beim PostgreSQL-Lauf.**
    Die geteilte Engine wird von der `db`-Fixture VOR JEDEM Test geleert — ein
    modulweiter Bestand darauf wäre nach dem ersten fremden Test weg, und die
    Zusicherungen danach prüften eine leere Datenbank, ohne rot zu werden. Was
    an diesem Bestand dialektabhängig ist (Fremdschlüssel), prüft
    `test_seed_survives_foreign_keys` auf der echten Datenbank.
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    user = User(id="demo", oidc_subject="demo-sub", email="demo@example.org",
                display_name=life.DISPLAY_NAME, role=UserRole.admin)
    db.add(user)
    db.commit()
    seed_demo(db, user)
    yield db, user
    db.close()
    engine.dispose()


# --------------------------------------------------------------------------- #
# Das synthetische Wetter — eine reine Funktion, also billig zu prüfen
# --------------------------------------------------------------------------- #
def test_weather_is_reproducible():
    """Zweimal gefragt, zweimal dieselbe Antwort — sonst ist kein Screenshot
    zweimal derselbe und keine Messung wiederholbar."""
    a = synth_weather(53.55, 9.99, date(2019, 7, 14))
    b = synth_weather(53.55, 9.99, date(2019, 7, 14))
    assert a == b
    assert synth_weather(53.55, 9.99, date(2019, 7, 15)) != a


def test_weather_has_exactly_the_real_keys():
    """Dieselben Schlüssel wie das echte Wetter — nicht mehr und nicht weniger.

    Ein fehlender Schlüssel ergäbe eine Statistik-Kachel, die in der Demo leer
    bleibt; ein erfundener ginge lautlos ins Nichts, weil ihn niemand abbildet.
    Beides sind Defekte, deshalb wird in BEIDE Richtungen verglichen.
    """
    got = set(synth_weather(53.55, 9.99, date(2019, 7, 14)))
    expected = set(_WEATHER_METRICS) | set(_WEATHER_TEXT_METRICS) | {"condition", "code"}
    assert got == expected


def test_weather_never_contradicts_itself():
    """Über zwei Jahre an fünf sehr verschiedenen Orten."""
    spots = [(53.55, 9.99), (38.72, -9.14), (69.65, 18.96), (-33.87, 151.21), (18.79, 98.99)]
    day = date(2020, 1, 1)
    while day < date(2022, 1, 1):
        for lat, lng in spots:
            w = synth_weather(lat, lng, day)
            assert w["temp_min_c"] <= w["temp_max_c"]
            # Mehr Sonne als Tag ist keine Ungenauigkeit, sondern eine
            # Unmöglichkeit — und sie stünde in einer Rangliste.
            assert w["sun_h"] <= w["daylight_h"] + 0.05
            assert w["gust_max_kmh"] >= w["wind_max_kmh"]
            assert w["rain_h"] <= w["daylight_h"] + 0.05
            assert w["uv_max"] >= 0
            assert w["condition"]
        day += timedelta(days=17)


def test_seasons_are_inverted_south_of_the_equator():
    """Sonst hätte die Demo im australischen Juli Schnee — und die Zahl sähe
    für sich genommen richtig aus."""
    july, january = date(2021, 7, 15), date(2021, 1, 15)
    hamburg_summer = synth_weather(53.55, 9.99, july)["temp_c"]
    hamburg_winter = synth_weather(53.55, 9.99, january)["temp_c"]
    sydney_july = synth_weather(-33.87, 151.21, july)["temp_c"]
    sydney_january = synth_weather(-33.87, 151.21, january)["temp_c"]
    assert hamburg_summer > hamburg_winter
    assert sydney_january > sydney_july


def test_polar_day_and_night_do_not_crash():
    """Tromsø steht im Bestand — `acos` außerhalb seines Bereichs wäre ein
    Absturz mitten im Aufbau, nicht eine schiefe Zahl."""
    assert daylight_hours(78.2, date(2021, 6, 21)) == 24.0
    assert daylight_hours(78.2, date(2021, 12, 21)) == 0.0
    assert 0 < daylight_hours(53.55, date(2021, 3, 20)) < 24


# --------------------------------------------------------------------------- #
# Der Aufbau
# --------------------------------------------------------------------------- #
def test_the_schedule_is_reproducible(db, user, monkeypatch):
    """Zweimal aufgebaut, zweimal dieselben Ereignisse.

    Das Wetter wird für diesen Vergleich abgeschaltet: es ist eine reine
    Funktion von (Ort, Tag) und hat seine eigene Prüfung oben — was hier auf
    dem Spiel steht, ist der GEWÜRFELTE Teil, also wann jemand laufen war.
    Ohne das Abschalten kostete die Zusicherung zweihunderttausend Zeilen für
    eine Frage, die keine einzige davon betrifft.
    """
    monkeypatch.setattr(_Builder, "_weather_rows", lambda self, loc, day: [])

    def fingerprint(tag):
        second = User(oidc_subject=f"twin-{tag}", email=f"{tag}@example.org",
                      role=UserRole.user)
        db.add(second)
        db.flush()
        b = _Builder(db, second)
        from app.demo import _concerts, _habits, _milestones, _residences, _trips
        spans = _residences(b)
        _milestones(b)
        _trips(b)
        _concerts(b)
        _habits(b, spans)
        db.expunge_all()
        return [(e["date_start"], e["title"], e["category"]) for e in b.events]

    first, again = fingerprint("a"), fingerprint("b")
    assert first == again
    assert len(first) > 2000, "ein Leben aus zweitausend Einträgen ist das Minimum"


def test_the_generators_stop_at_their_last_day(db, user):
    """Die Schranke selbst, ohne Wanduhr und ohne Zufall.

    Der Test darüber prüft den fertigen Bestand und ist damit auf den
    Würfel angewiesen: ob die kaputte Fassung wirklich einen Besuch am
    heutigen Tag anlegt, hängt daran, was der Zufallsstrom an dieser Stelle
    gerade sagt — an manchen Tagen bliebe sie grün. Hier wird die Grenze
    stattdessen VORGEGEBEN und jeder erzeugte Tag dagegen gehalten; die
    Schleife zählte hoch, BEVOR sie prüfte, und das ist unabhängig davon
    immer derselbe Fehler.
    """
    from app.demo import _habits, _residences, _timeline_import
    b = _Builder(db, user)
    b.today = date(2016, 7, 1)
    b.last_day = date(2016, 6, 30)
    spans = _residences(b)
    _timeline_import(b, spans)
    _habits(b, spans)
    assert b.events, "ohne Ereignisse prüft diese Zusicherung nichts"
    assert max(e["date_start"].date() for e in b.events) <= b.last_day
    assert max(t["date_end"].date() for t in b.tracks) <= b.last_day


def test_corpus_has_all_four_kinds_of_statement(corpus):
    """Fragment, Vorschlag, Lebensdatenbank — und der Wohnort daneben.

    Ein Bestand, in dem alles bestätigt ist, zeigt die halbe App nicht: die
    Warteschlange wäre leer und der Weg dorthin unsichtbar.
    """
    db, user = corpus
    assert db.query(Fragment).filter(Fragment.status == FragmentStatus.pending).count() > 0
    assert db.query(Event).filter(Event.confirmed == ConfirmState.unconfirmed).count() > 0
    assert db.query(Event).filter(Event.confirmed == ConfirmState.confirmed).count() > 2000
    assert db.query(BaselineLocation).count() == len(life.RESIDENCES)


def test_nothing_is_dated_in_the_future(corpus):
    """Die App behandelt Zukunft überall als Sonderfall (kein Wetter, keine
    Wertung) — ein Schaufenster darf den Sonderfall nicht als Normalfall zeigen.

    **Geprüft wird die REGEL, nicht der Zufall.** „Nichts liegt hinter *jetzt*"
    allein wäre eine Zusicherung gegen die Wanduhr: ein Besuch, der um 7 Uhr
    des heutigen Tages angelegt wird, ist um 9 Uhr Vergangenheit und um 6 Uhr
    Zukunft — dieselbe kaputte Schleife wäre je nach Startzeit grün oder rot.
    Die Regel des Erbauers ist „der Alltag endet gestern", und die gilt
    unabhängig davon, wann jemand die Tests laufen lässt.
    """
    db, _ = corpus
    latest = db.query(Event.date_start).order_by(Event.date_start.desc()).first()[0]
    assert latest.date() < date.today(), f"jüngster Eintrag: {latest}"
    assert db.query(Event).filter(Event.date_start > datetime.now()).count() == 0
    assert db.query(Track).filter(Track.date_end > datetime.now()).count() == 0


def test_every_place_can_be_drawn_and_resolved(corpus):
    """Ohne Koordinate keine Karte, ohne bekanntes Land ein grauer Fleck.

    Der Welt-Reiter meldet nicht auflösbare Ländernamen ausdrücklich als
    „nicht zugeordnet" — im eigenen Demo-Bestand wäre das eine Fehlermeldung
    über uns selbst.
    """
    db, _ = corpus
    for loc in db.query(Location).all():
        assert loc.lat is not None and loc.lng is not None, loc.name
        assert loc.city, loc.name
        assert ref.resolve(loc.country) is not None, f"{loc.name}: {loc.country!r}"


def test_the_weather_run_has_nothing_left_to_fetch(corpus):
    """**Die Endlos-Abruf-Falle, diesmal vom Erbauer eingebaut.**

    Ohne den Revisionsmarker hielte der Wetter-Lauf den ganzen Demo-Bestand
    für unbearbeitet und startete beim ersten Klick zehntausend Abrufe gegen
    Open-Meteo — aus einem Schaufenster heraus, das ohne Netz laufen soll.
    Übrig bleiben dürfen nur die frischen Vorschläge: sie sind noch nicht in
    der Lebensdatenbank, und dass der Knopf für sie etwas zu tun hat, ist
    richtig so.
    """
    db, user = corpus
    left = _weather_candidates(db, user.id)
    assert all(e.confirmed == ConfirmState.unconfirmed for e in left), \
        [e.title for e in left if e.confirmed == ConfirmState.confirmed][:5]
    marks = (db.query(Metric).filter(Metric.key == "weather_rev").first(),
             db.query(DayMetric).filter(DayMetric.key == "weather_rev").first())
    assert all(m is not None and m.value == WEATHER_REVISION for m in marks)


def test_event_days_and_residence_days_stay_disjoint(corpus):
    """**Die Kernregel über die beiden Tagesmengen** — der Wohnort füllt nur
    Lücken. Überschnitten sie sich, zählte jeder solche Tag in jeder Zahl über
    TAGE doppelt, und zwar lautlos."""
    db, user = corpus
    event_days = {row[0].date() for row in
                  db.query(Event.date_start).filter(Event.date_start.isnot(None)).all()}
    day_metric_days = {row[0] for row in db.query(DayMetric.day).distinct().all()}
    assert not (event_days & day_metric_days)
    assert len(day_metric_days) > 3000, "ohne Wohnort-Tage fehlt F20 in der Demo"


def test_there_is_exactly_one_blank_stretch(corpus):
    """Ein Bestand ohne Lücke lässt den Lückenbericht leer, und eine Ansicht,
    die nichts zu sagen hat, sieht aus wie eine kaputte."""
    from app.services.gaps import report
    db, user = corpus
    r = report(db, user.id)
    assert r["stretch_count"] == 1, r["stretches"]
    only = r["stretches"][0]
    assert only["from"] == life.BLANK[0].isoformat()
    assert only["to"] == life.BLANK[1].isoformat()


def test_nothing_at_all_happens_in_the_blank(corpus):
    """Die weiße Stelle steht an EINER Stelle und wird von dreien gelesen —
    ein Ereignis in ihr wäre der Beweis, dass eine der drei sie nicht kennt."""
    db, _ = corpus
    lo = datetime.combine(life.BLANK[0], datetime.min.time())
    hi = datetime.combine(life.BLANK[1], datetime.max.time())
    assert db.query(Event).filter(Event.date_start.between(lo, hi)).count() == 0
    assert db.query(DayMetric).filter(
        DayMetric.day.between(life.BLANK[0], life.BLANK[1])).count() == 0


def test_the_collection_is_not_instantly_platinum(corpus):
    """Aus dem Grund, den `ROADMAP` beim Vorziehen von F19 aufgeschrieben hat:
    ein Leben, das in allem sofort Platin ist, stellt zwei Features gerade
    dem Publikum falsch dar, für das die Demo existiert."""
    from app.services.achievements import compute
    db, user = corpus
    result = compute(db, user.id)
    tiers = [a.tier for a in result.achievements]
    assert len(set(tiers)) >= 3, f"nur {set(tiers)} — das ist keine Sammlung"
    assert sum(1 for t in tiers if t == "platin") < len(tiers) / 2


def test_the_compendium_has_every_kind(corpus):
    """Sieben Reiter, sieben gefüllte Sorten — ein leerer Reiter in der Demo
    liest sich als „kann das nicht"."""
    db, _ = corpus
    have = {row[0] for row in db.query(Entity.type).distinct().all()}
    assert {"animal", "country", "artist", "food", "movie", "game", "book"} <= have


def test_imported_entries_are_recognisable_as_such(corpus):
    """Der Zeitstrahl kann Gerätedaten als Gruppe ausblenden — ohne sie zeigte
    die Demo weder den Schalter noch den Wege-Reiter."""
    db, _ = corpus
    imported = db.query(Event).filter(Event.source == Source.google_timeline)
    assert imported.count() > 500
    assert all(e.confirmed_by == "import" for e in imported.limit(50).all())
    assert db.query(Track).count() > 500


def test_seeding_twice_changes_nothing(corpus):
    """Der Startvorgang läuft bei jedem Containerstart — ein zweiter Bestand
    obendrauf wäre ein doppeltes Leben."""
    db, user = corpus
    before = db.query(Event).count()
    seed_demo(db, user)
    assert db.query(Event).count() == before


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").strip(),
                    reason="Fremdschlüssel erzwingt nur PostgreSQL — auf SQLite "
                           "wäre diese Prüfung in jedem Fall grün")
def test_seed_survives_foreign_keys(db, user):
    """**Auf SQLite beweist das nichts, deshalb läuft es dort auch nicht.**

    Der Erbauer schreibt mit Core-Inserts, also ohne die ORM-Beziehungen, die
    sonst für die Reihenfolge sorgen. Ein Verweis auf einen Ort, der noch nicht
    geschrieben ist, fällt genau einmal auf: auf der Datenbank, die
    Fremdschlüssel erzwingt.
    """
    seed_demo(db, user)
    assert db.query(Event).count() > 2000
