"""Anmerkung 139 — ein verortetes Foto ist EIN bestätigtes Ereignis.

Diese Datei ersetzt `test_a45_photo_points.py`. Sie prüft nicht dieselben
Zusagen an einer neuen Tabelle, sondern die Zusagen, die durch das Auflösen der
Tabelle überhaupt erst entstehen — und die man dem Ergebnis nicht ansieht:

* **Ein Foto, ein Ereignis** — keine Mindestzahl mehr, sofort bestätigt.
* **Der Ort wird über die KOORDINATE entdoppelt.** Je Stadt wäre der gemeldete
  A45-Defekt („London, 1200 Bilder" = ein Punkt), je Foto wären 20.000
  Ortszeilen für Aufnahmen vom identischen GPS-Fix.
* **Diese Orte fragen nie bei Nominatim nach** — sie tragen die Marke, an der
  der Rückfüll-Lauf sie stehen lässt. Ohne sie wären es 20.000 gedrosselte
  Abrufe für eine Auskunft, die schon vorliegt.
* **Der Grabstein** — ein gelöschtes Foto-Ereignis kommt nicht wieder.
* **Zurücksetzen** nimmt die Grabsteine MIT, Löschen nicht. Zwei verschiedene
  Absichten, zwei verschiedene Antworten.
* **Der Zeitstrahl bekommt kein Bild**, die Karte schon — beides hängt an
  derselben Asset-Kennung, die im Platz steht.
* Die drei Filter aus Anmerkung 107 gelten unverändert.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import (ConfirmState, DatePrecision, Entity, Event,
                        EventEntityLink, Fragment, Location, MediaRef, Metric,
                        Source, User, UserRole)
from app.services import immich as api
from app.services import photo_points as pp

MY_ID = "own-user-uuid"
OTHER_ID = "partner-user-uuid"
YEAR = 2024


def _asset(idx: int, *, hour: int = 10, minute: int = 0, day: int = 12,
           month: int = 7, lat: float | None = 51.93, lng: float | None = 8.87,
           city: str | None = "Detmold", state: str | None = "Nordrhein-Westfalen",
           country: str | None = "Deutschland",
           owner: str = MY_ID, visibility: str = "timeline") -> dict:
    stamp = f"{YEAR}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00.000Z"
    exif = {"dateTimeOriginal": stamp, "city": city, "state": state,
            "country": country}
    if lat is not None:
        exif["latitude"] = lat
    if lng is not None:
        exif["longitude"] = lng
    return {"id": f"asset-{idx}", "ownerId": owner, "visibility": visibility,
            "originalMimeType": "image/jpeg", "localDateTime": stamp,
            "exifInfo": exif}


def _props(assets, db=None, user=None, known=None, report=None):
    districts = pp.district_index(db, user.id) if db is not None else []
    return pp.photo_proposals(assets, MY_ID, districts, known, report)


# --------------------------------------------------------------------------- #
# Ein Foto, ein Ereignis
# --------------------------------------------------------------------------- #
def test_one_photo_is_enough(db, user):
    """Kein `MIN_CLUSTER_PHOTOS` mehr (Anmerkung 139).

    Bis 0.39 brauchte ein Tag vier Fotos, um ein Ereignis zu werden. Die Zahl
    war die letzte Bremse vor der Lebensdatenbank, nachdem Anmerkung 138 die
    Moderation abgeschafft hatte. Sie fällt hier bewusst: ein einzelnes Foto
    ist genauso viel Beleg dafür, dort gewesen zu sein, wie vier — die Bremse
    ist stattdessen die Pflicht-Vorschau.
    """
    created = pp.create_photo_events(db, user, _props([_asset(1)], db, user))
    db.commit()
    assert created == 1
    e = db.query(Event).one()
    assert e.confirmed == ConfirmState.confirmed
    assert e.confirmed_by == "import"
    assert e.source == Source.immich
    assert e.external_id == "immich:photo:asset-1"
    assert e.date_precision == DatePrecision.exact


def test_the_timeline_gets_text_and_the_map_gets_the_picture(db, user):
    """Der Titel nennt den ORT, das Bild hängt an der Asset-Kennung.

    Anmerkung 139 trennt das ausdrücklich: die Karte ist der Platz für das
    BILD, der Zeitstrahl der für die TATSACHE. Beides aus derselben Zeile —
    aber der Weg zum Bild führt über den Platz, nicht über einen `MediaRef`.
    """
    pp.create_photo_events(db, user, _props([_asset(1)], db, user))
    db.commit()
    e = db.query(Event).one()
    assert "Detmold" in e.title
    assert pp.asset_of(e.external_id) == "asset-1"
    # Kein Medien-Verweis: die Zwölfer-Deckelung von `MediaRef` beantwortet eine
    # andere Frage, und zwei Fragen mit zwei Deckelungen teilen sich keine
    # Tabelle (A45/Anmerkung 116).
    assert e.media == []


def test_asset_of_says_no_for_everything_else():
    """`null` ist die richtige Antwort, kein leerer String.

    Ein leerer String sähe aus wie eine Kennung und ergäbe im Browser die
    Bild-URL `/api/photos//thumb` — eine 404 je Google-Besuch auf der Karte.
    """
    assert pp.asset_of(None) is None
    assert pp.asset_of("immich:day:2024-07-12:Detmold") is None
    assert pp.asset_of("gtl:abcdef") is None
    assert pp.asset_of("immich:photo:") is None


# --------------------------------------------------------------------------- #
# Der Ort — die Frage, an der A45 hing
# --------------------------------------------------------------------------- #
def test_a_city_is_not_one_point(db, user):
    """Der gemeldete A45-Defekt darf nicht zurückkommen.

    „London, 1200 Bilder" war EIN Kartenpunkt, weil der Ort die Stadt war. Drei
    Fotos an drei Stellen sind drei Orte — auch wenn `exifInfo` für alle drei
    dieselbe Stadt nennt.
    """
    assets = [_asset(1, lat=51.500, lng=-0.120, city="London"),
              _asset(2, lat=51.510, lng=-0.140, city="London"),
              _asset(3, lat=51.520, lng=-0.100, city="London")]
    pp.create_photo_events(db, user, _props(assets, db, user))
    db.commit()
    locs = db.query(Location).filter(Location.type == "photo").all()
    assert len(locs) == 3, "eine Stadt darf nicht auf einen Punkt fallen"
    assert {round(loc.lat, 3) for loc in locs} == {51.500, 51.510, 51.520}


def test_the_same_fix_is_one_place(db, user):
    """…und dieselbe Koordinate ist EIN Ort.

    Die Gegenrichtung, und ohne sie wären es 20.000 Ortszeilen: eine
    Serienaufnahme teilt sich einen GPS-Fix, und drei Zeilen mit identischen
    Koordinaten sind drei Zeilen über dieselbe Sache.
    """
    assets = [_asset(i, minute=i) for i in range(1, 6)]   # gleiche lat/lng
    pp.create_photo_events(db, user, _props(assets, db, user))
    db.commit()
    assert db.query(Event).count() == 5
    assert db.query(Location).filter(Location.type == "photo").count() == 1


def test_a_second_run_reuses_the_place(db, user):
    """Über zwei Läufe hinweg gilt dasselbe — sonst wächst der Ortsbestand
    bei jedem Lauf um dieselben Punkte."""
    pp.create_photo_events(db, user, _props([_asset(1)], db, user))
    db.commit()
    pp.create_photo_events(db, user, _props([_asset(2)], db, user))
    db.commit()
    assert db.query(Location).filter(Location.type == "photo").count() == 1


def test_photo_places_are_marked_as_looked_up(db, user):
    """**Die Marke gegen die Endlos-Abruf-Falle**, neunte Auflage.

    `Location.address IS NULL` heißt „nie nachgesehen" (A47). Bliebe sie bei
    diesen Zeilen leer, hielte der Rückfüll-Lauf 20.000 Foto-Orte für
    unaufgelöst und schickte gedrosselte Nominatim-Abrufe hinterher — bei
    1,2 s je Ort knapp sieben Stunden für eine Auskunft, die Immich längst
    mitgeliefert hat. Und beim nächsten Lauf wieder.
    """
    pp.create_photo_events(db, user, _props([_asset(1)], db, user))
    db.commit()
    loc = db.query(Location).filter(Location.type == "photo").one()
    assert loc.address is not None, "sonst fragt der Rückfüll-Lauf sie ewig neu"
    assert loc.city == "Detmold"
    assert loc.country == "Deutschland"


def test_a_photo_without_a_city_still_gets_a_place(db, user):
    """Ohne Ortsangabe bleibt die Koordinate — und die ist der Punkt.

    Ein Foto in der Wildnis trägt kein `exifInfo.city`. Es deshalb wegzulassen
    hieße, ausgerechnet die Orte zu verlieren, an denen sonst nichts steht.
    """
    pp.create_photo_events(
        db, user, _props([_asset(1, city=None, state=None, country=None)], db, user))
    db.commit()
    loc = db.query(Location).filter(Location.type == "photo").one()
    assert loc.lat and loc.lng
    assert loc.address is not None


# --------------------------------------------------------------------------- #
# Die drei Filter aus Anmerkung 107
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad,reason", [
    (dict(owner=OTHER_ID), "foreign"),
    (dict(visibility="archive"), "hidden"),
    (dict(lat=None, lng=None), "no_geo"),
])
def test_the_three_filters_hold(db, user, bad, reason):
    """Fremd, versteckt, ohne Koordinaten — jeder Grund EINZELN gezählt.

    Verodert ließe sich nicht mehr sagen, welcher zugeschlagen hat, und genau
    das ist die Frage, die man beim Lesen des Protokolls stellt (Anm. 120).
    """
    report: dict = {}
    props = _props([_asset(1, **bad)], db, user, report=report)
    assert props == []
    assert report["dropped"][reason] == 1
    assert sum(report["dropped"].values()) == 1, "ein Ausschluss, nicht zwei"


def test_reasons_are_readable_and_biggest_first():
    report = {"dropped": {"foreign": 2, "no_geo": 9, "hidden": 0}}
    lines = pp.drop_reasons(report)
    assert "9" in lines[0] and "Koordinaten" in lines[0]
    assert len(lines) == 2, "was null ist, wird nicht genannt"


# --------------------------------------------------------------------------- #
# Der Grabstein
# --------------------------------------------------------------------------- #
def test_a_deleted_photo_event_stays_deleted(db, user):
    """Eine bewusste Löschung darf der nächste Lauf nicht rückgängig machen.

    Das Löschen nimmt nur die Ereigniszeile mit; das Fragment bleibt und trägt
    den Platz. Gefragt werden deshalb BEIDE — Fragment und Ereignis.
    """
    pp.create_photo_events(db, user, _props([_asset(1)], db, user))
    db.commit()
    db.query(Event).delete()
    db.commit()

    known = pp.known_slots(db, user.id)
    assert "immich:photo:asset-1" in known
    report: dict = {}
    assert _props([_asset(1)], db, user, known, report) == []
    assert report["dropped"]["known"] == 1


def test_an_existing_event_is_not_created_twice(db, user):
    pp.create_photo_events(db, user, _props([_asset(1)], db, user))
    db.commit()
    known = pp.known_slots(db, user.id)
    assert _props([_asset(1), _asset(2)], db, user, known) == [
        p for p in _props([_asset(2)], db, user)]
    assert len(_props([_asset(1), _asset(2)], db, user, known)) == 1


def test_a_duplicate_inside_one_answer_counts_once(db, user):
    """Liefert Immich dasselbe Asset über eine Seitengrenze zweimal, wäre es
    sonst zweimal angelegt — der Grabstein käme zu spät."""
    assert len(_props([_asset(1), _asset(1)], db, user)) == 1


# --------------------------------------------------------------------------- #
# Zurücknehmen: zwei Absichten, zwei Antworten
# --------------------------------------------------------------------------- #
def test_reset_takes_the_tombstones_with_it(db, user):
    """**„Noch einmal von vorn" ist nicht „das will ich nicht sehen".**

    Blieben beim Zurücksetzen die Grabsteine stehen, fände der nächste Lauf
    jeden Platz vergeben und legte nichts an — der Knopf hätte dann alles
    gelöscht UND die Wiederherstellung unmöglich gemacht. Beim Löschen EINES
    Ereignisses gilt genau das Gegenteil (siehe Test darüber).
    """
    pp.create_photo_events(db, user, _props([_asset(1), _asset(2)], db, user))
    db.commit()
    assert pp.reset(db, user.id) == 2
    db.commit()
    assert db.query(Event).count() == 0
    assert db.query(Fragment).count() == 0
    assert pp.known_slots(db, user.id) == set()
    # Der Ort geht mit, sofern nichts mehr an ihm hängt.
    assert db.query(Location).filter(Location.type == "photo").count() == 0


def test_reset_leaves_places_that_are_still_in_use(db, user):
    """Ein Ort, an dem noch ein von Hand erfasstes Ereignis hängt, bleibt.

    Sonst risse das Zurücksetzen einer Ableitung Lebensdatenbank mit — das ist
    die Invariante aus Anmerkung 57, nur von der anderen Seite.
    """
    pp.create_photo_events(db, user, _props([_asset(1)], db, user))
    db.commit()
    loc = db.query(Location).filter(Location.type == "photo").one()
    db.add(Event(user_id=user.id, title="Konzert", category="concert",
                 date_start=datetime(YEAR, 7, 12, 20, 0),
                 date_precision=DatePrecision.exact, location=loc,
                 source=Source.manual, confirmed=ConfirmState.confirmed))
    db.commit()

    pp.reset(db, user.id)
    db.commit()
    assert db.query(Location).filter(Location.id == loc.id).count() == 1
    assert db.query(Event).count() == 1


def test_reset_leaves_other_accounts_alone(db, user):
    other = User(oidc_subject="other", email="o@example.org",
                 display_name="Andere", role=UserRole.user)
    db.add(other)
    db.commit()
    pp.create_photo_events(db, user, _props([_asset(1)], db, user))
    pp.create_photo_events(db, other, _props([_asset(2)], db, other))
    db.commit()
    assert pp.reset(db, other.id) == 1
    db.commit()
    assert db.query(Event).count() == 1
    assert db.query(Event).one().user_id == user.id


# --------------------------------------------------------------------------- #
# Der Aufräum-Lauf für die Tagescluster aus Anmerkung 138
# --------------------------------------------------------------------------- #
def _day_cluster(db, user, day: int = 12) -> Event:
    """Ein Tagescluster, **so wie er im Bestand wirklich steht.**

    Das Doppel hat diese Zeilen lange nackt nachgebaut — und genau daran ist
    die Prüfung vorbeigelaufen: ein Tagescluster ist bestätigt und verortet,
    also hat der Wetter-Lauf ihm Metriken angehängt, die KI eine Entity
    verknüpft und der Foto-Lauf Bilder. Ein Doppel, das ein Feld auslässt, ist
    keine Vereinfachung, sondern eine andere Funktion (Anmerkung 116).
    """
    frag = Fragment(user_id=user.id, raw_text='{"slot": "immich:day:x"}',
                    source=Source.immich)
    loc = Location(user_id=user.id, name="Detmold", lat=51.93, lng=8.87,
                   city="Detmold", country="Deutschland")
    db.add_all([frag, loc])
    db.flush()
    e = Event(user_id=user.id, title="34 Fotos in Detmold", category="event",
              date_start=datetime(YEAR, 7, day), date_precision=DatePrecision.day,
              source=Source.immich, confirmed=ConfirmState.confirmed,
              confirmed_by="import", origin_fragment=frag, location=loc,
              external_id=f"immich:day:{YEAR}-07-{day:02d}:Detmold")
    db.add(e)
    db.flush()
    ent = Entity(user_id=user.id, type="country", name=f"Land {day}")
    db.add(ent)
    db.flush()
    db.add_all([
        Metric(event_id=e.id, key="temperature_c", value=21.5,
               source=Source.weather),
        EventEntityLink(event_id=e.id, entity_id=ent.id),
        MediaRef(user_id=user.id, event_id=e.id, provider="immich",
                 external_id=f"asset-{day}",
                 captured_at=datetime(YEAR, 7, day, 10)),
    ])
    db.commit()
    return e


def test_the_cleanup_names_the_rows_before_it_removes_them(db, user):
    """Eine Vorschau, die nur zählt, ist keine (A46/F7-Zusage)."""
    _day_cluster(db, user, 12)
    _day_cluster(db, user, 13)
    assert pp.count_day_clusters(db, user.id) == 2
    sample = pp.day_cluster_sample(db, user.id)
    assert len(sample) == 2
    assert all(s["title"] and s["date"] for s in sample)


def test_the_cleanup_removes_only_the_day_clusters(db, user):
    """Foto-Ereignisse und Handerfasstes bleiben — der Platz entscheidet."""
    _day_cluster(db, user)
    pp.create_photo_events(db, user, _props([_asset(1)], db, user))
    db.add(Event(user_id=user.id, title="Konzert", category="concert",
                 date_start=datetime(YEAR, 7, 12, 20, 0),
                 date_precision=DatePrecision.exact, source=Source.manual,
                 confirmed=ConfirmState.confirmed))
    db.commit()

    assert pp.remove_day_clusters(db, user.id) == 1
    db.commit()
    titles = {e.title for e in db.query(Event).all()}
    assert titles == {"Foto in Detmold", "Konzert"}


def test_the_cleanup_is_idempotent(db, user):
    _day_cluster(db, user)
    assert pp.remove_day_clusters(db, user.id) == 1
    db.commit()
    assert pp.remove_day_clusters(db, user.id) == 0


def test_the_cleanup_takes_everything_that_hangs_on_the_row(db, user):
    """**Der gemeldete 500er.** Metriken und Verknüpfungen sind auf PostgreSQL
    ein Fremdschlüssel; ein Massenlöschen geht an der ORM-Kaskade vorbei, also
    scheiterte der Knopf dort mit einem Serverfehler und hier — auf SQLite —
    still mit Waisen."""
    _day_cluster(db, user)
    assert pp.remove_day_clusters(db, user.id) == 1
    db.commit()
    assert db.query(Metric).count() == 0
    assert db.query(EventEntityLink).count() == 0
    assert db.query(MediaRef).count() == 0


def test_the_cleanup_detaches_uploads_instead_of_deleting_them(db, user):
    """Anmerkung 57: ein hochgeladenes Bild ist Lebensdatenbank. Es hängt
    danach am TAG (F18) — und braucht dafür `captured_at`, sonst wäre das
    Abhängen ein stilles Wegwerfen."""
    e = _day_cluster(db, user)
    db.add(MediaRef(user_id=user.id, event_id=e.id, provider="local",
                    external_id="eigenes.jpg"))
    db.commit()

    pp.remove_day_clusters(db, user.id)
    db.commit()
    ref = db.query(MediaRef).one()
    assert ref.provider == "local" and ref.event_id is None
    assert ref.captured_at == datetime(YEAR, 7, 12)


def test_the_cleanup_unhooks_children_instead_of_orphaning_them(db, user):
    """F7: Kinder werden abgehängt, nicht mitgelöscht — dieselbe Entscheidung
    wie im Lösch-Dialog. Ohne sie zeigte `parent_event_id` ins Leere."""
    parent = _day_cluster(db, user)
    child = Event(user_id=user.id, title="Abends am See", category="event",
                  date_start=datetime(YEAR, 7, 12, 20), source=Source.manual,
                  date_precision=DatePrecision.exact,
                  confirmed=ConfirmState.confirmed, parent_event_id=parent.id)
    db.add(child)
    db.commit()

    assert pp.remove_day_clusters(db, user.id) == 1
    db.commit()
    kept = db.query(Event).one()
    assert kept.id == child.id and kept.parent_event_id is None


# --------------------------------------------------------------------------- #
# Die Merkliste — Monate mit ihrer Fotozahl (Anmerkung 206)
# --------------------------------------------------------------------------- #
# Hier standen zwei Merklisten: die JAHRE dieses Laufs (ein Häkchen) und die
# MONATE des Verknüpfungs-Laufs (die Fotozahl). Seit beide Läufe einer sind,
# gibt es nur die zweite — und sie ist die bessere von beiden: ein Häkchen kann
# „nachgesehen, nichts gefunden" nicht von „nie nachgesehen" unterscheiden, und
# eine Zahl macht den Monat von selbst wieder auf, sobald jemand nachlädt.
# Geprüft wird sie in `test_p21_review.py`, wo sie zu Hause ist.
#
# Die VORSCHAU ist mit derselben Anmerkung weggefallen (Entscheidung des
# Users): „im doing schaue ich mir keine 8.000 Vorschläge an." Was an ihre
# Stelle tritt, ist der Rückweg — `reset()`, geprüft weiter oben.


# --------------------------------------------------------------------------- #
# Mitternacht — der Fall aus Anmerkung 111
# --------------------------------------------------------------------------- #
def test_local_time_decides_the_day(db, user, monkeypatch):
    """`localDateTime` statt `fileCreatedAt` (Anmerkung 111).

    Ein Foto vom 13.5. 01:30 Berliner Zeit landete auf dem **12.**, weil die
    Zone abgeschnitten statt angewandt wurde. Nicht eine Stunde daneben, ein
    TAG — und am Tag hängt der Behälter.
    """
    asset = _asset(1, day=13, hour=1, minute=30)
    props = _props([asset], db, user)
    assert props[0].taken_at.date() == datetime(YEAR, 7, 13).date()
    assert api.asset_time(asset).hour == 1
