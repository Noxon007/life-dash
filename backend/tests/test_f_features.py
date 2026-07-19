"""Tests für 0.14.0: F2 (Gerätestandort), F3 (Wetter-Verfeinerung),
F4 (Länder-Kompendium aus der Ortsauflösung). Offline."""
from __future__ import annotations

from app.models import Entity, Event, EventEntityLink, Fragment, Location, Metric, Source
from app.routers.tracks import import_timeline, resolve_place_names
from app.services.enrichment import _add_weather
from app.services.ingestion import ingest_fragment
from tests.test_timeline_a12_users import _device_payload, fake_reverse  # noqa: F401


# --------------------------------------------------------------------------- #
# F3 — Wetter: reine Tageswerte (Min/Max, Sonne, Regen, Schnee, Wind)
# --------------------------------------------------------------------------- #
def test_add_weather_stores_daily_values(db, user, monkeypatch):
    monkeypatch.setattr(
        "app.services.enrichment.fetch_weather",
        lambda lat, lng, when: {"temp_c": 21.5, "temp_min_c": 14.0,
                                "temp_max_c": 29.0, "sun_h": 11.2,
                                "rain_mm": 0.4, "snow_cm": 0.0,
                                "wind_max_kmh": 18.4, "condition": "klar"})
    loc = Location(user_id=user.id, name="Detmold", lat=51.9, lng=8.9)
    db.add(loc)
    db.flush()
    ev = Event(user_id=user.id, title="Sommertag", location_id=loc.id)
    db.add(ev)
    db.flush()
    from datetime import datetime
    ev.date_start = datetime(2024, 7, 1)

    assert _add_weather(db, ev) is True
    db.commit()
    keys = {m.key: (m.value, m.value_text, m.unit) for m in db.query(Metric).all()}
    assert keys["temperature_c"][0] == 21.5
    assert keys["temp_min_c"][0] == 14.0
    assert keys["temp_max_c"][0] == 29.0
    assert keys["sunshine_h"] == (11.2, None, "h")
    assert keys["rain_mm"] == (0.4, None, "mm")
    assert keys["snow_cm"][0] == 0.0
    assert keys["wind_max_kmh"] == (18.4, None, "km/h")
    assert keys["weather"][1] == "klar"


# --------------------------------------------------------------------------- #
# F4 — Länder-Kompendium aus der Ortsauflösung
# --------------------------------------------------------------------------- #
def test_resolve_links_country_entity(db, user, fake_reverse):  # noqa: F811
    import_timeline(_device_payload(), auto_resolve=False, db=db, user=user)
    resolve_place_names(limit=10, scope="unnamed", db=db, user=user)

    loc = db.query(Location).one()
    assert loc.country == "Deutschland"
    entity = db.query(Entity).filter(Entity.type == "country").one()
    assert entity.name == "Deutschland"
    link = db.query(EventEntityLink).one()
    assert link.entity_id == entity.id

    # Idempotent: zweiter Lauf erzeugt keine Duplikate
    loc.name = "Ort (51.94, 8.87)"  # wieder Kandidat machen
    db.commit()
    resolve_place_names(limit=10, scope="unnamed", db=db, user=user)
    assert db.query(Entity).filter(Entity.type == "country").count() == 1
    assert db.query(EventEntityLink).count() == 1


# --------------------------------------------------------------------------- #
# F2 — Gerätestandort beim Erfassen (Text ohne Ort -> Standort greift)
# --------------------------------------------------------------------------- #
def test_capture_position_becomes_location(db, user):
    frag = Fragment(user_id=user.id, raw_text="habe einen Adler gesehen",
                    source=Source.manual, capture_lat=51.94, capture_lng=8.87)
    db.add(frag)
    db.flush()
    events = ingest_fragment(db, frag)
    db.commit()
    assert events and events[0].location is not None
    # Geocoding ist in Tests aus -> Koordinaten-Name (löst später auf)
    assert events[0].location.name.startswith("Ort (")
    assert events[0].location.lat == 51.94


def test_capture_position_text_wins(db, user):
    """Nennt der Text selbst einen Ort, wird der Standort ignoriert."""
    frag = Fragment(user_id=user.id,
                    raw_text="12.07.2026 war in Detmold und habe einen Adler gesehen",
                    source=Source.manual, capture_lat=48.1, capture_lng=11.5)
    db.add(frag)
    db.flush()
    events = ingest_fragment(db, frag)
    db.commit()
    with_loc = [e for e in events if e.location]
    assert with_loc and all("Ort (" not in e.location.name for e in with_loc)
