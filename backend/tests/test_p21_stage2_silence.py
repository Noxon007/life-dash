"""Anmerkung 113 — Beobachtungen aus dem Betrieb an P2.1 Stufe 2.

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

Anmerkung 138: die Album-Fälle (achter Kollisionsfall, Ortsname aus dem
Albumtitel, „Album nicht erneut laden") sind mit den Alben selbst entfallen —
diese Datei behält nur, was unabhängig davon gilt.
"""
from __future__ import annotations

import time

import pytest

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
# Rechte: die Anleitung nannte drei, der Konnektor braucht vier
# --------------------------------------------------------------------------- #
def test_a_403_names_the_missing_permission(monkeypatch):
    """„Lehnt den API-Schlüssel ab" schickt zum Wegwerfen eines Schlüssels,
    dem nur ein Häkchen fehlt. 401 und 403 sind zwei verschiedene Lagen."""
    import urllib.error

    def _raise(*a, **kw):
        raise urllib.error.HTTPError("http://x", 403, "Forbidden", {}, None)

    monkeypatch.setattr(api.urllib.request, "urlopen", _raise)
    with pytest.raises(api.ImmichError) as exc:
        api._request("http://immich.local", "k", "/users/me")
    assert "user.read" in str(exc.value)

    def _unknown(*a, **kw):
        raise urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(api.urllib.request, "urlopen", _unknown)
    with pytest.raises(api.ImmichError) as exc2:
        api._request("http://immich.local", "k", "/users/me")
    assert "401" in str(exc2.value) and "user.read" not in str(exc2.value)


def test_every_endpoint_we_call_has_a_known_permission():
    """Der eigentliche Fehler war nicht der fehlende Text, sondern dass er
    nie nachgezogen wurde, als Stufe 2 einen Endpunkt dazunahm."""
    for path in ("/server/about", "/users/me", "/search/metadata",
                 "/timeline/buckets", "/assets/x/thumbnail"):
        assert api.permission_for(path), path


def test_album_permission_is_gone(monkeypatch):
    """Anmerkung 138: mit den Album-Vorschlägen ist auch der einzige Aufruf
    verschwunden, der `album.read` brauchte — der Schlüssel darf jetzt kleiner
    sein, nicht nur größer als nötig."""
    assert api.permission_for("/albums") is None
    assert not hasattr(api, "albums")


def test_connection_test_probes_what_the_feature_uses(monkeypatch):
    """Ein Verbindungstest, der weniger prüft als die Funktion benutzt, ist
    keine Entwarnung — er ist eine falsche."""
    def _request(url, key, path, *, payload=None, raw=False):
        if path == "/users/me":
            raise api.ImmichError(api._denied(path, 403), 403)
        if path == "/server/about":
            return {"version": "1.140.0"}
        if path == "/search/metadata":
            return {"assets": {"items": [{"id": "a1"}]}}
        return {"id": "me"}

    monkeypatch.setattr(api, "_request", _request)
    out = api.check("http://immich.local", "k")
    assert out["missing"] == ["user.read"]
    assert {r["right"] for r in out["rights"]} >= {
        "server.about", "user.read", "asset.read", "asset.view"}
    assert "album.read" not in {r["right"] for r in out["rights"]}


# --------------------------------------------------------------------------- #
# Zeitbudget der Vorschau — unabhängig von Alben, jetzt gegen Fotoseiten geprüft
# --------------------------------------------------------------------------- #
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
    Läuft die ab, ist die Arbeit weg — deshalb ein Zeitbudget. `scan_year`
    selbst wird jetzt nur noch am Fotoabruf gemessen (kein Alben-Zweig mehr),
    also prüft dieser Test, dass die Messung überhaupt greift.
    """
    monkeypatch.setattr(api, "own_user_id", lambda url, key: "me")

    def _slow(url, key, start, end, *, album_id=None, heartbeat=None,
              max_items=20000):
        time.sleep(0.05)
        return []

    monkeypatch.setattr(api, "search_assets_paged", _slow)

    report: dict = {}
    source.scan_year(db, user, YEAR, "u", "k", budget_s=0.01, report=report)
    assert report["seconds"] >= 0.04


def test_missing_own_id_still_reported(db, user, monkeypatch):
    """Ohne eigene Nutzerkennung liefert der Lauf nichts — aber still, nicht
    mit einem Absturz. Ein fehlendes Recht darf nicht die ganze Funktion
    umbringen."""
    monkeypatch.setattr(api, "own_user_id", lambda url, key: None)
    monkeypatch.setattr(api, "search_assets_paged",
                        lambda url, key, s, e, **kw: [
                            {"id": "a1", "ownerId": "me", "visibility": "timeline",
                             "fileCreatedAt": f"{YEAR}-07-12T10:00:00.000Z",
                             "exifInfo": {"latitude": 51.9, "longitude": 8.8,
                                          "city": "Detmold", "country": "Deutschland"}}])

    out = source.scan_year(db, user, YEAR, "u", "k")
    assert out == []
