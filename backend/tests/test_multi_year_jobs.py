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
from app.routers.jobs import (_job_years, _run_photo_points, _year_span,
                              list_jobs)


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


def _props(n: int):
    """`n` Foto-Vorschläge — der Rückgabewert von `scan_year` seit Anm. 139."""
    from datetime import datetime as _dt

    from app.services.photo_points import PhotoProposal
    return [PhotoProposal(slot=f"immich:photo:a{i}", asset_id=f"a{i}",
                          taken_at=_dt(2024, 7, 12, 10, i % 60),
                          lat=51.93, lng=8.87, place="Detmold", city="Detmold")
            for i in range(n)]


def test_photo_points_walks_every_year_and_sums_up(db, user, immich_cfg, monkeypatch):
    from app.routers import jobs as jobs_mod
    from app.services import photo_points as pp

    seen_years: list[int] = []

    def fake_scan(db_, user_, year, url, key, heartbeat=None, report=None, **kw):
        seen_years.append(year)
        if report is not None:
            report["seen"] = 10
            report["dropped"] = {"no_geo": 2}
        return _props(3)

    monkeypatch.setattr(pp, "scan_year", fake_scan)
    monkeypatch.setattr(pp, "create_photo_events",
                        lambda db_, user_, block: len(block))
    monkeypatch.setattr(jobs_mod, "_tick", lambda *a, **kw: True)
    job = Job(user_id=user.id, type="photo_points", params={"years": [2011, 2024]})
    db.add(job)
    db.commit()

    state, msg = _run_photo_points(db, job)

    assert state == "done"
    assert seen_years == [2024, 2011]              # jüngstes zuerst
    assert "2011–2024 (2 Jahre)" in msg
    # Summiert, nicht nur das letzte Jahr — und die Ausschlussgründe ebenso.
    assert "20 Fotos gelesen" in msg and "6 Ereignisse angelegt" in msg
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

    def fake_scan(db_, user_, year, url, key, heartbeat=None, report=None, **kw):
        if year == 2011:
            raise immich_api.ImmichError("Immich weg")
        if report is not None:
            report["seen"] = 4
        return _props(4)

    monkeypatch.setattr(pp, "scan_year", fake_scan)
    monkeypatch.setattr(pp, "create_photo_events",
                        lambda db_, user_, block: len(block))
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

    def fake_scan(db_, user_, year, url, key, heartbeat=None, report=None, **kw):
        if report is not None:
            report["seen"] = 4
        return _props(4)

    monkeypatch.setattr(pp, "scan_year", fake_scan)
    monkeypatch.setattr(pp, "create_photo_events",
                        lambda db_, user_, block: len(block))
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
    # **Ein mittendrin gestopptes Jahr wird NICHT abgehakt** (Anmerkung 139).
    # Vorher hakte der Lauf jedes Jahr ab, sobald er es angefasst hatte — bei
    # einem Abbruch mitten im Jahr stand es damit als „nachgesehen" da, obwohl
    # nur die Hälfte angelegt war. Solange dieser Lauf Kartenpunkte anlegte,
    # war das ärgerlich; seit er Lebensdatenbank anlegt, fehlten Ereignisse
    # ohne einen Weg, sie je wiederzufinden.
    db.expire(user)
    assert pp.scanned_years(user) == {2024}
    assert "2024" in msg


def test_photo_points_without_a_year_refuses(db, user, immich_cfg):
    """Der Riegel gilt weiter: ohne Jahr kein Lauf (Anmerkung 120)."""
    job = Job(user_id=user.id, type="photo_points", params={})
    db.add(job)
    db.commit()
    state, msg = _run_photo_points(db, job)
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
