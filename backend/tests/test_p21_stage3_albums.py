"""P2.1 Stufe 3 (Anmerkung 116) — Alben nur noch auf Nachfrage.

Gemeldet aus dem Betrieb: Immich legte einen Sammeleintrag „London, 1200
Bilder" an. Das ist ein mehrtägiges Ereignis mit **einem** Punkt auf der
Karte, obwohl jedes der 1200 Bilder für sich weiß, wo es entstanden ist. Und
es tritt der von Hand erfassten Reise in die Quere: `covering_event` fängt den
Zwilling nur ab, wenn die Reise vorher dasteht — bei einem Nachtlauf ist das
Zufall.

Die Richtung ist damit umgedreht: **Reisen legt der Mensch an, die Fotos
hängen sich daran.** Alben verschwinden nicht, sie werden zu einer
ausdrücklichen Frage.

Diese Datei prüft nur den Schalter und seine Folgen. Dass der Alben-Zweig
inhaltlich richtig rechnet, steht unverändert in `test_p21_stage2.py` — der
Aufruf dort fragt jetzt ausdrücklich danach.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import (ConfirmState, Event, Fragment, FragmentStatus, Source,
                        User, UserRole)
from app.routers.immich import source_preview
from app.services import immich as api
from app.services import immich_source as source

MY_ID = "own-user-uuid"
YEAR = 2024


def _asset(idx: int, *, hour: int = 10, day: int = 12, month: int = 7) -> dict:
    return {
        "id": f"asset-{idx}",
        "ownerId": MY_ID,
        "visibility": "timeline",
        "originalMimeType": "image/jpeg",
        "fileCreatedAt": f"{YEAR}-{month:02d}-{day:02d}T{hour:02d}:00:00.000Z",
        "exifInfo": {
            "dateTimeOriginal": f"{YEAR}-{month:02d}-{day:02d}T{hour:02d}:00:00.000Z",
            "latitude": 51.93, "longitude": 8.87,
            "city": "Detmold", "state": "Nordrhein-Westfalen",
            "country": "Deutschland",
        },
    }


@pytest.fixture()
def immich_cfg(user, db):
    user.settings = {"immich": {"url": "http://immich.local", "api_key": "k"}}
    db.commit()
    return user


@pytest.fixture()
def fake_api(monkeypatch):
    state = {"assets": [], "albums": [], "album_assets": {}, "me": MY_ID,
             "album_calls": 0, "asset_calls": []}

    monkeypatch.setattr(api, "own_user_id", lambda url, key: state["me"])

    def _albums(url, key, owned=None):
        state["album_calls"] += 1
        return [a for a in state["albums"]
                if owned is None or bool(a.get("_owned")) == owned]

    def _search(url, key, start, end, *, album_id=None, heartbeat=None,
                max_items=20000):
        state["asset_calls"].append((start, end, album_id))
        if album_id:
            return [a for a in state["album_assets"].get(album_id, [])
                    if start <= api.asset_time(a) <= end]
        return [a for a in state["assets"]
                if start <= api.asset_time(a) <= end]

    monkeypatch.setattr(api, "albums", _albums)
    monkeypatch.setattr(api, "search_assets_paged", _search)
    return state


@pytest.fixture()
def library(fake_api):
    """Eine Bibliothek mit einem Fototag UND einem Album darüber."""
    fake_api["assets"] = [_asset(i, hour=9 + i) for i in range(6)]
    fake_api["albums"] = [{"id": "alb-1", "albumName": "London", "_owned": True}]
    fake_api["album_assets"]["alb-1"] = fake_api["assets"]
    return fake_api


# --------------------------------------------------------------------------- #
# Der Schalter
# --------------------------------------------------------------------------- #
def test_the_run_does_not_ask_for_albums_by_default(db, user, immich_cfg, library):
    props = source.scan_year(db, user, YEAR, "u", "k")
    assert all(p.kind == "day" for p in props), [p.kind for p in props]
    # Und zwar wirklich NICHT gefragt: der Alben-Zweig kostet einen
    # Assets-Abruf je Album. Am Ende zu filtern hätte die Fotos trotzdem
    # geholt — bei einer gewachsenen Bibliothek ist genau das die Laufzeit.
    assert library["album_calls"] == 0
    assert all(album_id is None for _, _, album_id in library["asset_calls"])


def test_albums_are_still_available_when_asked_for(db, user, immich_cfg, library):
    props = source.scan_year(db, user, YEAR, "u", "k", albums=True)
    assert any(p.kind == "album" and p.title == "London" for p in props)
    assert library["album_calls"] > 0


def test_a_photo_day_inside_an_album_survives_without_albums(db, user, immich_cfg,
                                                             library):
    """Fall (5) rückwärts gelesen: Solange Alben mitliefen, gewann das Album
    und der Tagescluster wurde verworfen. Ohne Alben darf der Tag nicht
    zwischen den Stühlen verschwinden — sonst hätte das Abschalten still
    Vorschläge gekostet."""
    without = source.scan_year(db, user, YEAR, "u", "k")
    assert len(without) == 1
    assert without[0].kind == "day"

    withal = source.scan_year(db, user, YEAR, "u", "k", albums=True)
    assert [p.kind for p in withal] == ["album"]


# --------------------------------------------------------------------------- #
# Der Job fragt nie von selbst
# --------------------------------------------------------------------------- #
def test_the_background_job_never_asks_for_albums_on_its_own(db, user,
                                                             immich_cfg, library,
                                                             monkeypatch):
    """Der Nachtplan ist genau der Ort, an dem ein Album-Zwilling entsteht,
    ohne dass jemand zusieht."""
    from app.models import Job
    from app.routers import jobs as jobs_router

    seen = {}

    def _spy(db_, user_, year, url, key, **kw):
        seen.update(kw)
        return []

    monkeypatch.setattr(source, "scan_year", _spy)
    job = Job(user_id=user.id, type="immich_source", params={"year": YEAR})
    db.add(job)
    db.commit()
    jobs_router._run_immich_source(db, job)
    assert seen.get("albums") is False

    # Ausdrücklich angefordert geht es weiterhin — der Knopf schickt das Flag.
    seen.clear()
    job.params = {"year": YEAR, "albums": True}
    db.commit()
    jobs_router._run_immich_source(db, job)
    assert seen.get("albums") is True


# --------------------------------------------------------------------------- #
# „nicht gefragt" darf nicht wie „nichts gefunden" aussehen
# --------------------------------------------------------------------------- #
def test_the_preview_says_whether_it_looked_at_albums(db, user, immich_cfg,
                                                      library):
    quiet = source_preview(year=YEAR, db=db, user=user)
    assert quiet["albums"] == 0
    assert quiet["albums_asked"] is False

    loud = source_preview(year=YEAR, albums=True, db=db, user=user)
    assert loud["albums"] == 1
    assert loud["albums_asked"] is True


def test_a_failed_preview_still_reports_the_flag(db, user, immich_cfg, fake_api,
                                                 monkeypatch):
    """Der Fehlerzweig antwortet mit 200 und `error` im Rumpf (Anmerkung 113).
    Er baut sein Ergebnis von Hand zusammen — genau dort fehlt ein neues Feld
    am ehesten, und dann steht bei einem Immich-Ausfall „keine Alben"."""
    def _boom(*a, **kw):
        raise api.ImmichError("Immich nicht erreichbar")

    monkeypatch.setattr(source, "scan_year", _boom)
    out = source_preview(year=YEAR, albums=True, db=db, user=user)
    assert out["error"]
    assert out["albums_asked"] is True


# --------------------------------------------------------------------------- #
# Vorhandene Album-Vorschläge wegräumen
# --------------------------------------------------------------------------- #
def _album_proposal(db, user, *, confirmed=ConfirmState.unconfirmed,
                    slot="immich:album:alb-1", title="London"):
    fragment = Fragment(user_id=user.id, raw_text='{"slot": "%s"}' % slot,
                        source=Source.immich, status=FragmentStatus.processed)
    db.add(fragment)
    db.flush()
    event = Event(user_id=user.id, title=title,
                  date_start=datetime(YEAR, 7, 1), date_end=datetime(YEAR, 7, 5),
                  category="trip", confirmed=confirmed, source=Source.immich,
                  origin_fragment=fragment, external_id=slot)
    db.add(event)
    db.commit()
    return event


def test_discarding_album_proposals_counts_before_it_acts(db, user):
    from app.routers.immich import album_proposals, discard_album_proposals

    _album_proposal(db, user, slot="immich:album:a", title="London")
    _album_proposal(db, user, slot="immich:album:b", title="Kreta")
    assert album_proposals(db=db, user=user)["events"] == 2

    out = discard_album_proposals(db=db, user=user)
    assert out["deleted"] == 2
    assert album_proposals(db=db, user=user)["events"] == 0


def test_discarding_never_touches_confirmed_albums(db, user):
    """Bestätigt heißt Lebensdatenbank. Ein Aufräumknopf, der die anfasst,
    löscht eine Entscheidung, die ein Mensch getroffen hat."""
    from app.routers.immich import discard_album_proposals

    keep = _album_proposal(db, user, confirmed=ConfirmState.confirmed,
                           slot="immich:album:keep", title="Dänemark 2024")
    drop = _album_proposal(db, user, slot="immich:album:drop", title="London")

    out = discard_album_proposals(db=db, user=user)
    assert out["deleted"] == 1
    assert db.get(Event, keep.id) is not None
    assert db.get(Event, drop.id) is None


def test_discarding_never_touches_photo_day_proposals(db, user):
    """Die Tage sind der Zweig, der bleiben soll — ein Knopf, der beim
    Aufräumen mehr mitnimmt als sein Text sagt, ist der teuerste Defekt hier."""
    from app.routers.immich import discard_album_proposals

    day = _album_proposal(db, user, slot="immich:day:2024-07-12:Detmold",
                          title="6 Fotos in Detmold")
    discard_album_proposals(db=db, user=user)
    assert db.get(Event, day.id) is not None


def test_discarding_leaves_the_tombstone_in_place(db, user):
    """Das Fragment ist der Grabstein (Anmerkung 107, Fall 2). Bliebe es nicht
    liegen, schlüge derselbe Knopf »Alben ansehen« dieselben Alben sofort
    wieder vor — die Endlos-Abruf-Falle, diesmal von der anderen Seite."""
    from app.routers.immich import discard_album_proposals

    event = _album_proposal(db, user, slot="immich:album:x")
    fragment_id = event.origin_fragment_id
    discard_album_proposals(db=db, user=user)
    assert db.get(Fragment, fragment_id) is not None
    assert "immich:album:x" in source._proposed_slots(db, user.id)


def test_discarding_stays_within_the_account(db, user, db_other_user):
    from app.routers.immich import discard_album_proposals

    mine = _album_proposal(db, user, slot="immich:album:mine")
    theirs = _album_proposal(db, db_other_user, slot="immich:album:theirs")

    discard_album_proposals(db=db, user=user)
    assert db.get(Event, mine.id) is None
    assert db.get(Event, theirs.id) is not None


@pytest.fixture()
def db_other_user(db):
    other = User(oidc_subject="other-sub", email="other@example.org",
                 display_name="Andere", role=UserRole.user)
    db.add(other)
    db.commit()
    return other
