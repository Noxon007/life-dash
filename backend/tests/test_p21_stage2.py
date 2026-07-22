"""P2.1 Stufe 2 (0.37.0) — Immich als Ereignis-Quelle.

Anmerkung 107 sagt, wo die Kosten liegen: **nicht im Clustern**, sondern in
jedem Fall, in dem Life-Dash den Tag schon kennt. Diese Datei prüft deshalb
vor allem die sieben Fälle und die drei Filter, die die gekippte
Unterdrückungsregel ersetzt haben — nicht die Frage, ob aus vier Fotos ein
Vorschlag wird.

Der Immich-Client wird über die Antwortformen ersetzt, die die **echte
OpenAPI-Spezifikation** vorgibt (`AssetResponseDto` mit `ownerId`/`visibility`/
`exifInfo`, `AlbumResponseDto`): Stufe 1 hatte gelernt, dass eine frei
erfundene Attrappe genau die Fehler durchwinkt, die der echte Server ablehnt.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Event, Fragment,
                        FragmentStatus, MediaRef, Source, User, UserRole)
from app.services import immich as api
from app.services import immich_source as source

MY_ID = "own-user-uuid"
OTHER_ID = "partner-user-uuid"
YEAR = 2024


def _asset(idx: int, *, hour: int = 10, day: int = 12, month: int = 7,
           lat: float = 51.93, lng: float = 8.87, city: str | None = "Detmold",
           owner: str = MY_ID, visibility: str = "timeline") -> dict:
    """Ein Asset in der Form, die `AssetResponseDto` vorschreibt."""
    return {
        "id": f"asset-{idx}",
        "ownerId": owner,
        "visibility": visibility,
        "originalMimeType": "image/jpeg",
        "fileCreatedAt": f"{YEAR}-{month:02d}-{day:02d}T{hour:02d}:00:00.000Z",
        "exifInfo": {
            "dateTimeOriginal": f"{YEAR}-{month:02d}-{day:02d}T{hour:02d}:00:00.000Z",
            "latitude": lat, "longitude": lng,
            "city": city, "state": "Nordrhein-Westfalen", "country": "Deutschland",
        },
    }


def _cluster_assets(n: int = 6, **kw) -> list[dict]:
    return [_asset(i, hour=10 + (i % 3), **kw) for i in range(n)]


@pytest.fixture()
def immich_cfg(user, db):
    user.settings = {"immich": {"url": "http://immich.local", "api_key": "k"}}
    db.commit()
    return user


@pytest.fixture()
def fake_api(monkeypatch):
    """Ersetzt die vier Immich-Aufrufe. Gibt einen Steuerstand zurück."""
    state = {"assets": [], "albums": [], "album_assets": {}, "me": MY_ID,
             "asset_calls": []}

    monkeypatch.setattr(api, "own_user_id", lambda url, key: state["me"])
    monkeypatch.setattr(api, "albums",
                        lambda url, key, owned=None: [
                            a for a in state["albums"]
                            if owned is None or bool(a.get("_owned")) == owned])

    def _search(url, key, start, end, *, album_id=None, heartbeat=None,
                max_items=20000):
        state["asset_calls"].append((start, end, album_id))
        # Der Herzschlag wird auch hier durchgereicht: ein Doppel, das ihn
        # verschluckt, würde die Abbruch-Prüfung unbemerkt aushebeln.
        if heartbeat is not None and heartbeat() is False:
            raise api.ScanAborted("Lauf gestoppt")
        if album_id:
            return [a for a in state["album_assets"].get(album_id, [])
                    if start <= api.asset_time(a) <= end]
        return [a for a in state["assets"]
                if start <= api.asset_time(a) <= end]

    monkeypatch.setattr(api, "search_assets_paged", _search)
    return state


# --------------------------------------------------------------------------- #
# Identität: der PLATZ, nicht der Inhalt
# --------------------------------------------------------------------------- #
def test_slot_is_stable_when_photos_are_added(db, user, immich_cfg, fake_api):
    """Der Kern von Anmerkung 107: ein nachgeladenes Foto darf denselben Tag
    nicht zu einem zweiten Vorschlag machen. Ein Hash über die Asset-IDs täte
    genau das."""
    fake_api["assets"] = _cluster_assets(6)
    first = source.scan_year(db, user, YEAR, "u", "k")
    assert len(first) == 1
    slot_before = first[0].slot

    fake_api["assets"] = _cluster_assets(9)          # drei Fotos mehr
    again = source.scan_year(db, user, YEAR, "u", "k")
    assert again[0].slot == slot_before


def test_slot_fits_the_column(db):
    """`Event.external_id` ist String(64). Ein Ortsname, der darüber
    hinausschießt, würde beim Schreiben abgeschnitten — und der Platz wäre
    beim nächsten Lauf ein anderer als der gespeicherte."""
    long_place = "Sankt Maria im Wunderschönen Tal an der Oberen Donau" * 2
    slot = source.slot_day(date(2024, 7, 12), long_place)
    assert len(slot) <= 64
    # Deterministisch: zweimal dasselbe, sonst wäre es kein Platz.
    assert slot == source.slot_day(date(2024, 7, 12), long_place)


# --------------------------------------------------------------------------- #
# Die drei Filter, die die gekippte Unterdrückungsregel ersetzen (Fall 7)
# --------------------------------------------------------------------------- #
def test_foreign_photos_never_form_a_cluster(db, user, immich_cfg, fake_api):
    """Die eigentliche Gefahr sind geteilte Alben, nicht Screenshots: fremde
    Urlaubsfotos HABEN GPS und erfänden sonst still einen eigenen Tag."""
    fake_api["assets"] = _cluster_assets(8, owner=OTHER_ID)
    assert source.scan_year(db, user, YEAR, "u", "k") == []


def test_photos_without_coordinates_form_no_cluster(db, user, immich_cfg, fake_api):
    """Weitergeleitete Bilder, Screenshots, Downloads: kein EXIF-GPS, also
    kein erfundener Ort. Sie bleiben Anreicherung am Tag."""
    fake_api["assets"] = _cluster_assets(8, lat=None, lng=None, city=None)
    assert source.scan_year(db, user, YEAR, "u", "k") == []


def test_archived_and_locked_photos_form_no_cluster(db, user, immich_cfg, fake_api):
    """Was im Archiv oder im gesperrten Ordner liegt, hat der Nutzer bewusst
    aus seinem Zeitstrahl genommen. Ein Vorschlag daraus wäre ein
    Vertrauensbruch — `visibility` steht in der Spezifikation, also wird es
    gelesen."""
    fake_api["assets"] = _cluster_assets(8, visibility="archive")
    assert source.scan_year(db, user, YEAR, "u", "k") == []
    fake_api["assets"] = _cluster_assets(8, visibility="locked")
    assert source.scan_year(db, user, YEAR, "u", "k") == []


def test_without_own_user_id_nothing_is_clustered(db, user, immich_cfg, fake_api):
    """Kennt Immich die eigene Nutzerkennung nicht, ist „eigen oder fremd?"
    unbeantwortbar. Dann lieber nichts vorschlagen als im Unklaren einen
    fremden Tag behaupten."""
    fake_api["me"] = None
    fake_api["assets"] = _cluster_assets(8)
    assert source.scan_year(db, user, YEAR, "u", "k") == []


# --------------------------------------------------------------------------- #
# Die sieben Fälle
# --------------------------------------------------------------------------- #
def test_case1_day_whose_photos_already_have_a_home(db, user, immich_cfg, fake_api):
    """Fall (1): Es geht nicht um „gibt es an dem Tag ein Ereignis?", sondern
    darum, dass die Fotos schon ein Zuhause haben."""
    fake_api["assets"] = _cluster_assets(6)
    ev = Event(user_id=user.id, title="Konzert", category="concert",
               date_start=datetime(YEAR, 7, 12, 20), date_end=datetime(YEAR, 7, 12, 23),
               date_precision=DatePrecision.exact, source=Source.manual,
               confirmed=ConfirmState.confirmed)
    db.add(ev)
    db.commit()
    # Noch kein Foto am Ereignis -> der Tag ist offen, der Vorschlag kommt.
    assert len(source.scan_year(db, user, YEAR, "u", "k")) == 1

    db.add(MediaRef(user_id=user.id, event_id=ev.id, provider="immich",
                    external_id="asset-0"))
    db.commit()
    assert source.scan_year(db, user, YEAR, "u", "k") == []


def test_case2_a_rejected_proposal_never_returns(db, user, immich_cfg, fake_api):
    """Fall (2), der wichtigste. `discard_event` LÖSCHT das Ereignis — ohne
    Grabstein käme derselbe Vorschlag beim nächsten Lauf wieder, und das
    Ablehnen wäre eine Sisyphosarbeit. Vierte Auflage derselben Falle nach
    F12, A39 und A42."""
    from app.routers.moderation import discard_event

    fake_api["assets"] = _cluster_assets(6)
    props = source.scan_year(db, user, YEAR, "u", "k")
    source.create_proposals(db, user, props)
    db.commit()

    created = db.query(Event).filter(Event.source == Source.immich).one()
    discard_event(created.id, db=db, user=user)

    assert db.query(Event).filter(Event.source == Source.immich).count() == 0
    # Das Fragment lebt — es IST der Grabstein.
    assert db.query(Fragment).filter(Fragment.source == Source.immich).count() == 1
    assert source.scan_year(db, user, YEAR, "u", "k") == []


def test_case3_confirmed_then_renamed_is_recognised(db, user, immich_cfg, fake_api):
    """Fall (3): bestätigt und dann umbenannt/umdatiert — der Platz erkennt
    es wieder, und ab da wird es nicht mehr angefasst."""
    fake_api["assets"] = _cluster_assets(6)
    source.create_proposals(db, user, source.scan_year(db, user, YEAR, "u", "k"))
    db.commit()

    ev = db.query(Event).filter(Event.source == Source.immich).one()
    ev.title = "Sommerfest bei Anke"
    ev.date_start = datetime(YEAR, 7, 12, 18)
    ev.confirmed = ConfirmState.confirmed
    db.commit()

    assert source.scan_year(db, user, YEAR, "u", "k") == []
    ev2 = db.query(Event).filter(Event.source == Source.immich).one()
    assert ev2.title == "Sommerfest bei Anke"      # unangetastet


def test_case4_a_grown_album_gets_no_second_proposal(db, user, immich_cfg, fake_api):
    fake_api["albums"] = [{"id": "alb-1", "albumName": "Dänemark 2024",
                           "assetCount": 5, "shared": False, "_owned": True}]
    fake_api["album_assets"]["alb-1"] = _cluster_assets(5, month=8, day=3)
    props = source.scan_year(db, user, YEAR, "u", "k")
    assert len(props) == 1 and props[0].kind == "album"
    source.create_proposals(db, user, props)
    db.commit()

    fake_api["album_assets"]["alb-1"] = _cluster_assets(20, month=8, day=3)
    assert source.scan_year(db, user, YEAR, "u", "k") == []


def test_case5_album_beats_a_cluster_in_its_span(db, user, immich_cfg, fake_api):
    """Fall (5): „Dänemark 2024" sagt mehr über den 3. August als „5 Fotos in
    Detmold" — und beides nebeneinander wäre derselbe Tag zweimal."""
    assets = _cluster_assets(6, month=8, day=3)
    fake_api["assets"] = assets
    fake_api["albums"] = [{"id": "alb-1", "albumName": "Dänemark 2024",
                           "assetCount": 6, "shared": False, "_owned": True}]
    fake_api["album_assets"]["alb-1"] = assets

    props = source.scan_year(db, user, YEAR, "u", "k")
    assert [p.kind for p in props] == ["album"]


def test_case6_photos_are_shown_not_moved(db, user, immich_cfg, fake_api):
    """Fall (6): Ein Vorschlag ZEIGT die Fotos seines Fensters, besitzt sie
    aber nicht. Erst das Bestätigen hängt sie um — deshalb hat eine Ablehnung
    nichts rückgängig zu machen."""
    fake_api["assets"] = _cluster_assets(6)
    # Die Bilder hängen am TAG (F18/Anmerkung 106).
    for i in range(6):
        db.add(MediaRef(user_id=user.id, event_id=None, provider="immich",
                        external_id=f"asset-{i}",
                        captured_at=datetime(YEAR, 7, 12, 10)))
    db.commit()

    source.create_proposals(db, user, source.scan_year(db, user, YEAR, "u", "k"))
    db.commit()

    still_on_day = (db.query(MediaRef)
                    .filter(MediaRef.user_id == user.id,
                            MediaRef.event_id.is_(None)).count())
    assert still_on_day == 6


def test_case7_a_day_of_google_visits_still_gets_a_proposal(db, user, immich_cfg,
                                                            fake_api):
    """Fall (7), vom Autor umgedreht: Foto-GPS ist ein Beleg, ein
    Google-Besuch eine Vermutung. Der Vorschlag ist also kein Duplikat,
    sondern die genauere Zeile."""
    fake_api["assets"] = _cluster_assets(6)
    for hour in (9, 11, 13):
        db.add(Event(user_id=user.id, title=f"Besuch: Straße {hour}",
                     category="event", date_start=datetime(YEAR, 7, 12, hour),
                     date_end=datetime(YEAR, 7, 12, hour, 30),
                     date_precision=DatePrecision.exact,
                     source=Source.google_timeline,
                     confirmed=ConfirmState.confirmed))
    db.commit()

    props = source.scan_year(db, user, YEAR, "u", "k")
    assert len(props) == 1 and props[0].kind == "day"


# --------------------------------------------------------------------------- #
# Alben: geteilt ist erlaubt — und sagt es
# --------------------------------------------------------------------------- #
def test_shared_album_is_allowed_and_declares_itself(db, user, immich_cfg, fake_api):
    """Fall (7c): Ein Album ist ein von Menschen benannter Behälter, also ist
    der Behälter der Beleg. Aber der Vorschlag muss SAGEN, dass die Bilder von
    jemand anderem stammen — sonst ist es eine stille Übernahme."""
    fake_api["albums"] = [{"id": "alb-2", "albumName": "Kreta mit Jan",
                           "assetCount": 9, "shared": True, "_owned": False}]
    fake_api["album_assets"]["alb-2"] = _cluster_assets(9, month=6, day=5,
                                                        owner=OTHER_ID)
    props = source.scan_year(db, user, YEAR, "u", "k")
    assert len(props) == 1
    assert props[0].shared is True

    source.create_proposals(db, user, props)
    db.commit()
    ev = db.query(Event).filter(Event.source == Source.immich).one()
    assert "geteilt" in (ev.description or "").lower()


def test_proposals_are_never_confirmed_automatically(db, user, immich_cfg, fake_api):
    """Anmerkung 30, die Zusage des ganzen Pakets."""
    fake_api["assets"] = _cluster_assets(6)
    fake_api["albums"] = [{"id": "alb-3", "albumName": "Wandern", "assetCount": 5,
                           "shared": False, "_owned": True}]
    fake_api["album_assets"]["alb-3"] = _cluster_assets(5, month=9, day=1)

    source.create_proposals(db, user, source.scan_year(db, user, YEAR, "u", "k"))
    db.commit()

    rows = db.query(Event).filter(Event.source == Source.immich).all()
    assert rows and all(e.confirmed == ConfirmState.unconfirmed for e in rows)


def test_preview_creates_nothing(db, user, immich_cfg, fake_api):
    """Das P2.5-Muster: erst sehen, dann anlegen. Eine Vorschau, die anlegt,
    ist keine."""
    from app.routers.immich import source_preview

    fake_api["assets"] = _cluster_assets(6)
    out = source_preview(year=YEAR, db=db, user=user)

    assert out["total"] == 1 and out["days"] == 1
    assert out["proposals"][0]["photos"] == 6
    assert db.query(Event).count() == 0
    assert db.query(Fragment).count() == 0


def test_a_run_asks_only_for_its_year(db, user, immich_cfg, fake_api):
    """Jahresweise ist der Sinn der Sache: eine zwanzig Jahre alte Bibliothek
    auf einmal wäre genau die Warteschlange, die niemand mehr durchsieht."""
    fake_api["assets"] = _cluster_assets(6)
    source.scan_year(db, user, YEAR, "u", "k")
    starts = {c[0].year for c in fake_api["asset_calls"]}
    ends = {c[1].year for c in fake_api["asset_calls"]}
    assert starts == {YEAR} and ends == {YEAR}


def test_precision_follows_the_spread_of_the_day(db, user, immich_cfg, fake_api):
    """Kap. 3.1: Genauigkeit nie überzeichnen. Vier Fotos in einer Stunde sind
    ein Zeitpunkt, über den ganzen Tag verteilt sind sie ein Tag."""
    fake_api["assets"] = [_asset(i, hour=14) for i in range(5)]
    tight = source.scan_year(db, user, YEAR, "u", "k")
    assert tight[0].precision == DatePrecision.exact

    fake_api["assets"] = [_asset(i, hour=8 + i * 3) for i in range(5)]
    wide = source.scan_year(db, user, YEAR, "u", "k")
    assert wide[0].precision == DatePrecision.day


def test_album_spans_whole_days(db, user, immich_cfg, fake_api):
    """Im Smoke-Lauf aufgefallen: ein Album, dessen Bilder alle aus einer
    Stunde stammen, behielt die Uhrzeiten und behauptete daneben `day`. Ein
    Album ist eine Spanne von TAGEN — eine Angabe, die ihre eigene Genauigkeit
    dementiert, ist schlimmer als eine grobe."""
    fake_api["albums"] = [{"id": "alb-9", "albumName": "Ein Nachmittag",
                           "assetCount": 5, "shared": False, "_owned": True}]
    fake_api["album_assets"]["alb-9"] = [_asset(i, hour=14, month=5, day=4)
                                         for i in range(5)]
    prop = source.scan_year(db, user, YEAR, "u", "k")[0]
    assert prop.precision == DatePrecision.day
    assert (prop.start.hour, prop.start.minute) == (0, 0)
    assert (prop.end.hour, prop.end.minute) == (23, 59)


def test_an_album_across_new_year_keeps_its_whole_span(db, user, immich_cfg,
                                                       fake_api):
    """Selbstkontrolle-Befund: Die Album-Assets wurden auf das LAUFJAHR
    eingegrenzt. Eine Silvesterreise (28.12.–3.1.) hätte im 2024er-Lauf einen
    Vorschlag über drei Tage statt sieben bekommen — und weil der Platz
    derselbe ist, hätte der 2023er-Lauf ihn stillschweigend übersprungen statt
    ihn zu vervollständigen. Das Jahr entscheidet, OB ein Album angeboten wird,
    nicht was drin ist."""
    silvester = ([_asset(i, month=12, day=28 + i) for i in range(3)]
                 + [_asset(10 + i, month=1, day=1 + i) for i in range(3)])
    # Die Dezember-Bilder gehören ins Vorjahr.
    for a in silvester[:3]:
        a["exifInfo"]["dateTimeOriginal"] = a["exifInfo"]["dateTimeOriginal"].replace(
            str(YEAR), str(YEAR - 1))
        a["fileCreatedAt"] = a["fileCreatedAt"].replace(str(YEAR), str(YEAR - 1))
    fake_api["albums"] = [{"id": "alb-ny", "albumName": "Silvester in Kopenhagen",
                           "assetCount": 6, "shared": False, "_owned": True,
                           "startDate": f"{YEAR - 1}-12-28T00:00:00.000Z",
                           "endDate": f"{YEAR}-01-03T00:00:00.000Z"}]
    fake_api["album_assets"]["alb-ny"] = silvester

    prop = source.scan_year(db, user, YEAR, "u", "k")[0]
    assert prop.start.year == YEAR - 1 and prop.start.month == 12
    assert prop.end.year == YEAR and prop.end.month == 1
    assert prop.photos == 6


def test_wide_window_stamps_survive_dates_before_1970():
    """Selbstkontrolle-Befund aus dem SMOKE-Lauf, nicht aus den Unit-Tests —
    die ersetzen `search_assets_paged` komplett und kommen an `_stamp` nie
    vorbei. Die Album-Abfrage fragt bewusst ohne Zeitfenster (ab 1900), und
    `datetime.astimezone()` wirft unter Windows für alles vor der Epoche
    `OSError`. Fünf Releases lang hatte diese Funktion nie ein so altes Datum
    gesehen.

    Geprüft wird die ECHTE Funktion, samt der Zusage, die Stufe 1 teuer gelernt
    hat: Immich lehnt Zeitstempel ohne Zone mit 400 ab."""
    for when in (source._WIDE_START, source._WIDE_END, datetime(1955, 3, 2)):
        stamp = api._stamp(when)
        assert stamp.startswith(when.strftime("%Y-%m-%dT"))
        assert stamp[-6] in "+-" or stamp.endswith("Z"), f"ohne Zeitzone: {stamp}"


def test_same_place_name_in_two_countries_stays_two_places(db, user, immich_cfg,
                                                           fake_api):
    """Selbstkontrolle-Befund: Der Ortsschlüssel war der blanke Name. Zwei
    Springfields in zwei Ländern wären ein Ort geworden — der zweite Vorschlag
    läge auf den Koordinaten des ersten, also auf dem falschen Kontinent.
    Anmerkung 105 hat genau diesen Schlüssel als „(Stadt, Land)" benannt und
    für den Altbestand liegen gelassen; hier wird er neu vergeben."""
    from app.models import Location

    us = _cluster_assets(5, city="Springfield", lat=39.8, lng=-89.6)
    for a in us:
        a["exifInfo"]["country"] = "United States"
    fake_api["assets"] = us
    source.create_proposals(db, user, source.scan_year(db, user, YEAR, "u", "k"))
    db.commit()

    uk = _cluster_assets(5, day=14, city="Springfield", lat=51.5, lng=-0.1)
    for i, a in enumerate(uk):
        a["id"] = f"uk-{i}"
        a["exifInfo"]["country"] = "United Kingdom"
    fake_api["assets"] = uk
    source.create_proposals(db, user, source.scan_year(db, user, YEAR, "u", "k"))
    db.commit()

    places = db.query(Location).filter(Location.name == "Springfield").all()
    assert len(places) == 2, "beide Springfields wurden zu einem Ort"
    assert {round(p.lng) for p in places} == {-90, 0}


def test_a_long_scan_keeps_the_job_alive(db, user, immich_cfg, fake_api):
    """Selbstkontrolle-Befund: `scan_year` lief komplett durch, BEVOR der Job
    seinen ersten Fortschritt meldete. Ein Job ohne Lebenszeichen gilt nach
    drei Minuten als verwaist (`STALE_SECONDS`) — und genau die Bibliothek,
    für die dieses Paket gebaut ist, blättert länger. Der Lauf hätte die ganze
    Arbeit gemacht und danach „gestoppt" gemeldet."""
    beats = []
    fake_api["assets"] = _cluster_assets(6)
    fake_api["albums"] = [{"id": "alb-x", "albumName": "Wandern", "assetCount": 4,
                           "shared": False, "_owned": True}]
    fake_api["album_assets"]["alb-x"] = _cluster_assets(4, month=9, day=2)

    source.scan_year(db, user, YEAR, "u", "k",
                     heartbeat=lambda: beats.append(1) or True)
    assert beats, "kein Lebenszeichen während des Scans"


def test_a_stopped_job_creates_nothing_from_half_a_scan(db, user, immich_cfg,
                                                        fake_api):
    """Abbrechen heißt abbrechen. „Gib zurück, was du hast" wäre schlimmer als
    der Abbruch: eine halb geladene Albumspanne sähe aus wie eine vollständige
    und stünde als Datum in einem Vorschlag."""
    fake_api["assets"] = _cluster_assets(6)
    with pytest.raises(api.ScanAborted):
        source.scan_year(db, user, YEAR, "u", "k", heartbeat=lambda: False)
    assert db.query(Event).count() == 0


def test_year_list_asks_immich_not_only_our_own_data(db, user, immich_cfg,
                                                     monkeypatch):
    """Im Smoke-Lauf aufgefallen: die Jahresauswahl kam aus dem EIGENEN
    Bestand — und war damit bei einer frischen Instanz „nur dieses Jahr".
    Anmerkung 107 nennt aber gerade die Jahre ohne eigene Daten als die
    wertvollsten (die Zeit vor dem Smartphone). Wer die nicht anbietet,
    versteckt die halbe Funktion."""
    from app.routers.immich import source_years

    monkeypatch.setattr(api, "own_user_id", lambda url, key: MY_ID)
    monkeypatch.setattr(api, "photo_years",
                        lambda url, key, my_id: {2004: 412, 2024: 6})
    out = source_years(db=db, user=user)

    assert out["source"] == "immich"
    assert [y["year"] for y in out["years"]] == [2024, 2004]
    assert dict((y["year"], y["photos"]) for y in out["years"])[2004] == 412


def test_year_list_falls_back_on_an_older_immich(db, user, immich_cfg, monkeypatch):
    """`/timeline/buckets` gibt es nicht ewig rückwärts. Ein 404 darf die
    Auswahl nicht leeren — eine magere Liste ist bedienbar, ein leeres Feld
    nicht."""
    from app.routers.immich import source_years

    monkeypatch.setattr(api, "own_user_id", lambda url, key: MY_ID)

    def _boom(url, key, my_id):
        raise api.ImmichError("Immich kennt /timeline/buckets nicht (404)")

    monkeypatch.setattr(api, "photo_years", _boom)
    out = source_years(db=db, user=user)
    assert out["source"] == "own"
    assert out["years"]      # nie leer: mindestens das laufende Jahr


def test_other_users_proposals_stay_invisible(db, user, immich_cfg, fake_api):
    """A12: in JEDER Abfrage. Der Grabstein eines anderen Nutzers darf meinen
    Vorschlag nicht unterdrücken — und umgekehrt."""
    other = User(oidc_subject="other", email="o@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    db.add(Fragment(user_id=other.id, source=Source.immich,
                    status=FragmentStatus.processed,
                    raw_text='{"type":"immich_source","slot":"%s"}'
                             % source.slot_day(date(YEAR, 7, 12), "Detmold")))
    db.commit()

    fake_api["assets"] = _cluster_assets(6)
    assert len(source.scan_year(db, user, YEAR, "u", "k")) == 1
