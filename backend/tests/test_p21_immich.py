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


def test_photos_go_to_day_children_not_the_trip(db, immich_user, fake_search):
    """F7: Hat eine Reise Tages-Kinder, bekommt sie selbst keine Fotos — die
    Anreicherung hängt an den Tagen, genau wie das Wetter. Vorher lagen die
    ersten zwölf Bilder am Reise-Eintrag und nichts an den einzelnen Tagen."""
    trip = _event(db, immich_user, when=datetime(2024, 7, 1),
                  end=datetime(2024, 7, 3), precision=DatePrecision.day)
    for day in (1, 2, 3):
        child = _event(db, immich_user, when=datetime(2024, 7, day),
                       precision=DatePrecision.day)
        child.parent_event_id = trip.id
    db.commit()

    cand_ids = {e.id for e in candidates(db, immich_user.id)}
    assert trip.id not in cand_ids           # Eltern-Reise ausgeschlossen
    assert len(cand_ids) == 3                 # nur die drei Tage

    fake_search["assets"] = [_asset("foto", "2024-07-02T10:00:00")]
    link_batch(db, immich_user)
    linked = db.query(MediaRef).all()
    assert len(linked) == 1
    assert linked[0].event_id != trip.id      # hängt an einem Tag, nicht an der Reise


def test_multi_day_trip_without_children_still_gets_photos(db, immich_user, fake_search):
    """Ohne Tages-Kinder bekommt die Reise als Ganzes ihre Fotos."""
    trip = _event(db, immich_user, when=datetime(2024, 7, 1),
                  end=datetime(2024, 7, 3), precision=DatePrecision.day)
    fake_search["assets"] = [_asset("foto", "2024-07-02T10:00:00")]

    link_batch(db, immich_user)

    assert db.query(MediaRef).one().event_id == trip.id


def test_transient_errors_are_retried(monkeypatch):
    """Ein 502/503/504 vom Reverse-Proxy ist vorübergehend — einmal warten und
    erneut versuchen, statt den ganzen Foto-Lauf abzubrechen.

    Gezählt wird jetzt der ERSTE Pfad und nicht mehr alle Aufrufe: `check()`
    prüft seit Anmerkung 113 jedes Recht einzeln, macht also mehrere Aufrufe.
    Die Wiederholung gilt aber weiterhin je Aufruf, und genau das steht hier.
    """
    import urllib.error

    from app.services import immich as api

    monkeypatch.setattr(api.time, "sleep", lambda *_: None, raising=False)
    seen: list[str] = []

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"version":"1.0"}'

    def _open(req, timeout=0):
        seen.append(req.full_url)
        if len(seen) == 1:
            raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, None)
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _open)
    result = api.check("https://immich.example.org", "key")
    assert result["version"] == "1.0"
    # Zweimal derselbe Pfad: erst 502, dann Erfolg.
    assert seen[:2] == [seen[0], seen[0]] and seen[0].endswith("/server/about")


def test_immich_job_terminates_on_photoless_events(db, immich_user, fake_search):
    """Regression: Ereignisse ohne passende Fotos bleiben Kandidaten. Der alte
    Runner nahm im Kreis dieselben ersten 25 — Endlosschleife ohne Fortschritt
    und ohne Fehlermeldung. Der neue prüft jedes Ereignis genau einmal."""
    from app.models import Job
    from app.routers.jobs import _run_immich

    # Fünf datierte Ereignisse, für die Immich NICHTS liefert
    for i in range(5):
        _event(db, immich_user, when=datetime(2024, 3, i + 1, 12, 0))
    fake_search["assets"] = []

    job = Job(user_id=immich_user.id, type="immich", status="running")
    db.add(job)
    db.commit()

    status, msg = _run_immich(db, job)      # muss zurückkehren, nicht hängen

    assert status == "done"
    assert "5" in msg                        # 5 Ereignisse geprüft
    assert db.query(MediaRef).count() == 0   # nichts verknüpft (kein Foto)


def test_same_photo_is_linked_only_once_across_events(db, immich_user, fake_search):
    """Regression (Nutzer-Bericht): Timeline-Import mit vielen Besuchen am
    selben Tag. Ein GPS-loses Foto wurde an JEDEN Besuch des Tages gehängt.
    Jetzt: genau einmal, am ersten passenden Ereignis."""
    from app.models import Job
    from app.routers.jobs import _run_immich

    # Fünf Besuche am selben Tag, je eigener Ort — wie ein Städtetag
    for i in range(5):
        _event(db, immich_user, when=datetime(2024, 5, 1, 9 + i, 0),
               loc=_loc(db, immich_user, f"Ort {i}", 51.0 + i * 0.01, 8.0))
    fake_search["assets"] = [_asset("ein-foto", "2024-05-01T12:00:00")]  # ohne GPS

    job = Job(user_id=immich_user.id, type="immich", status="running")
    db.add(job)
    db.commit()
    _run_immich(db, job)

    refs = db.query(MediaRef).filter(MediaRef.external_id == "ein-foto").all()
    assert len(refs) == 1        # NICHT fünfmal


def test_rerun_does_not_duplicate_existing_links(db, immich_user, fake_search):
    """Ein zweiter Lauf verknüpft ein bereits hängendes Foto nicht erneut."""
    from app.models import Job
    from app.routers.jobs import _run_immich

    _event(db, immich_user, when=datetime(2024, 5, 1, 12, 0))
    fake_search["assets"] = [_asset("foto", "2024-05-01T12:00:00")]

    for _ in range(2):
        job = Job(user_id=immich_user.id, type="immich", status="running")
        db.add(job)
        db.commit()
        _run_immich(db, job)

    assert db.query(MediaRef).filter(MediaRef.external_id == "foto").count() == 1


def test_immich_job_reports_missing_config(db, user):
    """Ohne eingerichtetes Immich stoppt der Job MIT Meldung — nicht stumm."""
    from app.models import Job
    from app.routers.jobs import _run_immich

    job = Job(user_id=user.id, type="immich", status="running")
    db.add(job)
    db.commit()
    status, msg = _run_immich(db, job)
    assert status == "stopped"
    assert "eingerichtet" in msg


def test_persistent_errors_still_fail(monkeypatch):
    import urllib.error

    from app.services import immich as api

    monkeypatch.setattr(api.time, "sleep", lambda *_: None, raising=False)

    def _open(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _open)
    with pytest.raises(api.ImmichError):
        api.check("https://immich.example.org", "key")


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


# --------------------------------------------------------------------------- #
# Anmerkung 106 — importierte Besuche bekommen ihre Fotos über den TAG
#
# Gemessen an einem nachgebauten Tag (25.05., zehn Besuche, drei Orte): Ein
# Foto landete beim ERSTEN Besuch, dessen ±6-Stunden-Fenster es erwischte, und
# „erster" war die Reihenfolge einer Abfrage ohne ORDER BY. Der Ort unterschied
# nichts — drei Orte einer Stadt liegen alle im 25-km-Umkreis. Dazu zeigt der
# verdichtete Zeitstrahl den Vertreter `min(id)`, bei UUIDs also fast nie
# denselben: vier Fotos verknüpft, null sichtbar.
# --------------------------------------------------------------------------- #
def _visit(db, user, *, hour, loc, day=25) -> Event:
    e = Event(user_id=user.id, title=f"Besuch: {loc.name}",
              date_start=datetime(2024, 5, day, hour, 0),
              date_end=datetime(2024, 5, day, hour, 45),
              date_precision=DatePrecision.exact, category="event",
              confirmed=ConfirmState.confirmed, source=Source.google_timeline,
              location=loc)
    db.add(e)
    db.commit()
    return e


@pytest.fixture()
def besuchstag(db, immich_user):
    """Zehn importierte Besuche an drei Orten, alle am 25.05."""
    orte = [_loc(db, immich_user, n, lat, lng) for n, lat, lng in
            [("Kaiserstraße", 51.22, 6.77), ("Hofgarten", 51.24, 6.78),
             ("Medienhafen", 51.21, 6.75)]]
    return [_visit(db, immich_user, hour=h, loc=orte[i % 3])
            for i, h in enumerate([8, 9, 10, 11, 13, 14, 15, 17, 19, 21])]


def test_importierte_besuche_sind_keine_ereignis_kandidaten(db, immich_user, besuchstag):
    assert candidates(db, immich_user.id) == []


def test_der_tag_ist_das_ziel(db, immich_user, besuchstag, fake_search):
    from app.services.immich_link import link_batch

    fake_search["assets"] = [_asset(f"a{i}", f"2024-05-25T{h:02d}:30:00", 51.23, 6.78)
                             for i, h in enumerate([9, 12, 16, 20])]

    processed, linked, remaining = link_batch(db, immich_user)

    assert (processed, linked, remaining) == (1, 4, 0), "ein Ziel: der Tag"
    refs = db.query(MediaRef).filter(MediaRef.provider == "immich").all()
    assert len(refs) == 4
    assert all(r.event_id is None for r in refs), "hängt an keinem Besuch mehr"
    assert {r.captured_at.date() for r in refs} == {datetime(2024, 5, 25).date()}
    assert all(r.user_id == immich_user.id for r in refs)


def test_ein_echtes_ereignis_desselben_tages_geht_vor(db, immich_user, besuchstag,
                                                      fake_search):
    """Ein selbst erfasstes Ereignis ist eine Aussage darüber, was der Tag war —
    sein engeres Fenster bekommt seine Fotos, der Tag sammelt den Rest auf."""
    from app.services.immich_link import link_batch

    konzert = _event(db, immich_user, when=datetime(2024, 5, 25, 20, 0),
                     precision=DatePrecision.exact,
                     loc=_loc(db, immich_user, "Halle", 51.22, 6.78))
    fake_search["assets"] = [
        _asset("morgens", "2024-05-25T09:30:00", 51.23, 6.78),
        _asset("konzert", "2024-05-25T20:30:00", 51.22, 6.78),
    ]

    link_batch(db, immich_user)

    am_konzert = [m.external_id for m in konzert.media]
    am_tag = [m.external_id for m in db.query(MediaRef)
              .filter(MediaRef.event_id.is_(None)).all()]
    assert am_konzert == ["konzert"]
    assert am_tag == ["morgens"]


def test_zweiter_lauf_verdoppelt_nichts(db, immich_user, besuchstag, fake_search):
    from app.services.immich_link import link_batch

    fake_search["assets"] = [_asset("a0", "2024-05-25T12:00:00")]
    link_batch(db, immich_user)
    processed, linked, _ = link_batch(db, immich_user)

    assert (processed, linked) == (0, 0), "der Tag ist erledigt und kein Ziel mehr"
    assert db.query(MediaRef).count() == 1


def test_der_tag_filtert_nicht_nach_ort(db, immich_user, besuchstag, fake_search):
    """Bewusst kein Orts-Abgleich: der Tag ist ein Behälter der ZEITachse
    (Anmerkung 87). Wer abends 500 km weiter fotografiert, hat trotzdem ein
    Foto von diesem Tag — und sonst hätte es gar keinen Platz."""
    from app.services.immich_link import link_batch

    fake_search["assets"] = [_asset("weit_weg", "2024-05-25T21:00:00", 48.13, 11.58)]
    _, linked, _ = link_batch(db, immich_user)

    assert linked == 1


def test_foto_ohne_zeitstempel_bekommt_keinen_tag(db, immich_user, besuchstag,
                                                  fake_search):
    """Ohne Aufnahmezeit gibt es keinen Kalendertag — und der Behälter IST das
    Datum. Ein Bild ohne Zeit hätte dort nur ein erfundenes."""
    from app.services.immich_link import link_day, linked_asset_ids

    ohne_zeit = {"id": "x", "originalMimeType": "image/jpeg", "exifInfo": {}}
    fake_search["assets"] = [ohne_zeit]
    n = link_day(db, immich_user, datetime(2024, 5, 25).date(), "u", "k",
                 linked_asset_ids(db, immich_user.id))

    assert n == 0


def test_bestandsverknuepfungen_an_besuchen_werden_geloest(db, immich_user,
                                                           besuchstag):
    """Ohne das behielten schon verknüpfte Fotos ihren willkürlichen Besuch,
    und `seen` erklärte sie als vergeben: die Korrektur käme nie an."""
    from app.services.immich_link import detach_visit_links

    besuch = besuchstag[0]
    db.add(MediaRef(user_id=immich_user.id, event_id=besuch.id,
                    provider="immich", external_id="alt"))
    eigenes = _event(db, immich_user, when=datetime(2024, 5, 25, 20, 0))
    db.add(MediaRef(user_id=immich_user.id, event_id=eigenes.id,
                    provider="immich", external_id="am-ereignis"))
    db.add(MediaRef(user_id=immich_user.id, event_id=besuch.id,
                    provider="local", external_id="hochgeladen.jpg"))
    db.commit()

    assert detach_visit_links(db, immich_user.id) == 1
    bleibt = {m.external_id for m in db.query(MediaRef).all()}
    assert bleibt == {"am-ereignis", "hochgeladen.jpg"}, \
        "Uploads und Ereignis-Verweise bleiben unangetastet"
    assert detach_visit_links(db, immich_user.id) == 0, "zweiter Lauf: Nulldurchlauf"
