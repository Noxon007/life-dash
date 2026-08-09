"""Der Immich-Lauf über die ganze Bibliothek, und die Sichtbarkeit laufender Jobs.

Zwei Beobachtungen aus der Nutzung, beide aus derselben Ecke:

**(a)** Fotos verorten ging nur jahresweise, mit Vorschau und Jahresauswahl.
Anmerkung 120 hat daraus „alle Jahre in einem Lauf" gemacht, **Anmerkung 206**
den Rest: es gibt nur noch EINEN Immich-Lauf, er geht über die ganze
Bibliothek, und seine Einheit ist der MONAT. Die Zusagen aus Anmerkung 120
gelten unverändert weiter — sie heißen jetzt nur Monat statt Jahr: jüngstes
zuerst, jede Einheit einzeln abgehakt, jederzeit stoppbar, und **erst
festschreiben, dann abhaken**.

**(b)** Der Jobs-Reiter zeigte die letzten zwölf Jobs nach Startzeit. Ein Lauf,
der eine Stunde arbeitet, steht damit nach zwölf kurzen Läufen unten und
irgendwann gar nicht mehr da — ausgerechnet der Job, für den es diesen Reiter
gibt (zusehen, stoppen). Laufendes ist ein Zustand, Abgeschlossenes eine
Chronik; nur die Chronik wird beschnitten.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import Job, User
from app.routers.jobs import _run_immich, list_jobs


# --------------------------------------------------------------------------- #
# Der Lauf über die Bibliothek — Monat für Monat
# --------------------------------------------------------------------------- #
@pytest.fixture()
def immich_cfg(user, db):
    user.settings = {"immich": {"url": "http://immich.local", "api_key": "k"}}
    db.commit()
    return user


@pytest.fixture()
def library(monkeypatch):
    """Immichs Zeitachse als Attrappe — sonst greift der Lauf zur echten Adresse."""
    state = {"months": {}, "my_id": "me"}
    monkeypatch.setattr("app.services.immich.own_user_id",
                        lambda url, key: state["my_id"])
    monkeypatch.setattr("app.services.immich.timeline_buckets",
                        lambda url, key, my_id, **kw: dict(state["months"]))
    return state


def _no_ticks(monkeypatch):
    from app.routers import jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "_tick", lambda *a, **kw: True)


def test_the_run_walks_every_month_newest_first(db, user, immich_cfg, library,
                                                monkeypatch):
    from app.services import photo_points as pp

    seen: list[str] = []

    def fake_scan(db_, user_, month, url, key, my_id, *, report=None, **kw):
        seen.append(month)
        if report is not None:
            report["seen"] = 10
            report["dropped"] = {"no_geo": 2}
        return 3, 5

    monkeypatch.setattr(pp, "scan_month", fake_scan)
    _no_ticks(monkeypatch)
    library["months"] = {"2011-04": 7, "2024-09": 9}
    job = Job(user_id=user.id, type="immich", status="running")
    db.add(job)
    db.commit()

    state, msg = _run_immich(db, job)

    assert state == "done"
    assert seen == ["2024-09", "2011-04"]           # jüngstes zuerst
    # Summiert, nicht nur der letzte Monat — und die Ausschlussgründe ebenso.
    assert "6 Ereignisse angelegt" in msg and "10 Fotos verknüpft" in msg
    assert "4 ohne Koordinaten" in msg


def test_every_month_is_ticked_off_on_its_own(db, user, immich_cfg, library,
                                              monkeypatch):
    """**Erst festschreiben, dann abhaken — und zwar je Monat.**

    Bräche der Lauf in 2011 ab und wären die Haken erst am Ende gesetzt, gälten
    2024 und 2018 wieder als „nie nachgesehen": die Arbeit ist getan, die
    Auskunft darüber weg. Dieselbe Falle wie beim F12-Wettermarker, nur in der
    Reihenfolge statt im Wert.
    """
    from app.services import immich as immich_api
    from app.services import immich_link as link
    from app.services import photo_points as pp

    def fake_scan(db_, user_, month, url, key, my_id, *, report=None, **kw):
        if month == "2011-04":
            raise immich_api.ImmichError("Immich weg")
        return 4, 0

    monkeypatch.setattr(pp, "scan_month", fake_scan)
    _no_ticks(monkeypatch)
    library["months"] = {"2011-04": 1, "2018-05": 2, "2024-09": 3}
    job = Job(user_id=user.id, type="immich", status="running")
    db.add(job)
    db.commit()

    state, msg = _run_immich(db, job)

    assert state == "stopped"
    assert "Immich weg" in msg
    db.expire(user)
    # NICHT leer, und NICHT der Monat, in dem es schiefging.
    assert set(link.scanned_months(user)) == {"2018-05", "2024-09"}


def test_a_stop_between_months_keeps_what_is_done(db, user, immich_cfg, library,
                                                  monkeypatch):
    from app.routers import jobs as jobs_mod
    from app.services import immich_link as link
    from app.services import photo_points as pp

    monkeypatch.setattr(pp, "scan_month",
                        lambda *a, **kw: (4, 0))
    # Der Stopp-Wunsch kommt nach dem ersten Monat an.
    ticks = {"n": 0}

    def fake_tick(*a, **kw):
        ticks["n"] += 1
        return ticks["n"] < 2

    monkeypatch.setattr(jobs_mod, "_tick", fake_tick)
    library["months"] = {"2011-04": 1, "2018-05": 2, "2024-09": 3}
    job = Job(user_id=user.id, type="immich", status="running")
    db.add(job)
    db.commit()

    state, msg = _run_immich(db, job)

    assert state == "stopped"
    assert "gestoppt bei" in msg
    # **Die FERTIGEN Monate bleiben abgehakt.** Der Stopp-Wunsch wird geprüft,
    # nachdem ein Monat durch und festgeschrieben ist; ihn dann wieder zu
    # vergessen hieße, die Arbeit beim nächsten Lauf noch einmal zu machen.
    db.expire(user)
    assert set(link.scanned_months(user)) == {"2024-09", "2018-05"}
    assert "2011-04" not in link.scanned_months(user)


def test_a_month_stopped_MIDWAY_is_not_ticked_off(db, user, immich_cfg, library,
                                                  monkeypatch):
    """Die andere Hälfte derselben Regel — und die teurere.

    `scan_month` blättert; der Heartbeat darf mittendrin abbrechen
    (`ScanAborted`). Dieser Monat ist dann HALB angelegt. Ihn trotzdem
    abzuhaken wäre die F12-Falle in Reinform: die Fotozahl stimmt beim nächsten
    Lauf wieder, der Monat gilt als nachgesehen, und die fehlende Hälfte findet
    nie jemand wieder."""
    from app.services import immich as immich_api
    from app.services import immich_link as link
    from app.services import photo_points as pp

    def fake_scan(db_, user_, month, url, key, my_id, **kw):
        if month == "2018-05":
            raise immich_api.ScanAborted("Lauf gestoppt")
        return 1, 1

    monkeypatch.setattr(pp, "scan_month", fake_scan)
    _no_ticks(monkeypatch)
    library["months"] = {"2018-05": 2, "2024-09": 3}
    job = Job(user_id=user.id, type="immich", status="running")
    db.add(job)
    db.commit()

    state, _ = _run_immich(db, job)

    assert state == "stopped"
    db.expire(user)
    assert set(link.scanned_months(user)) == {"2024-09"}


def test_nothing_open_says_so(db, user, immich_cfg, library, monkeypatch):
    """Kein Jahr-Riegel mehr (Anmerkung 120 „ohne Jahr kein Lauf"): der Lauf
    braucht keine Auswahl, er geht über alles. Was er stattdessen sagen muss,
    ist der Fall, in dem es nichts zu tun gibt — sonst sieht „fertig, 0" wie
    ein Fehlschlag aus."""
    _no_ticks(monkeypatch)
    library["months"] = {}
    job = Job(user_id=user.id, type="immich", status="running")
    db.add(job)
    db.commit()

    state, msg = _run_immich(db, job)

    assert state == "done"
    assert "alles aktuell" in msg


# --------------------------------------------------------------------------- #
# Laufende Jobs verschwinden nicht aus der Liste
# --------------------------------------------------------------------------- #
def _job(db, user: User, status: str, minutes_ago: int, type_: str = "weather") -> Job:
    job = Job(user_id=user.id, type=type_, status=status,
              started_at=datetime(2026, 7, 23, 12, 0) - timedelta(minutes=minutes_ago))
    db.add(job)
    db.commit()
    return job


def test_a_running_job_survives_the_limit(db, user):
    """Der gemeldete Fehler: „viele abgeschlossene Jobs führen dazu, dass
    laufende nicht mehr gesehen werden."""
    old_runner = _job(db, user, "running", minutes_ago=90, type_="immich")
    for i in range(20):
        _job(db, user, "done", minutes_ago=i)

    rows = list_jobs(limit=5, db=db, user=user)

    assert rows[0].id == old_runner.id              # ganz oben, trotz Alter
    assert rows[0].status == "running"
    # Der Verlauf bleibt beschnitten — die Grenze gilt weiter, nur nicht mehr
    # für den Zustand.
    assert len([r for r in rows if r.status == "done"]) == 5


def test_stopping_counts_as_running(db, user):
    stopping = _job(db, user, "stopping", minutes_ago=200)
    for i in range(15):
        _job(db, user, "done", minutes_ago=i)
    rows = list_jobs(limit=3, db=db, user=user)
    assert rows[0].id == stopping.id
