"""Tests für 0.26.0: A29 — vollständiges Backup als ZIP.

Der Kern ist der **Round-Trip**: exportieren, alles löschen, zurückspielen —
und danach müssen Daten UND Bilddateien wieder da sein. Ein Archiv, das man
nicht zurückspielen kann, ist kein Backup, sondern eine Datei, die so aussieht.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.models import ConfirmState, Event, MediaRef, Source, User, UserRole
from app.routers.data import export_archive, export_data, import_archive
from app.routers.media import upload_media
from app.services import archive
from app.services import media as media_svc


@pytest.fixture(autouse=True)
def media_tmp(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    return tmp_path / "media"


def _png(size=(40, 30), color=(10, 160, 60)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


class _Upload:
    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


def _event(db, user, title="Mit Foto") -> Event:
    e = Event(user_id=user.id, title=title, category="trip",
              date_start=datetime(2024, 5, 1), source=Source.manual,
              confirmed=ConfirmState.confirmed)
    db.add(e)
    db.commit()
    return e


def _zip_bytes(db, user, **kw) -> bytes:
    """Führt den Streaming-Export vollständig aus und gibt das Archiv zurück.

    Bewusst über den echten Endpunkt statt direkt über `archive.stream`: nur
    so ist mitgeprüft, dass StreamingResponse den Generator auch wirklich
    abarbeitet — das Archiv entsteht ja erst beim Ausliefern.
    """
    import asyncio

    resp = export_archive(db=db, user=user, **kw)

    async def _collect() -> bytes:
        return b"".join([chunk async for chunk in resp.body_iterator])

    return asyncio.run(_collect())


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def test_archive_contains_json_and_files(db, user):
    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)

    with zipfile.ZipFile(io.BytesIO(_zip_bytes(db, user))) as zf:
        names = zf.namelist()
        payload = json.loads(zf.read("export.json"))

    ref = db.query(MediaRef).one()
    assert "export.json" in names
    assert f"media/{ref.external_id}" in names
    assert payload["media_files_included"] is True
    assert len(payload["events"]) == 1


def test_archive_omits_thumbnails(db, user):
    """Vorschauen sind ableitbar — im Archiv wären sie nur Ballast."""
    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)

    with zipfile.ZipFile(io.BytesIO(_zip_bytes(db, user))) as zf:
        assert not [n for n in zf.namelist() if media_svc.THUMB_SUFFIX in n]


def test_archive_skips_immich_references(db, user):
    """Immich-Bilder gehören einem fremden System und werden dort gesichert."""
    ev = _event(db, user)
    db.add(MediaRef(user_id=user.id, event_id=ev.id, provider="immich",
                    external_id="fremde-asset-id"))
    db.commit()

    with zipfile.ZipFile(io.BytesIO(_zip_bytes(db, user))) as zf:
        assert [n for n in zf.namelist() if n.startswith("media/")] == []
        # Der VERWEIS bleibt trotzdem im JSON — er ist neu berechenbar
        assert len(json.loads(zf.read("export.json"))["media_refs"]) == 1


def test_archive_survives_a_missing_file(db, user, media_tmp):
    """Fehlt eine Datei auf der Platte, bricht der Export nicht ab — ein
    unvollständiges Backup ist besser als gar keines."""
    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)
    ref = db.query(MediaRef).one()
    (media_tmp / user.id / ref.external_id).unlink()

    with zipfile.ZipFile(io.BytesIO(_zip_bytes(db, user))) as zf:
        assert "export.json" in zf.namelist()
        assert [n for n in zf.namelist() if n.startswith("media/")] == []


def test_export_selection_still_applies(db, user):
    """A21 gilt unverändert: ausgeschlossene Quellen bleiben draußen."""
    _event(db, user, title="Von Hand")
    imported = Event(user_id=user.id, title="Aus dem Import", category="event",
                     date_start=datetime(2024, 5, 2), source=Source.google_timeline)
    db.add(imported)
    db.commit()

    payload = export_data(exclude_source="google_timeline", db=db, user=user)
    assert [e["title"] for e in payload["events"]] == ["Von Hand"]


# --------------------------------------------------------------------------- #
# Round-Trip — der eigentliche Punkt
# --------------------------------------------------------------------------- #
def test_full_round_trip_restores_data_and_files(db, user, media_tmp):
    ev = _event(db, user, title="Urlaubstag")
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)
    ref = db.query(MediaRef).one()
    filename, original = ref.external_id, _png()
    blob = _zip_bytes(db, user)

    # Totalverlust simulieren: Datenbankzeilen weg, Dateien weg
    db.query(MediaRef).delete()
    db.query(Event).delete()
    db.commit()
    for f in (media_tmp / user.id).iterdir():
        f.unlink()

    result = import_archive(file=_Upload(blob), db=db, user=user)

    assert result["media_restored"] == 1
    assert db.query(Event).count() == 1
    restored = db.query(MediaRef).one()
    assert restored.external_id == filename
    assert restored.user_id == user.id
    # Die Datei ist byte-identisch zurück
    assert (media_tmp / user.id / filename).read_bytes() == original
    # ... und die Vorschau wurde neu erzeugt, obwohl sie nicht im Archiv war
    assert result["thumbnails_created"] == 1
    assert (media_tmp / user.id / (filename + media_svc.THUMB_SUFFIX)).is_file()


def test_import_is_idempotent(db, user):
    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)
    blob = _zip_bytes(db, user)

    first = import_archive(file=_Upload(blob), db=db, user=user)
    second = import_archive(file=_Upload(blob), db=db, user=user)

    assert first["media_restored"] == 0      # Datei war noch da
    assert second["media_restored"] == 0
    assert second["media_skipped"] >= 1
    assert db.query(MediaRef).count() == 1   # keine Dubletten
    assert db.query(Event).count() == 1


def test_restore_assigns_media_to_the_importing_user(db, user, media_tmp):
    """Ein Archiv aus einer anderen Instanz trägt eine fremde Nutzer-ID. Wird
    die übernommen, sind die Bilder für niemanden mehr erreichbar."""
    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)
    blob = _zip_bytes(db, user)
    db.query(MediaRef).delete()
    db.query(Event).delete()
    db.commit()

    other = User(oidc_subject="empfaenger", email="e@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    import_archive(file=_Upload(blob), db=db, user=other)

    assert db.query(MediaRef).one().user_id == other.id


# --------------------------------------------------------------------------- #
# Sicherheit: ein Archiv ist genauso fremd wie ein Upload
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("evil", [
    "../../etc/passwd",
    "media/../../etc/passwd",
    "media/../geheim.jpg",
    "media/unter/ordner.jpg",
    "media/",
    "media/.versteckt",
    "beliebig.txt",
])
def test_zip_slip_entries_are_refused(evil):
    """Ein Eintrag mit Pfadanteilen würde beim Entpacken außerhalb des
    Zielverzeichnisses landen."""
    assert archive.safe_member(evil) is None


def test_plain_filenames_are_accepted():
    assert archive.safe_member("media/abc123.jpg") == "abc123.jpg"


def test_non_images_in_the_archive_are_not_written(db, user, media_tmp):
    """Auch aus einem Archiv darf nichts auf die Platte, was kein Bild ist."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("export.json", json.dumps({"format": "lifedash-export"}))
        zf.writestr("media/schadhaft.jpg", b"#!/bin/sh\nrm -rf /\n")
        zf.writestr("../ausbruch.txt", b"nein")

    result = import_archive(file=_Upload(buf.getvalue()), db=db, user=user)

    assert result["media_restored"] == 0
    assert result["media_skipped"] == 2
    assert not (media_tmp / user.id / "schadhaft.jpg").exists()


def test_broken_archive_is_reported(db, user):
    with pytest.raises(HTTPException) as exc:
        import_archive(file=_Upload(b"kein zip"), db=db, user=user)
    assert exc.value.status_code == 400


def test_archive_without_json_is_reported(db, user):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("media/x.jpg", _png())

    with pytest.raises(HTTPException) as exc:
        import_archive(file=_Upload(buf.getvalue()), db=db, user=user)
    assert exc.value.status_code == 400
    assert "export.json" in exc.value.detail


# --------------------------------------------------------------------------- #
# „Alle Daten löschen" — beim Rauchtest von 0.26.0 als seit v0.9.0 kaputt
# aufgefallen (fehlender text-Import -> 500). Nie getestet gewesen.
# --------------------------------------------------------------------------- #
def test_wipe_removes_rows_and_files(db, user, media_tmp, monkeypatch):
    from app.routers import admin

    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)
    ref = db.query(MediaRef).one()
    original = media_tmp / user.id / ref.external_id
    assert original.is_file()

    # wipe_data arbeitet auf der echten Engine/Session — in Tests auf die
    # In-Memory-Session umbiegen, damit dieselben Daten gemeint sind.
    monkeypatch.setattr(admin, "SessionLocal", lambda: db)
    monkeypatch.setattr(admin, "engine", db.get_bind())

    result = admin.wipe_data()

    assert result["total"] > 0
    assert result["media_files"] == 1
    assert not original.exists()
    assert db.query(Event).count() == 0


def test_wipe_deletes_files_only_after_the_database(db, user, media_tmp, monkeypatch):
    """Scheitert das Löschen der Zeilen, dürfen die Bilder NICHT weg sein —
    sonst bleibt der schlimmstmögliche Zustand zurück: Daten da, Fotos weg."""
    from app.routers import admin

    ev = _event(db, user)
    upload_media(ev.id, file=_Upload(_png()), db=db, user=user)
    original = media_tmp / user.id / db.query(MediaRef).one().external_id

    class _Boom:
        def begin(self):
            raise RuntimeError("Datenbank streikt")

    monkeypatch.setattr(admin, "SessionLocal", lambda: db)
    monkeypatch.setattr(admin, "engine", _Boom())

    with pytest.raises(RuntimeError):
        admin.wipe_data()

    assert original.is_file()          # Foto überlebt den Fehlschlag


def test_oversized_entries_are_skipped(db, user, monkeypatch, media_tmp):
    from app.config import settings
    monkeypatch.setattr(settings, "media_max_mb", 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("export.json", json.dumps({"format": "lifedash-export"}))
        zf.writestr("media/riesig.png", b"x" * (2 * 1024 * 1024))

    result = import_archive(file=_Upload(buf.getvalue()), db=db, user=user)
    assert result["media_restored"] == 0
    assert not (media_tmp / user.id / "riesig.png").exists()
