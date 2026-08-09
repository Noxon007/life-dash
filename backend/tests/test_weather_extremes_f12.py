"""Anmerkung 114 — die F12-Werte bekommen ihre Extremwert-Kacheln.

UV-Index, Böen, gefühlte Temperatur und Tageslichtdauer kommen seit v0.22 bei
jeder Wetter-Anreicherung mit (derselbe Open-Meteo-Aufruf, keine Zusatzkosten)
und standen bis 0.38 nur in der Detailansicht eines einzelnen Ereignisses.
Gespeicherte Daten, die nirgends zusammengefasst werden, sind Ballast.

Der interessante Teil ist nicht „Maximum finden", sondern die Frage, wann eine
Null ein Rekord ist: beim Regen nicht — der trockenste Tag ist kein „nassester
Tag".

**Anmerkung 216 (2026-08-09): die Tageslicht-Kacheln sind weg**, und mit ihnen
der Fall, an dem diese Datei die Null-Frage vorgeführt hat. Die Begründung ist
nicht, dass die Regel falsch war, sondern dass die KACHEL keine Auskunft gab:
die Tageslänge ist eine Eigenschaft des Kalenders und des Breitengrads, also
nannte „längster Tag" jedes Jahr aufs Neue die Sonnenwende. Zusammen mit
„Sonnigster Tag" und „Längster Regen" — beide nach oben gedeckelt, beide mit
zehn identischen Werten in der Rangliste — ist sie gestrichen.

Was hier geprüft wird, ist deshalb seitdem beides: dass die verbliebenen
F12-Kacheln rechnen, und dass die vier gestrichenen **wirklich nicht mehr
auftauchen**. Ein Extremwert, den der Server weiter berechnet und den niemand
zeigt, wäre der teurere Zustand — er käme beim nächsten Umbau als „das gibt es
doch schon" zurück.
"""
from __future__ import annotations

from datetime import datetime

from app.models import (ConfirmState, DatePrecision, Event, Location, Metric,
                        Source)
from app.services.stats_overview import compute_overview

NOW = datetime(2026, 7, 22)

# Anmerkung 216: die vier gestrichenen Kacheln, an EINER Stelle. Die beiden
# Tests unten lesen dieselbe Liste — zwei Aufzählungen liefen still auseinander,
# und die zweite bliebe grün, weil sie weniger prüft.
GONE = ("sunny", "rain_long", "longest_day", "shortest_day")


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
    # Anmerkung 123: die UV-Kachel ist raus (ERA5 liefert nie UV) — es gibt
    # keinen "uv"-Extremwert mehr.
    assert "uv" not in ex
    assert ex["gust"]["value"] == 112.0 and ex["gust"]["title"] == "Novembersturm"
    assert ex["felt_hot"]["value"] == 38.2
    assert ex["felt_cold"]["value"] == -11.4
    # Ort und Datum kommen mit, wie bei den älteren Kacheln
    assert ex["gust"]["place"] == "Ort Novembersturm"
    assert ex["gust"]["date_start"].date() == datetime(2024, 11, 3).date()


def test_the_capped_records_are_gone(db, user):
    """**Anmerkung 216 — vier Kacheln, deren Wert nicht unterscheiden kann.**

    Die Daten hier sind genau der gemeldete Fall: zwei wolkenlose Tage um die
    Sonnenwende, beide mit derselben Sonnenscheindauer, weil Sonnenschein die
    Tageslänge nicht überschreiten kann; dazu zwei durchgeregnete Tage mit je
    24 Regenstunden. In der alten Fassung standen daraus vier Ranglisten mit
    identischen Werten auf allen Plätzen.

    Geprüft wird der Schlüssel und nicht die Anzeige: solange der Server ihn
    liefert, baut die Oberfläche früher oder später wieder eine Kachel daraus.
    """
    _day(db, user, "Sonnenwende", datetime(2024, 6, 20),
         sunshine_h=16.4, daylight_h=16.4, rain_h=0.0)
    _day(db, user, "Sonnenwende zwei", datetime(2024, 6, 21),
         sunshine_h=16.4, daylight_h=16.5, rain_h=0.0)
    _day(db, user, "Landregen", datetime(2024, 11, 3),
         sunshine_h=0.0, daylight_h=9.1, rain_h=24.0, rain_mm=31.0)
    db.commit()

    ex = compute_overview(db, user.id, today=NOW)["extremes"]
    for key in GONE:
        assert key not in ex, key
    # Der Regen in MILLIMETERN bleibt — er ist nicht gedeckelt und trennt die
    # Tage weiterhin. Die Streichung galt der Einheit, nicht dem Wetter.
    assert ex["rainy"]["title"] == "Landregen"


def test_missing_f12_values_leave_the_tiles_empty(db, user):
    """Altbestand (vor v0.22) trägt die Werte nicht — dann steht dort nichts,
    nicht etwa eine Null. Eine erfundene Null wäre ein Rekord, den es nie
    gegeben hat."""
    _day(db, user, "Altbestand", datetime(2015, 5, 5), temperature_c=21.0)
    db.commit()

    ex = compute_overview(db, user.id, today=NOW)["extremes"]
    assert ex["hot"] is not None            # das Tagesmittel gibt es
    for key in ("gust", "felt_hot", "felt_cold"):
        assert ex[key] is None, key
    assert "uv" not in ex                    # Anmerkung 123: UV-Kachel entfernt
    for key in GONE:                         # Anmerkung 216
        assert key not in ex, key
