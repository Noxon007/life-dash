"""Tests für 0.24.0: F15 — Fotos von Hand an Events.

Schwerpunkt sind die drei Zusagen aus KONZEPT Anmerkung 57:
Hochgeladenes gehört zur Lebensdatenbank, es gibt keine fremden Bilder,
und Dateien bleiben beim Löschen nicht verwaist liegen.
"""
from __future__ import annotations

import io
from datetime import datetime

import pytest
from fastapi import HTTPException
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app.models import (ConfirmState, Event, Fragment, FragmentStatus, MediaRef,
                        Source, User, UserRole)
from app.routers.media import (delete_media, get_file, get_thumb, list_media,
                               update_media, upload_media)
from app.services import media as media_svc


# --------------------------------------------------------------------------- #
# Hilfen
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def media_tmp(tmp_path, monkeypatch):
    """Jeder Test bekommt ein eigenes Medienverzeichnis."""
    from app.config import settings
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    return tmp_path / "media"


def _png(size=(40, 30), color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _jpeg_with_exif(when="2019:08:14 16:45:00") -> bytes:
    """JPEG mit Aufnahmezeitpunkt und GPS (Athen) in den EXIF-Daten."""
    img = Image.new("RGB", (24, 18), (10, 120, 200))
    exif = img.getexif()
    exif[36867] = when                                    # DateTimeOriginal
    # Grad/Minute/Sekunde als Rationale — so schreibt es jede Kamera
    exif.get_ifd(0x8825).update({
        1: "N", 2: (IFDRational(37), IFDRational(58), IFDRational(0)),   # 37°58'N
        3: "E", 4: (IFDRational(23), IFDRational(43), IFDRational(0)),   # 23°43'E
    })
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


class _Upload:
    """Minimaler Ersatz für FastAPIs UploadFile."""

    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


def _event(db, user, title="Mit Foto") -> Event:
    e = Event(user_id=user.id, title=title, category="trip",
              date_start=datetime(2024, 5, 1), source=Source.manual,
              confirmed=ConfirmState.confirmed)
    db.add(e)
    db.commit()
    return e


def _upload(db, user, event, data=None):
    return upload_media(event.id, file=_Upload(data or _png()),
                              db=db, user=user)


# --------------------------------------------------------------------------- #
# Speichern, Vermessen, EXIF
# --------------------------------------------------------------------------- #
def test_upload_stores_file_and_thumbnail(db, user, media_tmp):
    ev = _event(db, user)
    res = _upload(db, user, ev)

    assert res.media.provider == "local"
    assert res.media.width == 40 and res.media.height == 30
    assert res.media.mime == "image/png"
    ref = db.query(MediaRef).one()
    assert ref.user_id == user.id
    original = media_tmp / user.id / ref.external_id
    thumb = media_tmp / user.id / (ref.external_id + media_svc.THUMB_SUFFIX)
    assert original.is_file() and thumb.is_file()


def test_exif_is_suggested_not_applied(db, user):
    """Kap. 3.1: über das Datum eines Eintrags entscheidet der Mensch."""
    ev = _event(db, user)
    before = ev.date_start

    res = _upload(db, user, ev, _jpeg_with_exif())

    assert res.suggested_captured_at == datetime(2019, 8, 14, 16, 45)
    assert res.suggested_lat == pytest.approx(37.9667, abs=0.01)
    assert res.suggested_lng == pytest.approx(23.7167, abs=0.01)
    db.refresh(ev)
    assert ev.date_start == before          # Event NICHT verändert


def test_broken_and_foreign_files_are_rejected(db, user):
    ev = _event(db, user)
    for payload in (b"das ist kein Bild",
                    b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>",
                    _png()[:20]):
        with pytest.raises(HTTPException) as exc:
            upload_media(ev.id, file=_Upload(payload), db=db, user=user)
        assert exc.value.status_code == 400
    assert db.query(MediaRef).count() == 0


def test_oversized_file_is_rejected():
    """Die Grenze greift beim LESEN — eine 5-GB-Datei darf nie erst komplett
    in den Speicher wandern, um dann abgelehnt zu werden."""
    big = _png((300, 300))
    with pytest.raises(media_svc.MediaError, match="größer als"):
        media_svc.read_upload(io.BytesIO(big), max_bytes=len(big) - 1)
    # genau auf der Grenze ist noch erlaubt
    assert media_svc.read_upload(io.BytesIO(big), max_bytes=len(big)) == big


def test_empty_file_is_rejected():
    with pytest.raises(media_svc.MediaError):
        media_svc.read_upload(io.BytesIO(b""))


def test_path_traversal_is_blocked(user):
    for evil in ("../../etc/passwd", "..\\windows\\win.ini", "/etc/passwd", ".hidden"):
        with pytest.raises(media_svc.MediaError):
            media_svc.path_for(user.id, evil)


# --------------------------------------------------------------------------- #
# Zugriff: keine fremden Bilder (Anmerkung 57)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def other(db):
    u = User(oidc_subject="other-media", email="om@example.org", role=UserRole.user)
    db.add(u)
    db.commit()
    return u


def test_foreign_media_is_not_readable(db, user, other):
    ev = _event(db, user)
    res = _upload(db, user, ev)

    for call in (get_file, get_thumb):
        with pytest.raises(HTTPException) as exc:
            call(res.media.id, db=db, user=other)
        assert exc.value.status_code == 404


def test_foreign_media_is_not_deletable_or_editable(db, user, other):
    ev = _event(db, user)
    res = _upload(db, user, ev)

    with pytest.raises(HTTPException):
        delete_media(res.media.id, db=db, user=other)
    with pytest.raises(HTTPException):
        update_media(res.media.id, caption="geklaut", db=db, user=other)
    assert db.query(MediaRef).count() == 1


def test_upload_to_foreign_event_is_rejected(db, user, other):
    ev = _event(db, user)
    with pytest.raises(HTTPException) as exc:
        upload_media(ev.id, file=_Upload(_png()), db=db, user=other)
    assert exc.value.status_code == 404


def test_served_file_forbids_content_sniffing(db, user):
    """Fremde Bytes dürfen vom Browser nie selbst typisiert werden."""
    ev = _event(db, user)
    res = _upload(db, user, ev)
    resp = get_file(res.media.id, db=db, user=user)
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.media_type == "image/png"


# --------------------------------------------------------------------------- #
# Die Invariante: Hochgeladenes ist Lebensdatenbank, keine Ableitung
# --------------------------------------------------------------------------- #
def test_recompute_never_discards_events_with_uploads(db, user):
    """Der Kern von Anmerkung 57: eine Neuberechnung darf ein Event mit
    hochgeladenem Bild nicht verwerfen — die Datei gäbe es sonst nirgends mehr."""
    from app.services.ingestion import reset_reprocess

    frag = Fragment(user_id=user.id, raw_text="Foto-Notiz", source=Source.manual,
                    status=FragmentStatus.processed)
    db.add(frag)
    db.flush()
    ev = Event(user_id=user.id, title="Unbestätigt mit Foto", category="event",
               date_start=datetime(2024, 5, 1), source=Source.ai,
               confirmed=ConfirmState.unconfirmed, origin_fragment_id=frag.id)
    db.add(ev)
    db.commit()
    _upload(db, user, ev)

    reset_reprocess(db)

    assert db.get(Event, ev.id) is not None       # Event überlebt
    assert db.query(MediaRef).count() == 1        # Bild überlebt


def test_recompute_still_discards_events_without_uploads(db, user):
    """Gegenprobe: ohne Bild bleibt die Neuberechnung, wie sie war."""
    from app.services.ingestion import reset_reprocess

    frag = Fragment(user_id=user.id, raw_text="Nur Text", source=Source.manual,
                    status=FragmentStatus.processed)
    db.add(frag)
    db.flush()
    ev = Event(user_id=user.id, title="Unbestätigt ohne Foto", category="event",
               date_start=datetime(2024, 5, 1), source=Source.ai,
               confirmed=ConfirmState.unconfirmed, origin_fragment_id=frag.id)
    db.add(ev)
    db.commit()

    reset_reprocess(db)
    assert db.get(Event, ev.id) is None


# --------------------------------------------------------------------------- #
# Löschen räumt die Dateien mit ab
# --------------------------------------------------------------------------- #
def test_delete_removes_file_and_thumbnail(db, user, media_tmp):
    ev = _event(db, user)
    res = _upload(db, user, ev)
    ref = db.query(MediaRef).one()
    original = media_tmp / user.id / ref.external_id

    delete_media(res.media.id, db=db, user=user)

    assert db.query(MediaRef).count() == 0
    assert not original.exists()
    assert not (media_tmp / user.id / (ref.external_id + media_svc.THUMB_SUFFIX)).exists()


def test_discarding_an_event_removes_its_files(db, user, media_tmp):
    """Sonst bliebe bei jedem gelöschten Eintrag eine verwaiste Datei liegen."""
    from app.routers.moderation import discard_event

    ev = _event(db, user)
    _upload(db, user, ev)
    ref = db.query(MediaRef).one()
    original = media_tmp / user.id / ref.external_id

    discard_event(ev.id, db=db, user=user)

    assert not original.exists()


def test_media_list_and_caption(db, user):
    ev = _event(db, user)
    first = _upload(db, user, ev)
    second = _upload(db, user, ev)

    update_media(first.media.id, caption="  Sonnenuntergang  ", db=db, user=user)
    items = list_media(ev.id, db=db, user=user)

    assert [m.id for m in items] == [first.media.id, second.media.id]
    assert items[0].caption == "Sonnenuntergang"        # getrimmt
    assert items[1].sort_order == 1


def test_export_warns_that_files_are_missing(db, user):
    """Anmerkung 57: Niemand darf glauben, der JSON-Export sichere die Fotos."""
    from app.routers.data import export_data

    ev = _event(db, user)
    _upload(db, user, ev)

    dump = export_data(db=db, user=user)

    assert dump["media_files_included"] is False
    assert dump["media_files_count"] == 1
    assert "MEDIA_DIR" in dump["media_note"]
    assert len(dump["media_refs"]) == 1                 # Metadaten sind drin
