"""0.38.0 — Adress-Bausteine aufbewahren, statt sie wegzuwerfen (Anmerkung 110).

Gefragt wurde: „Kann man Bestandsdaten nicht ohne neuen Durchlauf umformatieren?
Das ist doch nur eine Anzeige." Die Antwort war nein — und der Grund war ein
Versäumnis, keine Notwendigkeit: `short_name()` baute aus den Nominatim-
Bausteinen einen String, und die Bausteine wurden danach verworfen. Ein anderes
Format hieß deshalb: jeden Ort erneut abfragen, gedrosselt auf 1,2 Sekunden.

Ab jetzt liegen die Bausteine in `Location.address`. Ein Formatwechsel ist eine
Rechnung ohne Netz — und diese Datei prüft genau das: **kein Abruf, keine
Wartezeit, trotzdem ein neuer Name.**
"""
from __future__ import annotations

import pytest

from app.models import Event, Location, Source, User, UserRole
from app.routers.tracks import resolve_names_batch

ADDRESS = {
    "house_number": "12", "road": "Kaiserstraße", "suburb": "Altstadt",
    "city": "Düsseldorf", "county": "Regierungsbezirk Düsseldorf",
    "state": "Nordrhein-Westfalen", "postcode": "40213", "country": "Deutschland",
}


@pytest.fixture()
def geo_spy(monkeypatch):
    """Zählt JEDEN Geocoder-Abruf. Der Test lebt von dieser Zahl."""
    calls: list[tuple] = []

    def _reverse(lat, lng, lang=None):
        calls.append((lat, lng))
        return {"address": dict(ADDRESS), "type": "poi"}

    monkeypatch.setattr("app.routers.tracks.geocode_svc.reverse_geocode", _reverse)
    # Wartezeit auf null: sonst dauert der Test so lange wie die Drossel.
    monkeypatch.setattr("app.routers.tracks._geo_delay", lambda: 0)
    return calls


def _place(db, user, *, name, address=None):
    loc = Location(user_id=user.id, name=name, lat=51.22, lng=6.77,
                   address=address, city="Düsseldorf", country="Deutschland")
    db.add(loc)
    db.commit()
    return loc


def _visit(db, user, loc, title):
    ev = Event(user_id=user.id, title=title, category="event",
               location_id=loc.id, source=Source.google_timeline)
    db.add(ev)
    db.commit()
    return ev


def test_reformatting_stored_places_asks_nobody(db, user, geo_spy, monkeypatch):
    """Der Kern der Frage: dieselben Daten, anderes Format, **kein Abruf**."""
    user.settings = {"place_name_parts": ["road", "city", "country"]}
    db.commit()
    loc = _place(db, user, name="Kaiserstraße 12, Altstadt, Düsseldorf, "
                                "Regierungsbezirk Düsseldorf, 40213, Deutschland",
                 address=dict(ADDRESS))

    res = resolve_names_batch(db, user, limit=10, scope="verbose")

    assert geo_spy == [], "es wurde trotz gespeicherter Bausteine gefragt"
    assert res.resolved == 1
    db.refresh(loc)
    assert loc.name == "Kaiserstraße 12, Düsseldorf, Deutschland"


def test_the_visit_titles_move_with_it(db, user, geo_spy):
    """Ein Ortsname, der sich ändert, ohne dass die Besuche folgen, zerfällt in
    zwei Wahrheiten — im Geocoder-Weg war das immer schon geregelt."""
    user.settings = {"place_name_parts": ["city", "country"]}
    db.commit()
    loc = _place(db, user, name="Kaiserstraße 12, Altstadt, Düsseldorf, 40213, Deutschland",
                 address=dict(ADDRESS))
    ev = _visit(db, user, loc, "Besuch: Kaiserstraße 12, Altstadt, Düsseldorf, 40213, Deutschland")

    resolve_names_batch(db, user, limit=10, scope="verbose")

    db.refresh(ev)
    assert ev.title == "Besuch: Düsseldorf, Deutschland"


def test_a_manually_renamed_visit_is_left_alone(db, user, geo_spy):
    """Dieselbe Zusage wie im Geocoder-Weg: was ein Mensch umbenannt hat,
    fasst keine Neuberechnung an."""
    user.settings = {"place_name_parts": ["city", "country"]}
    db.commit()
    loc = _place(db, user, name="Kaiserstraße 12, Altstadt, Düsseldorf, 40213, Deutschland",
                 address=dict(ADDRESS))
    ev = _visit(db, user, loc, "Besuch: bei Oma")
    ev.field_overrides = {"title": True}
    db.commit()

    resolve_names_batch(db, user, limit=10, scope="verbose")

    db.refresh(ev)
    assert ev.title == "Besuch: bei Oma"


def test_places_without_stored_parts_still_use_the_geocoder(db, user, geo_spy):
    """Der Bestand hat keine Bausteine — für ihn muss der alte Weg bleiben,
    sonst wäre die Neuerung eine Verschlechterung für alle Altdaten."""
    user.settings = {"place_name_parts": ["road", "city", "country"]}
    db.commit()
    _place(db, user, name="Kaiserstraße 12, Altstadt, Düsseldorf, "
                          "Regierungsbezirk Düsseldorf, 40213, Deutschland",
           address=None)

    res = resolve_names_batch(db, user, limit=10, scope="verbose")

    assert len(geo_spy) == 1
    assert res.resolved == 1


def test_the_geocoder_run_stores_the_parts_for_next_time(db, user, geo_spy):
    """Damit der Schnellweg überhaupt je greift, muss der langsame ihn füttern."""
    user.settings = {"place_name_parts": ["road", "city", "country"]}
    db.commit()
    loc = _place(db, user, name="Ort (51.22000, 6.77000)", address=None)

    resolve_names_batch(db, user, limit=10, scope="unnamed")

    db.refresh(loc)
    assert loc.address and loc.address["road"] == "Kaiserstraße"


def test_a_poi_name_survives_reformatting(db, user, geo_spy):
    """Der Eigenname eines POI steht NICHT in den Adress-Bausteinen. Würde er
    nicht mitgespeichert, verlöre das Umformatieren genau das, was den Namen
    ausmacht — aus „Café Central, Düsseldorf" würde „Düsseldorf"."""
    user.settings = {"place_name_parts": ["city", "country"]}
    db.commit()
    loc = _place(db, user, name="Café Central, Altstadt, Düsseldorf, 40213, Deutschland",
                 address=dict(ADDRESS, poi="Café Central"))

    resolve_names_batch(db, user, limit=10, scope="verbose")

    db.refresh(loc)
    assert loc.name == "Café Central, Düsseldorf, Deutschland"


def test_the_geocoder_run_also_stores_the_poi_name(db, user, monkeypatch):
    """Gegenprobe zur Leseseite: Der obige Test REICHT den POI selbst herein und
    prüft damit nur `short_name`. Wird er beim Speichern vergessen, fällt das
    dort nicht auf — und beim nächsten Umformatieren wäre aus „Café Central,
    Düsseldorf" ein blankes „Düsseldorf" geworden. Also hier die Schreibseite."""
    monkeypatch.setattr("app.routers.tracks._geo_delay", lambda: 0)
    monkeypatch.setattr(
        "app.routers.tracks.geocode_svc.reverse_geocode",
        lambda lat, lng, lang=None: {"address": dict(ADDRESS), "poi": "Café Central"})
    user.settings = {"place_name_parts": ["city", "country"]}
    db.commit()
    loc = _place(db, user, name="Ort (51.22000, 6.77000)", address=None)

    resolve_names_batch(db, user, limit=10, scope="unnamed")

    db.refresh(loc)
    assert loc.address.get("poi") == "Café Central", \
        "der Eigenname ging beim Speichern verloren"
    assert loc.name.startswith("Café Central")


def test_other_users_places_are_not_touched(db, user, geo_spy):
    """A12: in JEDER Abfrage."""
    other = User(oidc_subject="x", email="x@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    user.settings = {"place_name_parts": ["city"]}
    db.commit()
    foreign = _place(db, other, name="Kaiserstraße 12, Altstadt, Düsseldorf, 40213, Deutschland",
                     address=dict(ADDRESS))

    resolve_names_batch(db, user, limit=10, scope="verbose")

    db.refresh(foreign)
    assert foreign.name.startswith("Kaiserstraße 12")
