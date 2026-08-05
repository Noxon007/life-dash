"""Die Wege-Ebene lässt nichts still weg (Anmerkung 141).

Gemeldet aus dem Betrieb: „Vektorkarte an, dann Wochenansicht — alles stürzt
ab, kein Fehler im Log." Kein Absturz, sondern Arbeit: `/api/tracks` lieferte
bis zu 1000 Wege mit **voller Punktliste**, der Browser zeichnete jeden als
SVG-Pfad, und über einer lebenden WebGL-Leinwand (Vektorkarte) wird daraus ein
eingefrorener Reiter.

Der Defekt dahinter ist aber der ältere und der teurere: `ORDER BY date_start
DESC LIMIT 1000` **schnitt ab und schwieg**. In einem Monat mit 3.000 Wegen
fehlten die ersten drei Wochen, und die Karte sah vollständig aus — Anmerkung
110 (`all.slice(0, 300)`) in einer anderen Datei, mit demselben Satz.

Geprüft wird deshalb beides getrennt: dass gedeckelt wird (Zeichenlast) und
dass die Deckelung GESAGT wird und nicht vorne abschneidet (Auslassung). Ein
Test allein auf `len(rows) <= limit` wäre auch beim alten, kaputten Stand grün
gewesen — genau die Sorte Zusicherung, die Anmerkung 108 meint.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import Track, User, UserRole
from app.routers.tracks import list_tracks

START = datetime(2024, 3, 1)


@pytest.fixture()
def many_tracks(db, user):
    """900 Wege über 30 Tage — gleichmäßig, ein Weg alle 48 Minuten."""
    for i in range(900):
        begin = START + timedelta(minutes=48 * i)
        db.add(Track(user_id=user.id, date_start=begin,
                     date_end=begin + timedelta(minutes=20),
                     points=[[51.0 + i / 1000, 8.0], [51.1 + i / 1000, 8.1]],
                     activity_type="walk", distance_m=1200.0))
    db.commit()
    return 900


def test_antwort_nennt_die_wahre_zahl(db, user, many_tracks):
    """`total` ist der Bestand, `shown` das Gelieferte — beide stehen da."""
    res = list_tracks(limit=400, db=db, user=user)
    assert res["total"] == 900
    assert res["shown"] == 400
    assert len(res["tracks"]) == 400


def test_gedeckelt_wird_ueberhaupt(db, user, many_tracks):
    """Der Standard deckelt — 900 volle Punktlisten sind die gemeldete Last."""
    res = list_tracks(db=db, user=user)
    assert res["shown"] < res["total"], (
        "ohne Deckel gehen tausende Punktlisten in EINE Antwort — genau das "
        "war die eingefrorene Wochenansicht")


def test_deckeln_ist_nicht_abschneiden(db, user, many_tracks):
    """Gegriffen wird über den GANZEN Zeitraum, nicht vorne oder hinten.

    Das ist die Prüfung, die den alten Stand umbringt: der nahm die neuesten
    400 und ließ den Anfang des Zeitraums verschwinden. Gemessen wird deshalb
    nicht die Zahl, sondern die SPANNE — sie muss die des Bestands sein.
    """
    res = list_tracks(limit=400, db=db, user=user)
    stamps = [t["date_start"] for t in res["tracks"]]
    assert stamps == sorted(stamps), "chronologisch, sonst springt die Karte"
    erste, letzte = datetime.fromisoformat(stamps[0]), datetime.fromisoformat(stamps[-1])
    assert erste - START < timedelta(hours=2), (
        f"der Anfang des Zeitraums fehlt: erster Weg {erste}")
    ende = START + timedelta(minutes=48 * 899)
    assert ende - letzte < timedelta(hours=2), (
        f"das Ende des Zeitraums fehlt: letzter Weg {letzte}")

    # Und dazwischen soll nichts klumpen: die 400 liegen gleichmäßig, also ist
    # jeder Zehn-Prozent-Abschnitt des Zeitraums mit etwa 40 Wegen besetzt.
    spanne = (ende - START).total_seconds()
    eimer = [0] * 10
    for s in stamps:
        anteil = (datetime.fromisoformat(s) - START).total_seconds() / spanne
        eimer[min(9, int(anteil * 10))] += 1
    assert min(eimer) >= 25, f"ungleich verteilt: {eimer}"


def test_kleiner_bestand_bleibt_vollstaendig(db, user):
    """Unter dem Deckel wird nichts gegriffen und nichts gesagt."""
    for i in range(5):
        begin = START + timedelta(hours=i)
        db.add(Track(user_id=user.id, date_start=begin,
                     date_end=begin + timedelta(minutes=10),
                     points=[[51.0, 8.0], [51.1, 8.1]], activity_type="drive"))
    db.commit()
    res = list_tracks(db=db, user=user)
    assert res["total"] == res["shown"] == 5


def test_zeitraum_grenzt_ein(db, user, many_tracks):
    """Der Zeitraum filtert VOR der Deckelung — sonst deckelt man das Falsche."""
    res = list_tracks(start=START, end=START + timedelta(days=1),
                      limit=400, db=db, user=user)
    # 24 h / 48 min = 30 Wege — plus den, der GENAU auf der Grenze beginnt.
    # Gefiltert wird auf Überlappung, nicht auf Enthaltensein: ein Weg, der um
    # Mitternacht losgeht, gehört auf beide Tage, und ein Zeitraum, der ihn
    # nirgends zeigt, hat ihn verloren.
    assert res["total"] == 31, res["total"]
    assert res["shown"] == 31


def test_fremde_wege_bleiben_draussen(db, user):
    """Der Besitzfilter sitzt vor allem anderen (A12)."""
    other = User(oidc_subject="other", email="o@example.org",
                 display_name="Andere", role=UserRole.user)
    db.add(other)
    db.commit()
    for owner in (user.id, other.id):
        db.add(Track(user_id=owner, date_start=START,
                     date_end=START + timedelta(minutes=5),
                     points=[[51.0, 8.0], [51.1, 8.1]]))
    db.commit()
    res = list_tracks(db=db, user=user)
    assert res["total"] == 1


# --------------------------------------------------------------------------- #
# Anmerkung 189 — die Kilometer, zum ersten Mal zusammengezählt
# --------------------------------------------------------------------------- #
def test_track_stats_sum_by_mode_and_year(db, user):
    """`distance_m` und `activity_type` lagen seit dem Timeline-Import in der
    Datenbank und wurden nirgends ausgewertet.

    Zwei Zusagen, die man dem Ergebnis nicht ansieht:

    * **Ein Weg OHNE Strecke zählt als Weg mit.** `distance_m` kann `NULL`
      sein. Ihn aus der ANZAHL zu nehmen wäre eine zweite Auswahl für dieselbe
      Frage — „wie viele Wege" darf nicht davon abhängen, ob eine Strecke
      dabeisteht.
    * **`None` bleibt `None`.** „Google wusste die Art nicht" (`unknown`) und
      „im Export stand gar nichts" (`NULL`) sind zwei Fälle; sie hier
      zusammenzuwerfen nähme der Oberfläche die Möglichkeit, es zu sagen.
    """
    from app.services.stats_tracks import compute_tracks

    db.add_all([
        Track(user_id=user.id, date_start=datetime(2024, 3, 1, 8),
              date_end=datetime(2024, 3, 1, 9), points=[],
              activity_type="drive", distance_m=42000.0),
        Track(user_id=user.id, date_start=datetime(2024, 3, 2, 8),
              date_end=datetime(2024, 3, 2, 9), points=[],
              activity_type="drive", distance_m=8000.0),
        Track(user_id=user.id, date_start=datetime(2025, 5, 5, 8),
              date_end=datetime(2025, 5, 5, 9), points=[],
              activity_type="walk", distance_m=3500.0),
        # ohne Strecke UND ohne Art
        Track(user_id=user.id, date_start=datetime(2025, 5, 6, 8),
              date_end=datetime(2025, 5, 6, 9), points=[],
              activity_type=None, distance_m=None),
    ])
    db.commit()

    r = compute_tracks(db, user.id)
    assert r["count"] == 4, "der Weg ohne Strecke ist trotzdem ein Weg"
    assert r["total_km"] == 53.5
    modes = {m["mode"]: m for m in r["modes"]}
    assert modes["drive"]["km"] == 50.0 and modes["drive"]["count"] == 2
    assert None in modes and modes[None]["km"] == 0.0
    years = {y["year"]: y for y in r["years"]}
    assert years[2024]["km"] == 50.0 and years[2025]["count"] == 2
    assert r["longest"][0]["km"] == 42.0
    assert r["first"] == "2024-03-01" and r["last"] == "2025-05-06"


def test_track_stats_stay_empty_without_tracks(db, user):
    """Eine Null ist hier keine Auskunft, sondern der Anlass, gar nichts zu
    zeigen — die Oberfläche sagt dann, wo der Import steht."""
    from app.services.stats_tracks import compute_tracks

    r = compute_tracks(db, user.id)
    assert r["count"] == 0 and r["modes"] == [] and r["first"] is None
