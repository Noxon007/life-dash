"""Tests für 0.9.0: A4 (Rohansicht-Leitplanken), A11 (Job-Lock,
Wetter-Dubletten-Index), A18 (Cluster-Schwelle in den Einstellungen)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.migrate import ensure_weather_unique_index
from app.models import (
    ConfirmState,
    Entity,
    Event,
    EventEntityLink,
    Job,
    Location,
    Metric,
    Source,
)
from app.routers.admin import delete_row, update_row
from app.routers.auth import update_my_settings
from app.routers.jobs import JobFinish, JobProgress, JobStart, job_finish, start_job


# --------------------------------------------------------------------------- #
# A4 — Rohansicht: Validierung
# --------------------------------------------------------------------------- #
def _event(db, user, **kw) -> Event:
    e = Event(user_id=user.id, title=kw.pop("title", "Strandtag"),
              confirmed=ConfirmState.confirmed, source=Source.manual, **kw)
    db.add(e)
    db.commit()
    return e


def test_update_row_rejects_invalid_enum(db, user):
    e = _event(db, user)
    with pytest.raises(HTTPException) as exc:
        update_row("events", e.id, {"confirmed": "vielleicht"}, db=db)
    assert exc.value.status_code == 400
    assert "erlaubt" in exc.value.detail


def test_update_row_rejects_broken_json_and_bad_datetime(db, user):
    e = _event(db, user)
    with pytest.raises(HTTPException) as exc:
        update_row("events", e.id, {"field_overrides": "{kaputt"}, db=db)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        update_row("events", e.id, {"date_start": "gestern"}, db=db)
    assert exc.value.status_code == 400


def test_update_row_rejects_emptying_required_column(db, user):
    e = _event(db, user)
    with pytest.raises(HTTPException) as exc:
        update_row("events", e.id, {"title": ""}, db=db)
    assert exc.value.status_code == 400


def test_update_row_valid_change_resets_embedding(db, user):
    e = _event(db, user)
    e.embedding = [0.1, 0.2]
    db.commit()
    result = update_row("events", e.id, {"title": "Strandtag in Italien"}, db=db)
    assert result["updated"] is True
    assert any("Embedding" in s for s in result["side_effects"])
    db.expire_all()
    assert db.get(Event, e.id).embedding is None


def test_update_row_time_change_refreshes_weather(db, user, fake_weather):
    loc = Location(user_id=user.id, name="Detmold", lat=51.94, lng=8.88)
    db.add(loc)
    db.flush()
    e = _event(db, user, location_id=loc.id, date_start=datetime(2024, 7, 1))
    db.add(Metric(event_id=e.id, key="temperature_c", value=99.0, source=Source.weather))
    db.commit()

    result = update_row("events", e.id, {"date_start": "2024-08-01T00:00:00"}, db=db)
    assert any("Wetter" in s for s in result["side_effects"])
    db.expire_all()
    temps = [m for m in db.get(Event, e.id).metrics if m.key == "temperature_c"]
    assert len(temps) == 1 and temps[0].value == 21.5  # neu geholt, nicht der Altwert


# --------------------------------------------------------------------------- #
# A4 — Rohansicht: Lösch-Leitplanken & Aufräumen
# --------------------------------------------------------------------------- #
def test_delete_fragment_and_user_blocked(db, user):
    from app.models import Fragment

    frag = Fragment(user_id=user.id, raw_text="Beweis")
    db.add(frag)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        delete_row("fragments", frag.id, db=db)
    assert exc.value.status_code == 400
    assert db.get(Fragment, frag.id) is not None

    with pytest.raises(HTTPException) as exc:
        delete_row("users", user.id, db=db)
    assert exc.value.status_code == 400


def test_delete_event_cleans_children(db, user):
    e = _event(db, user)
    ent = Entity(user_id=user.id, type="animal", name="Adler")
    db.add(ent)
    db.flush()
    db.add(EventEntityLink(event_id=e.id, entity_id=ent.id))
    db.add(Metric(event_id=e.id, key="temperature_c", value=20.0, source=Source.weather))
    db.commit()

    result = delete_row("events", e.id, db=db)
    assert result["deleted"] is True and result["side_effects"]
    assert db.query(Metric).count() == 0
    assert db.query(EventEntityLink).count() == 0


def test_delete_location_detaches_events(db, user):
    loc = Location(user_id=user.id, name="Detmold", lat=51.9, lng=8.9)
    db.add(loc)
    db.flush()
    e = _event(db, user, location_id=loc.id)

    result = delete_row("locations", loc.id, db=db)
    assert any("ohne Ort" in s for s in result["side_effects"])
    db.expire_all()
    assert db.get(Event, e.id).location_id is None


# --------------------------------------------------------------------------- #
# A11 — Job-Lock & Wetter-Dubletten-Index
# --------------------------------------------------------------------------- #
def test_job_lock_blocks_second_start(db, user):
    job = start_job(JobStart(type="weather", unit="Events"), db=db, user=user)
    assert job.status == "running"
    with pytest.raises(HTTPException) as exc:
        start_job(JobStart(type="weather"), db=db, user=user)
    assert exc.value.status_code == 409
    # anderer Typ läuft parallel
    start_job(JobStart(type="resolve_names"), db=db, user=user)
    # nach finish ist der Typ wieder frei
    job_finish(job.id, JobFinish(status="done", result="ok"), db=db, user=user)
    again = start_job(JobStart(type="weather"), db=db, user=user)
    assert again.status == "running"


def test_stale_job_is_reaped(db, user):
    job = start_job(JobStart(type="weather"), db=db, user=user)
    row = db.get(Job, job.id)
    row.updated_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(tzinfo=None)
    db.commit()
    # Verwaister Lauf blockiert nicht mehr — und wird als gestoppt markiert
    second = start_job(JobStart(type="weather"), db=db, user=user)
    assert second.status == "running"
    assert db.get(Job, job.id).status == "stopped"


def test_weather_unique_index_blocks_duplicates(db, user):
    ensure_weather_unique_index(db.get_bind())
    e = _event(db, user)
    db.add(Metric(event_id=e.id, key="temperature_c", value=20.0, source=Source.weather))
    db.commit()
    db.add(Metric(event_id=e.id, key="temperature_c", value=21.0, source=Source.weather))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # andere Kennzahl am selben Event bleibt erlaubt
    db.add(Metric(event_id=e.id, key="weather", value_text="Klar", source=Source.weather))
    db.commit()


# --------------------------------------------------------------------------- #
# A18 — Cluster-Schwelle: Whitelist + Rahmen
# --------------------------------------------------------------------------- #
def test_cluster_min_clamped_to_safe_range(db, user):
    assert update_my_settings(payload={"map_cluster_min": 5000}, db=db,
                              user=user)["map_cluster_min"] == 300
    assert update_my_settings(payload={"map_cluster_min": 1}, db=db,
                              user=user)["map_cluster_min"] == 10
    assert update_my_settings(payload={"map_cluster_min": 80}, db=db,
                              user=user)["map_cluster_min"] == 80
    with pytest.raises(HTTPException):
        update_my_settings(payload={"map_cluster_min": "viele"}, db=db, user=user)
