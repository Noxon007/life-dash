"""F18 — ein Foto darf an einem TAG hängen statt an einem Ereignis (Anm. 87).

Die Funktion selbst ist klein. Gefährlich ist, was drumherum stillschweigend
annahm, dass jedes Bild ein Ereignis hat: Löschen, Konto-Löschen und Export
suchten Bilder ÜBER ihre Ereignisse. Ein Tages-Bild fällt durch jeden dieser
Filter — und zwar lautlos: die Datei bliebe auf der Platte, der Datensatz ohne
Besitzer, das Backup sähe vollständig aus und wäre es nicht.

Diese Datei prüft deshalb vor allem die Ränder, nicht den Normalfall.
"""
from __future__ import annotations

import io
from datetime import date, datetime

import pytest
from PIL import Image

from app.models import ConfirmState, Event, MediaRef, Source, User, UserRole
from app.routers.data import export_data
from app.routers.media import (list_day_media, list_media, upload_day_media,
                               upload_media)
from app.services import media as media_svc


@pytest.fixture(autouse=True)
def media_tmp(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    return tmp_path / "media"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 18), (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


class _Upload:
    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


DAY = date(2026, 7, 5)


@pytest.fixture()
def other(db):
    u = User(oidc_subject="other-day-media", email="odm@example.org",
             role=UserRole.user)
    db.add(u)
    db.commit()
    return u


def _day_photo(db, user, day: date = DAY):
    return upload_day_media(day, file=_Upload(_png()), db=db, user=user)


def _event(db, user):
    e = Event(user_id=user.id, title="Konzert", category="concert",
              date_start=datetime(2026, 7, 5, 20), source=Source.manual,
              confirmed=ConfirmState.confirmed)
    db.add(e)
    db.commit()
    return e


# --------------------------------------------------------------------------- #
# Der Normalfall
# --------------------------------------------------------------------------- #
def test_photo_can_hang_on_a_day(db, user):
    res = _day_photo(db, user)
    assert res.media.event_id is None
    ref = db.get(MediaRef, res.media.id)
    assert ref.captured_at.date() == DAY
    assert ref.user_id == user.id
    assert ref.is_upload          # Anmerkung 57: Lebensdatenbank, keine Ableitung


def test_day_listing_finds_it(db, user):
    _day_photo(db, user)
    assert len(list_day_media(DAY, db=db, user=user)) == 1
    assert list_day_media(date(2026, 7, 6), db=db, user=user) == []


def test_day_photos_do_not_leak_into_events(db, user):
    """Der Tag und das Ereignis sind zwei Anker, keine Hierarchie — ein
    Tages-Bild darf nicht plötzlich an einem Ereignis desselben Tages
    auftauchen."""
    ev = _event(db, user)
    _day_photo(db, user)
    assert list_media(ev.id, db=db, user=user) == []


def test_event_photos_do_not_leak_into_the_day(db, user):
    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)
    assert list_day_media(DAY, db=db, user=user) == []


def test_capture_time_falls_back_to_the_chosen_day(db, user):
    """Ohne Ereignis ist `captured_at` der einzige Anker — ein Bild ohne EXIF
    darf deshalb nicht ohne Zeit gespeichert werden, sonst wäre es nirgends
    mehr auffindbar."""
    res = _day_photo(db, user)
    assert res.media.captured_at is not None
    assert res.suggested_captured_at is None      # PNG ohne EXIF


# --------------------------------------------------------------------------- #
# Die Ränder: alles, was Bilder über ihre Ereignisse suchte
# --------------------------------------------------------------------------- #
def test_deleting_the_account_removes_day_photos_too(db, user, media_tmp):
    """`purge_for_events` findet ein Tages-Bild nicht — es hat kein Ereignis.
    Ohne den Nutzer-Weg bliebe die Datei als Waise auf der Platte."""
    _day_photo(db, user)
    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)
    assert len(list((media_tmp / user.id).iterdir())) == 4      # 2 Bilder + 2 Thumbs

    assert media_svc.purge_for_user(db, user.id) == 2
    rest = list((media_tmp / user.id).iterdir()) if (media_tmp / user.id).exists() else []
    assert rest == []


def test_purge_for_events_alone_would_have_missed_it(db, user, media_tmp):
    """Hält den Grund fest, warum es den zweiten Weg gibt — verschwindet diese
    Lücke je, darf dieser Test rot werden und die Stelle vereinfacht."""
    _day_photo(db, user)
    ev = _event(db, user)
    assert media_svc.purge_for_events(db, [ev.id]) == 0


def test_export_contains_day_photos(db, user):
    """Ein Backup, das Tages-Bilder auslässt, sieht vollständig aus und ist es
    nicht — die schlimmste Sorte Fehler in einem Backup."""
    res = _day_photo(db, user)
    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)

    dump = export_data(db=db, user=user)
    ids = {m["id"] for m in dump["media_refs"]}
    assert res.media.id in ids
    assert len(ids) == 2


def test_foreign_day_photos_stay_invisible(db, user, other):
    """A12: Jede Abfrage ist auf den Nutzer eingeschränkt — auch die neue."""
    _day_photo(db, user)
    assert list_day_media(DAY, db=db, user=other) == []
