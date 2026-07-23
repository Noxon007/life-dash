"""Anmerkung 113 — die drei Beobachtungen aus dem Betrieb an P2.1 Stufe 2.

Gemeldet wurde: „Vorschau geht nicht, kein Log, keine Rückmeldung" und „man
kann nur Jahre auswählen, die schon in Life-Dash sind". Beides ist dieselbe
Krankheit wie in Anmerkung 110 und 112 — **Stille**:

* Die Jahresliste fällt auf die eigenen Jahre zurück, wenn Immich die Frage
  nicht beantwortet, und sagt es niemandem. Genau die Jahre, für die es dieses
  Paket gibt (vor dem Smartphone), fehlen dann.
* `/timeline/buckets` hat seine Pflichtparameter **gewechselt**: `size=MONTH`
  war bis Immich 1.133 Pflicht und ist seit 1.134 verboten. Immich antwortet in
  beiden Fällen mit 400 — die häufigste Ursache dafür, dass die Liste
  zurückfällt.
* Der Vorschlaglauf lud bei JEDEM Durchgang jedes Album vollständig herunter,
  auch die längst bestätigten und die abgelehnten.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime

import pytest

from app.models import ConfirmState, Event, Fragment, FragmentStatus, Source
from app.services import immich as api
from app.services import immich_source as source

YEAR = 2024


# --------------------------------------------------------------------------- #
# Die wandernde Parametergrenze von /timeline/buckets
# --------------------------------------------------------------------------- #
def _bucket_server(reject: set[str]):
    """Ein Immich, das bestimmte Parameter mit 400 ablehnt — wie das echte.

    `reject` nennt die Parameternamen, die diese fingierte Version NICHT kennt.
    Immich prüft streng gegen sein DTO; ein unbekannter Parameter ist ein
    Fehler, keine Warnung.
    """
    seen: list[str] = []

    def _request(url, key, path, *, payload=None, raw=False):
        seen.append(path)
        query = path.split("?", 1)[1] if "?" in path else ""
        names = {p.split("=")[0] for p in query.split("&") if p}
        bad = sorted(names & reject)
        if bad:
            raise api.ImmichError(
                f"Immich antwortet mit 400: property {bad[0]} should not exist", 400)
        return [{"timeBucket": "2004-07-01", "count": 412},
                {"timeBucket": "2004-08-01", "count": 8},
                {"timeBucket": f"{YEAR}-07-01", "count": 6}]

    return _request, seen


def test_year_counts_survive_a_new_immich(monkeypatch):
    """Ab 1.134 ist `size` verboten. Die erste Sprosse fragt ohne — ein Treffer."""
    request, seen = _bucket_server(reject={"size"})
    monkeypatch.setattr(api, "_request", request)
    assert api.photo_years("u", "k", "me") == {2004: 420, YEAR: 6}
    assert len(seen) == 1, "die neueste Form muss zuerst gefragt werden"


def test_year_counts_survive_an_older_immich(monkeypatch):
    """Bis 1.133 war `size` Pflicht — ohne ihn ein 400. Die Leiter fängt das ab.

    Genau dieser Fall ist die wahrscheinlichste Ursache der Meldung „ich kann
    nur Jahre auswählen, die schon in Life-Dash sind": ein einziger 400, und
    die ganze Empfehlung war weg.
    """
    request, seen = _bucket_server(reject={"visibility", "withCoordinates"})
    monkeypatch.setattr(api, "_request", request)
    assert api.photo_years("u", "k", "me")[2004] == 420
    assert len(seen) == 3, "es muss bis zur ältesten Form heruntergegangen werden"


def test_ladder_stops_at_a_wrong_key(monkeypatch):
    """Bei 401 wird nicht weitergeraten: dasselbe Problem, dreimal langsamer."""
    calls = []

    def _request(url, key, path, *, payload=None, raw=False):
        calls.append(path)
        raise api.ImmichError("Immich lehnt den API-Schlüssel ab (401/403)", 401)

    monkeypatch.setattr(api, "_request", _request)
    with pytest.raises(api.ImmichError):
        api.photo_years("u", "k", "me")
    assert len(calls) == 1


def test_error_carries_its_status(monkeypatch):
    """`status` ist die Unterscheidung „Immich hat geantwortet" (P5.1-Regel)."""
    import urllib.error

    def _raise(*a, **kw):
        raise urllib.error.HTTPError("http://x", 400, "Bad Request", {}, None)

    monkeypatch.setattr(api.urllib.request, "urlopen", _raise)
    with pytest.raises(api.ImmichError) as exc:
        api._request("http://immich.local", "k", "/timeline/buckets")
    assert exc.value.status == 400


# --------------------------------------------------------------------------- #
# Der Notnagel sagt, dass er einer ist
# --------------------------------------------------------------------------- #
def test_year_list_names_the_reason_for_falling_back(db, user, monkeypatch):
    """Ohne den Grund ist die Notliste von einer Empfehlung nicht zu
    unterscheiden — und sie ist genau die Liste, die das Paket abschaffen
    wollte."""
    from app.routers.immich import source_years

    user.settings = {"immich": {"url": "http://immich.local", "api_key": "k"}}
    db.commit()
    monkeypatch.setattr(api, "own_user_id", lambda url, key: "me")

    def _boom(url, key, my_id):
        raise api.ImmichError("Immich antwortet mit 400: property size should "
                              "not exist", 400)

    monkeypatch.setattr(api, "photo_years", _boom)
    out = source_years(db=db, user=user)
    assert out["source"] == "own"
    assert "400" in out["reason"]


def test_year_list_says_when_immich_is_not_set_up(db, user):
    """Auch der harmloseste Rückfall braucht einen Grund: ohne Zugangsdaten
    sieht die Liste sonst aus, als hätte Immich nichts."""
    from app.routers.immich import source_years

    out = source_years(db=db, user=user)
    assert out["source"] == "own" and out["reason"]


# --------------------------------------------------------------------------- #
# Rechte: die Anleitung nannte drei, der Konnektor braucht fünf
# --------------------------------------------------------------------------- #
def test_a_403_names_the_missing_permission(monkeypatch):
    """„Lehnt den API-Schlüssel ab" schickt zum Wegwerfen eines Schlüssels,
    dem nur ein Häkchen fehlt. 401 und 403 sind zwei verschiedene Lagen."""
    import urllib.error

    def _raise(*a, **kw):
        raise urllib.error.HTTPError("http://x", 403, "Forbidden", {}, None)

    monkeypatch.setattr(api.urllib.request, "urlopen", _raise)
    with pytest.raises(api.ImmichError) as exc:
        api._request("http://immich.local", "k", "/albums?isOwned=true")
    assert "album.read" in str(exc.value)

    def _unknown(*a, **kw):
        raise urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(api.urllib.request, "urlopen", _unknown)
    with pytest.raises(api.ImmichError) as exc2:
        api._request("http://immich.local", "k", "/albums")
    assert "401" in str(exc2.value) and "album.read" not in str(exc2.value)


def test_every_endpoint_we_call_has_a_known_permission():
    """Der eigentliche Fehler war nicht der fehlende Text, sondern dass er
    nie nachgezogen wurde, als Stufe 2 zwei Endpunkte dazunahm."""
    for path in ("/server/about", "/users/me", "/search/metadata",
                 "/timeline/buckets", "/albums", "/assets/x/thumbnail"):
        assert api.permission_for(path), path


def test_connection_test_probes_what_the_feature_uses(monkeypatch):
    """Ein Verbindungstest, der weniger prüft als die Funktion benutzt, ist
    keine Entwarnung — er ist eine falsche. Genau dieser Knopf meldete grün,
    während die Vorschau an einem 403 scheiterte."""
    def _request(url, key, path, *, payload=None, raw=False):
        if path.startswith("/albums"):
            raise api.ImmichError(api._denied(path, 403), 403)
        if path == "/server/about":
            return {"version": "1.140.0"}
        if path == "/search/metadata":
            return {"assets": {"items": [{"id": "a1"}]}}
        return {"id": "me"}

    monkeypatch.setattr(api, "_request", _request)
    out = api.check("http://immich.local", "k")
    assert out["missing"] == ["album.read"]
    assert {r["right"] for r in out["rights"]} >= {
        "server.about", "user.read", "asset.read", "album.read", "asset.view"}


def test_missing_album_right_still_yields_photo_days(db, user, monkeypatch):
    """Ein fehlendes Häkchen darf nicht die ganze Funktion umbringen —
    verschwiegen wird es trotzdem nicht."""
    def _albums(url, key, owned=None):
        raise api.ImmichError(api._denied("/albums", 403), 403)

    monkeypatch.setattr(api, "own_user_id", lambda url, key: "me")
    monkeypatch.setattr(api, "albums", _albums)
    monkeypatch.setattr(api, "search_assets_paged",
                        lambda url, key, s, e, **kw: [
                            {"id": f"a{i}", "ownerId": "me", "visibility": "timeline",
                             "localDateTime": f"{YEAR}-07-12T1{i}:00:00",
                             "exifInfo": {"latitude": 51.9, "longitude": 8.8,
                                          "city": "Detmold", "country": "Deutschland"}}
                            for i in range(5)])

    report: dict = {}
    out = source.scan_year(db, user, YEAR, "u", "k", report=report)
    assert [p.kind for p in out] == ["day"]
    assert "album.read" in report["albums_denied"]


# --------------------------------------------------------------------------- #
# Was der Lauf NICHT mehr herunterlädt
# --------------------------------------------------------------------------- #
def test_known_albums_are_not_downloaded_again(db, user, monkeypatch):
    """Ein Album, dessen Platz vergeben ist, wird nicht mehr geholt.

    Vorher wurde jedes Album bei jedem Lauf vollständig heruntergeladen und am
    Ende weggeworfen — bei einer gewachsenen Bibliothek der Löwenanteil der
    Wartezeit, und ab dem zweiten Lauf komplett umsonst. Genau diese Wartezeit
    steckte hinter „der Knopf tut nichts": bis die Antwort steht, schreibt der
    Server nicht einmal eine Zugriffszeile.
    """
    user.settings = {"immich": {"url": "http://immich.local", "api_key": "k"}}
    albums = [{"id": "alb-alt", "albumName": "Dänemark", "_owned": True,
               "startDate": f"{YEAR}-07-01T00:00:00.000Z",
               "endDate": f"{YEAR}-07-14T00:00:00.000Z"},
              {"id": "alb-neu", "albumName": "Ostsee", "_owned": True,
               "startDate": f"{YEAR}-08-01T00:00:00.000Z",
               "endDate": f"{YEAR}-08-05T00:00:00.000Z"}]
    # Das erste Album wurde schon einmal vorgeschlagen (und abgelehnt: das
    # Ereignis ist weg, das Fragment als Grabstein geblieben).
    db.add(Fragment(user_id=user.id, source=Source.immich,
                    status=FragmentStatus.processed,
                    raw_text=json.dumps({"type": "immich_source",
                                         "slot": source.slot_album("alb-alt")})))
    db.commit()

    fetched: list[str] = []

    def _search(url, key, start, end, *, album_id=None, heartbeat=None,
                max_items=20000):
        if album_id:
            fetched.append(album_id)
            return [{"id": "a1", "ownerId": "me", "visibility": "timeline",
                     "fileCreatedAt": f"{YEAR}-08-02T10:00:00.000Z",
                     "localDateTime": f"{YEAR}-08-02T12:00:00.000Z",
                     "exifInfo": {"latitude": 54.1, "longitude": 12.1,
                                  "city": "Warnemünde", "country": "Deutschland"}}]
        return []

    monkeypatch.setattr(api, "own_user_id", lambda url, key: "me")
    monkeypatch.setattr(api, "albums",
                        lambda url, key, owned=None: [
                            a for a in albums
                            if owned is None or bool(a.get("_owned")) == owned])
    monkeypatch.setattr(api, "search_assets_paged", _search)

    out = source.scan_year(db, user, YEAR, "u", "k")
    assert fetched == ["alb-neu"], "das vergebene Album wurde erneut geladen"
    assert [p.slot for p in out] == [source.slot_album("alb-neu")]


def test_preview_never_answers_with_a_gateway_status(db, user, monkeypatch):
    """Ein Immich-Ausfall darf kein 502 dieser App sein.

    Der gemeldete Fehler, mit Beweis aus dem Netzwerk-Reiter: 502 in 205 ms,
    `content-type: text/html`, 6,5 kB. So schnell antwortet kein Zeitlimit —
    Immich hat sofort abgelehnt, die App hat daraus ein 502 gemacht, und
    **Cloudflare hat den Rumpf durch seine eigene Fehlerseite ersetzt**. Der
    Satz, der genau sagt, was klemmt, kam nie an; die Seite bekam HTML, wo sie
    JSON erwartete.

    Ein Statuscode gehört der eigenen App. Die Auskunft über einen fremden
    Dienst gehört in die Nutzlast, wo kein Vermittler sie anfasst — genauso
    hält es `/api/immich/years` mit `reason`.
    """
    from fastapi import HTTPException

    from app.routers.immich import source_preview

    user.settings = {"immich": {"url": "http://immich.local", "api_key": "k"}}
    db.commit()

    def _boom(*a, **kw):
        raise api.ImmichError("Immich lehnt den API-Schlüssel ab (401/403)", 401)

    monkeypatch.setattr(source, "scan_year", _boom)
    try:
        out = source_preview(year=YEAR, db=db, user=user)
    except HTTPException as exc:  # pragma: no cover - genau das darf nicht sein
        raise AssertionError(
            f"Vorschau antwortet mit {exc.status_code} — ein 5xx wird unterwegs "
            "durch die Fehlerseite des Vermittlers ersetzt") from exc
    assert "401" in out["error"]
    assert out["total"] == 0 and out["proposals"] == []


def test_preview_gives_up_in_time_and_says_so(db, user, monkeypatch):
    """Ein 502 ist keine späte Antwort, sondern gar keine.

    Aus der Ferne steht ein umgekehrter Vertreter mit fester Geduld dazwischen.
    Läuft die ab, ist die Arbeit weg — deshalb ein Zeitbudget und eine
    Teilantwort, die sich als Teilantwort zu erkennen gibt.
    """
    albums = [{"id": f"alb-{i}", "albumName": f"Album {i}", "_owned": True}
              for i in range(5)]
    monkeypatch.setattr(api, "own_user_id", lambda url, key: "me")
    monkeypatch.setattr(api, "albums",
                        lambda url, key, owned=None: albums if owned else [])

    def _slow(url, key, start, end, *, album_id=None, heartbeat=None,
              max_items=20000):
        if album_id:
            time.sleep(0.05)      # ein Album kostet Zeit — wie im Betrieb
        return []

    monkeypatch.setattr(api, "search_assets_paged", _slow)

    report: dict = {}
    source.scan_year(db, user, YEAR, "u", "k", budget_s=0.08, report=report)
    assert report["partial"] is True
    assert report["albums_open"] >= 1
    assert report["albums_checked"] < len(albums)


def test_the_run_has_no_budget(db, user, monkeypatch):
    """Der Job wartet auf niemanden — eine halbe Vorschau ist brauchbar,
    ein halber Lauf wäre es nicht."""
    albums = [{"id": f"alb-{i}", "albumName": f"Album {i}", "_owned": True}
              for i in range(4)]
    seen: list[str] = []
    monkeypatch.setattr(api, "own_user_id", lambda url, key: "me")
    monkeypatch.setattr(api, "albums",
                        lambda url, key, owned=None: albums if owned else [])

    def _slow(url, key, start, end, *, album_id=None, heartbeat=None,
              max_items=20000):
        if album_id:
            seen.append(album_id)
            time.sleep(0.02)
        return []

    monkeypatch.setattr(api, "search_assets_paged", _slow)
    report: dict = {}
    source.scan_year(db, user, YEAR, "u", "k", report=report)
    assert len(seen) == len(albums)
    assert report["partial"] is False


def test_confirmed_album_is_not_downloaded_again(db, user, monkeypatch):
    """Dasselbe für den bestätigten Fall (3): das Ereignis trägt den Platz."""
    db.add(Event(user_id=user.id, title="Dänemark", category="trip",
                 date_start=datetime(YEAR, 7, 1), source=Source.immich,
                 confirmed=ConfirmState.confirmed,
                 external_id=source.slot_album("alb-alt")))
    db.commit()

    fetched: list[str] = []
    monkeypatch.setattr(api, "own_user_id", lambda url, key: "me")
    monkeypatch.setattr(api, "albums", lambda url, key, owned=None: [
        {"id": "alb-alt", "albumName": "Dänemark", "_owned": True}] if owned else [])

    def _search(url, key, start, end, *, album_id=None, heartbeat=None,
                max_items=20000):
        if album_id:
            fetched.append(album_id)
        return []

    monkeypatch.setattr(api, "search_assets_paged", _search)
    assert source.scan_year(db, user, YEAR, "u", "k") == []
    assert fetched == []
