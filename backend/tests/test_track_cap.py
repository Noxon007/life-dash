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
