"""Tests für 0.31.0: A36 — schlanke Ereignisliste (ohne Roh-Metriken)."""
from __future__ import annotations

import json
from datetime import datetime

from app.models import (ConfirmState, DatePrecision, Entity, Event,
                        EventEntityLink, Location, MediaRef, Metric, Source)
from app.routers._serialize import event_to_read


def _event_with_weather(db, user) -> Event:
    loc = Location(user_id=user.id, name="Hamburg", lat=53.5, lng=10.0)
    db.add(loc)
    db.flush()
    e = Event(user_id=user.id, title="Regentag", category="trip", location=loc,
              date_start=datetime(2024, 6, 1), date_precision=DatePrecision.day,
              source=Source.manual, confirmed=ConfirmState.confirmed)
    db.add(e)
    db.flush()
    for key, val, txt in [("temp_min_c", 12.0, None), ("temp_max_c", 23.0, None),
                          ("temperature_c", 17.0, None), ("sunshine_h", 4.0, None),
                          ("rain_mm", 5.6, None), ("weather", None, "Regen"),
                          ("sunrise", None, "05:20"), ("sunset", None, "21:40"),
                          ("weather_rev", 2.0, None)]:
        db.add(Metric(event_id=e.id, key=key, value=val, value_text=txt,
                      source=Source.weather))
    ent = Entity(user_id=user.id, type="country", name="Deutschland",
                 confirmed=ConfirmState.confirmed)
    db.add(ent)
    db.flush()
    db.add(EventEntityLink(event_id=e.id, entity_id=ent.id))
    db.commit()
    return e


def test_slim_drops_metrics_and_adds_compact_weather(db, user):
    e = _event_with_weather(db, user)

    full = event_to_read(e)
    slim = event_to_read(e, slim=True)

    # Voll: Rohzeilen da, kein kompaktes Wetter
    assert len(full.metrics) == 9 and full.weather is None
    # Schlank: keine Rohzeilen, aber kompaktes Wetter mit denselben Werten
    assert slim.metrics == []
    assert slim.weather["temp_min_c"] == 12.0
    assert slim.weather["weather"] == "Regen"
    assert slim.weather["sunrise"] == "05:20"
    # Interner Marker taucht im kompakten Wetter NICHT auf
    assert "weather_rev" not in slim.weather


def test_slim_keeps_entities_media_location(db, user):
    """Nur die Metriken fallen weg — alles, was die Karte sonst zeigt, bleibt."""
    e = _event_with_weather(db, user)
    db.add(MediaRef(user_id=user.id, event_id=e.id, provider="local",
                    external_id="foto.jpg"))
    db.commit()

    slim = event_to_read(e, slim=True)
    assert [x.name for x in slim.entities] == ["Deutschland"]
    assert len(slim.media) == 1
    assert slim.location.name == "Hamburg"


def test_slim_is_substantially_smaller(db, user):
    e = _event_with_weather(db, user)
    full = json.dumps(event_to_read(e).model_dump(mode="json"))
    slim = json.dumps(event_to_read(e, slim=True).model_dump(mode="json"))
    # Die neun Metrik-Zeilen sind der Löwenanteil — schlank ist klar kleiner
    assert len(slim) < len(full) * 0.7


def test_event_without_weather_has_null_compact(db, user):
    e = Event(user_id=user.id, title="Ohne Wetter", category="event",
              date_start=datetime(2024, 6, 1), date_precision=DatePrecision.day,
              source=Source.manual, confirmed=ConfirmState.confirmed)
    db.add(e)
    db.commit()
    assert event_to_read(e, slim=True).weather is None
