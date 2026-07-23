"""Läufe über mehrere Jahre und die Sichtbarkeit laufender Jobs (Anmerkung 120).

Zwei Beobachtungen aus der Nutzung, beide aus derselben Ecke:

**(a)** Fotos verorten und Vorschläge anlegen gingen nur jahresweise. Bei zwanzig
Jahren ist das zwanzigmal dieselbe Handbewegung — und weil jeder Start in den
Jobs-Reiter sprang, zwanzigmal auch der Weg zurück. Die Aufteilung war richtig
für eine ANFRAGE (Zeitbudget der Vorschau), nicht für einen Hintergrund-Lauf:
der wartet auf niemanden, hakt jedes Jahr einzeln ab und ist stoppbar.

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
from app.routers.jobs import (_job_years, _run_immich_source,
                              _run_photo_points, _year_span, list_jobs)


# --------------------------------------------------------------------------- #
# Die Jahre eines Laufs — eine Prüfung für beide Läufe
# --------------------------------------------------------------------------- #
def test_single_year_still_works():
    assert _job_years(Job(type="photo_points", params={"year": 2024})) == ([2024], None)


def test_many_years_come_back_newest_first():
    job = Job(type="photo_points", params={"years": [2004, 2024, 2011]})
    assert _job_years(job) == ([2024, 2011, 2004], None)


def test_duplicates_collapse():
    job = Job(type="photo_points", params={"years": [2024, 2024]})
    assert _job_years(job) == ([2024], None)


@pytest.mark.parametrize("params", [
    {},                        # gar nichts
    {"year": None},
    {"years": []},
    {"years": "2024"},         # kein Array
    {"years": [2024, 99999]},  # ein fauler Eintrag verdirbt den Lauf
    {"years": ["2024"]},       # Zeichenkette ist kein Jahr
    # `bool` IST in Python ein `int`: ohne den Ausschluss wäre das Jahr 1, und
    # `datetime(1, 1, 1)` beantwortet keine Frage, die jemand gestellt hat.
    {"years": [True]},
])
def test_a_bad_year_is_refused_not_guessed(params):
    years, bad = _job_years(Job(type="photo_points", params=params))
    assert years == []
    assert bad and "Jahr" in bad


def test_the_span_is_the_headline():
    assert _year_span([2024]) == "2024"
    assert _year_span([2004, 2011, 2024]) == "2004–2024 (3 Jahre)"
    assert _year_span([]) == "—"


# --------------------------------------------------------------------------- #
# Fotos verorten über mehrere Jahre
# --------------------------------------------------------------------------- #
@pytest.fixture()
def immich_cfg(user, db):
    user.settings = {"immich": {"url": "http://immich.local", "api_key": "k"}}
    db.commit()
    return user


def test_photo_points_walks_every_year_and_sums_up(db, user, immich_cfg, monkeypatch):
    from app.routers import jobs as jobs_mod
    from app.services import photo_points as pp

    seen_years: list[int] = []

    def fake_scan(db_, user_, year, url, key, heartbeat=None, report=None):
        seen_years.append(year)
        if report is not None:
            report["unchanged"] = 1
            report["dropped"] = {"no_geo": 2}
        return 10, 3, 1

    monkeypatch.setattr(pp, "scan_year", fake_scan)
    monkeypatch.setattr(jobs_mod, "_tick", lambda *a, **kw: True)
    job = Job(user_id=user.id, type="photo_points", params={"years": [2011, 2024]})
    db.add(job)
    db.commit()

    state, msg = _run_photo_points(db, job)

    assert state == "done"
    assert seen_years == [2024, 2011]              # jüngstes zuerst
    assert "2011–2024 (2 Jahre)" in msg
    # Summiert, nicht nur das letzte Jahr — und die Ausschlussgründe ebenso.
    assert "20 Fotos gelesen" in msg and "6 neu verortet" in msg
    assert "2 unverändert" in msg
    assert "4 ohne Koordinaten" in msg


def test_every_year_is_ticked_off_on_its_own(db, user, immich_cfg, monkeypatch):
    """**Erst festschreiben, dann abhaken — und zwar je Jahr.**

    Bräche der Lauf in 2011 ab und wären die Haken erst am Ende gesetzt, gälten
    2024 und 2018 wieder als „nie nachgesehen": die Arbeit ist getan, die
    Auskunft darüber weg. Dieselbe Falle wie beim F12-Wettermarker, nur in der
    Reihenfolge statt im Wert.
    """
    from app.routers import jobs as jobs_mod
    from app.services import immich as immich_api
    from app.services import photo_points as pp

    def fake_scan(db_, user_, year, url, key, heartbeat=None, report=None):
        if year == 2011:
            raise immich_api.ImmichError("Immich weg")
        if report is not None:
            report["unchanged"] = 0
        return 4, 4, 0

    monkeypatch.setattr(pp, "scan_year", fake_scan)
    monkeypatch.setattr(jobs_mod, "_tick", lambda *a, **kw: True)
    job = Job(user_id=user.id, type="photo_points",
              params={"years": [2011, 2018, 2024]})
    db.add(job)
    db.commit()

    state, msg = _run_photo_points(db, job)

    assert state == "stopped"
    assert "Immich weg" in msg
    db.expire(user)
    assert pp.scanned_years(user) == {2018, 2024}   # NICHT leer, NICHT 2011


def test_a_stop_between_years_keeps_what_is_done(db, user, immich_cfg, monkeypatch):
    from app.routers import jobs as jobs_mod
    from app.services import photo_points as pp

    def fake_scan(db_, user_, year, url, key, heartbeat=None, report=None):
        if report is not None:
            report["unchanged"] = 0
        return 4, 4, 0

    monkeypatch.setattr(pp, "scan_year", fake_scan)
    # Der Stopp-Wunsch kommt nach dem ersten Jahr an.
    ticks = {"n": 0}

    def fake_tick(*a, **kw):
        ticks["n"] += 1
        return ticks["n"] < 2

    monkeypatch.setattr(jobs_mod, "_tick", fake_tick)
    job = Job(user_id=user.id, type="photo_points",
              params={"years": [2011, 2018, 2024]})
    db.add(job)
    db.commit()

    state, msg = _run_photo_points(db, job)

    assert state == "stopped"
    assert "Gestoppt" in msg
    # **Der Stopp wirkt zwischen den Jahren, nicht mitten in einem.** Was fertig
    # ist, bleibt abgehakt (2024, 2018); das noch nicht begonnene Jahr bleibt
    # offen — und genau so findet ein zweiter Lauf die Arbeit wieder.
    db.expire(user)
    assert pp.scanned_years(user) == {2018, 2024}
    assert "2018–2024 (2 Jahre)" in msg


# --------------------------------------------------------------------------- #
# Vorschläge über mehrere Jahre — der Riegel bleibt, er wird nur breiter
# --------------------------------------------------------------------------- #
def test_immich_source_walks_every_year(db, user, immich_cfg, monkeypatch):
    from app.routers import jobs as jobs_mod
    from app.services import immich_source as source

    class _P:
        def __init__(self, kind):
            self.kind = kind

    asked: list[int] = []

    def fake_scan(db_, user_, year, url, key, albums=False, heartbeat=None, **kw):
        asked.append(year)
        return [_P("day"), _P("album")] if albums else [_P("day")]

    monkeypatch.setattr(source, "scan_year", fake_scan)
    monkeypatch.setattr(source, "create_proposals",
                        lambda db_, user_, block: len(block))
    monkeypatch.setattr(jobs_mod, "_tick", lambda *a, **kw: True)
    job = Job(user_id=user.id, type="immich_source",
              params={"years": [2004, 2024], "albums": True})
    db.add(job)
    db.commit()

    state, msg = _run_immich_source(db, job)

    assert state == "done"
    assert asked == [2024, 2004]
    assert "2004–2024 (2 Jahre)" in msg
    assert "4 Vorschläge angelegt" in msg
    assert "2 Fototage, 2 Alben" in msg


def test_immich_source_without_a_year_refuses(db, user, immich_cfg):
    job = Job(user_id=user.id, type="immich_source", params={})
    db.add(job)
    db.commit()
    state, msg = _run_immich_source(db, job)
    assert state == "error"
    assert "Jahr" in msg


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
    old_runner = _job(db, user, "running", minutes_ago=90, type_="photo_points")
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
