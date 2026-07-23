"""Anmerkung 114 — die F12-Werte bekommen ihre Extremwert-Kacheln.

UV-Index, Böen, gefühlte Temperatur und Tageslichtdauer kommen seit v0.22 bei
jeder Wetter-Anreicherung mit (derselbe Open-Meteo-Aufruf, keine Zusatzkosten)
und standen bis 0.38 nur in der Detailansicht eines einzelnen Ereignisses.
Gespeicherte Daten, die nirgends zusammengefasst werden, sind Ballast.

Der interessante Teil ist nicht „Maximum finden", sondern die Frage, wann eine
Null ein Rekord ist: beim Regen nicht (der trockenste Tag ist kein „nassester
Tag"), beim Tageslicht schon — die Polarnacht mit 0 h IST der kürzeste Tag.
"""
from __future__ import annotations

from datetime import datetime

from app.models import (ConfirmState, DatePrecision, Event, Location, Metric,
                        Source)
from app.services.stats_overview import compute_overview

NOW = datetime(2026, 7, 22)


def _day(db, user, title: str, date: datetime, **wx) -> Event:
    loc = Location(user_id=user.id, name=f"Ort {title}", lat=53.0, lng=10.0)
    db.add(loc)
    db.flush()
    ev = Event(user_id=user.id, title=title, category="event", date_start=date,
               date_precision=DatePrecision.day, location=loc,
               source=Source.manual, confirmed=ConfirmState.confirmed)
    db.add(ev)
    db.flush()
    for key, value in wx.items():
        db.add(Metric(event_id=ev.id, key=key, value=value, source=Source.weather))
    return ev


def test_f12_values_become_extremes(db, user):
    _day(db, user, "Strandtag", datetime(2024, 7, 1),
         uv_max=8.4, gust_max_kmh=31.0, apparent_temp_max_c=38.2,
         apparent_temp_min_c=19.0, daylight_h=16.3)
    _day(db, user, "Novembersturm", datetime(2024, 11, 3),
         uv_max=0.9, gust_max_kmh=112.0, apparent_temp_max_c=7.0,
         apparent_temp_min_c=-11.4, daylight_h=9.1)
    db.commit()

    ex = compute_overview(db, user.id, today=NOW)["extremes"]
    assert ex["uv"]["value"] == 8.4 and ex["uv"]["title"] == "Strandtag"
    assert ex["gust"]["value"] == 112.0 and ex["gust"]["title"] == "Novembersturm"
    assert ex["felt_hot"]["value"] == 38.2
    assert ex["felt_cold"]["value"] == -11.4
    assert ex["longest_day"]["value"] == 16.3
    assert ex["shortest_day"]["value"] == 9.1
    # Ort und Datum kommen mit, wie bei den älteren Kacheln
    assert ex["uv"]["place"] == "Ort Strandtag"
    assert ex["gust"]["date_start"].date() == datetime(2024, 11, 3).date()


def test_polar_night_counts_as_shortest_day(db, user):
    """Null Stunden Tageslicht sind ein Messwert, kein fehlender Wert.

    Bei Regen und Schnee wird die Null bewusst ausgeschlossen — sonst wäre der
    trockenste Tag der „nasseste". Beim Tageslicht wäre dieselbe Regel ein
    Fehler mit Anspruch: sie würde ausgerechnet den bemerkenswertesten Wert der
    Kachel verschlucken. Dieselbe Frage wie bei F19/Anmerkung 104 — eine Regel
    gilt nicht überall nur, weil sie irgendwo richtig war."""
    _day(db, user, "Tromsø im Dezember", datetime(2024, 12, 21),
         daylight_h=0.0, rain_mm=0.0)
    _day(db, user, "Ein normaler Tag", datetime(2024, 4, 4),
         daylight_h=13.0, rain_mm=2.0)
    db.commit()

    ex = compute_overview(db, user.id, today=NOW)["extremes"]
    assert ex["shortest_day"]["value"] == 0.0
    assert ex["shortest_day"]["title"] == "Tromsø im Dezember"
    # …und die Null bleibt beim Regen weiterhin draußen
    assert ex["rainy"]["title"] == "Ein normaler Tag"
    # Ein Tag ohne Tageslicht ist auch nicht der „längste"
    assert ex["longest_day"]["title"] == "Ein normaler Tag"


def test_missing_f12_values_leave_the_tiles_empty(db, user):
    """Altbestand (vor v0.22) trägt die Werte nicht — dann steht dort nichts,
    nicht etwa eine Null. Eine erfundene Null wäre ein Rekord, den es nie
    gegeben hat."""
    _day(db, user, "Altbestand", datetime(2015, 5, 5), temperature_c=21.0)
    db.commit()

    ex = compute_overview(db, user.id, today=NOW)["extremes"]
    assert ex["hot"] is not None            # das Tagesmittel gibt es
    for key in ("uv", "gust", "felt_hot", "felt_cold",
                "longest_day", "shortest_day"):
        assert ex[key] is None, key
