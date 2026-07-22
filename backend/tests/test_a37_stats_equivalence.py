"""A37 — Beweis, dass der Umzug der Statistik die ZAHLEN nicht verändert hat.

Bis v0.31 rechnete der Browser die Statistik-Kacheln über die volle
Ereignisliste. Dieser Test schreibt jene Regeln **unabhängig noch einmal auf**
(portiert aus dem entfernten `loadStats()`/`renderWeatherSummary()`, siehe
Commit 61c9bd8) und vergleicht sie mit `compute_overview` — auf absichtlich
unordentlichen Daten: Tage mit mehreren Einträgen, Orte mit Langadressen,
Wetter mal vollständig, mal nur als Tagesmittel, Undatiertes, Unbestätigtes.

Warum eine zweite Implementierung statt fester Erwartungswerte: Feste Zahlen
prüfen nur, dass der Code tut, was ich beim Schreiben dachte. Eine unabhängig
formulierte Regel prüft, dass er tut, was die App **vorher** tat — und das ist
hier die eigentliche Zusage.

Eine bewusste Abweichung ist unten festgehalten und geprüft (Geburt/„birth").
"""
from __future__ import annotations

import re
from datetime import datetime

from app.models import (ConfirmState, DatePrecision, Entity, Event,
                        EventEntityLink, Location, Metric, Source)
from app.services.stats_overview import compute_overview

NOW = datetime(2026, 7, 22)


# --------------------------------------------------------------------------- #
# Die ALTEN Regeln, aus dem entfernten Frontend-Code portiert
# --------------------------------------------------------------------------- #
def _old_rules(events: list[dict]) -> dict:
    place_of = lambda e: (e["place"].split(",")[0].strip() or None) if e.get("place") else None
    text_of = lambda e: f"{e['title']} {e.get('description') or ''}".lower()
    metric_of = lambda e, *keys: next(
        (e["m"][k] for k in keys if e["m"].get(k) is not None), None)

    milestones = [e for e in events if e["category"] == "milestone"]
    places = {p for p in (place_of(e) for e in events) if p}

    births = sorted((e for e in milestones
                     if e["date"] and re.search(r"geburt|geboren", text_of(e))),
                    key=lambda e: e["date"])
    age = None
    if births:
        b = births[0]["date"]
        age = NOW.year - b.year - ((NOW.month, NOW.day) < (b.month, b.day))

    # Extreme je EINTRAG
    hot = cold = None
    for e in events:
        hi = metric_of(e, "temp_max_c", "temperature_c")
        if hi is not None and (hot is None or hi > hot):
            hot = hi
        lo = metric_of(e, "temp_min_c", "temperature_c")
        if lo is not None and (cold is None or lo < cold):
            cold = lo

    def metric_max(key):
        best = None
        for e in events:
            v = metric_of(e, key)
            if v is not None and v > 0 and (best is None or v > best):
                best = v
        return best

    # Bilanz je KALENDERTAG (A31): erster Eintrag des Tages mit Wetter gewinnt
    with_weather = [e for e in events
                    if metric_of(e, "temperature_c", "temp_max_c") is not None]
    by_day: dict[str, dict] = {}
    for e in sorted(with_weather, key=lambda e: e["date"]):
        by_day.setdefault(e["date"].date().isoformat(), e)
    days = list(by_day.values())

    trips: dict[str, list] = {}
    for e in days:
        temp = metric_of(e, "temperature_c")
        if e["category"] != "trip" or temp is None:
            continue
        k = e.get("parent") or e["id"]
        entry = trips.setdefault(k, [0.0, 0])
        entry[0] += temp
        entry[1] += 1
    warmest = max((s / n for s, n in trips.values()), default=None)

    per_year: dict[int, int] = {}
    for e in events:
        if e["date"]:
            per_year[e["date"].year] = per_year.get(e["date"].year, 0) + 1

    per_place: dict[str, int] = {}
    for e in events:
        p = place_of(e)
        if p:
            per_place[p] = per_place.get(p, 0) + 1

    return {
        "events": len(events),
        "unconfirmed": sum(1 for e in events if not e["confirmed"]),
        "places": len(places),
        "concerts": sum(1 for e in events if e["category"] == "concert"),
        "milestones": len(milestones),
        "meals": sum(1 for e in events if e["category"] == "meal"),
        "moves": sum(1 for e in milestones
                     if re.search(r"umzug|umgezogen|eingezogen", text_of(e))),
        "age": age,
        "hot": hot, "cold": cold,
        "sunny": metric_max("sunshine_h"), "rainy": metric_max("rain_mm"),
        "windy": metric_max("wind_max_kmh"), "snowy": metric_max("snow_cm"),
        "wx_days": len(days),
        "rain_days": sum(1 for e in days if (metric_of(e, "rain_mm") or 0) >= 1),
        "sun_hours": round(sum(metric_of(e, "sunshine_h") or 0 for e in days)),
        "warmest_trip": round(warmest, 1) if warmest is not None else None,
        "per_year": sorted(per_year.items()),
        "top_places": sorted(per_place.items(), key=lambda kv: -kv[1])[:8],
    }


# --------------------------------------------------------------------------- #
# Ein absichtlich unordentlicher Bestand
# --------------------------------------------------------------------------- #
def _messy_dataset(db, user) -> list[dict]:
    """Beides bauen: die Datenbank UND die Vergleichsliste für die alten Regeln."""
    mirror: list[dict] = []

    def add(title, *, category="event", date=None, place=None, confirmed=True,
            description=None, parent=None, source=Source.manual, **wx):
        loc = None
        if place:
            loc = Location(user_id=user.id, name=place, lat=53.0, lng=10.0)
            db.add(loc)
            db.flush()
        e = Event(user_id=user.id, title=title, description=description,
                  category=category, date_start=date, location=loc,
                  parent_event_id=parent, source=source,
                  date_precision=DatePrecision.day if date else DatePrecision.year,
                  confirmed=ConfirmState.confirmed if confirmed
                  else ConfirmState.unconfirmed)
        db.add(e)
        db.flush()
        for key, value in wx.items():
            db.add(Metric(event_id=e.id, key=key, value=value, source=Source.weather))
        mirror.append({"id": e.id, "title": title, "description": description,
                       "category": category, "date": date, "place": place,
                       "confirmed": confirmed, "parent": parent, "m": dict(wx)})
        return e

    # Geburt + ein Geburtstag (beide treffen die Regel — auch früher schon)
    add("Geburt", category="milestone", date=datetime(1990, 4, 12))
    add("Geburtstag von Anna", category="milestone", date=datetime(2015, 3, 3))
    # Umzüge: im Titel, in der Beschreibung, und ein Nicht-Treffer
    add("Umzug nach Kiel", category="milestone", date=datetime(2010, 5, 1))
    add("Erste Wohnung", category="milestone", date=datetime(2011, 9, 1),
        description="Endlich eingezogen.")
    add("Abitur", category="milestone", date=datetime(2009, 6, 20))
    # Orte: dieselbe Stadt in drei Schreibweisen, einer ohne Ort
    add("Konzert A", category="concert", date=datetime(2024, 1, 5),
        place="Berlin, Deutschland", temperature_c=4.0, rain_mm=0.0)
    add("Konzert B", category="concert", date=datetime(2024, 2, 6),
        place="Berlin, Berlin, Deutschland", temp_min_c=-3.0, temp_max_c=2.0,
        rain_mm=1.4, sunshine_h=1.5)
    add("Konzert ohne Ort", category="concert", date=datetime(2024, 3, 7))
    add("Abendessen", category="meal", date=datetime(2024, 4, 8), place="Kiel")
    # Ein importierter Tag: fünf Besuche, dasselbe Wetter (A31-Falle)
    for hour in range(9, 14):
        add(f"Besuch {hour}", date=datetime(2024, 6, 15, hour), place="Hamburg, Hansestadt",
            source=Source.google_timeline, temperature_c=19.0, rain_mm=3.2,
            sunshine_h=2.0, temp_max_c=22.0, temp_min_c=15.0)
    # Reise mit zwei Tages-Kindern, jedes Kind zweimal am Tag
    trip = add("Andalusien", category="trip", date=datetime(2023, 8, 1))
    for day, temp in ((1, 30.0), (2, 36.0)):
        add(f"Tag {day} vormittags", category="trip", parent=trip.id,
            date=datetime(2023, 8, day, 9), temperature_c=temp,
            temp_max_c=temp + 5, sunshine_h=11.0)
        add(f"Tag {day} abends", category="trip", parent=trip.id,
            date=datetime(2023, 8, day, 21), temperature_c=temp - 8,
            sunshine_h=0.0)
    # Extremwerte, teils nur als Tagesmittel (Altbestand)
    add("Frosttag", date=datetime(2021, 2, 12), temp_min_c=-18.5, temp_max_c=-4.0,
        snow_cm=24.0)
    add("Sturm", date=datetime(2022, 1, 30), temperature_c=6.0, wind_max_kmh=118.0)
    add("Altbestand", date=datetime(2015, 7, 3), temperature_c=27.5)
    # Undatiert und unbestätigt
    add("Irgendwann in den Neunzigern", date=None)
    add("Vorschlag der KI", date=datetime(2026, 1, 2), confirmed=False)
    db.commit()
    return mirror


def test_the_numbers_did_not_change(db, user):
    mirror = _messy_dataset(db, user)
    old = _old_rules(mirror)
    new = compute_overview(db, user.id, today=NOW)
    c, ex, wx = new["counts"], new["extremes"], new["weather"]

    assert c["events"] == old["events"]
    assert c["unconfirmed"] == old["unconfirmed"]
    assert c["places"] == old["places"]
    assert c["concerts"] == old["concerts"]
    assert c["milestones"] == old["milestones"]
    assert c["meals"] == old["meals"]
    assert c["moves"] == old["moves"]
    assert new["age"] == old["age"]

    assert ex["hot"]["value"] == old["hot"]
    assert ex["cold"]["value"] == old["cold"]
    assert ex["sunny"]["value"] == old["sunny"]
    assert ex["rainy"]["value"] == old["rainy"]
    assert ex["windy"]["value"] == old["windy"]
    assert ex["snowy"]["value"] == old["snowy"]

    assert wx["days"] == old["wx_days"]
    assert wx["rain_days"] == old["rain_days"]
    assert wx["sun_hours"] == old["sun_hours"]
    assert wx["warmest_trip"]["avg"] == old["warmest_trip"]

    assert [tuple(y) for y in new["per_year"]] == old["per_year"]
    assert [tuple(p) for p in new["top_places"]] == old["top_places"]


def test_the_one_deliberate_difference_is_the_english_birth(db, user):
    """Die einzige bewusste Abweichung, hier festgehalten statt versteckt.

    Die alte Statistik-Kachel erkannte die Geburt mit `geburt|geboren`, der
    Zeitstrahl (F17) aber mit `geburt|geboren|birth`. Zwei Regeln für eine
    Tatsache — in einer zweisprachigen App (F10) ist das schlicht ein Fehler.
    Der Server benutzt jetzt für beide dieselbe Regel; in einer deutschen
    Datenbank ändert das nichts, in einer englischen zeigt die Kachel endlich
    dasselbe Alter wie die Chips am Zeitstrahl."""
    db.add(Event(user_id=user.id, title="Birth", category="milestone",
                 date_start=datetime(1985, 6, 1), date_precision=DatePrecision.day,
                 source=Source.manual, confirmed=ConfirmState.confirmed))
    db.commit()

    ov = compute_overview(db, user.id, today=NOW)
    assert ov["birth"] is not None and ov["age"] == 41


def test_top_animals_match_the_old_counting(db, user):
    """Tiere wurden vorher über die Entity-Verweise der Ereignisse gezählt."""
    names = ["Fuchs", "Graureiher", "Eisvogel"]
    ents = []
    for n in names:
        ent = Entity(user_id=user.id, type="animal", name=n,
                     confirmed=ConfirmState.confirmed)
        db.add(ent)
        db.flush()
        ents.append(ent)
    counts = {"Fuchs": 5, "Graureiher": 2, "Eisvogel": 1}
    for ent in ents:
        for i in range(counts[ent.name]):
            e = Event(user_id=user.id, title=f"{ent.name} {i}", category="sighting",
                      date_start=datetime(2024, 5, i + 1),
                      date_precision=DatePrecision.day, source=Source.manual,
                      confirmed=ConfirmState.confirmed)
            db.add(e)
            db.flush()
            db.add(EventEntityLink(event_id=e.id, entity_id=ent.id))
    db.commit()

    top = compute_overview(db, user.id)["top_animals"]
    assert [(n, c) for n, c, _ in top] == [("Fuchs", 5), ("Graureiher", 2),
                                           ("Eisvogel", 1)]
