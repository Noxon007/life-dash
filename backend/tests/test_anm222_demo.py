"""Anmerkung 222 — Teil 3 der Durchsicht: der Demo-Bestand als Schaufenster.

**Die teuren Fehler eines Schaufensters sind nicht Abstürze, sondern leere
Kacheln und Knöpfe, die nichts finden.** Ein Fremder, der die Demo öffnet und
„Längste Reise: —" sieht, hält die Funktion für kaputt und nicht den Bestand
für unvollständig; er kann den Unterschied gar nicht kennen.

Geprüft wird deshalb, dass jede Ansicht, die es GIBT, im ausgelieferten
Bestand auch etwas zu sagen hat — und dass die Zahlen, die sie zeigt, zwei
Tage unterscheiden können.

Der Bestand wird über die `corpus`-Fixture von `test_r1a_demo.py` gebaut
(modulweit, ~11 s); die Zusicherungen hier hängen an denselben Zeilen.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func

from app.demo import life
from app.models import Event, Location, Source
from app.services import geocode, stats_overview as ov, stats_toplists as tl

# Der Bestand kommt aus dem Nachbarmodul — eine zweite Fixture wäre ein
# zweiter Aufbau und damit elf Sekunden für dieselben Zeilen.
from tests.test_r1a_demo import corpus, demo_media  # noqa: F401


@pytest.fixture()
def db(corpus):
    """Nur die Session — `corpus` liefert `(db, user)`."""
    return corpus[0]


@pytest.fixture()
def uid(corpus):
    return corpus[1].id


# --------------------------------------------------------------------------- #
#  (a) Mehrtägiges — es gab keins
# --------------------------------------------------------------------------- #
def test_the_stock_has_multi_day_events(db):
    """Ohne eine einzige Spanne bleibt „Längste Reise" für immer leer.

    Vorher: `date_end` war auf ALLEN 8.468 Ereignissen NULL.
    """
    spans = (db.query(func.count(Event.id))
             .filter(Event.date_end.isnot(None),
                     func.date(Event.date_end) > func.date(Event.date_start))
             .scalar())
    assert spans >= 20, f"nur {spans} mehrtägige Ereignisse im Demo-Bestand"


def test_trips_are_parents_of_their_days(db):
    """F7 ist im Bestand vorgeführt: Reisen haben Tages-Kinder.

    Vorher gab es kein einziges Eltern/Kind-Paar — also weder ein Beispiel für
    F7, noch etwas für die Mittelung der wärmsten Reise über
    `parent_event_id`, noch eine Zeile für die Abfrage, die in
    `weather_values` genau dafür steht (Anmerkung 220).
    """
    parents = (db.query(func.count(func.distinct(Event.parent_event_id)))
               .filter(Event.parent_event_id.isnot(None)).scalar())
    assert parents >= 20, f"nur {parents} Ereignisse mit Tages-Kindern"


def test_the_longest_trip_tile_says_something(db, uid):
    """Die Kachel stand dauerhaft auf `null`."""
    trip = tl.compute_toplists(db, uid)["streaks"]["longest_trip"]
    assert trip is not None, "die Kachel „Längste Reise“ ist leer"
    assert trip["days"] >= 2 and trip["title"]


def test_the_warmest_trip_is_named_after_the_trip(db, uid):
    """Nicht nach einem einzelnen Tag — der Fall aus Anmerkung 199.

    Er war im Demo-Bestand nicht herstellbar, weil es keine Elternzeile gab:
    jede Reise war ihr eigener Schlüssel und hieß deshalb immer „richtig",
    ohne dass die Regel je gegriffen hätte. Jetzt trägt die Kachel den
    Reisetitel („Andalusien") und nicht die Tagesüberschrift.
    """
    warmest = ov.compute_overview(db, uid)["weather"]["warmest_trip"]
    assert warmest is not None
    titles = {t for (t,) in db.query(Event.title)
              .filter(Event.category == "trip",
                      Event.parent_event_id.is_(None),
                      Event.date_end.isnot(None)).all()}
    assert warmest["title"] in titles, (
        f"„{warmest['title']}“ ist kein Reisetitel, sondern vermutlich "
        "eine Tagesüberschrift — genau der Rückfall aus Anmerkung 199.")


def test_splitting_multi_day_visits_has_work(db, uid):
    """Der Knopf „Mehrtägiges aufteilen" findet etwas.

    Er greift ausschließlich `google_timeline`-Ereignisse mit Spanne und ohne
    Tages-Kinder. Der Bestand hatte kein einziges — ein Knopf, der in der Demo
    nichts findet, sieht aus wie einer, der nicht geht.
    """
    from app.routers.events import _scan_multiday_visits

    ready, _long, _kids = _scan_multiday_visits(db, uid)
    assert len(ready) >= 3, f"nur {len(ready)} schneidbare Besuche"


def test_those_stays_stay_unsplit(db, uid):
    """**Die Gegenprobe.** Wären sie schon geteilt, hätte der Lauf wieder nichts.

    Ohne diesen Test hätte ich sie beim nächsten Aufräumen mit Kindern
    versehen und die Zusicherung darüber wäre grün geblieben — sie zählt ja
    nur, was der Lauf findet, und der Lauf sucht die ungeteilten.
    """
    stays = (db.query(Event)
             .filter(Event.source == Source.google_timeline,
                     Event.date_end.isnot(None)).all())
    assert stays and all(not e.children for e in stays)


# --------------------------------------------------------------------------- #
#  (b) Orte, die einen Namen haben
# --------------------------------------------------------------------------- #
def test_places_are_mostly_named(db, uid):
    """99 % Koordinaten-Platzhalter war kein Ortsbestand, sondern Rauschen.

    Vorher: 3.633 von 3.675 Orten hießen „Ort (53.555, 9.966)" — ein
    Zufallspunkt je Besuch. Ein Standortverlauf besteht aber aus
    Wiederholungen, und jede Ansicht, die einen Ortsnamen zeigt, zeigte eine
    Koordinate.
    """
    names = [n for (n,) in db.query(Location.name).all()]
    placeholders = [n for n in names if geocode.is_coordinate_name(n)]
    assert len(names) < 300, f"{len(names)} Orte — das sind wieder Zufallspunkte"
    assert len(placeholders) / len(names) < 0.35, (
        f"{len(placeholders)} von {len(names)} Orten sind Koordinaten-Platzhalter")


def test_resolving_place_names_has_work(db, uid):
    """Und ein Rest bleibt offen, damit „Ortsnamen auflösen" etwas zu tun hat.

    **Beide Richtungen zählen.** Vorher waren 3.633 Orte unaufgelöst und der
    Lauf meldete NULL offene — weil der Erbauer jedem Ort `name_manual=True`
    mitgab und `_resolve_candidates` von Hand benannte Orte auslässt. Die
    Marke heißt „ein Mensch hat diesen Namen getippt"; für einen Platzhalter
    war sie schlicht unwahr.
    """
    from app.routers.tracks import _resolve_candidates

    open_ones = _resolve_candidates(db, uid, list(geocode.PLACE_NAME_PARTS))
    assert open_ones, "„Ortsnamen auflösen“ findet nichts zu tun"
    assert len(open_ones) < 100, (
        f"{len(open_ones)} offene Orte — die Liste soll eine Liste sein, "
        "keine Wand")


def test_invented_places_are_not_sent_to_a_geocoder(db, uid):
    """Die Gegenprobe: ein BENANNTER Erfindungsort bleibt unangetastet.

    Sonst führe der Auflöse-Lauf für „Café am Knooper Weg" echtes Geocoding —
    genau das, wogegen `name_manual=True` im Erbauer steht. Die Marke ist jetzt
    an die Wahrheit über den Namen gebunden, nicht pauschal gesetzt.
    """
    named = (db.query(Location)
             .filter(Location.name == "Kirschenallee 12, Bad Segeberg").first())
    assert named is not None and named.name_manual is True
    assert named.address == {}


# --------------------------------------------------------------------------- #
#  (c) Wetter, das zwei Tage unterscheiden kann
# --------------------------------------------------------------------------- #
def test_the_wind_record_is_not_a_ceiling(db, uid):
    """Ein Extremwert über eine gedeckelte Größe beschreibt den Deckel.

    `wind_max_kmh` war `6 + 22 * gleichverteilt`, also hart bei 36,0 gedeckelt
    — der „windigste Tag" aus zweiunddreißig Jahren zeigte den Deckel, und die
    Rangliste darunter zeigte ihn zehnmal. Dieselbe Klasse, für die Anmerkung
    216 vier Kacheln gestrichen hat, nur im erfundenen Wetter statt in der
    Auswertung.

    **Die Probe ist die Rangliste, nicht die Kachel.**
    """
    tops = tl.compute_toplists(db, uid)["weather"]["windy"]
    assert len(tops) >= 5
    values = [r["value"] for r in tops[:5]]
    assert len(set(values)) == len(values), (
        f"die ersten fünf Windwerte sind nicht unterscheidbar: {values}")
    assert values[0] > 45, (
        f"stärkster Wind in 32 Jahren: {values[0]} km/h — das ist eine frische "
        "Brise, kein Rekord")


@pytest.mark.parametrize("key", ["wind_max_kmh", "gust_max_kmh"])
def test_wind_stays_physical(db, uid, key):
    """Nach oben offen heißt nicht beliebig — Böen bleiben im Rahmen."""
    from app.models import Metric

    top = (db.query(func.max(Metric.value))
           .filter(Metric.key == key, Metric.source == Source.weather).scalar())
    assert 40 < top < 200, f"{key} Höchstwert {top}"


# --------------------------------------------------------------------------- #
#  (d) Was sich NICHT ändern durfte
# --------------------------------------------------------------------------- #
def test_the_blank_is_still_blank(db, uid):
    """`life.BLANK` trägt den Lückenbericht — 75 Tage ohne alles.

    Die Umbauten oben fassen den Timeline-Import und die Reisen an; beide
    schweigen in der weißen Stelle. Eine Zeile darin würde den Lückenbericht
    leeren, und zwar lautlos.
    """
    rows = (db.query(func.count(Event.id))
            .filter(func.date(Event.date_start) >= life.BLANK[0].isoformat(),
                    func.date(Event.date_start) <= life.BLANK[1].isoformat())
            .scalar())
    assert rows == 0, f"{rows} Ereignisse in der weißen Stelle"


def test_nothing_is_dated_later_than_yesterday(db, uid):
    """Der Alltag endet gestern — auch die neuen Mehrtäger.

    Ein Elternteil mit `date_end` in der Zukunft wäre der leichteste Weg,
    diese Regel zu verletzen: die Spanne wird gerechnet, nicht getippt.
    """
    import datetime as dt

    latest = db.query(func.max(Event.date_end)).scalar()
    if latest is not None:
        if isinstance(latest, str):
            latest = dt.datetime.fromisoformat(latest)
        assert latest.date() < dt.date.today()
