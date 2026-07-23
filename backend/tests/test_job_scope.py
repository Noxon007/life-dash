"""Kontogebundene Läufe (Anmerkung 115).

Der Wetterlauf stand bis 0.38 im System-Reiter und arbeitete über den GANZEN
Bestand. Beides gehört zusammen: als Admin-Werkzeug war „über alle" richtig,
als Aktion unter „Meine Daten" ist es falsch — ein Nutzer, der seinen eigenen
Knopf drückt, fasst sonst die Ereignisse aller anderen an.

Der zweite Test ist der teurere Fall, weil er still ist: der Nachtplan fragte
„lief dieser Typ heute schon?" ohne nach dem Konto zu unterscheiden. Bei einem
Konto ist das dasselbe; ab dem zweiten nimmt der erste Nutzer allen anderen den
Termin weg — Nacht für Nacht, ohne Fehlermeldung. Für `immich`, `immich_source`
und `resolve_names` galt das schon vorher.

Offline: kein Open-Meteo (`fake_weather`), keine Worker-Threads.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import (ConfirmState, Event, Job, Location, Metric, Source,
                        User, UserRole)
from app.routers import jobs as jobs_mod
from app.services.enrichment import enrich_weather


def _located_event(db, user, name="Detmold", lat=51.94) -> Event:
    loc = Location(user_id=user.id, name=name, lat=lat, lng=8.88)
    db.add(loc)
    db.flush()
    ev = Event(user_id=user.id, title=f"Tag in {name}", category="trip",
               date_start=datetime(2024, 5, 1), location=loc,
               source=Source.manual, confirmed=ConfirmState.confirmed)
    db.add(ev)
    db.commit()
    return ev


@pytest.fixture()
def other(db) -> User:
    u = User(oidc_subject="other-sub", email="andere@example.org",
             display_name="Andere", role=UserRole.user)
    db.add(u)
    db.commit()
    return u


# --------------------------------------------------------------------------- #
# Der Lauf bleibt beim eigenen Konto
# --------------------------------------------------------------------------- #
def test_weather_run_only_touches_its_own_account(db, user, other, fake_weather):
    mine = _located_event(db, user)
    theirs = _located_event(db, other, name="Lemgo", lat=52.02)

    enriched, remaining = enrich_weather(db, user_id=user.id)

    assert enriched == 1
    assert remaining == 0            # „offen" heißt: offen bei MIR
    assert len(fake_weather) == 1    # genau eine Abfrage, nicht zwei
    assert db.query(Metric).filter(Metric.event_id == mine.id).count() > 0
    assert db.query(Metric).filter(Metric.event_id == theirs.id).count() == 0


def test_weather_run_without_account_stays_instance_wide(db, user, other,
                                                         fake_weather):
    """Der Admin-Endpunkt (und die Tests) geben kein Konto mit — dann gilt
    weiterhin der Rundum-Lauf. Sonst wäre die Voreinstellung eine andere als
    vor der Änderung, und zwar unbemerkt."""
    _located_event(db, user)
    _located_event(db, other, name="Lemgo", lat=52.02)

    enriched, remaining = enrich_weather(db)

    assert (enriched, remaining) == (2, 0)


def test_job_runner_passes_the_starters_account(db, user, other, fake_weather):
    """Der Weg, den die Oberfläche tatsächlich nimmt: Job → Runner → Lauf."""
    _located_event(db, user)
    _located_event(db, other, name="Lemgo", lat=52.02)
    job = Job(user_id=user.id, type="weather")
    db.add(job)
    db.commit()

    status, result = jobs_mod._run_weather(db, job)

    assert status == "done"
    assert len(fake_weather) == 1
    assert "1 Events" in result


# --------------------------------------------------------------------------- #
# Nachtplan: jedes Konto bekommt seinen Termin
# --------------------------------------------------------------------------- #
@pytest.fixture()
def planner(db, monkeypatch):
    """Stellt den Nachtplan-Lauf her: eigene Session ersetzt, Worker gezählt
    statt gestartet (die In-Memory-DB verträgt keine fremden Threads)."""
    started: list[str] = []
    monkeypatch.setattr(jobs_mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(jobs_mod, "spawn_worker", lambda job_id: started.append(job_id))
    return started


def _schedule(db, user, jtype="weather"):
    user.settings = {"job_schedule": {jtype: {"enabled": True,
                                              "hour": datetime.now().hour}}}
    db.commit()


def _ran_today(db, user, jtype="weather") -> Job:
    """Ein heute gelaufener, abgeschlossener Job dieses Kontos."""
    job = Job(user_id=user.id, type=jtype, status="done",
              started_at=datetime.now(timezone.utc).replace(tzinfo=None),
              finished_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(job)
    db.commit()
    return job


def test_a_foreign_run_does_not_use_up_my_slot(db, user, other, planner):
    """Der eigentliche Befund: A ist heute gelaufen, B war noch nie dran."""
    _schedule(db, user)
    _schedule(db, other)
    _ran_today(db, user)

    jobs_mod.run_due_schedules()

    fresh = [j for j in db.query(Job).filter(Job.type == "weather").all()
             if j.status == "running"]
    assert [j.user_id for j in fresh] == [other.id]
    assert len(planner) == 1


def test_my_own_run_still_uses_up_my_slot(db, user, planner):
    """Die Regel, die es zu erhalten galt: zweimal in derselben Nacht nicht."""
    _schedule(db, user)
    _ran_today(db, user)

    jobs_mod.run_due_schedules()

    assert db.query(Job).filter(Job.type == "weather").count() == 1
    assert planner == []


def test_a_running_job_blocks_everyone(db, user, other, planner):
    """Die Sperre bleibt global — sie schützt das Kontingent bei Open-Meteo,
    und das hängt an der Instanz, nicht am Konto."""
    _schedule(db, user)
    _schedule(db, other)
    db.add(Job(user_id=user.id, type="weather", status="running"))
    db.commit()

    jobs_mod.run_due_schedules()

    assert db.query(Job).filter(Job.type == "weather").count() == 1
    assert planner == []


def test_instance_wide_types_keep_one_slot_for_everyone(db, user, other, planner):
    """`embeddings` rechnet über den ganzen Bestand — dort ist „einer für alle"
    richtig, und diese Hälfte darf die Trennung nicht mitreißen."""
    _schedule(db, user, "embeddings")
    _schedule(db, other, "embeddings")
    job = _ran_today(db, user, "embeddings")
    # gestern gestartet wäre wieder fällig; heute nicht
    assert job.started_at.date() == datetime.now(timezone.utc).date()

    jobs_mod.run_due_schedules()

    assert db.query(Job).filter(Job.type == "embeddings").count() == 1
    assert planner == []


def test_yesterdays_run_frees_the_slot_again(db, user, planner):
    _schedule(db, user)
    old = _ran_today(db, user)
    old.started_at = old.started_at - timedelta(days=1)
    old.finished_at = old.finished_at - timedelta(days=1)
    db.commit()

    jobs_mod.run_due_schedules()

    assert db.query(Job).filter(Job.type == "weather").count() == 2
    assert len(planner) == 1
