"""Anmerkung 204 — die Wetter-Bilanz wird gezählt, nicht ausgeliefert.

Der Statistik-Überblick holte sich `day_values` über den GANZEN Bestand und
reduzierte in Python: am Demo-Leben gemessen 1,3 s für 152.854 Zeilen, aus
denen vier Zahlen und ein Balkendiagramm wurden. Die Zeilenzahl war nie eine
Frage der Statistik — F20 gibt jedem Wohnort-Tag siebzehn Wetterwerte, also
wuchs sie um eine Größenordnung, ohne dass sich die Frage geändert hätte.

**Was hier geprüft wird, ist nicht die Geschwindigkeit.** Eine Zusicherung über
Millisekunden ist auf fremder Hardware entweder wertlos oder launisch. Geprüft
wird, dass die Verlagerung nach SQL die REGELN mitgenommen hat — und das sind
genau die, die eine naive Aggregation über die Rohzeilen verlöre:

* ein Tag zählt EINMAL, auch mit dreißig importierten Besuchen (A31),
* je Schlüssel gilt der kleinste Wert des Tages (Anmerkung 119),
* beide Quellen zählen, Ereignisse wie Wohnort-Tage (F20),
* ein Jahr ohne Regen steht mit `0` da und nicht gar nicht.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.models import (BaselineLocation, ConfirmState, DayMetric, Event,
                        Location, Metric, Source)
from app.services import weather_day
from app.services.stats_overview import _WX_KEYS


def _place(db, user, name, lat, lng):
    loc = Location(user_id=user.id, name=name, lat=lat, lng=lng,
                   city="Hamburg", country="Deutschland")
    db.add(loc)
    db.flush()
    return loc


def _entry(db, user, loc, when: datetime, wx: dict[str, float]):
    ev = Event(user_id=user.id, title="Eintrag", category="event",
               date_start=when, location_id=loc.id,
               confirmed=ConfirmState.confirmed)
    db.add(ev)
    db.flush()
    for key, value in wx.items():
        db.add(Metric(event_id=ev.id, key=key, value=value, source=Source.weather))
    return ev


def _resident(db, user, loc, start: date, end: date):
    db.add(BaselineLocation(user_id=user.id, location_id=loc.id,
                            date_start=start, date_end=end))


def _day_wx(db, user, day: date, wx: dict[str, float]):
    for key, value in wx.items():
        db.add(DayMetric(user_id=user.id, day=day, key=key, value=value,
                         source=Source.weather))


def _as_dict(rows):
    return {y: (days, rain, round(sun, 1)) for y, days, rain, sun in rows}


# --------------------------------------------------------------------------- #
def test_one_day_counts_once_however_many_entries_it_has(db, user):
    """**A31, und der Grund, aus dem in ZWEI Stufen gruppiert wird.**

    Ein importierter Tag trägt dutzende Besuche mit demselben Wetter. Wer die
    Rohzeilen direkt aggregiert, bekommt mehr als 365 Regentage im Jahr — eine
    Zahl, die sofort auffällt, und ihre kleine Schwester (ein Tag mit drei
    Einträgen zählt dreifach) fällt nie auf.
    """
    loc = _place(db, user, "Osterstraße", 53.57, 9.95)
    for hour in range(30):
        _entry(db, user, loc, datetime(2021, 6, 14, hour % 24),
               {"rain_mm": 4.0, "sunshine_h": 2.0})
    db.commit()

    rows = _as_dict(weather_day.year_totals(db, user.id, keys=_WX_KEYS))
    assert rows == {2021: (1, 1, 2.0)}, rows


def test_the_smallest_value_of_the_day_wins(db, user):
    """Anmerkung 119 — der vorsichtige Wert, an einem Tag mit zwei Regionen.

    Auch das geht verloren, wenn jemand die zweite Stufe wegoptimiert: `sum`
    über die Rohzeilen addierte beide Sonnenwerte statt den kleineren zu
    nehmen.
    """
    hh = _place(db, user, "Hamburg", 53.57, 9.95)
    kiel = _place(db, user, "Kiel", 54.32, 10.14)
    _entry(db, user, hh, datetime(2021, 6, 14, 9), {"rain_mm": 0.2, "sunshine_h": 9.0})
    _entry(db, user, kiel, datetime(2021, 6, 14, 18), {"rain_mm": 7.0, "sunshine_h": 3.0})
    db.commit()

    rows = _as_dict(weather_day.year_totals(db, user.id, keys=_WX_KEYS))
    # Der kleinere Regenwert (0,2 mm) entscheidet — also KEIN Regentag —,
    # und die kleinere Sonnenzahl steht in der Summe.
    assert rows == {2021: (1, 0, 3.0)}, rows


def test_both_sources_count(db, user):
    """F20 — ein Jahr, in dem nur der Wohnort steht, ist ein Jahr mit Wetter.

    Genau das war Anmerkung 194: die Bilanz zählte über eine aus den
    EREIGNISSEN gebaute Tagesliste, und solche Jahre kamen nicht einmal als
    Balken vor.
    """
    loc = _place(db, user, "Elternhaus", 53.93, 10.31)
    _resident(db, user, loc, date(2005, 1, 1), date(2005, 12, 31))
    _day_wx(db, user, date(2005, 3, 4), {"rain_mm": 6.0, "sunshine_h": 1.0})
    _day_wx(db, user, date(2005, 3, 5), {"rain_mm": 0.0, "sunshine_h": 8.0})
    _entry(db, user, loc, datetime(2006, 7, 1, 12), {"rain_mm": 3.0, "sunshine_h": 5.0})
    db.commit()

    rows = _as_dict(weather_day.year_totals(db, user.id, keys=_WX_KEYS))
    assert rows == {2005: (2, 1, 9.0), 2006: (1, 1, 5.0)}, rows


def test_a_year_without_rain_still_has_a_bar(db, user):
    """Ein fehlender Balken liest sich wie ein fehlendes Jahr."""
    loc = _place(db, user, "Hamburg", 53.57, 9.95)
    _entry(db, user, loc, datetime(2019, 8, 2, 12), {"rain_mm": 0.0, "sunshine_h": 11.0})
    _entry(db, user, loc, datetime(2020, 8, 2, 12), {"rain_mm": 5.0, "sunshine_h": 1.0})
    db.commit()

    rows = _as_dict(weather_day.year_totals(db, user.id, keys=_WX_KEYS))
    assert rows == {2019: (1, 0, 11.0), 2020: (1, 1, 1.0)}, rows


def test_a_day_without_rain_or_sun_is_still_a_day_with_weather(db, user):
    """**Die Beinahe-Änderung dieser Runde.**

    Es liegt nahe, die Abfrage auf `rain_mm` und `sunshine_h` zu verengen —
    gebraucht werden ja nur die zwei. Damit zählte „Tage mit Wetter" plötzlich
    Tage MIT REGENWERT, und ein Tag, der nur eine Temperatur trägt, fiele
    heraus. Die Kachel sähe weiterhin richtig aus, wäre nur kleiner: die Sorte
    Änderung, die niemand bemerkt und niemand mehr erklären kann.
    """
    loc = _place(db, user, "Hamburg", 53.57, 9.95)
    _entry(db, user, loc, datetime(2022, 4, 4, 12), {"temperature_c": 14.0})
    db.commit()

    rows = _as_dict(weather_day.year_totals(db, user.id, keys=_WX_KEYS))
    assert rows == {2022: (1, 0, 0.0)}, rows


def test_sql_and_the_python_reduction_agree(db, user):
    """Die eigentliche Umstellung: dieselbe Antwort, anderswo gerechnet.

    Die Python-Fassung steht hier ausgeschrieben — sie ist die, die im
    Überblick stand, und sie ist der Maßstab. Fällt dieser Fall, hat die
    SQL-Fassung eine Regel verloren, und zwar in einer Größe, in der man es
    von Hand nachrechnen kann.
    """
    hh = _place(db, user, "Hamburg", 53.57, 9.95)
    kiel = _place(db, user, "Kiel", 54.32, 10.14)
    home = _place(db, user, "Elternhaus", 53.93, 10.31)
    _resident(db, user, home, date(2015, 1, 1), date(2015, 12, 31))
    for day in range(1, 40):
        _day_wx(db, user, date(2015, 1, 1) + timedelta(days=day - 1),
                {"rain_mm": (day % 7) * 0.5, "sunshine_h": day % 5,
                 "temperature_c": 10.0 + day % 9})
    for day in range(1, 25):
        when = datetime(2016, 3, 1, 12) + timedelta(days=day - 1)
        _entry(db, user, hh, when, {"rain_mm": (day % 4) * 1.2,
                                    "sunshine_h": day % 6, "temperature_c": 12.0})
        if day % 3 == 0:                     # zweite Region am selben Tag
            _entry(db, user, kiel, when.replace(hour=18),
                   {"rain_mm": 9.0, "sunshine_h": 0.5, "temperature_c": 8.0})
    db.commit()

    day_wx = weather_day.day_values(db, user.id, keys=_WX_KEYS)
    expected: dict[int, list] = {}
    for iso, vals in day_wx.items():
        slot = expected.setdefault(int(iso[:4]), [0, 0, 0.0])
        slot[0] += 1
        if (vals.get("rain_mm") or 0) >= weather_day.RAIN_DAY_MM:
            slot[1] += 1
        slot[2] += vals.get("sunshine_h") or 0

    got = weather_day.year_totals(db, user.id, keys=_WX_KEYS)
    assert {y: [d, r, round(s, 6)] for y, d, r, s in got} == \
        {y: [d, r, round(s, 6)] for y, (d, r, s) in expected.items()}
    assert len(got) == 2, got
