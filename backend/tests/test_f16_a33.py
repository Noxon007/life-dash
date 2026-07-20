"""Tests für 0.28.0: F16 („Heute"-Rückblick gedeckelt) und A33 (eigene Daten löschen)."""
from __future__ import annotations

import io
from datetime import date, datetime

import pytest
from fastapi import HTTPException

from app.models import (ConfirmState, DatePrecision, Entity, Event,
                        EventEntityLink, Fragment, FragmentStatus, Location,
                        MediaRef, Metric, Source, Track, User, UserRole)
from app.routers.data import wipe_my_data
from app.routers.events import on_this_day
from app.routers.media import upload_media

TODAY = date(2026, 7, 20)


@pytest.fixture(autouse=True)
def media_tmp(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    return tmp_path / "media"


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (20, 15), (90, 30, 160)).save(buf, "PNG")
    return buf.getvalue()


class _Upload:
    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


def _ev(db, user, title, when, source=Source.manual) -> Event:
    e = Event(user_id=user.id, title=title, category="event", date_start=when,
              date_precision=DatePrecision.day, source=source,
              confirmed=ConfirmState.confirmed)
    db.add(e)
    db.commit()
    return e


# --------------------------------------------------------------------------- #
# F16 — der Rückblick bleibt ein Rückblick
# --------------------------------------------------------------------------- #
def test_look_back_is_capped_per_year(db, user):
    """Ein Tag vor fünf Jahren kann dreißig Einträge haben — ungedeckelt wird
    aus der Erinnerung eine Liste."""
    for i in range(10):
        _ev(db, user, f"Eintrag {i}", datetime(2021, 7, 20, 8 + i))

    groups = on_this_day(db=db, user=user, date=TODAY)

    assert len(groups) == 1
    assert len(groups[0].events) == 3      # Standard-Deckel
    assert groups[0].total == 10           # ehrlich mitgezählt


def test_cap_is_adjustable(db, user):
    for i in range(6):
        _ev(db, user, f"Eintrag {i}", datetime(2021, 7, 20, 8 + i))
    groups = on_this_day(db=db, user=user, date=TODAY, max_per_year=5)
    assert len(groups[0].events) == 5


def test_imported_visits_are_left_out(db, user):
    """Sonst besteht der Rückblick aus Standort-Besuchen statt aus Erlebtem."""
    _ev(db, user, "Konzert", datetime(2021, 7, 20, 20), source=Source.manual)
    for i in range(20):
        _ev(db, user, f"Besuch {i}", datetime(2021, 7, 20, 8), source=Source.google_timeline)

    groups = on_this_day(db=db, user=user, date=TODAY)

    assert [e.title for e in groups[0].events] == ["Konzert"]
    assert groups[0].total == 1


def test_imported_visits_can_be_requested(db, user):
    _ev(db, user, "Besuch", datetime(2021, 7, 20, 8), source=Source.google_timeline)
    assert on_this_day(db=db, user=user, date=TODAY) == []
    groups = on_this_day(db=db, user=user, date=TODAY, include_imported=True)
    assert len(groups) == 1


# --------------------------------------------------------------------------- #
# A33 — eigene Daten löschen
# --------------------------------------------------------------------------- #
@pytest.fixture()
def other(db):
    u = User(oidc_subject="other-wipe", email="ow@example.org", role=UserRole.user)
    db.add(u)
    db.commit()
    return u


def _populate(db, user) -> Event:
    loc = Location(user_id=user.id, name="Detmold", lat=51.9, lng=8.9)
    frag = Fragment(user_id=user.id, raw_text="roh", source=Source.manual,
                    status=FragmentStatus.processed)
    db.add_all([loc, frag])
    db.flush()
    ev = Event(user_id=user.id, title="Ereignis", category="event",
               date_start=datetime(2024, 5, 1), location=loc, source=Source.manual,
               confirmed=ConfirmState.confirmed, origin_fragment_id=frag.id)
    db.add(ev)
    db.flush()
    ent = Entity(user_id=user.id, type="animal", name="Adler",
                 confirmed=ConfirmState.confirmed)
    db.add(ent)
    db.flush()
    db.add_all([
        EventEntityLink(event_id=ev.id, entity_id=ent.id),
        Metric(event_id=ev.id, key="temperature_c", value=21.0, source=Source.weather),
        Track(user_id=user.id, date_start=datetime(2024, 5, 1),
              date_end=datetime(2024, 5, 1), points=[[51.9, 8.9]], source=Source.manual),
    ])
    db.commit()
    return ev


def test_wipe_removes_everything_of_this_user(db, user, media_tmp):
    ev = _populate(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)
    file_path = media_tmp / user.id / db.query(MediaRef).one().external_id

    result = wipe_my_data(confirm="LOESCHEN", db=db, user=user)

    assert result["media_files"] == 1
    assert not file_path.exists()
    for model in (Event, Entity, Location, Track, Fragment, MediaRef, Metric,
                  EventEntityLink):
        assert db.query(model).count() == 0, model.__name__
    assert db.get(User, user.id) is not None       # Konto bleibt


def test_wipe_leaves_other_users_untouched(db, user, other):
    _populate(db, user)
    _populate(db, other)

    wipe_my_data(confirm="LOESCHEN", db=db, user=user)

    assert db.query(Event).count() == 1
    assert db.query(Event).one().user_id == other.id
    assert db.query(Fragment).count() == 1
    assert db.query(Track).count() == 1


def test_wipe_needs_the_typed_confirmation(db, user):
    _populate(db, user)
    for wrong in ("", "ja", "loeschen bitte", "DELETE"):
        with pytest.raises(HTTPException) as exc:
            wipe_my_data(confirm=wrong, db=db, user=user)
        assert exc.value.status_code == 400
    assert db.query(Event).count() == 1


def test_wipe_accepts_lowercase_and_spaces(db, user):
    """Die Hürde soll vor Fehlklicks schützen, nicht vor Tippstil."""
    _populate(db, user)
    wipe_my_data(confirm="  loeschen  ", db=db, user=user)
    assert db.query(Event).count() == 0


def test_wipe_on_empty_account_is_harmless(db, user):
    result = wipe_my_data(confirm="LOESCHEN", db=db, user=user)
    assert result["total"] == 0
    assert result["media_files"] == 0
