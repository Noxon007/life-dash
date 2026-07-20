"""Tests für 0.25.0: P2.1 — Immich-Konnektor.

Immich selbst läuft hier nicht; der HTTP-Client wird durch eine Attrappe
ersetzt. Geprüft wird das, was Life-Dash entscheidet: welche Fotos zu welchem
Ereignis gehören, dass nichts doppelt verknüpft wird, und dass Verweise eine
verwerfbare Ableitung bleiben, hochgeladene Dateien aber nicht.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException

from app.models import (ConfirmState, DatePrecision, Event, Location, MediaRef,
                        Source, User, UserRole)
from app.services import immich as api
from app.services.immich_link import candidates, link_batch, reset

IMMICH = {"url": "https://immich.example.org", "api_key": "geheim"}


# --------------------------------------------------------------------------- #
# Hilfen
# --------------------------------------------------------------------------- #
def _asset(aid: str, when: str, lat=None, lng=None) -> dict:
    exif = {"dateTimeOriginal": when}
    if lat is not None:
        exif |= {"latitude": lat, "longitude": lng}
    return {"id": aid, "originalMimeType": "image/jpeg", "exifInfo": exif}


@pytest.fixture()
def immich_user(db, user):
    user.settings = dict(user.settings or {}) | {"immich": IMMICH}
    db.commit()
    return user


@pytest.fixture()
def fake_search(monkeypatch):
    """Ersetzt die Immich-Suche; sammelt die Aufrufe und liefert `assets`."""
    state = {"assets": [], "calls": []}

    def _search(url, key, start, end):
        state["calls"].append((url, key, start, end))
        return [a for a in state["assets"]
                if (t := api.asset_time(a)) is not None and start <= t <= end]

    monkeypatch.setattr("app.services.immich.search_assets", _search)
    return state


def _event(db, user, *, when=datetime(2024, 5, 1, 12, 0),
           precision=DatePrecision.day, loc=None, end=None) -> Event:
    e = Event(user_id=user.id, title="Ausflug", category="trip",
              date_start=when, date_end=end, date_precision=precision,
              location=loc, source=Source.manual,
              confirmed=ConfirmState.confirmed)
    db.add(e)
    db.commit()
    return e


def _loc(db, user, name="Detmold", lat=51.94, lng=8.88) -> Location:
    l = Location(user_id=user.id, name=name, lat=lat, lng=lng)
    db.add(l)
    db.flush()
    return l


# --------------------------------------------------------------------------- #
# Zeitfenster: vage Datierung bekommt KEINE Fotos
# --------------------------------------------------------------------------- #
def test_window_covers_exact_and_day(db, user):
    day = _event(db, user, precision=DatePrecision.day)
    start, end = api.window_for(day)
    assert (start.hour, start.minute) == (0, 0)
    assert (end.hour, end.minute) == (23, 59)

    exact = _event(db, user, precision=DatePrecision.exact)
    start, end = api.window_for(exact)
    assert start < exact.date_start < end


def test_window_spans_multi_day_events(db, user):
    trip = _event(db, user, when=datetime(2024, 7, 5), end=datetime(2024, 7, 12),
                  precision=DatePrecision.day)
    start, end = api.window_for(trip)
    assert start.date() == trip.date_start.date()
    assert end.date() == trip.date_end.date()


@pytest.mark.parametrize("precision", [DatePrecision.month, DatePrecision.season,
                                       DatePrecision.year, DatePrecision.decade])
def test_vague_events_get_no_window(db, user, precision):
    """„Sommer 2002" würde wahllos Fotos einsammeln — ein falsches Foto am
    Eintrag ist schlimmer als gar keins."""
    assert api.window_for(_event(db, user, precision=precision)) is None


def test_events_without_date_get_no_window(db, user):
    e = _event(db, user)
    e.date_start = None
    assert api.window_for(e) is None


# --------------------------------------------------------------------------- #
# Anfrageformat: gegen Immichs echtes Schema, nicht gegen unsere Attrappe
# --------------------------------------------------------------------------- #
# Immich validiert takenAfter/takenBefore gegen dieses Muster aus seiner
# OpenAPI-Spezifikation (Stand API 3.0.3). Entscheidend ist die geforderte
# ZEITZONE am Ende: ein nacktes "2024-05-01T00:00:00" wird mit 400 abgelehnt.
# Eine Attrappe würde das nie zeigen — deshalb steht das Muster hier.
IMMICH_DATETIME_PATTERN = (
    r"^(?:(?:\d\d[2468][048]|\d\d[13579][26]|\d\d0[48]|[02468][048]00"
    r"|[13579][26]00)-02-29|\d{4}-(?:(?:0[13578]|1[02])-(?:0[1-9]|[12]\d|3[01])"
    r"|(?:0[469]|11)-(?:0[1-9]|[12]\d|30)|(?:02)-(?:0[1-9]|1\d|2[0-8])))"
    r"T(?:(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?"
    r"(?:Z|([+-](?:[01]\d|2[0-3]):[0-5]\d)))$"
)


@pytest.mark.parametrize("precision", [DatePrecision.exact, DatePrecision.day])
def test_search_timestamps_match_immichs_schema(db, user, precision):
    import re

    window = api.window_for(_event(db, user, precision=precision))
    for stamp in (api._stamp(window[0]), api._stamp(window[1])):
        assert re.match(IMMICH_DATETIME_PATTERN, stamp), f"Immich lehnt {stamp} ab"


def test_search_timestamps_keep_local_time(db, user):
    """Mit `Z` statt der lokalen Zone verschöbe sich das Fenster um den
    UTC-Versatz — an Tagesgrenzen kämen dann die Fotos des Nachbartages."""
    window = api.window_for(_event(db, user, precision=DatePrecision.day))
    assert api._stamp(window[0]).startswith("2024-05-01T00:00:00")


# --------------------------------------------------------------------------- #
# Ortsprüfung
# --------------------------------------------------------------------------- #
def test_far_away_photos_are_rejected(db, user):
    """Sonst landen fremde Urlaubsfotos vom selben Tag im eigenen Eintrag."""
    ev = _event(db, user, loc=_loc(db, user))
    assert api.matches(ev, _asset("a", "2024-05-01T12:00:00", 51.95, 8.89)) is True
    assert api.matches(ev, _asset("b", "2024-05-01T12:00:00", 37.98, 23.72)) is False


def test_photos_without_gps_are_accepted(db, user):
    """Ungetaggte Fotos sind häufig — dann entscheidet allein die Zeit."""
    ev = _event(db, user, loc=_loc(db, user))
    assert api.matches(ev, _asset("a", "2024-05-01T12:00:00")) is True


def test_events_without_location_accept_everything(db, user):
    ev = _event(db, user)
    assert api.matches(ev, _asset("a", "2024-05-01T12:00:00", 37.98, 23.72)) is True


# --------------------------------------------------------------------------- #
# Verknüpfen
# --------------------------------------------------------------------------- #
def test_links_photos_from_the_same_day(db, immich_user, fake_search):
    ev = _event(db, immich_user)
    fake_search["assets"] = [
        _asset("treffer-1", "2024-05-01T09:30:00"),
        _asset("treffer-2", "2024-05-01T18:10:00"),
        _asset("anderer-tag", "2024-05-09T09:30:00"),
    ]

    processed, linked, remaining = link_batch(db, immich_user)

    assert (processed, linked, remaining) == (1, 2, 0)
    refs = db.query(MediaRef).all()
    assert {r.external_id for r in refs} == {"treffer-1", "treffer-2"}
    assert all(r.provider == "immich" and r.user_id == immich_user.id for r in refs)
    assert all(r.event_id == ev.id for r in refs)


def test_linking_is_idempotent(db, immich_user, fake_search):
    _event(db, immich_user)
    fake_search["assets"] = [_asset("foto", "2024-05-01T09:30:00")]

    link_batch(db, immich_user)
    calls_after_first = len(fake_search["calls"])
    link_batch(db, immich_user)

    assert db.query(MediaRef).count() == 1
    # Bereits verknüpfte Ereignisse werden gar nicht erst erneut abgefragt
    assert len(fake_search["calls"]) == calls_after_first


def test_link_count_is_capped_per_event(db, immich_user, fake_search):
    """Ein Urlaubstag mit 300 Bildern soll den Zeitstrahl nicht zumauern."""
    from app.services.immich_link import MAX_PER_EVENT

    _event(db, immich_user)
    fake_search["assets"] = [_asset(f"foto-{i}", "2024-05-01T09:00:00")
                             for i in range(MAX_PER_EVENT + 20)]

    _, linked, _ = link_batch(db, immich_user)
    assert linked == MAX_PER_EVENT


def test_distant_photos_are_not_linked(db, immich_user, fake_search):
    _event(db, immich_user, loc=_loc(db, immich_user))
    fake_search["assets"] = [
        _asset("nah", "2024-05-01T09:00:00", 51.95, 8.89),
        _asset("fern", "2024-05-01T09:00:00", 37.98, 23.72),
    ]

    link_batch(db, immich_user)
    assert [r.external_id for r in db.query(MediaRef).all()] == ["nah"]


def test_batch_reports_remaining(db, immich_user, fake_search):
    for i in range(5):
        _event(db, immich_user, when=datetime(2024, 5, i + 1, 12, 0))
    fake_search["assets"] = []

    processed, linked, remaining = link_batch(db, immich_user, limit=2)
    assert (processed, linked, remaining) == (2, 0, 3)


def test_unconfigured_account_is_told_so(db, user):
    _event(db, user)
    with pytest.raises(api.ImmichError, match="nicht eingerichtet"):
        link_batch(db, user)


def test_candidates_skip_vague_events(db, immich_user):
    _event(db, immich_user, precision=DatePrecision.year)
    _event(db, immich_user, precision=DatePrecision.day)
    assert len(candidates(db, immich_user.id)) == 1


# --------------------------------------------------------------------------- #
# Verweise sind Ableitung — Uploads nicht (Anmerkung 57)
# --------------------------------------------------------------------------- #
def test_reset_discards_links_but_never_uploads(db, immich_user, fake_search):
    ev = _event(db, immich_user)
    fake_search["assets"] = [_asset("aus-immich", "2024-05-01T09:00:00")]
    link_batch(db, immich_user)
    db.add(MediaRef(user_id=immich_user.id, event_id=ev.id, provider="local",
                    external_id="eigenes-foto.jpg"))
    db.commit()

    removed = reset(db, immich_user.id)

    assert removed == 1
    rest = db.query(MediaRef).all()
    assert [r.provider for r in rest] == ["local"]
    assert rest[0].external_id == "eigenes-foto.jpg"


def test_reset_leaves_other_users_alone(db, immich_user, fake_search):
    other = User(oidc_subject="other-immich", email="oi@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    other_event = _event(db, other)
    db.add(MediaRef(user_id=other.id, event_id=other_event.id, provider="immich",
                    external_id="fremd"))
    db.commit()

    reset(db, immich_user.id)
    assert db.query(MediaRef).count() == 1


# --------------------------------------------------------------------------- #
# Einstellungen: der Schlüssel verlässt den Server nicht
# --------------------------------------------------------------------------- #
def test_settings_never_return_the_api_key(db, immich_user):
    from app.routers.auth import my_settings

    view = my_settings(user=immich_user)
    assert view["immich"] == {"url": IMMICH["url"], "has_key": True}
    assert "geheim" not in str(view)


def test_empty_key_keeps_the_stored_one(db, immich_user):
    from app.routers.auth import update_my_settings

    update_my_settings(payload={"immich": {"url": "https://neu.example.org"}},
                       db=db, user=immich_user)

    assert immich_user.settings["immich"]["api_key"] == "geheim"
    assert immich_user.settings["immich"]["url"] == "https://neu.example.org"


def test_url_must_be_http(db, user):
    from app.routers.auth import update_my_settings

    with pytest.raises(HTTPException) as exc:
        update_my_settings(payload={"immich": {"url": "immich.example.org"}},
                           db=db, user=user)
    assert exc.value.status_code == 400


def test_clear_removes_the_access(db, immich_user):
    from app.routers.auth import update_my_settings

    update_my_settings(payload={"immich": {"clear": True}}, db=db, user=immich_user)
    assert immich_user.settings["immich"] == {}
    assert api.config_for(immich_user) is None
