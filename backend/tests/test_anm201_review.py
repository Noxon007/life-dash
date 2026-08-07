"""Anmerkung 201 — die dritte Code-Durchsicht, und wieder derselbe Nenner.

Fünf Reparaturen, vier Aufräumungen. Was hier steht, sind die Befunde, die
sich überhaupt festnageln lassen — und das ist weniger als die Hälfte, denn
zwei der Reparaturen sind Einzeiler in Pfaden, die die Suite längst fährt
(der tote Zweig in `_run_weather`, der fehlende `user_id`-Filter in
`on_this_day`: beide ändern kein Ergebnis, sondern eine Zusage).

**Der teuerste Befund hatte gar keinen Test**, und das ist die Lücke, um die
es hier geht: die Login-Sperre ließ nach ihrer Zeit nicht wieder los. Prüfbar
ist das nur, indem man `_fail_state` von Hand in die Vergangenheit setzt —
eine viertelstündige Wartezeit ist kein Test. Genau das tut die erste Gruppe
unten; die bestehenden Auth-Tests fassen den Zustand ohnehin an (`.clear()`),
das Verfahren ist also nicht neu, nur die Frage.
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

from app import auth
from app.models import (ConfirmState, DatePrecision, Event, Location, Source)
from app.routers.events import _visit_group_info
from app.services.photo_points import district_index


@pytest.fixture(autouse=True)
def clean_fail_state():
    auth._fail_state.clear()
    yield
    auth._fail_state.clear()


# --------------------------------------------------------------------------- #
# 1. Die Login-Sperre muss nach ihrer Zeit wieder loslassen
# --------------------------------------------------------------------------- #
MAIL = "sperre@example.org"


def _fail(n: int) -> None:
    for _ in range(n):
        auth.note_login_failure(MAIL)


def _age_window(seconds: float) -> None:
    """Das Fenster künstlich altern lassen — ohne die Uhr zu stellen."""
    count, until = auth._fail_state[MAIL.lower()]
    auth._fail_state[MAIL.lower()] = (count, until - seconds)


def test_five_failures_lock_the_address():
    """Die Sperre selbst ist unverändert — sie ist die Voraussetzung, gegen
    die alles Folgende etwas beweist."""
    _fail(auth._FAIL_MAX - 1)
    assert auth.login_locked_for(MAIL) == 0, "vier Fehlversuche sind noch keine Sperre"
    _fail(1)
    assert auth.login_locked_for(MAIL) > 0


def test_expired_lock_takes_its_counter_with_it():
    """**Der eigentliche Befund.**

    Vorher blieb `count` nach Ablauf bei fünf stehen. Die fünfzehn Minuten
    liefen ab, der nächste Vertipper sperrte sofort wieder fünfzehn Minuten —
    und der danach wieder. Wer einmal fünfmal danebengegriffen hatte, war
    danach dauerhaft EINEN Vertipper von der Sperre entfernt.

    Gegen den kaputten Stand gefahren ist die letzte Zusicherung rot: dort
    stand nach dem einen Fehlversuch wieder eine volle Sperre.
    """
    _fail(auth._FAIL_MAX)
    assert auth.login_locked_for(MAIL) > 0
    _age_window(auth._LOCK_SECONDS + 1)

    assert auth.login_locked_for(MAIL) == 0, "die Sperre muss nach ihrer Zeit fallen"
    _fail(1)
    assert auth.login_locked_for(MAIL) == 0, (
        "Ein einzelner Fehlversuch nach abgelaufener Sperre darf nicht erneut "
        "sperren — der Zähler hat die Sperre überlebt.")


def test_a_quiet_series_expires_too():
    """Vier Fehlversuche vor einem Jahr sind kein Rateversuch von heute.

    Ohne das liefe die Serie ewig weiter: vier Vertipper über Monate verteilt,
    und der fünfte irgendwann sperrt — obwohl nie jemand geraten hat.
    """
    _fail(auth._FAIL_MAX - 1)
    _age_window(auth._LOCK_SECONDS + 1)
    _fail(1)
    assert auth.login_locked_for(MAIL) == 0, (
        "Eine Serie, die ihr Fenster überlebt hat, muss verfallen sein.")


def test_guessing_during_the_lock_extends_it():
    """Die Gegenrichtung: wer während der Sperre weiterrät, verlängert sie.

    Ohne diese Prüfung ließe sich der Verfall so „reparieren", dass die Sperre
    gar nicht mehr greift — ein Wächter, der nur eine Richtung kennt, ist einer
    für die Vergangenheit.
    """
    _fail(auth._FAIL_MAX)
    _age_window(auth._LOCK_SECONDS - 60)     # noch 60 s übrig
    assert 0 < auth.login_locked_for(MAIL) <= 60
    auth.note_login_failure(MAIL)
    assert auth.login_locked_for(MAIL) > 60, "der Versuch muss das Fenster schieben"


def test_success_clears_everything():
    _fail(auth._FAIL_MAX)
    auth.clear_login_failures(MAIL)
    assert auth.login_locked_for(MAIL) == 0
    assert MAIL.lower() not in auth._fail_state


# --------------------------------------------------------------------------- #
# 2. Ein Eintrag um exakt Mitternacht gehört in die Gruppe
# --------------------------------------------------------------------------- #
def test_midnight_entry_counts_towards_its_group(db, user):
    """`lo.replace(hour=0, …)` ließ die Mikrosekunden stehen.

    Trug der Vertreter der Seite welche, lag der abgerundete Tagesanfang
    NACH Mitternacht — und ein Besuch um exakt 00:00:00.000000 fiel aus der
    Zählung. Die Karte sagte dann „2× …" für drei.

    Gegen den kaputten Stand gefahren meldet die Gruppe zwei statt drei.
    """
    loc = Location(user_id=user.id, name="Musterweg 1", city="Detmold",
                   lat=51.9, lng=8.9)
    db.add(loc)
    db.flush()

    def _visit(when: datetime) -> Event:
        e = Event(user_id=user.id, title=f"Besuch: {loc.name}",
                  date_start=when, date_end=when,
                  date_precision=DatePrecision.exact, category="event",
                  confirmed=ConfirmState.confirmed,
                  source=Source.google_timeline, location=loc)
        db.add(e)
        return e

    # Der Vertreter trägt Mikrosekunden, ein Geschwister liegt auf exakt
    # Mitternacht desselben Tages.
    midnight = _visit(datetime(2024, 5, 3, 0, 0, 0, 0))
    rep = _visit(datetime(2024, 5, 3, 9, 30, 15, 123456))
    _visit(datetime(2024, 5, 3, 18, 0, 0, 500000))
    db.flush()

    info = _visit_group_info(db, user.id, [rep], "city")
    assert rep.id in info, "der Vertreter muss eine Gruppe haben"
    assert info[rep.id]["count"] == 3, (
        "Der Eintrag um exakt Mitternacht fehlt in der Gruppenzahl — der "
        f"Tagesanfang wurde nicht bis auf die Mikrosekunde abgerundet "
        f"(bekommen: {info[rep.id]['count']}, {midnight.id} fehlt).")


# --------------------------------------------------------------------------- #
# 3. Ein Ort mit halber Koordinate darf keinen Lauf abreißen
# --------------------------------------------------------------------------- #
def test_district_index_skips_half_coordinates(db, user):
    """`district_index` filterte auf `lat` und nicht auf `lng`.

    `rough_km` rechnet mit beiden — eine Zeile mit gesetzter Breite und leerer
    Länge riss den ganzen Jahreslauf mit einem `TypeError` ab, für einen
    Ortsteil, den niemand vermisst. Gegen den kaputten Stand gefahren fliegt
    dieser Test genau dort auf.
    """
    db.add(Location(user_id=user.id, name="Halb", lat=51.9, lng=None,
                    address={"suburb": "Nirgendwo"}))
    db.add(Location(user_id=user.id, name="Ganz", lat=53.55, lng=9.99,
                    address={"suburb": "Barmbek"}))
    db.flush()

    index = district_index(db, user.id)

    assert [name for _lat, _lng, name in index] == ["Barmbek"]
    assert all(lat is not None and lng is not None for lat, lng, _n in index), (
        "Ein Ort ohne Länge gehört nicht in den Index — `rough_km` bricht daran ab.")


def test_rough_km_is_public():
    """Der Unterstrich war die einzige Zusage, die es gab, und sie wurde von
    `photo_points` gebrochen. Sie ist jetzt öffentlich UND benannt."""
    from app.services import immich

    assert hasattr(immich, "rough_km")
    assert not hasattr(immich, "_km"), (
        "Beide Namen nebeneinander wären genau die Doppelung, die der Umbau "
        "abgeschafft hat.")
