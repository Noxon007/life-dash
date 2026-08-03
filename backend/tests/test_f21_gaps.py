"""F21 — die Lückenprüfung (Anmerkung 145).

Festgenagelt wird nicht „es gibt einen Endpunkt", sondern die vier Stellen, an
denen dieser Bericht still eine andere Frage beantwortet als die gestellte:

* **Ein Grundort-Tag ist keine Lücke.** Das ist der ganze Grund, aus dem F21
  hinter F20 steht: vorher hätte der Bericht jeden Kindheitstag gemeldet, und
  eine Liste mit sechstausend Zeilen ist kein Bericht. Gefragt ist „wo weiß ich
  gar nichts", nicht „wo habe ich nichts getippt".
* **Die Ränder hängen am Geburts-Meilenstein.** Mit ihm wird über ein LEBEN
  berichtet, ohne ihn nur über den Zeitraum, in dem aufgezeichnet wurde. Beides
  ist richtig; falsch wäre, das eine zu zeigen und das andere zu behaupten —
  deshalb reist `since_birth` bis in die Anzeige mit.
* **Die Kachel ist Platz 1 der Liste.** „Längste Lücke" in den Ranglisten und
  die Lücken-Ansicht lesen dieselbe Funktion (dasselbe Muster wie Anmerkung 156
  bei den Wetter-Rekorden). Wären es zwei, liefen sie beim ersten Sonderfall
  auseinander — und die Sonderfälle sind hier die Ränder.
* **Die Summen müssen aufgehen.** `bekannt + unbekannt` ist die Länge des
  Zeitraums. Geht das nicht auf, zählt irgendwo ein Tag doppelt oder gar nicht,
  und beides sieht man einer Prozentzahl nicht an.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (BaselineLocation, ConfirmState, DatePrecision, Event,
                        Location, Source)
from app.services import gaps
from app.services.stats_toplists import compute_toplists

TODAY = date(2026, 8, 3)


def _loc(db, user, name="Bad Segeberg"):
    loc = Location(user_id=user.id, name=name, lat=53.9, lng=10.3)
    db.add(loc)
    db.flush()
    return loc


def _event(db, user, when, *, title="Eintrag", category="event", loc=None):
    ev = Event(user_id=user.id, title=title, category=category,
               date_start=when, date_precision=DatePrecision.day,
               confirmed=ConfirmState.confirmed, source=Source.manual,
               location=loc)
    db.add(ev)
    db.flush()
    return ev


def _birth(db, user, when):
    """Der Geburts-Meilenstein — F17 findet ihn über Titel/Beschreibung."""
    return _event(db, user, when, title="Geburt", category="milestone")


def _base(db, user, start, end=None):
    row = BaselineLocation(user_id=user.id, location_id=_loc(db, user).id,
                           date_start=start, date_end=end)
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def client(db, user):
    """Ohne `with`: im Kontextmanager fährt der Lifespan und fasst die
    KONFIGURIERTE Datenbank an (siehe `test_f20_baseline.py`)."""
    app.dependency_overrides[get_db] = lambda: db
    from app.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Was eine Lücke IST
# --------------------------------------------------------------------------- #
def test_a_gap_is_a_stretch_with_nothing_at_all(db, user):
    for d in (1, 2, 10, 11):
        _event(db, user, datetime(2024, 1, d, 9))
    db.commit()

    rows = gaps.stretches(db, user.id, today=TODAY)
    assert rows == [{"from": "2024-01-03", "to": "2024-01-09", "days": 7}]


def test_a_baseline_day_is_not_a_gap(db, user):
    """Der Grund, aus dem F21 hinter F20 steht (Anmerkung 145).

    Ohne diese Regel meldete der Bericht jeden Kindheitstag — und eine Liste
    mit sechstausend Zeilen beantwortet keine Frage.
    """
    _event(db, user, datetime(2024, 1, 1, 9))
    _event(db, user, datetime(2024, 1, 31, 9))
    _base(db, user, date(2024, 1, 5), date(2024, 1, 20))
    db.commit()

    rows = gaps.stretches(db, user.id, today=TODAY)
    assert rows == [{"from": "2024-01-02", "to": "2024-01-04", "days": 3},
                    {"from": "2024-01-21", "to": "2024-01-30", "days": 10}]


def test_a_fully_covered_period_has_no_gap_at_all(db, user):
    _event(db, user, datetime(2024, 1, 1, 9))
    _event(db, user, datetime(2024, 3, 1, 9))
    _base(db, user, date(2024, 1, 2), date(2024, 2, 29))
    db.commit()
    assert gaps.stretches(db, user.id, today=TODAY) == []


def test_an_unconfirmed_entry_still_counts_as_knowledge(db, user):
    """Ein Vorschlag für den 14. März ist ein Hinweis, dass an dem Tag etwas
    war — ihn zu übergehen hieße, eine Lücke über einen Tag zu melden, über den
    die Datenbank bereits etwas weiß."""
    _event(db, user, datetime(2024, 5, 1, 9))
    ev = _event(db, user, datetime(2024, 5, 3, 9))
    ev.confirmed = ConfirmState.unconfirmed
    _event(db, user, datetime(2024, 5, 5, 9))
    db.commit()

    rows = gaps.stretches(db, user.id, today=TODAY)
    assert [r["from"] for r in rows] == ["2024-05-02", "2024-05-04"]


# --------------------------------------------------------------------------- #
# Die Ränder
# --------------------------------------------------------------------------- #
def test_without_a_birth_milestone_the_report_covers_only_what_was_recorded(db, user):
    """Anmerkung 156s Regel bleibt: die Zeit vor dem ersten Eintrag ist keine
    Lücke, sondern die Zeit vor dem ersten Eintrag — sie als Befund über ein
    Leben auszugeben wäre eine Aussage über den Beginn der Aufzeichnung."""
    _event(db, user, datetime(2020, 1, 1, 9))
    _event(db, user, datetime(2020, 3, 1, 9))
    db.commit()

    r = gaps.report(db, user.id, today=TODAY)
    assert r["since_birth"] is False
    assert (r["from"], r["to"]) == ("2020-01-01", "2020-03-01")
    assert r["stretches"] == [{"from": "2020-01-02", "to": "2020-02-29",
                               "days": 59}]


def test_with_a_birth_milestone_the_report_covers_the_whole_life(db, user):
    """Mit dem Meilenstein ist bekannt, DASS da ein Leben war, über das nichts
    vorliegt — und genau danach wurde gefragt."""
    _birth(db, user, datetime(2020, 1, 1))
    _event(db, user, datetime(2020, 3, 1, 9))
    db.commit()

    r = gaps.report(db, user.id, today=TODAY)
    assert r["since_birth"] is True
    assert (r["from"], r["to"]) == ("2020-01-01", TODAY.isoformat())
    # Die Lücke zwischen Geburt und erstem Eintrag ist jetzt eine, und die
    # Zeit seit dem letzten Eintrag ebenfalls.
    assert r["stretches"][0]["from"] == "2020-03-02"
    assert r["stretches"][0]["to"] == TODAY.isoformat()
    assert {"from": "2020-01-02", "to": "2020-02-29", "days": 59} in r["stretches"]


def test_a_birth_milestone_in_the_future_is_not_a_window(db, user):
    """Ein Tippfehler im Geburtsdatum darf keinen Bericht über eine negative
    Spanne erzeugen — dann gilt wieder die Regel ohne Meilenstein."""
    _birth(db, user, datetime(2099, 1, 1))
    _event(db, user, datetime(2020, 3, 1, 9))
    db.commit()

    r = gaps.report(db, user.id, today=TODAY)
    assert r["since_birth"] is False
    assert (r["from"], r["to"]) == ("2020-03-01", "2020-03-01")


# --------------------------------------------------------------------------- #
# Die Zahlen
# --------------------------------------------------------------------------- #
def test_known_plus_unknown_is_the_length_of_the_window(db, user):
    """Geht das nicht auf, zählt irgendwo ein Tag doppelt oder gar nicht — und
    beides sieht man einer Prozentzahl nicht an."""
    _birth(db, user, datetime(2024, 1, 1))
    _event(db, user, datetime(2024, 6, 15, 9))
    _base(db, user, date(2024, 2, 1), date(2024, 2, 29))
    db.commit()

    r = gaps.report(db, user.id, today=TODAY)
    assert r["known_days"] + r["unknown_days"] == r["total_days"]
    assert r["total_days"] == (TODAY - date(2024, 1, 1)).days + 1
    # 29 Grundort-Tage + 2 Einträge (Geburt und der Eintrag im Juni)
    assert r["recorded_days"] == 2 and r["baseline_days"] == 29
    assert r["known_days"] == 31


def test_an_entry_outside_the_window_does_not_inflate_the_coverage(db, user):
    """Ein Eintrag VOR der Geburt (ein Tippfehler, ein Meilenstein der Eltern)
    ist keine Abdeckung — sonst ergäbe „bekannt + unbekannt" nicht mehr die
    Länge des Zeitraums."""
    _birth(db, user, datetime(2024, 1, 1))
    _event(db, user, datetime(1990, 5, 5, 9))
    db.commit()

    r = gaps.report(db, user.id, today=TODAY)
    assert r["from"] == "2024-01-01"
    assert r["known_days"] == 1          # nur die Geburt selbst
    assert r["known_days"] + r["unknown_days"] == r["total_days"]


def test_the_year_coverage_counts_only_the_days_inside_the_window(db, user):
    """Das erste und das letzte Jahr dürfen nicht als unvollständig dastehen,
    nur weil der Zeitraum mitten in ihnen beginnt."""
    _birth(db, user, datetime(2025, 12, 30))
    db.commit()

    r = gaps.report(db, user.id, today=date(2026, 1, 2))
    assert r["per_year"] == [[2025, 1, 2], [2026, 0, 2]]


def test_the_stretch_list_is_capped_and_says_so(db, user):
    """A40: was die Ansicht nicht alles zeigen kann, muss sie sagen — sonst
    sieht eine Liste von zwanzig Zeilen aus wie die ganze Wahrheit."""
    for i in range(40):
        _event(db, user, datetime(2024, 1, 1) + timedelta(days=i * 3))
    db.commit()

    r = gaps.report(db, user.id, today=TODAY, limit=20)
    assert len(r["stretches"]) == 20
    assert r["stretch_count"] == 39
    assert r["unknown_days"] == 39 * 2


def test_an_empty_corpus_answers_with_nothing_not_with_zero(db, user):
    r = gaps.report(db, user.id, today=TODAY)
    assert r["from"] is None and r["to"] is None
    assert r["total_days"] == 0 and r["stretches"] == []


# --------------------------------------------------------------------------- #
# Eine Regel, zwei Leser
# --------------------------------------------------------------------------- #
def test_the_longest_gap_tile_is_row_one_of_the_list(db, user):
    """Wären es zwei Rechnungen, wäre dies der Test, der sie zusammenhält —
    und sie liefen genau an den Rändern auseinander (Anmerkung 156er Muster)."""
    _birth(db, user, datetime(2020, 1, 1))
    _event(db, user, datetime(2020, 3, 1, 9))
    _event(db, user, datetime(2021, 9, 1, 9))
    db.commit()

    tile = compute_toplists(db, user.id)["streaks"]["longest_gap"]
    rows = gaps.report(db, user.id)["stretches"]
    assert tile is not None and rows
    assert rows[0] == tile


def test_a_mistyped_year_does_not_open_a_thousand_year_window(db, user):
    """Der Zähler in den Ranglisten reicht seine EIGENE Tagesliste herein, und
    die ist nicht gefiltert.

    Ein Eintrag mit vertipptem Jahr — 2999 statt 1999 — machte daraus ohne die
    Grenze in `stretches` ein Fenster über tausend Jahre: ein Kalenderdurchlauf
    über 350 000 Tage für eine Kachel, und als Befund eine Lücke, die es nie
    gab. Eine Zusage, die davon abhängt, dass der Aufrufer sie kennt, ist keine.
    """
    _event(db, user, datetime(2024, 1, 1, 9))
    _event(db, user, datetime(2024, 1, 5, 9))
    _event(db, user, datetime(2999, 1, 1, 9))     # Tippfehler
    db.commit()

    gap = compute_toplists(db, user.id)["streaks"]["longest_gap"]
    assert gap == {"from": "2024-01-02", "to": "2024-01-04", "days": 3}


def test_the_longest_gap_knows_about_baselines(db, user):
    """Der Zähler in den Ranglisten liest dieselbe Funktion — ein Grundort
    verkürzt also auch ihn, statt eine zweite Wahrheit zu behalten."""
    _event(db, user, datetime(2024, 1, 1, 9))
    _event(db, user, datetime(2024, 4, 1, 9))
    before = compute_toplists(db, user.id)["streaks"]["longest_gap"]["days"]
    _base(db, user, date(2024, 1, 2), date(2024, 3, 20))
    db.commit()
    after = compute_toplists(db, user.id)["streaks"]["longest_gap"]["days"]
    assert before == 90 and after == 11


# --------------------------------------------------------------------------- #
# Endpunkt
# --------------------------------------------------------------------------- #
def test_the_endpoint_answers_for_the_own_account_only(client, db, user):
    from app.models import User, UserRole
    other = User(oidc_subject="other-gap", email="g@example.org", role=UserRole.user)
    db.add(other)
    db.flush()
    _event(db, other, datetime(2019, 1, 1, 9))
    _event(db, user, datetime(2024, 1, 1, 9))
    _event(db, user, datetime(2024, 1, 5, 9))
    db.commit()

    r = client.get("/api/stats/gaps").json()
    assert r["from"] == "2024-01-01"
    assert r["stretches"] == [{"from": "2024-01-02", "to": "2024-01-04",
                               "days": 3}]
