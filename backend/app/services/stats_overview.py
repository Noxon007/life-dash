"""A37 — die Statistik-Kacheln als serverseitige Ableitung.

Bis v0.31 rechnete der **Browser** diese Zahlen: `loadStats()` holte die volle
Ereignisliste (bei 12.000 Einträgen 19 MB) und reduzierte darüber — Orte,
Kategorien, Meilensteine, Umzüge, Wetter-Extreme, Diagramme. Das war der Grund,
warum die Statistik überhaupt die volle Liste brauchte, und damit der Grund,
warum ein serverseitiges Zeitfenster ohne diesen Umbau **still falsche** Zahlen
ergeben hätte: Ein Client, der nur noch ein Fenster kennt, zählt das Fenster.

Die Regeln sind absichtlich dieselben geblieben — die Zahlen sollen sich durch
den Umzug nicht ändern (`test_a37_window.py` vergleicht sie mit der alten
Client-Logik). Wo eine Regel Text auswertet (Ortsnamen kürzen, „Umzug"
erkennen), narrowt SQL nur vor und Python entscheidet, damit dieselbe
Bedingung gilt wie im Frontend.

Schicht 4: nichts gespeichert, alles bei jeder Abfrage neu gerechnet.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import (ConfirmState, Entity, Event, EventEntityLink, Location,
                        Metric, Source)

# Dieselben Muster wie im Frontend (dort als RegExp über „Titel + Beschreibung")
_MOVE_RE = re.compile(r"umzug|umgezogen|eingezogen", re.I)
_BIRTH_RE = re.compile(r"geburt|geboren|\bbirth\b", re.I)
_MOVE_WORDS = ("umzug", "umgezogen", "eingezogen")
_BIRTH_WORDS = ("geburt", "geboren", "birth")

# Nur diese Wetterwerte gehen in Kacheln und Diagramme ein. Die Metrik-Abfrage
# auf sie einzuschränken halbiert die Zeilen (16 Schlüssel je Ereignis).
_WX_KEYS = ("temperature_c", "temp_max_c", "temp_min_c", "sunshine_h",
            "rain_mm", "wind_max_kmh", "snow_cm")

TOP_N = 8


def _short_place(name: str | None) -> str | None:
    """Ortsname auf den ersten Bestandteil kürzen.

    Ohne das zählt jede Nominatim-Langadresse als eigener Ort — dieselbe Regel
    wie im Frontend (`placeOf`)."""
    if not name:
        return None
    return name.split(",")[0].strip() or None


def _age_years(birth: datetime, when: datetime) -> int:
    """Volle Jahre — wie die Frontend-Rechnung, ohne Bibliothek."""
    years = when.year - birth.year
    if (when.month, when.day) < (birth.month, birth.day):
        years -= 1
    return years


def _milestone_matches(db: Session, user_id: str, words: tuple[str, ...],
                       pattern: re.Pattern) -> list:
    """Meilensteine, deren Text die Regel trifft — chronologisch.

    SQL grenzt mit ILIKE grob ein (das kann der Index bedienen), entschieden
    wird mit demselben Ausdruck wie im Frontend. Sonst zählte der Server etwas
    anderes als die Oberfläche zeigte — die Klasse von Fehler, die dieses Paket
    gerade verhindern soll."""
    like = [Event.title.ilike(f"%{w}%") for w in words]
    like += [Event.description.ilike(f"%{w}%") for w in words]
    rows = (db.query(Event.id, Event.title, Event.description,
                     Event.date_start, Event.date_precision)
            .filter(Event.user_id == user_id, Event.category == "milestone",
                    or_(*like))
            .order_by(Event.date_start.asc().nullslast()).all())
    return [r for r in rows if pattern.search(f"{r.title} {r.description or ''}")]


def find_birth(db: Session, user_id: str) -> dict | None:
    """F17/Anmerkung 72: Das Geburtsdatum ist ein **Meilenstein**, kein Profilfeld.

    Der Zeitstrahl las es bisher aus der geladenen Ereignisliste. Mit dem
    Zeitfenster liegt die Geburt außerhalb jeder Seite außer der letzten — die
    Alters-Chips wären reihenweise verschwunden. Deshalb hier, an einer Stelle,
    für Statistik und Zeitstrahl gemeinsam."""
    for r in _milestone_matches(db, user_id, _BIRTH_WORDS, _BIRTH_RE):
        if r.date_start:
            return {"id": r.id, "title": r.title, "date_start": r.date_start,
                    "date_precision": r.date_precision.value}
    return None


def compute_overview(db: Session, user_id: str, *, today: datetime | None = None) -> dict:
    """Alle Zahlen des Statistik-Reiters in einer Antwort (wenige hundert Byte)."""
    mine = (Event.user_id == user_id,)

    # ---------------- reine Zählungen: das kann SQL am besten ----------------
    per_cat_rows = (db.query(Event.category, func.count(Event.id))
                    .filter(*mine).group_by(Event.category).all())
    per_cat = {c: n for c, n in per_cat_rows}
    total = sum(per_cat.values())
    unconfirmed = (db.query(func.count(Event.id))
                   .filter(*mine, Event.confirmed != ConfirmState.confirmed)
                   .scalar() or 0)
    year_col = func.extract("year", Event.date_start)
    per_year = [[int(y), n] for y, n in
                (db.query(year_col.label("y"), func.count(Event.id))
                 .filter(*mine, Event.date_start.isnot(None))
                 .group_by("y").order_by("y").all())]

    # ---------------- Orte: gruppiert in SQL, gekürzt in Python --------------
    # Nach Location.name gruppieren heißt: nur die *verschiedenen* Namen landen
    # in Python (Tausende), nicht alle Ereignisse (Zehntausende).
    place_rows = (db.query(Location.name, func.count(Event.id))
                  .join(Event, Event.location_id == Location.id)
                  .filter(*mine, Location.name.isnot(None))
                  .group_by(Location.name).all())
    per_place: dict[str, int] = {}
    for name, n in place_rows:
        short = _short_place(name)
        if short:
            per_place[short] = per_place.get(short, 0) + n
    top_places = sorted(per_place.items(), key=lambda kv: -kv[1])[:TOP_N]

    # ---------------- Textregeln: SQL grenzt ein, Python entscheidet ---------
    moves = len(_milestone_matches(db, user_id, _MOVE_WORDS, _MOVE_RE))
    birth = find_birth(db, user_id)
    age = _age_years(birth["date_start"], today or datetime.now()) if birth else None

    # ---------------- Tiere: über die Verknüpfungen ------------------------
    animal_rows = (db.query(Entity.name, Entity.id, func.count(EventEntityLink.id))
                   .join(EventEntityLink, EventEntityLink.entity_id == Entity.id)
                   .join(Event, Event.id == EventEntityLink.event_id)
                   .filter(*mine, Entity.type == "animal")
                   .group_by(Entity.name, Entity.id)
                   .order_by(func.count(EventEntityLink.id).desc())
                   .limit(TOP_N).all())
    top_animals = [[name, n, eid] for name, eid, n in animal_rows]

    weather = _weather_stats(db, user_id)

    return {
        "counts": {
            "events": total,
            "unconfirmed": unconfirmed,
            "places": len(per_place),
            "concerts": per_cat.get("concert", 0),
            "milestones": per_cat.get("milestone", 0),
            "meals": per_cat.get("meal", 0),
            "moves": moves,
        },
        "birth": birth,
        "age": age,
        "per_year": per_year,
        "per_category": sorted(per_cat.items(), key=lambda kv: -kv[1]),
        "top_places": [[name, n] for name, n in top_places],
        "top_animals": top_animals,
        **weather,
    }


def _weather_stats(db: Session, user_id: str) -> dict:
    """Wetter-Extreme (je Ereignis) und Wetter-Bilanz (je KALENDERTAG, A31).

    Beides braucht die Werte je Ereignis, deshalb ein gemeinsamer Durchgang.
    Geladen werden Tupel, keine ORM-Objekte — das war die Lehre aus
    Anmerkung 80: die Objekterzeugung über eine volle Ergebnismenge ist der
    teure Teil, nicht das Finden der Zeilen."""
    base = (db.query(Event.id, Event.title, Event.date_start, Event.date_precision,
                     Event.category, Event.parent_event_id, Location.name)
            .outerjoin(Location, Event.location_id == Location.id)
            .filter(Event.user_id == user_id, Event.date_start.isnot(None)))
    events = {r.id: r for r in base.all()}
    if not events:
        return _empty_weather()

    values: dict[str, dict[str, float]] = {}
    rows = (db.query(Metric.event_id, Metric.key, Metric.value)
            .join(Event, Event.id == Metric.event_id)
            .filter(Event.user_id == user_id, Metric.source == Source.weather,
                    Metric.key.in_(_WX_KEYS), Metric.value.isnot(None))
            .all())
    for eid, key, value in rows:
        if eid in events:
            values.setdefault(eid, {})[key] = value
    if not values:
        return _empty_weather()

    def val(eid: str, *keys: str) -> float | None:
        vals = values.get(eid) or {}
        for k in keys:
            if vals.get(k) is not None:
                return vals[k]
        return None

    def card(eid: str, value: float) -> dict:
        e = events[eid]
        # Auf eine Nachkommastelle: die Kachel zeigt den Wert unverändert an,
        # und „24.99268360643208 °C" wäre keine Aussage, sondern ein Rohwert.
        return {"value": round(value, 1), "id": eid, "title": e.title,
                "date_start": e.date_start,
                "date_precision": e.date_precision.value,
                "place": _short_place(e.name)}

    # --- Extreme: je Ereignis, nicht je Tag (die heißeste Stunde zählt) ---
    extremes: dict[str, dict | None] = {}
    hot = cold = None
    for eid in values:
        hi = val(eid, "temp_max_c", "temperature_c")
        if hi is not None and (hot is None or hi > hot[1]):
            hot = (eid, hi)
        lo = val(eid, "temp_min_c", "temperature_c")
        if lo is not None and (cold is None or lo < cold[1]):
            cold = (eid, lo)
    extremes["hot"] = card(*hot) if hot else None
    extremes["cold"] = card(*cold) if cold else None
    for name, key in (("sunny", "sunshine_h"), ("rainy", "rain_mm"),
                      ("windy", "wind_max_kmh"), ("snowy", "snow_cm")):
        best = None
        for eid in values:
            v = val(eid, key)
            if v is not None and v > 0 and (best is None or v > best[1]):
                best = (eid, v)
        extremes[name] = card(*best) if best else None

    # --- Bilanz: EIN Datensatz je Kalendertag (A31/Anmerkung 64) ---
    # Ein importierter Tag trägt dutzende Besuche mit demselben Wetter; über
    # Einträge gerechnet kämen mehr als 365 Regentage im Jahr heraus.
    by_day: dict[str, str] = {}
    for eid in sorted(values, key=lambda i: (events[i].date_start, i)):
        day = events[eid].date_start.date().isoformat()
        by_day.setdefault(day, eid)
    day_ids = list(by_day.values())

    rain_days = sum(1 for i in day_ids if (val(i, "rain_mm") or 0) >= 1)
    sun_hours = round(sum(val(i, "sunshine_h") or 0 for i in day_ids))
    rain_per_year: dict[int, int] = {}
    for i in day_ids:
        y = events[i].date_start.year
        rain_per_year.setdefault(y, 0)
        if (val(i, "rain_mm") or 0) >= 1:
            rain_per_year[y] += 1

    # Wärmste Reise: Mittel über die TAGE einer Reise, nicht über ihre Einträge
    trips: dict[str, list] = {}
    for i in day_ids:
        e = events[i]
        temp = val(i, "temperature_c")
        if e.category != "trip" or temp is None:
            continue
        key = e.parent_event_id or i
        entry = trips.setdefault(key, [0.0, 0, e.title])
        entry[0] += temp
        entry[1] += 1
    warmest = None
    for total_temp, n, title in trips.values():
        avg = total_temp / n
        if warmest is None or avg > warmest["avg"]:
            warmest = {"avg": round(avg, 1), "title": title}

    return {
        "extremes": extremes,
        "weather": {
            "days": len(day_ids),
            "sun_hours": sun_hours,
            "rain_days": rain_days,
            "rain_share": round(rain_days / len(day_ids) * 100) if day_ids else 0,
            "warmest_trip": warmest,
            "rain_days_per_year": [[y, n] for y, n in sorted(rain_per_year.items())],
        },
    }


def _empty_weather() -> dict:
    return {
        "extremes": {k: None for k in ("hot", "cold", "sunny", "rainy", "windy", "snowy")},
        "weather": {"days": 0, "sun_hours": 0, "rain_days": 0, "rain_share": 0,
                    "warmest_trip": None, "rain_days_per_year": []},
    }
