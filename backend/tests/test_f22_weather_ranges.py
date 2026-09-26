"""F22 — der Wetterlauf fragt je Ort und Zeitspanne, nicht je Tag.

Ein Wohnort über zwanzig Jahre waren 7.298 Anfragen an EINER Koordinate. Jetzt
plant `_RangePrefetch` Spannen je Ort und legt die Antworten in den Cache von
`weather`; geschrieben wird weiter je Tag, auf dem alten Weg.

**Die Attrappe liest `start_date`/`end_date` und antwortet je Tag.** Eine, die
immer dieselbe Einzel-Antwort gibt, kann den Unterschied zwischen einer Spanne
und einem Tag nicht zeigen — ein Doppel, das ein Feld auslässt, ist eine andere
Funktion (Anmerkung 116/150).

Die drei Zusagen, um die es geht, stehen in der Roadmap als Falle:
  1. jeder Tag bekommt seine Werte und seine Marke — auch wenn sie aus einer
     Spanne kamen;
  2. ein Tag, zu dem die Spanne NICHTS bringt, bekommt keine Marke (wie auf dem
     Einzelweg) und wird im selben Lauf nicht noch einmal gefragt;
  3. eine Spanne, die als GANZES scheitert, markiert nichts.
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import date, datetime, timedelta

import pytest

from app.models import BaselineLocation, DayMetric, Event, Location, Metric, Source
from app.services import enrichment
from app.services import weather as weather_svc
from app.services.enrichment import _REVISION_KEY, enrich_weather


class _Api:
    """Open-Meteo im Kleinen: eine Antwort je gefragtem Tag, `time` inklusive."""

    def __init__(self, *, empty: set[str] = frozenset(), fail_ranges: bool = False,
                 fail_all: bool = False):
        self.calls: list[tuple[str, str]] = []
        self.empty, self.fail_ranges, self.fail_all = set(empty), fail_ranges, fail_all

    def __call__(self, req, timeout=None):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
        start, end = q["start_date"][0], q["end_date"][0]
        self.calls.append((start, end))
        if self.fail_all or (self.fail_ranges and start != end):
            raise OSError("Netz weg")
        d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
        days = [(d0 + timedelta(n)).isoformat() for n in range((d1 - d0).days + 1)]
        val = lambda v: [None if d in self.empty else v for d in days]  # noqa: E731
        body = json.dumps({"daily": {
            "time": days,
            "temperature_2m_max": val(22.0), "temperature_2m_min": val(12.0),
            "weathercode": val(3), "sunshine_duration": val(3600.0),
            "rain_sum": val(0.0), "snowfall_sum": val(0.0),
            "windspeed_10m_max": val(10.0), "apparent_temperature_max": val(21.0),
            "apparent_temperature_min": val(11.0), "precipitation_hours": val(0.0),
            "sunrise": [None if d in self.empty else f"{d}T05:10" for d in days],
            "sunset": [None if d in self.empty else f"{d}T21:00" for d in days],
            "daylight_duration": val(57600.0), "windgusts_10m_max": val(20.0),
            "uv_index_max": val(5.0)}}).encode()

        class _Resp:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return body
        return _Resp()

    @property
    def ranges(self):
        return [c for c in self.calls if c[0] != c[1]]

    @property
    def singles(self):
        return [c for c in self.calls if c[0] == c[1]]


@pytest.fixture()
def api(monkeypatch):
    weather_svc.reset_cache()
    holder = {}

    def install(**kw):
        holder["api"] = _Api(**kw)
        monkeypatch.setattr(weather_svc.urllib.request, "urlopen", holder["api"])
        return holder["api"]
    yield install
    weather_svc.reset_cache()


def _home(db, user, start: date, end: date, lat=53.5511, lng=9.9937):
    loc = Location(user_id=user.id, name="Zuhause", lat=lat, lng=lng, city="Hamburg")
    db.add(loc)
    db.flush()
    db.add(BaselineLocation(user_id=user.id, location_id=loc.id,
                            date_start=start, date_end=end))
    db.flush()
    return loc


def _marked(db, user) -> set[date]:
    return {d for (d,) in db.query(DayMetric.day).filter(
        DayMetric.user_id == user.id, DayMetric.key == _REVISION_KEY).all()}


def test_thirty_residence_days_are_one_request(db, user, api):
    a = api()
    _home(db, user, date(2024, 3, 1), date(2024, 3, 30))
    enriched, remaining = enrich_weather(db, user_id=user.id)
    assert enriched == 30 and remaining == 0
    assert len(a.ranges) == 1 and not a.singles, a.calls
    # (1) jeder Tag hat Werte UND Marke, obwohl nur einmal gefragt wurde
    assert len(_marked(db, user)) == 30
    temps = db.query(DayMetric).filter(DayMetric.user_id == user.id,
                                       DayMetric.key == "temp_max_c").count()
    assert temps == 30


def test_a_long_period_is_split_by_year(db, user, api):
    a = api()
    _home(db, user, date(2020, 1, 1), date(2022, 12, 31))
    enrich_weather(db, user_id=user.id)
    assert len(a.ranges) == 3 and not a.singles, a.calls
    assert len(_marked(db, user)) == (date(2022, 12, 31) - date(2020, 1, 1)).days + 1


def test_a_day_the_range_has_nothing_for_gets_no_mark_and_no_second_request(db, user, api):
    """(2) — dasselbe Verhalten wie auf dem Einzelweg, nur ohne dessen zweite
    Anfrage: kein Wert, keine Marke; der nächste LAUF fragt wieder."""
    a = api(empty={"2024-03-10"})
    _home(db, user, date(2024, 3, 1), date(2024, 3, 20))
    enrich_weather(db, user_id=user.id)
    assert date(2024, 3, 10) not in _marked(db, user)
    assert len(_marked(db, user)) == 19
    assert len(a.calls) == 1, a.calls


def test_a_range_that_fails_falls_back_and_marks_what_arrives(db, user, api):
    a = api(fail_ranges=True)
    _home(db, user, date(2024, 3, 1), date(2024, 3, 5))
    enrich_weather(db, user_id=user.id)
    assert len(a.ranges) == 1          # EINMAL versucht, nicht je Tag
    assert len(a.singles) == 5         # dann der alte Weg
    assert len(_marked(db, user)) == 5


def test_a_run_that_reaches_nothing_marks_nothing(db, user, api):
    """(3) — die Gegenrichtung: kein Netz heißt keine Marke, sonst wäre der
    Tag für immer „erledigt", ohne je Wetter bekommen zu haben."""
    api(fail_all=True)
    _home(db, user, date(2024, 3, 1), date(2024, 3, 5))
    enriched, remaining = enrich_weather(db, user_id=user.id)
    assert enriched == 0 and remaining == 5
    assert _marked(db, user) == set()


def test_a_gap_of_more_than_a_week_starts_a_new_range(db, user, api):
    a = api()
    loc = Location(user_id=user.id, name="Büro", lat=53.60, lng=10.00, city="Hamburg")
    db.add(loc)
    db.flush()
    for d in (date(2024, 5, 1), date(2024, 5, 2), date(2024, 5, 3),
              date(2024, 6, 1), date(2024, 6, 2)):
        db.add(Event(user_id=user.id, title="Arbeit", category="event",
                     date_start=datetime.combine(d, datetime.min.time()).replace(hour=9),
                     location_id=loc.id, source=Source.manual))
    db.flush()
    enrich_weather(db, user_id=user.id)
    assert sorted(a.ranges) == [("2024-05-01", "2024-05-03"), ("2024-06-01", "2024-06-02")]
    assert not a.singles
    marks = db.query(Metric).filter(Metric.key == _REVISION_KEY).count()
    assert marks == 5


def test_a_later_batch_reads_from_the_cache(db, user, api):
    """Die Spanne wird aus ALLEN Kandidaten geplant — der Job läuft in Stapeln
    zu 25, und eine Spanne so kurz wie der Stapel wäre fast nichts gespart."""
    a = api()
    _home(db, user, date(2024, 1, 1), date(2024, 3, 31))
    total = 0
    while True:
        done, left = enrich_weather(db, limit=25, user_id=user.id)
        total += done
        if not left or not done:
            break
    assert total == 91
    assert len(a.calls) == 1, a.calls


def test_a_later_batch_of_events_reads_from_the_cache(db, user, api):
    """Dasselbe für EREIGNISSE — sie haben eine eigene Planung, und die erste
    Fassung dieses Tests (nur Wohnort-Tage) blieb grün, als diese Hälfte nur
    aus dem Stapel plante."""
    a = api()
    loc = Location(user_id=user.id, name="Büro", lat=53.60, lng=10.00, city="Hamburg")
    db.add(loc)
    db.flush()
    for n in range(60):
        db.add(Event(user_id=user.id, title="Arbeit", category="event",
                     date_start=datetime(2024, 5, 1, 9) + timedelta(days=n),
                     location_id=loc.id, source=Source.manual))
    db.flush()
    total = 0
    while True:
        done, left = enrich_weather(db, limit=25, user_id=user.id)
        total += done
        if not left or not done:
            break
    assert total == 60
    assert len(a.calls) == 1, a.calls


def test_a_replaced_single_path_gets_no_range_behind_its_back(db, user, api, monkeypatch):
    """Die Spanne füllt einen Cache, den nur das echte `fetch_weather` liest.
    Ist der Einzelweg ersetzt, wäre sie eine Netzanfrage an ihm vorbei."""
    a = api()
    monkeypatch.setattr(enrichment, "fetch_weather", lambda lat, lng, day: None)
    _home(db, user, date(2024, 3, 1), date(2024, 3, 10))
    enrich_weather(db, user_id=user.id)
    assert a.calls == []
