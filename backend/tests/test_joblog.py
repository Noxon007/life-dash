"""Lebenszeichen langer Läufe (app.joblog).

Geprüft wird das, was ein späterer Umbau still kaputt machen kann: die
Drossel (sonst flutet ein schneller Lauf das Log und macht es unlesbar — die
umgekehrte Art von Stille) und die Restzeit (eine Zahl, die niemand
nachrechnet und die deshalb stimmen muss).
"""
import logging

from app.joblog import Progress, format_duration


class _Clock:
    """Kontrollierte Uhr — sonst prüft der Test die Laufzeit der Testmaschine."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _progress(monkeypatch, log, **kw) -> tuple[Progress, _Clock]:
    clock = _Clock()
    monkeypatch.setattr("app.joblog.time.monotonic", clock)
    return Progress(log, "Testlauf", **kw), clock


def test_beat_is_throttled_by_time(monkeypatch, caplog):
    """Zehn Batches in einer Sekunde ergeben eine Zeile, nicht zehn."""
    log = logging.getLogger("lifedash.test.joblog")
    caplog.set_level(logging.INFO, logger=log.name)
    p, clock = _progress(monkeypatch, log, every=10.0)

    assert p.beat(1, 99) is True            # die erste kommt sofort
    for i in range(2, 12):
        clock.t += 0.1
        assert p.beat(i, 100 - i) is False  # innerhalb der Drossel: still
    clock.t += 10
    assert p.beat(50, 50) is True

    assert len(caplog.records) == 2


def test_beat_reports_progress_speed_and_eta(monkeypatch, caplog):
    """60 in 60 s, 120 offen -> „60/min, noch ~2 min"."""
    log = logging.getLogger("lifedash.test.joblog")
    caplog.set_level(logging.INFO, logger=log.name)
    p, clock = _progress(monkeypatch, log)

    clock.t += 60
    p.beat(60, 120)

    line = caplog.records[-1].getMessage()
    assert "60/180" in line          # erledigt von insgesamt
    assert "60/min" in line
    assert "noch ~2 min" in line


def test_beat_survives_a_run_without_progress(monkeypatch, caplog):
    """Kein Fortschritt heißt keine Restzeit — und keinen ZeroDivisionError."""
    log = logging.getLogger("lifedash.test.joblog")
    caplog.set_level(logging.INFO, logger=log.name)
    p, clock = _progress(monkeypatch, log)

    clock.t += 30
    p.beat(0, 500)

    line = caplog.records[-1].getMessage()
    assert "noch" not in line


def test_start_and_finish_frame_the_run(monkeypatch, caplog):
    log = logging.getLogger("lifedash.test.joblog")
    caplog.set_level(logging.INFO, logger=log.name)
    p, clock = _progress(monkeypatch, log, unit="Orte")

    p.start(500, note="user=test")
    clock.t += 125
    p.finish("500 bearbeitet")

    first, last = caplog.records[0].getMessage(), caplog.records[-1].getMessage()
    assert "beginnt" in first and "500 Orte" in first and "user=test" in first
    assert "fertig nach 2 min" in last and "500 bearbeitet" in last


def test_start_says_so_when_the_size_is_unknown(monkeypatch, caplog):
    """Ein Job kennt sein Pensum erst nach dem ersten Batch — dann bitte auch
    keine erfundene Zahl."""
    log = logging.getLogger("lifedash.test.joblog")
    caplog.set_level(logging.INFO, logger=log.name)
    p, _ = _progress(monkeypatch, log)

    p.start()
    assert "offen" in caplog.records[0].getMessage()


def test_a_running_job_leaves_a_trace(db, user, fake_weather, caplog):
    """Der Wetter-Lauf muss unterwegs sprechen, nicht nur beim Start und Ende.

    Geprüft am echten Runner statt an `Progress` allein: die Zeile entsteht in
    `_tick`, durch das JEDER Job-Typ läuft — fällt der Aufruf dort weg, sind
    alle fünf Läufe wieder stumm, und kein Modultest würde es merken.
    """
    from datetime import datetime

    from app.models import ConfirmState, Event, Job, Location, Source
    from app.routers import jobs

    loc = Location(user_id=user.id, name="Detmold", lat=51.94, lng=8.88)
    db.add(loc)
    db.flush()
    for i in range(3):
        db.add(Event(user_id=user.id, title=f"Tag {i}", category="trip",
                     date_start=datetime(2024, 5, 1 + i), location=loc,
                     source=Source.manual, confirmed=ConfirmState.confirmed))
    job = Job(user_id=user.id, type="weather", unit="Ereignisse")
    db.add(job)
    db.commit()

    caplog.set_level(logging.INFO, logger="lifedash.jobs")
    status, result = jobs._run_weather(db, job)

    assert status == "done"
    lines = [r.getMessage() for r in caplog.records]
    assert any("Wetter ergänzen" in line and "3" in line for line in lines), lines


def test_duration_stays_readable():
    assert format_duration(45) == "45 s"
    assert format_duration(90) == "2 min"
    assert format_duration(60 * 60) == "60 min"
    assert format_duration(2 * 3600 + 5 * 60) == "2:05 h"
