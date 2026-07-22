"""0.38.0 — Der Bild-Endpunkt darf keine DB-Verbindung festhalten.

Aus dem Betrieb gemeldet: schnelles Scrollen im Zeitstrahl endete in
`QueuePool limit of size 5 overflow 10 reached, connection timed out` — und
danach scheiterte **jede** Anfrage, auch die des Zeitstrahls selbst. Der sah
deshalb aus, als lade er endlos.

Die Ursache ist nicht die Zahl der Anfragen, sondern ihre Dauer: `/media/{id}/thumb`
holt das Bild bei Immich (Zeitlimit 15 s) und hielt dabei die Verbindung, die
ihm `Depends(get_db)` zugeteilt hatte. Hinter HTTP/2 stellt ein Browser dutzende
Bildanfragen gleichzeitig — nach fünfzehn ist der Pool leer.

Geprüft wird deshalb nicht „kommt ein Bild zurück?", sondern die Eigenschaft,
die man dem Ergebnis nicht ansieht: **ist die Verbindung während des
Immich-Aufrufs frei?**
"""
from __future__ import annotations

import pytest

from app.models import MediaRef
from app.routers.media import get_thumb
from app.services import immich as immich_api


@pytest.fixture()
def immich_user(db, user):
    user.settings = {"immich": {"url": "http://immich.local", "api_key": "k"}}
    db.commit()
    return user


def test_thumbnail_releases_the_connection_before_calling_immich(
        db, immich_user, monkeypatch):
    ref = MediaRef(user_id=immich_user.id, provider="immich",
                   external_id="asset-1")
    db.add(ref)
    db.commit()

    seen: dict[str, bool] = {}

    def _slow_thumbnail(url, key, asset_id):
        # Genau hier hing der Lauf früher — mit belegter Verbindung.
        seen["connection_open"] = db.connection().closed is False \
            if db.in_transaction() else False
        return b"\xff\xd8\xff"

    monkeypatch.setattr(immich_api, "thumbnail", _slow_thumbnail)

    resp = get_thumb(ref.id, db=db, user=immich_user)

    assert resp.status_code == 200
    assert seen["connection_open"] is False, (
        "die Session hielt während des Immich-Aufrufs noch eine Verbindung — "
        "genau daran ist der Pool gestorben")


def test_thumbnail_still_answers_after_the_session_was_closed(
        db, immich_user, monkeypatch):
    """Die Kehrseite: Wer die Session vor dem Ausliefern schließt, darf danach
    kein ORM-Attribut mehr anfassen — sonst lädt SQLAlchemy nach und holt sich
    genau die Verbindung zurück, die gerade freigegeben wurde (oder wirft
    `DetachedInstanceError`). Alles Nötige muss vorher als Wert vorliegen."""
    ref = MediaRef(user_id=immich_user.id, provider="immich",
                   external_id="asset-2", mime="image/jpeg")
    db.add(ref)
    db.commit()
    monkeypatch.setattr(immich_api, "thumbnail", lambda *a: b"\xff\xd8\xff")

    resp = get_thumb(ref.id, db=db, user=immich_user)
    assert resp.body == b"\xff\xd8\xff"
    assert resp.media_type == "image/jpeg"


def test_local_files_do_not_need_immich_at_all(db, user, tmp_path, monkeypatch):
    """Hochgeladene Dateien (F15) gehen denselben Weg — auch sie dürfen die
    Verbindung nicht bis zum Ende halten, obwohl sie schneller sind."""
    from app.config import settings
    from app.services import media as media_svc

    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    target = media_svc.path_for(user.id, "bild.jpg" + media_svc.THUMB_SUFFIX)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\xff\xd8\xff-lokal")

    ref = MediaRef(user_id=user.id, provider="local", external_id="bild.jpg")
    db.add(ref)
    db.commit()

    resp = get_thumb(ref.id, db=db, user=user)
    assert resp.body == b"\xff\xd8\xff-lokal"
