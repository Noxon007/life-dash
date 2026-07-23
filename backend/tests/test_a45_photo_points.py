"""A45 (Anmerkung 116) — jedes verortete Foto ein Punkt auf der Karte.

Gemeldet: Immich hinterließ „London, 1200 Bilder" als EINEN Kartenpunkt. Die
Bilder wissen einzeln, wo sie entstanden sind; Life-Dash hat es nie
aufgeschrieben — `MediaRef` ist auf zwölf je Tag gedeckelt, weil es eine
andere Frage beantwortet („welche Bilder stehen neben diesem Eintrag?").

Geprüft werden die Eigenschaften, die man dem Ergebnis nicht ansieht:

* die Deckelung von `MediaRef` gilt hier NICHT,
* die drei Filter aus Anmerkung 107 gelten weiterhin (nur eigene, nur mit
  Koordinaten, nur im Zeitstrahl),
* „nie nachgesehen" sieht anders aus als „keine Fotos",
* und der Bild-Proxy hält keine Datenbankverbindung, während er wartet.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import MediaRef, PhotoPoint, User, UserRole
from app.routers.photos import (photo_groups, photo_index, photo_map,
                                photo_reset)
from app.services import immich as api
from app.services import photo_points as pp

MY_ID = "own-user-uuid"
OTHER_ID = "partner-user-uuid"
YEAR = 2024


def _asset(idx: int, *, hour: int = 10, day: int = 12, month: int = 7,
           lat: float | None = 51.93, lng: float | None = 8.87,
           city: str | None = "Detmold", state: str | None = "Nordrhein-Westfalen",
           country: str | None = "Deutschland",
           owner: str = MY_ID, visibility: str = "timeline") -> dict:
    exif = {"dateTimeOriginal": f"{YEAR}-{month:02d}-{day:02d}T{hour:02d}:00:00.000Z",
            "city": city, "state": state, "country": country}
    if lat is not None:
        exif["latitude"] = lat
    if lng is not None:
        exif["longitude"] = lng
    return {
        "id": f"asset-{idx}",
        "ownerId": owner,
        "visibility": visibility,
        "originalMimeType": "image/jpeg",
        "localDateTime": f"{YEAR}-{month:02d}-{day:02d}T{hour:02d}:00:00.000Z",
        "exifInfo": exif,
    }


@pytest.fixture()
def immich_cfg(user, db):
    user.settings = {"immich": {"url": "http://immich.local", "api_key": "k"}}
    db.commit()
    return user


@pytest.fixture()
def fake_api(monkeypatch):
    state = {"assets": [], "me": MY_ID}
    monkeypatch.setattr(api, "own_user_id", lambda url, key: state["me"])
    monkeypatch.setattr(api, "search_assets_paged",
                        lambda url, key, start, end, **kw: [
                            a for a in state["assets"]
                            if start <= api.asset_time(a) <= end])
    return state


def _points(db, user):
    return db.query(PhotoPoint).filter(PhotoPoint.user_id == user.id).all()


# --------------------------------------------------------------------------- #
# Die Deckelung von MediaRef gilt hier nicht — das ist der ganze Punkt
# --------------------------------------------------------------------------- #
def test_every_geotagged_photo_becomes_a_point(db, user, immich_cfg, fake_api):
    """Der gemeldete Fall in klein: 60 Fotos an einem Tag sind 60 Punkte.
    `MediaRef` hätte hier zwölf angelegt — und genau deshalb steht diese
    Tabelle daneben und nicht darin."""
    fake_api["assets"] = [_asset(i, hour=(i % 12) + 8) for i in range(60)]
    seen, added, changed = pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    assert (seen, added, changed) == (60, 60, 0)
    assert len(_points(db, user)) == 60

    from app.services.immich_link import MAX_PER_EVENT
    assert len(_points(db, user)) > MAX_PER_EVENT


def test_a_second_run_updates_instead_of_duplicating(db, user, immich_cfg, fake_api):
    fake_api["assets"] = [_asset(i) for i in range(5)]
    pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    _, added, changed = pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    assert (added, changed) == (0, 0)
    assert len(_points(db, user)) == 5


def test_a_place_added_later_in_immich_reaches_the_point(db, user, immich_cfg,
                                                         fake_api):
    """Ein Ort lässt sich in Immich nachtragen. Bliebe der Punkt, wie er war,
    zeigte die Karte dauerhaft den alten Stand — und niemand käme darauf,
    warum."""
    fake_api["assets"] = [_asset(0, city=None)]
    pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    assert _points(db, user)[0].city is None

    fake_api["assets"] = [_asset(0, city="Detmold")]
    _, added, changed = pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    assert (added, changed) == (0, 1)
    assert _points(db, user)[0].city == "Detmold"


# --------------------------------------------------------------------------- #
# Die drei Filter aus Anmerkung 107 gelten weiter
# --------------------------------------------------------------------------- #
def test_photos_without_coordinates_are_no_points(db, user, immich_cfg, fake_api):
    """Ein Bildschirmfoto kann keinen Ort erfinden."""
    fake_api["assets"] = [_asset(0, lat=None, lng=None), _asset(1)]
    pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    assert [p.asset_id for p in _points(db, user)] == ["asset-1"]


def test_foreign_photos_are_no_points(db, user, immich_cfg, fake_api):
    """Die eigentliche Gefahr sind geteilte Alben: fremde Urlaubsfotos haben
    sehr wohl GPS und schrieben Punkte in eine Karte, an denen man nie war."""
    fake_api["assets"] = [_asset(0, owner=OTHER_ID), _asset(1)]
    pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    assert [p.asset_id for p in _points(db, user)] == ["asset-1"]


def test_archived_photos_are_no_points(db, user, immich_cfg, fake_api):
    fake_api["assets"] = [_asset(0, visibility="archive"), _asset(1)]
    pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    assert [p.asset_id for p in _points(db, user)] == ["asset-1"]


def test_without_an_own_user_id_nothing_is_written(db, user, immich_cfg, fake_api):
    """Ohne eigene Kennung ist ein fremdes Foto nicht erkennbar — dann lieber
    nichts als eine Karte mit fremden Punkten (dieselbe Strenge wie `is_own`)."""
    fake_api["me"] = None
    fake_api["assets"] = [_asset(i) for i in range(5)]
    assert pp.scan_year(db, user, YEAR, "u", "k") == (0, 0, 0)
    db.commit()
    assert _points(db, user) == []


def test_the_local_time_decides_the_day(db, user, immich_cfg, fake_api):
    """Anmerkung 111: `localDateTime` beantwortet die Frage nach dem TAG.
    Die Zone abzuschneiden statt sie anzuwenden verschob ein Foto vom 13. um
    01:30 auf den 12. — und am Tag hängt hier die ganze Gruppierung."""
    asset = _asset(0, day=13, hour=1)
    asset["fileCreatedAt"] = f"{YEAR}-07-12T23:30:00.000Z"
    fake_api["assets"] = [asset]
    pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    assert _points(db, user)[0].taken_at.day == 13


# --------------------------------------------------------------------------- #
# „nie nachgesehen" ist nicht „keine Fotos"
# --------------------------------------------------------------------------- #
def test_a_scanned_year_is_remembered(db, user, immich_cfg, fake_api):
    fake_api["assets"] = []
    pp.scan_year(db, user, YEAR, "u", "k")
    pp.mark_scanned(db, user, YEAR)
    db.commit()
    assert pp.scanned_years(user) == {YEAR}
    assert photo_index(db=db, user=user)["years_scanned"] == [YEAR]


def test_an_unscanned_year_is_not_claimed_as_empty(db, user, immich_cfg):
    """Die sechste Auflage derselben Falle. Ohne diese Liste zeigte die Karte
    für 2004 dasselbe wie für ein Jahr ohne Kamera: nichts, wortlos."""
    assert photo_index(db=db, user=user)["years_scanned"] == []


def test_marking_survives_a_second_year(db, user, immich_cfg):
    """`user.settings` ist eine JSON-Spalte — an Ort und Stelle geändert merkt
    SQLAlchemy die Änderung nicht und schreibt nichts."""
    pp.mark_scanned(db, user, 2004)
    db.commit()
    pp.mark_scanned(db, user, 2024)
    db.commit()
    db.expire(user)
    assert pp.scanned_years(user) == {2004, 2024}


# --------------------------------------------------------------------------- #
# Die Karte sagt, was sie nicht zeigt
# --------------------------------------------------------------------------- #
def test_the_map_names_the_true_total_when_it_caps(db, user, monkeypatch):
    """Anmerkung 110 an der Ereignis-Karte: `all.slice(0, 300)`, chronologisch,
    ohne ein Wort darüber. Hier darf das nicht wieder passieren."""
    monkeypatch.setattr(pp, "MAX_POINTS", 3)
    for i in range(10):
        db.add(PhotoPoint(user_id=user.id, provider="immich", asset_id=f"a{i}",
                          taken_at=datetime(YEAR, 7, 12, 8 + i), lat=51.9, lng=8.8,
                          city="Detmold", country="Deutschland"))
    db.commit()
    out = photo_map(db=db, user=user)
    assert out["shown"] == 3
    assert out["total"] == 10


def test_the_map_window_filters_by_time(db, user):
    for day in (10, 20):
        db.add(PhotoPoint(user_id=user.id, provider="immich", asset_id=f"a{day}",
                          taken_at=datetime(YEAR, 7, day), lat=51.9, lng=8.8,
                          city="Detmold", country="Deutschland"))
    db.commit()
    out = photo_map(date_from=datetime(YEAR, 7, 15), db=db, user=user)
    assert [p["id"] for p in out["points"]] == ["a20"]


def test_points_stay_within_the_account(db, user):
    other = User(oidc_subject="other", email="o@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    db.add(PhotoPoint(user_id=other.id, provider="immich", asset_id="theirs",
                      taken_at=datetime(YEAR, 7, 12), lat=1.0, lng=1.0))
    db.commit()
    assert photo_map(db=db, user=user)["total"] == 0


# --------------------------------------------------------------------------- #
# Gruppen für den Zeitstrahl
# --------------------------------------------------------------------------- #
@pytest.fixture()
def two_cities(db, user):
    for i in range(4):
        db.add(PhotoPoint(user_id=user.id, provider="immich", asset_id=f"det{i}",
                          taken_at=datetime(YEAR, 7, 12, 8 + i), lat=51.9, lng=8.8,
                          city="Detmold", state="Nordrhein-Westfalen",
                          country="Deutschland"))
    for i in range(2):
        db.add(PhotoPoint(user_id=user.id, provider="immich", asset_id=f"lon{i}",
                          taken_at=datetime(YEAR, 7, 12, 18 + i), lat=51.5, lng=-0.1,
                          city="London", state="England", country="Vereinigtes Königreich"))
    db.commit()


def test_groups_condense_per_day_and_city(db, user, two_cities):
    out = photo_groups(level="city", db=db, user=user)
    by_place = {g["place"]: g["count"] for g in out["groups"]}
    assert by_place == {"Detmold": 4, "London": 2}


def test_a_coarser_level_merges_them(db, user, two_cities):
    out = photo_groups(level="country", db=db, user=user)
    assert {g["place"] for g in out["groups"]} == {"Deutschland", "Vereinigtes Königreich"}


def test_groups_carry_a_few_thumbnails_and_the_true_count(db, user):
    for i in range(50):
        db.add(PhotoPoint(user_id=user.id, provider="immich", asset_id=f"a{i}",
                          taken_at=datetime(YEAR, 7, 12, 6, i), lat=51.9, lng=8.8,
                          city="Detmold", country="Deutschland"))
    db.commit()
    group = photo_groups(level="city", db=db, user=user)["groups"][0]
    assert group["count"] == 50
    from app.routers.photos import GROUP_THUMBS
    assert len(group["assets"]) == GROUP_THUMBS
    # Gleichmäßig über den Tag gegriffen, nicht vorne abgeschnitten
    # (Anmerkung 111): sonst zeigt ein Urlaubstag sechsmal den Morgen.
    assert group["assets"][-1] != "a5"


def test_a_photo_without_a_city_gets_its_own_group(db, user):
    """Kein Rückfall auf die gröbere Stufe: ein Foto ohne Stadt in eine
    Stadt-Gruppe zu stecken, die eigentlich das Land ist, wäre eine Zahl mit
    Anspruch — und sie stünde neben echten Städten."""
    db.add(PhotoPoint(user_id=user.id, provider="immich", asset_id="a1",
                      taken_at=datetime(YEAR, 7, 12), lat=51.9, lng=8.8,
                      city="Detmold", country="Deutschland"))
    db.add(PhotoPoint(user_id=user.id, provider="immich", asset_id="a2",
                      taken_at=datetime(YEAR, 7, 12), lat=68.0, lng=25.0,
                      city=None, country="Finnland"))
    db.commit()
    groups = photo_groups(level="city", db=db, user=user)["groups"]
    assert len(groups) == 2
    assert None in {g["place"] for g in groups} or "" in {g["place"] for g in groups}


def test_an_unknown_level_is_refused(db, user):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        photo_groups(level="strasse", db=db, user=user)


# --------------------------------------------------------------------------- #
# Verwerfen und Aufräumen
# --------------------------------------------------------------------------- #
def test_reset_drops_the_points_and_the_scan_marks(db, user, two_cities):
    """Bliebe die Merkliste stehen, behauptete die Oberfläche nach dem
    Zurücksetzen „nachgesehen, keine Fotos" über einer leeren Tabelle."""
    pp.mark_scanned(db, user, YEAR)
    db.commit()
    assert photo_reset(db=db, user=user)["deleted"] == 6
    assert _points(db, user) == []
    assert pp.scanned_years(user) == set()


def test_deleting_the_account_takes_the_points(db, user, two_cities):
    """A45-Zeilen hängen an keinem Ereignis — wer sie über Ereignisse sucht,
    findet sie nicht (dieselbe Falle wie F18/Anmerkung 106)."""
    from app.routers.admin import delete_user

    admin = User(oidc_subject="adm", email="a@example.org", role=UserRole.admin)
    db.add(admin)
    db.commit()
    delete_user(user_id=user.id, admin=admin, db=db)
    assert db.query(PhotoPoint).count() == 0


def test_the_export_carries_the_points(db, user, two_cities):
    """Ein Backup, das etwas auslässt, sieht vollständig aus (F18)."""
    from app.routers.data import export_data

    out = export_data(db=db, user=user)
    assert len(out["photo_points"]) == 6


def test_uploads_are_never_touched_by_the_run(db, user, immich_cfg, fake_api):
    """Medien-Invariante (Anmerkung 57): `provider='local'` ist
    Lebensdatenbank. Der Lauf schreibt in eine ANDERE Tabelle und darf an
    hochgeladenen Dateien nichts ändern — auch nicht versehentlich."""
    upload = MediaRef(user_id=user.id, provider="local", external_id="foto.jpg",
                      captured_at=datetime(YEAR, 7, 12, 10))
    db.add(upload)
    db.commit()
    fake_api["assets"] = [_asset(i) for i in range(5)]
    pp.scan_year(db, user, YEAR, "u", "k")
    db.commit()
    assert db.get(MediaRef, upload.id) is not None
    assert db.query(MediaRef).count() == 1
