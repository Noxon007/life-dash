"""Tests für 0.23.0: F11 (Auswertungen aus vorhandenen Wetterdaten) und
F12 (zusätzliche Wetterfelder per Re-Enrichment). Offline."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.models import ConfirmState, Event, Location, Metric, Source, User, UserRole
from app.routers.world import world
from app.services.achievements import compute
from app.services.enrichment import (WEATHER_REVISION, _needs_weather,
                                     enrich_weather)


def _event(db, user, title="Tag", when=datetime(2024, 5, 1), loc=None,
           confirmed=True, category="trip") -> Event:
    e = Event(user_id=user.id, title=title, category=category, date_start=when,
              location=loc, source=Source.manual,
              confirmed=ConfirmState.confirmed if confirmed else ConfirmState.unconfirmed)
    db.add(e)
    db.commit()
    return e


def _weather(db, event, **values):
    for key, val in values.items():
        if isinstance(val, str):
            db.add(Metric(event_id=event.id, key=key, value_text=val,
                          source=Source.weather))
        else:
            db.add(Metric(event_id=event.id, key=key, value=val,
                          source=Source.weather))
    db.commit()


# --------------------------------------------------------------------------- #
# F12 — zusätzliche Wetterfelder
# --------------------------------------------------------------------------- #
def test_extended_fields_are_stored(db, user, fake_weather):
    loc = Location(user_id=user.id, name="Detmold", lat=51.94, lng=8.88)
    db.add(loc)
    db.flush()
    ev = _event(db, user, loc=loc)

    enrich_weather(db)

    rows = {m.key: m for m in db.query(Metric).all()}
    assert rows["apparent_temp_max_c"].value == 31.2
    assert rows["apparent_temp_min_c"].value == 12.5
    assert rows["rain_h"].value == 1.0
    assert rows["daylight_h"].value == 15.8
    assert rows["gust_max_kmh"].value == 42.0
    assert rows["uv_max"].value == 6.4
    # Uhrzeiten als Text, nicht als Zahl
    assert rows["sunrise"].value_text == "05:14"
    assert rows["sunset"].value_text == "21:02"


def test_f3_stock_is_topped_up_additively(db, user, fake_weather):
    """Bestand aus 0.14.0–0.22.0 (F3-Werte, kein Marker) bekommt genau einen
    Nachrüst-Lauf — vorhandene Werte bleiben unangetastet."""
    loc = Location(user_id=user.id, name="Detmold", lat=51.94, lng=8.88)
    db.add(loc)
    db.flush()
    ev = _event(db, user, loc=loc)
    _weather(db, ev, temperature_c=21.5, temp_min_c=14.0, temp_max_c=29.0,
             sunshine_h=11.2, rain_mm=0.4, snow_cm=0.0, wind_max_kmh=18.4,
             weather="klar")

    assert _needs_weather(ev) is True
    enrich_weather(db)
    db.refresh(ev)

    rows = {m.key: m for m in db.query(Metric).all()}
    assert rows["temperature_c"].value == 21.5      # unverändert
    assert rows["weather"].value_text == "klar"     # unverändert
    assert rows["uv_max"].value == 6.4              # additiv dazu
    assert rows["weather_rev"].value == WEATHER_REVISION
    assert _needs_weather(ev) is False              # danach fertig


def test_missing_extended_fields_do_not_loop(db, user, monkeypatch):
    """Die eigentliche Falle: liefert Open-Meteo die F12-Felder NICHT (bei
    alten Archivjahren fehlen UV und Böen regelmäßig), darf das Event nicht
    bei jedem Lauf erneut abgefragt werden. Der Revisionsmarker verhindert es."""
    calls = []

    def _sparse(lat, lng, when):
        calls.append((lat, lng, when))
        return {"temp_c": 8.0, "temp_min_c": 4.0, "temp_max_c": 12.0,
                "sun_h": 2.0, "rain_mm": 0.0, "snow_cm": 0.0,
                "wind_max_kmh": 10.0, "condition": "bewölkt"}

    monkeypatch.setattr("app.services.enrichment.fetch_weather", _sparse)
    loc = Location(user_id=user.id, name="Detmold", lat=51.94, lng=8.88)
    db.add(loc)
    db.flush()
    _event(db, user, loc=loc)

    enrich_weather(db)
    enrich_weather(db)
    enrich_weather(db)

    assert len(calls) == 1


def test_future_events_get_no_weather(db, user, fake_weather):
    loc = Location(user_id=user.id, name="Detmold", lat=51.94, lng=8.88)
    db.add(loc)
    db.flush()
    _event(db, user, when=datetime(2099, 1, 1), loc=loc)
    enriched, _ = enrich_weather(db)
    assert enriched == 0
    assert fake_weather == []


# --------------------------------------------------------------------------- #
# F11 — Erfolge aus vorhandenen Wetterdaten
# --------------------------------------------------------------------------- #
def _achievement(db, user, aid):
    return next((a for a in compute(db, user.id).achievements if a.id == aid), None)


# F19/Anmerkung 103: Die beiden Tests hießen von Anfang an „days" und legten
# alle Ereignisse auf DENSELBEN Tag (der Vorgabewert von `_event`) — sie haben
# also Einträge gezählt und Tage behauptet, genau wie der Code darunter. Seit
# die Metriken je Kalendertag rechnen, tragen sie verschiedene Daten.
def test_weather_achievements_count_matching_days(db, user):
    for i, sun in enumerate([12.0, 11.0, 3.0]):     # zwei Tage über der Schwelle
        _weather(db, _event(db, user, title=f"Tag {i}",
                            when=datetime(2024, 5, 1 + i)), sunshine_h=sun)

    a = _achievement(db, user, "sun_worshipper")
    assert a is not None
    assert a.value == 2


def test_weather_achievements_sum_values(db, user):
    _weather(db, _event(db, user, title="A", when=datetime(2024, 5, 1)), sunshine_h=10.4)
    _weather(db, _event(db, user, title="B", when=datetime(2024, 5, 2)), sunshine_h=5.2)

    assert _achievement(db, user, "sun_collector").value == 16   # gerundet


def test_weather_achievements_use_max_bound(db, user):
    """„Frostbeule": Tage, an denen das Maximum unter null blieb."""
    _weather(db, _event(db, user, title="Frost"), temp_max_c=-3.0)
    _weather(db, _event(db, user, title="Mild"), temp_max_c=8.0)

    assert _achievement(db, user, "frostbite").value == 1


def test_weather_achievements_ignore_unconfirmed(db, user):
    """Vorschläge dürfen keine Erfolge auslösen (F6-Grundregel)."""
    _weather(db, _event(db, user, title="Vorschlag", confirmed=False), sunshine_h=12.0)
    assert _achievement(db, user, "sun_worshipper").value == 0


def test_weather_achievements_are_scoped_to_the_user(db, user):
    other = User(oidc_subject="other-wx", email="wx@example.org", role=UserRole.user)
    db.add(other)
    db.commit()
    _weather(db, _event(db, other, title="Fremd"), sunshine_h=12.0)

    assert _achievement(db, user, "sun_worshipper").value == 0


# --------------------------------------------------------------------------- #
# F11 — Durchschnittstemperatur je Land im Welt-Reiter
# --------------------------------------------------------------------------- #
def _country_event(db, user, country_name, temp):
    from app.models import Entity, EventEntityLink

    ev = _event(db, user, title=f"Reise {country_name}")
    ent = Entity(user_id=user.id, type="country", name=country_name,
                 confirmed=ConfirmState.confirmed)
    db.add(ent)
    db.flush()
    db.add(EventEntityLink(event_id=ev.id, entity_id=ent.id))
    db.commit()
    if temp is not None:
        _weather(db, ev, temperature_c=temp)
    return ev


def test_world_reports_average_temperature(db, user):
    _country_event(db, user, "Griechenland", 28.0)
    _country_event(db, user, "Griechenland", 24.0)

    data = world(db=db, user=user)
    greece = next(c for cont in data.continents for c in cont.countries
                  if c.name == "Griechenland")
    assert greece.avg_temp_c == 26.0


def test_world_average_is_none_without_weather(db, user):
    _country_event(db, user, "Island", None)

    data = world(db=db, user=user)
    iceland = next(c for cont in data.continents for c in cont.countries
                   if c.name == "Island")
    assert iceland.avg_temp_c is None
