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
from datetime import date as date_type
from datetime import datetime, time
from typing import NamedTuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.sqlutil import day_number
from app.models import (ConfirmState, DatePrecision, DayMetric, Entity, Event,
                        EventEntityLink, Location, Metric, Source)
from app.services import baseline, weather_day

# Dieselben Muster wie im Frontend (dort als RegExp über „Titel + Beschreibung")
_MOVE_RE = re.compile(r"umzug|umgezogen|eingezogen", re.I)
_BIRTH_RE = re.compile(r"geburt|geboren|\bbirth\b", re.I)
_MOVE_WORDS = ("umzug", "umgezogen", "eingezogen")
_BIRTH_WORDS = ("geburt", "geboren", "birth")

# Nur diese Wetterwerte gehen in Kacheln und Diagramme ein. Die Metrik-Abfrage
# auf sie einzuschränken halbiert die Zeilen (16 Schlüssel je Ereignis).
_WX_KEYS = ("temperature_c", "temp_max_c", "temp_min_c", "sunshine_h",
            "rain_mm", "wind_max_kmh", "snow_cm",
            # Anmerkung 114: F12 holt diese Werte seit 0.22 bei JEDER
            # Anreicherung mit — aus demselben Aufruf, ohne Zusatzkosten. Sie
            # standen bisher nur in der Detailansicht eines einzelnen
            # Ereignisses. Gespeicherte Daten, die nirgends zusammengefasst
            # werden, sind Ballast; ein Rekord ist der Sinn eines Extremwerts.
            "uv_max", "gust_max_kmh", "apparent_temp_max_c",
            "apparent_temp_min_c", "daylight_h",
            # Anmerkung 189: Regenstunden. Seit F12 geholt und bis hierher in
            # keiner Zusammenfassung — genau der Ballast, den der Absatz
            # darüber beschreibt. „Nassester Tag" misst Millimeter; wie LANGE
            # es geregnet hat, ist eine andere Frage, und ERA5 beantwortet sie
            # (geprüft: 18 h am 21.06.2024 in Hamburg, gegen 0 h zwei Tage
            # später).
            "rain_h")

# Extremwert-Kacheln: Name -> (Metrik-Schlüssel …, Richtung, nur echte Werte?)
# „nur echte Werte" heißt: 0 zählt nicht als Rekord. Bei Regen und Schnee ist
# das richtig (der trockenste Tag ist kein „nassester Tag"), bei Tageslicht
# wäre es falsch — die Polarnacht mit 0 h IST der kürzeste Tag, und zwar der
# interessanteste Wert der ganzen Kachel.
_EXTREMES: tuple[tuple[str, tuple[str, ...], str, bool], ...] = (
    ("hot", ("temp_max_c", "temperature_c"), "max", False),
    ("cold", ("temp_min_c", "temperature_c"), "min", False),
    ("sunny", ("sunshine_h",), "max", True),
    ("rainy", ("rain_mm",), "max", True),
    ("windy", ("wind_max_kmh",), "max", True),
    ("snowy", ("snow_cm",), "max", True),
    # --- neu (F12-Werte, Anmerkung 114) ---
    # Anmerkung 123 (2026-07-24): "uv" ("Stärkste Sonne") ist raus. Open-Meteos
    # Archiv (ERA5) liefert `uv_index_max` für historische Tage grundsätzlich
    # `null` (live geprüft) — die Kachel konnte nie füllen. UV gibt es nur über
    # die historical-forecast-API und nur ab ~2022; das wäre ein zweiter
    # Endpunkt mit eigenen Fehlerpfaden, kein Kachelwert. "Sonnigster Tag"
    # (Sonnenstunden, oben) deckt "Sonne" ab und steht IM Archiv.
    # Anmerkung 189: „am längsten geregnet" — eine andere Frage als „am
    # meisten geregnet" (`rainy`, Millimeter). Ein Landregen über 18 Stunden
    # und ein Wolkenbruch von zwanzig Minuten können dieselbe Menge bringen.
    # `positive_only`, weil 0 h kein Rekord ist, sondern ein trockener Tag.
    ("rain_long", ("rain_h",), "max", True),
    ("gust", ("gust_max_kmh",), "max", True),
    ("felt_hot", ("apparent_temp_max_c",), "max", False),
    ("felt_cold", ("apparent_temp_min_c",), "min", False),
    ("longest_day", ("daylight_h",), "max", True),
    ("shortest_day", ("daylight_h",), "min", False),
)

TOP_N = 8


def _short_place(name: str | None) -> str | None:
    """Ortsname auf den ersten Bestandteil kürzen.

    Ohne das zählt jede Nominatim-Langadresse als eigener Ort — dieselbe Regel
    wie im Frontend (`placeOf`)."""
    if not name:
        return None
    return name.split(",")[0].strip() or None


def _as_day(value) -> date_type | None:
    """Was aus einer `Date`-Spalte kommt, als `date`.

    Beide Dialekte liefern hier ein `date`; die Zeichenketten-Rückfallebene
    steht trotzdem da, weil dieselbe Spalte über `union_all` und Subqueries
    läuft und SQLite dort schon einmal Text zurückgegeben hat (`recorded_days`
    trägt denselben Satz)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_type):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _by_count(item: tuple[str, int]) -> tuple[int, str]:
    """Sortierschlüssel für „viele zuerst, bei Gleichstand alphabetisch".

    **Anmerkung 199 — die zweite Stufe ist nicht Kosmetik.** `sorted` ist
    stabil, die Reihenfolge bei Gleichstand ist also die des `place_rows`, und
    die kommt aus einem `GROUP BY` ohne `ORDER BY`: auf PostgreSQL entscheidet
    darüber die Hash-Aggregation, also die Datenbank und nicht die Zahl. Zwei
    Orte mit je 40 Tagen konnten damit bei jedem Laden die Plätze tauschen —
    und, schlimmer, gegen die Rangliste direkt darunter stehen, die seit
    Anmerkung 156 genau diesen Stichentscheid führt (`_ranked`: Tage, Einträge,
    Wert). Die Regel stand an zwei Orten und lief still auseinander.
    """
    name, count = item
    return (-count, name)


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
    # Anmerkung 143: gezählt werden TAGE, nicht Einträge. „Zuhause: 4.812"
    # war nach dem Timeline-Import keine Auskunft über das Leben, sondern über
    # die Zufuhr — dreißig Besuche an einem Tag sind ein Tag. Dieselbe
    # Korrektur, die A31/Anmerkung 64 für die Wettertafeln schon gemacht hat;
    # sie hatte hier nur nie stattgefunden.
    day_key = day_number(Event.date_start)
    # Anmerkung 197: Koordinaten mit, und deshalb auch nach ihnen gruppiert —
    # ein Ort im Umkreis eines Wohnorts trägt dessen Namen, und ohne
    # Koordinate ließe sich das nicht fragen. Die Regel steht in
    # `baseline.home_naming`, weil die Rangliste darunter dieselbe liest:
    # zwei Umbenennungen wären zwei Antworten auf dieselbe Frage, und die
    # beiden Ansichten stehen im selben Reiter untereinander.
    place_rows = (db.query(Location.name, Location.lat, Location.lng,
                           func.count(func.distinct(day_key)))
                  .join(Event, Event.location_id == Location.id)
                  .filter(*mine, Location.name.isnot(None),
                          Event.date_start.isnot(None))
                  .group_by(Location.name, Location.lat, Location.lng).all())
    at_home = baseline.home_naming(db, user_id)
    # F20: Die abgeleiteten Tage zählen VOLL mit (Entscheidung des Users zu
    # Anmerkung 144). Ein Kindheitstag im Elternhaus war ein Tag in Bad
    # Segeberg — eine Statistik, die ihn wegließe, beschriebe die Aufzeichnung
    # und nicht das Leben. Addieren ist hier gefahrlos und zwar nicht aus
    # Nachlässigkeit: der Wohnort füllt nur LÜCKEN, die beiden Tagesmengen
    # sind also disjunkt (`services/baseline.py`). Einmal geholt, viermal
    # benutzt — sonst liefe der Kalender für Orte, Städte und Zähler dreimal.
    b_days = baseline.day_counts(db, user_id)
    per_place: dict[str, int] = {}
    for name, lat, lng, n in place_rows:
        short = _short_place(at_home(name, lat, lng))
        if short:
            per_place[short] = per_place.get(short, 0) + n
    for name, n in b_days["places"].items():
        # Gekürzt wie die Ereignis-Orte daneben — sonst stünde derselbe Ort
        # zweimal in derselben Liste, einmal lang und einmal kurz.
        short = _short_place(name)
        if short:
            per_place[short] = per_place.get(short, 0) + n
    top_places = sorted(per_place.items(), key=_by_count)[:TOP_N]

    # ---------------- A39: Städte ------------------------------------------
    # Eigenes Feld statt Namens-Textteil: `Location.name` hängt davon ab,
    # welche Bausteine der Nutzer gewählt hat (`place_name_parts`) — wer
    # „Stadt" abgewählt hat, hätte hier gar keine. Der Leerstring bedeutet
    # „nachgesehen, gibt es hier nicht" und zählt darum nicht mit.
    city_rows = (db.query(Location.city, func.count(func.distinct(day_key)))
                 .join(Event, Event.location_id == Location.id)
                 .filter(*mine, Location.city.isnot(None), Location.city != "",
                         Event.date_start.isnot(None))
                 .group_by(Location.city).all())
    per_city = {c: n for c, n in city_rows}
    for city, n in b_days["cities"].items():
        per_city[city] = per_city.get(city, 0) + n
    top_cities = sorted(per_city.items(), key=_by_count)[:TOP_N]

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
                   # Derselbe Stichentscheid wie oben — hier zusätzlich nötig,
                   # weil das `LIMIT` bei Gleichstand entscheidet, WER
                   # überhaupt in der Liste steht, nicht nur an welcher Stelle.
                   .order_by(func.count(EventEntityLink.id).desc(),
                             Entity.name.asc())
                   .limit(TOP_N).all())
    top_animals = [[name, n, eid] for name, eid, n in animal_rows]

    weather = _weather_stats(db, user_id)

    return {
        "counts": {
            "events": total,
            "unconfirmed": unconfirmed,
            "places": len(per_place),
            "cities": len(per_city),        # A39
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
        "top_cities": [[name, n] for name, n in top_cities],   # A39
        "top_animals": top_animals,
        # F20: die abgeleiteten Tage als EIGENE Zahl neben allem anderen. Sie
        # stecken in `top_places`/`top_cities` bereits drin (sie zählen voll
        # mit) — hier steht, WIE VIELE es sind, damit die Oberfläche es sagen
        # kann. A40: was eine Ansicht mitrechnet, muss sie auch nennen können.
        "baseline_days": b_days["total"],
        **weather,
    }


class WeatherSource(NamedTuple):
    """Alles, was eine Wetter-Auskunft braucht — als EIN Ding.

    Anmerkung 194: Vorher waren es vier lose Rückgabewerte, und als die
    Wohnort-Tage dazukamen, wären es sechs geworden. Eine benannte Struktur ist
    hier nicht Geschmack, sondern die Absicherung gegen genau den Defekt, der
    diese Anmerkung ausgelöst hat: **eine zweite Auswertung, die eine der
    Quellen einfach nicht mitgibt.** Wer `WeatherSource` bekommt, bekommt beide.
    """
    events: dict            # {id: Ereignis-Tupel}
    values: dict            # {id: {Schlüssel: Wert}} — Wetter je Ereignis
    val: object             # (id, *keys) -> Wert, mit Schlüssel-Kette
    card: object            # (id, Wert) -> Rekord-Zeile
    days: dict              # {Tag: {Schlüssel: Wert}} — Wohnort-Tage (F20)
    day_card: object        # (Tag, Wert) -> Rekord-Zeile


def _extreme_tops(src: WeatherSource, n: int) -> dict[str, list[dict]]:
    """Die besten `n` **Tage** je Extremwert — die Rangfolge an EINER Stelle.

    Die Kachel im Statistik-Reiter nimmt davon den Kopf, die Top-Liste
    (Anmerkung 156) die ganze Liste. Beide lesen dieselben Regeln: welcher
    Metrik-Schlüssel gilt, in welche Richtung verglichen wird und ob eine Null
    ein Rekord sein kann (`positive_only`). Die letzte ist der Grund, warum das
    hier nicht zweimal stehen darf — bei Regen ist 0 kein Rekord, beim
    Tageslicht ist die Polarnacht mit 0 h der interessanteste Wert überhaupt.

    **Anmerkung 161: ein Tag steht genau einmal in der Liste.** Bis hierher war
    die Rangfolge eine über EREIGNISSE, und das war schon immer eine Antwort auf
    eine Frage, die niemand gestellt hat: die Kachel heißt „Kältester **Tag**",
    der Klick führt seit Anmerkung 142 zum Tag, und die Liste darunter zeigte
    zehnmal denselben 11.1.2026, weil an dem Tag zehn Fotos liegen. Mit
    Anmerkung 139 ist jedes Foto ein Ereignis geworden — damit hat sich nicht
    die Regel geändert, sondern das, was sie zählt. Ein Bestand entscheidet
    darüber, ob eine Rangliste eine Auskunft ist oder eine Zählung der Zufuhr
    (dieselbe Verschiebung wie in Anmerkung 143).

    **Welcher Ort den Tag vertritt, entscheidet die Richtung des Rekords.** Beim
    kältesten Tag der kälteste Ort, beim heißesten der heißeste — das ist keine
    zweite Regel neben Anmerkung 119 („der Tageswert ist der vorsichtige"),
    sondern eine andere Frage: 119 beantwortet, was ein Tag BEISTEUERT, ein
    Rekord, wie extrem es an diesem Tag überhaupt wurde. Den vorsichtigen Wert
    hier zu nehmen hieße, den heißesten Tag am kühlsten seiner Orte zu messen.
    `direction` steht schon in `_EXTREMES`, es kommt also keine Angabe dazu.

    **Anmerkung 194: die Wohnort-Tage stehen mit in der Rangfolge**, und
    deshalb nimmt diese Funktion die ganze `WeatherSource` statt einer Auswahl
    daraus. Als Einzelparameter mit Vorbelegung wäre der Defekt genau so
    wiedergekommen, wie er entstanden ist: die zweite Auswertung (die
    Top-Listen) hätte eine Quelle einfach nicht mitgegeben, und niemandem wäre
    eine fehlende Zeile aufgefallen.
    """
    events, values, val, card, days, day_card = (
        src.events, src.values, src.val, src.card, src.days, src.day_card)
    out: dict[str, list[dict]] = {}
    for name, keys, direction, positive_only in _EXTREMES:
        # Je Tag der Anwärter, der ihn vertritt: (Stichentscheid, Wert, Kennung
        # oder None). `None` heißt „abgeleiteter Tag" — die Karte baut dann
        # `day_card`. Ein Tag kann nie beides sein (F20: der Wohnort füllt nur
        # Lücken), die beiden Mengen treten sich also nicht in die Quere.
        best: dict[object, tuple[str, float, object]] = {}

        def offer(day, v, eid=None):
            if v is None or (positive_only and v <= 0):
                return
            # Bei Gleichstand innerhalb eines Tages gewinnt die kleinere
            # Kennung — aus demselben Grund wie bei der Sortierung unten: ohne
            # eine zweite Stufe entschiede die Reihenfolge der Dict-Iteration,
            # welcher Ort neben dem Datum steht.
            tie = eid or ""
            cur = best.get(day)
            if cur is None or (v > cur[1] if direction == "max" else v < cur[1]) \
                    or (v == cur[1] and tie < cur[0]):
                best[day] = (tie, v, eid)

        for eid in values:
            when = getattr(events.get(eid), "date_start", None)
            if when is not None:
                offer(when.date(), val(eid, *keys), eid)
        for day, vals in days.items():
            # Dieselbe Schlüssel-Kette wie `val` bei den Ereignissen —
            # `temp_max_c`, sonst `temperature_c`. Zwei Fassungen davon liefen
            # still auseinander, und die zweite stünde hier.
            v = next((vals[k] for k in keys if vals.get(k) is not None), None)
            offer(day, v)

        # Der Stichentscheid als zweites Sortierkriterium: bei gleichen Werten —
        # nach dem Runden auf eine Nachkommastelle keine Seltenheit — wäre die
        # Reihenfolge sonst die der Dict-Iteration und damit zwischen zwei
        # Aufrufen verschieden. Eine Rangliste, die bei jedem Laden anders
        # aussieht, ist keine. Ein abgeleiteter Tag trägt dabei den leeren
        # Stichentscheid und steht bei Gleichstand deshalb vorn — willkürlich,
        # aber fest, und das ist die Eigenschaft, um die es geht.
        rows = sorted(best.items(),
                      key=lambda kv: (-kv[1][1] if direction == "max"
                                      else kv[1][1], kv[1][0]))
        out[name] = [(card(eid, v) if eid is not None else day_card(day, v))
                     for day, (_tie, v, eid) in rows[:n]]
    return out


def weather_values(db: Session, user_id: str):
    """Die Wetterwerte je Ereignis, plus die zwei Regeln, die auf ihnen gelten.

    Zurück kommen `(events, values, val, card)`: die Ereignisse als Tupel, die
    Werte je Ereignis, der Zugriff mit Schlüssel-Kette (`temp_max_c`, sonst
    `temperature_c`) und die Karte, wie eine Rekord-Zeile aussieht.

    Geladen werden Tupel, keine ORM-Objekte — das war die Lehre aus
    Anmerkung 80: die Objekterzeugung über eine volle Ergebnismenge ist der
    teure Teil, nicht das Finden der Zeilen.

    **Öffentlich seit Anmerkung 156**, weil die Top-Listen dieselben Werte
    brauchen. Sie dort ein zweites Mal zu laden hieße, die Schlüssel-Kette und
    die Rundung ein zweites Mal aufzuschreiben — und zwei Fassungen einer
    Rundungsregel laufen still auseinander.
    """
    base = (db.query(Event.id, Event.title, Event.date_start, Event.date_precision,
                     Event.category, Event.parent_event_id, Location.name)
            .outerjoin(Location, Event.location_id == Location.id)
            .filter(Event.user_id == user_id, Event.date_start.isnot(None)))
    events = {r.id: r for r in base.all()}
    values: dict[str, dict[str, float]] = {}
    if events:
        rows = (db.query(Metric.event_id, Metric.key, Metric.value)
                .join(Event, Event.id == Metric.event_id)
                .filter(Event.user_id == user_id, Metric.source == Source.weather,
                        Metric.key.in_(_WX_KEYS), Metric.value.isnot(None))
                .all())
        for eid, key, value in rows:
            if eid in events:
                values.setdefault(eid, {})[key] = value

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
                "place": _short_place(e.name), "derived": False}

    days, day_card = _baseline_weather_days(db, user_id)
    return WeatherSource(events, values, val, card, days, day_card)


# --------------------------------------------------------------------------- #
# **Anmerkung 194 — die zweite Hälfte der Tage.**
# --------------------------------------------------------------------------- #
# Gemeldet: „warum gibt es keine Regentage zwischen 1991 und 2009 — weil da nur
# ein Wohnort hinterlegt ist?" Ja, und das war ein Defekt und keine Eigenschaft.
#
# Die Wetterwerte dieser Jahre LIEGEN in der Datenbank (`DayMetric`, vom selben
# Lauf geholt wie die der Ereignisse), und `weather_day.day_values` vereinigt
# beide Quellen längst korrekt. Die Statistik hat die Vereinigung nur nicht
# benutzt: sie baute ihre Tagesliste aus den EREIGNISSEN und schlug die
# Tageswerte danach lediglich für Tage nach, an denen ohnehin schon ein Eintrag
# stand. Ein Jahr ohne Einträge kam damit nicht einmal als Balken vor.
#
# **Es ist genau die Regel aus F20, nur an einer Stelle, die sie nicht gelesen
# hat**: wer eine Zahl über TAGE bildet, muss den Wohnort mitzählen; wer eine
# über EINTRÄGE bildet, darf es nicht. „Regentage", „Sonnenstunden" und
# „kältester Tag" sind Zahlen über Tage — die Überschrift sagt es, seit
# Anmerkung 161 führt auch der Klick zum TAG. Die Abzeichen (F19) haben die
# Wohnort-Tage die ganze Zeit mitgezählt, weil sie über `weather_day` gehen: ein
# Sonnentag von 1998 konnte ein Abzeichen einbringen und stand trotzdem in
# keiner Sonnenstunde.
#
# **Nur die Tage werden geholt, die wirklich Wetter tragen** — nicht alle
# abgeleiteten. `baseline.inferred_days` würde bei vierzig Jahren Wohnort
# siebentausend Tage in den Speicher legen, um für die meisten nichts zu finden;
# die Bedingung als SQL (`inferred_day_clause`, dieselbe Regel) lässt die
# Datenbank aussortieren. Der Ort kommt danach aus den Zeiträumen, deren es eine
# Handvoll gibt.
def _baseline_weather_days(db: Session, user_id: str):
    """({Tag: {Schlüssel: Wert}}, Kartenbauer) für die Wohnort-Tage mit Wetter.

    Dieselbe Gestalt wie `values`/`card` bei den Ereignissen, damit
    `_extreme_tops` beide Mengen ohne Fallunterscheidung durchläuft.

    **Dass sich die beiden Mengen nicht überschneiden, ist keine Vorsicht,
    sondern die tragende Eigenschaft aus F20** (der Wohnort füllt nur Lücken).
    Deshalb darf hier schlicht dazugelegt werden, statt je Tag eine Vorrangregel
    zu erfinden — dieselbe Begründung, mit der `weather_day._rows` die beiden
    Quellen vereinigt.

    **Die Lückenregel steht hier in ihrer PYTHON-Fassung** (`recorded_days` +
    die Zeiträume), nicht als SQL-Bedingung. Das ist keine dritte Fassung: es
    sind die beiden, die `baseline.py` nebeneinander führt und gegeneinander
    prüft — `inferred_days` rechnet genauso.

    **Welche der drei möglichen Bauarten die billigste ist, war zweimal anders
    als vermutet.** Gemessen mit `tools/_measure_api.py` (20.000 Ereignisse,
    5.843 Wohnort-Tage mit Wetter), Ausgangswerte 405 ms für
    `/api/stats/overview` und 357 ms für `/api/stats/toplists`:

    * `inferred_day_clause` als Anti-Join in der Abfrage → 500 / 501 ms.
      `date()` über einer Spalte kann kein Index bedienen.
    * Aus `weather_day.day_values` abgeleitet (die Vereinigung, die die Bilanz
      ohnehin holt) → 442 / 628 ms. Für die Bilanz die beste Wahl, für die
      Ranglisten die schlechteste: die brauchen die Vereinigung sonst gar nicht.
    * Diese hier — Zeilen roh holen, in Python aussortieren → 509 / 554 ms.

    Die letzte ist die einzige, die BEIDE Auskünfte gleich behandelt, und sie
    ist damit die einzige, die ohne eine zweite Fassung derselben Frage
    auskommt. Von den ~120 ms Aufschlag entfallen rund 60 auf diese Funktion,
    der Rest auf die 5.843 zusätzlichen Anwärter je Rekord in `_extreme_tops`.
    Beide Endpunkte sind Klick-Endpunkte, und der Aufschlag kauft die ersten
    zwanzig Jahre eines Lebens — vorher standen sie in keiner dieser Zahlen.
    """
    rows = (db.query(DayMetric.day, DayMetric.key, DayMetric.value)
            .filter(DayMetric.user_id == user_id,
                    DayMetric.source == Source.weather,
                    DayMetric.key.in_(_WX_KEYS),
                    DayMetric.value.isnot(None))
            .all())
    # Welcher Wohnort einen Tag vertritt: der ERSTE Zeitraum, der ihn deckt —
    # dieselbe Wahl wie in `baseline.inferred_days` (dort gewinnt der erste,
    # weil `if day not in out` die späteren abweist). Zwei Antworten darauf
    # liefen still auseinander, und diese hier stünde in der Statistik.
    # `spans` deckelt zugleich bei HEUTE, beantwortet also auch die zweite
    # Hälfte der Regel („nicht in der Zukunft") — deshalb ist „kein Zeitraum
    # gefunden" hier dasselbe wie „zählt nicht mit".
    periods = baseline.spans(db, user_id) if rows else []

    def where(day: date_type):
        for start, end, row in periods:
            if start <= day <= end:
                return row
        return None

    recorded = baseline.recorded_days(db, user_id) if rows else set()
    days: dict[date_type, dict[str, float]] = {}
    for day, key, value in rows:
        d = _as_day(day)
        # Die dritte Hälfte der Regel: an dem Tag darf kein Eintrag stehen. Ein
        # Tageswert, dessen Tag nachträglich einen bekommen hat, bleibt liegen
        # und gilt von selbst wieder, sobald der Tag zurückfällt (Anm. 185).
        if d is None or d in recorded or where(d) is None:
            continue
        days.setdefault(d, {})[key] = value

    def day_card(day: date_type, value: float) -> dict:
        row = where(day)
        loc = getattr(row, "location", None)
        # **`title` bleibt leer, und das ist der Punkt.** Ein abgeleiteter Tag
        # hat keinen Titel, den jemand geschrieben hätte — „Wohnort" hier
        # einzusetzen hieße, deutschen Text aus dem Server in eine Oberfläche zu
        # schreiben, die auch englisch sein kann (F10). Die Marke ist `derived`,
        # den Satz dazu formuliert die Anzeige.
        return {"value": round(value, 1), "id": None, "title": None,
                "date_start": datetime.combine(day, time.min),
                "date_precision": DatePrecision.day.value,
                "place": _short_place(getattr(loc, "name", None)),
                "derived": True}

    return days, day_card


def _weather_stats(db: Session, user_id: str) -> dict:
    """Wetter-Rekorde und Wetter-Bilanz — beides je KALENDERTAG (A31).

    Beides braucht dieselben Werte, deshalb ein gemeinsamer Durchgang.

    Anmerkung 194: „je Ereignis" stand hier in der ersten Zeile und stimmte
    schon seit Anmerkung 161 nicht mehr für die Rekorde. Jetzt sind es zwei
    Quellen (Ereignisse und Wohnort-Tage) und eine Einheit."""
    src = weather_values(db, user_id)
    events, values = src.events, src.values
    if not values and not src.days:
        return _empty_weather()

    # --- Rekorde: je Tag, aus beiden Quellen (Anmerkung 161/194) ---
    # Anmerkung 114: Eine Schleife über eine Tabelle statt zwölf Blöcke. Die
    # ersten sechs Kacheln standen als zwei getrennte Fassungen desselben
    # Gedankens da; mit sechs weiteren wäre daraus dieselbe stille Doppelregel
    # geworden, an der schon Anmerkung 106 hing.
    #
    # Anmerkung 156: Die Kachel ist seitdem **Platz 1 einer Liste** und nicht
    # mehr ein eigenes Ergebnis. `_extreme_tops` rechnet beides; hier wird
    # nur der Kopf genommen. Zwei Fassungen derselben Rangfolge — eine für
    # die Kachel, eine für die Top-Liste — wären dieselbe Doppelregel eine
    # Ebene höher, und sie liefen genau dann auseinander, wenn jemand eine
    # Schwelle ändert (etwa „0 zählt nicht").
    extremes = {name: (rows[0] if rows else None)
                for name, rows in _extreme_tops(src, 1).items()}

    # --- Bilanz: EIN Datensatz je Kalendertag (A31/Anmerkung 64) ---
    # Ein importierter Tag trägt dutzende Besuche mit demselben Wetter; über
    # Einträge gerechnet kämen mehr als 365 Regentage im Jahr heraus.
    #
    # Anmerkung 119: WELCHER Wert das ist, entscheidet nicht mehr diese Datei.
    # Bis 0.39 gewann hier das erste Ereignis des Tages, in den Erfolgen das
    # kleinste je Schlüssel und im Zeitstrahl das des Verdichtungs-Vertreters —
    # drei Antworten auf eine Frage, und nur eine davon stand irgendwo
    # begründet. Jetzt gilt überall die Regel aus `weather_day`: je Schlüssel
    # der kleinste Wert des Tages, also der vorsichtige.
    day_wx = weather_day.day_values(db, user_id, keys=_WX_KEYS)
    dval = lambda day, key: (day_wx.get(day) or {}).get(key)  # noqa: E731

    # **Anmerkung 194: gezählt wird über `day_wx`, nicht über eine aus den
    # Ereignissen gebaute Tagesliste.** Hier stand genau das — und damit fielen
    # die Wohnort-Tage heraus, die `day_values` längst mitliefert. Ein Jahr, in
    # dem nur der Wohnort steht, kam nicht einmal als Balken vor.
    #
    # Ein Nebeneffekt der Umstellung ist ihre eigene Begründung: die Zahl „Tage
    # mit Wetter" ist jetzt die Länge derselben Menge, über die gezählt wird.
    # Vorher waren es zwei Mengen, die auseinanderlaufen konnten, ohne dass es
    # jemandem auffällt — die Bezugsgröße von „x % deiner Tage" stammte aus der
    # einen, der Zähler aus der anderen.
    rain_days = sum(1 for v in day_wx.values() if (v.get("rain_mm") or 0) >= 1)
    sun_hours = round(sum(v.get("sunshine_h") or 0 for v in day_wx.values()))
    rain_per_year: dict[int, int] = {}
    for day, v in day_wx.items():
        y = int(day[:4])
        rain_per_year.setdefault(y, 0)
        if (v.get("rain_mm") or 0) >= 1:
            rain_per_year[y] += 1

    # **Die wärmste Reise bleibt eine Frage über EINTRÄGE** (welche Reise?), und
    # deshalb bleibt hier die Tagesliste aus den Ereignissen stehen. Ein
    # Wohnort-Tag gehört zu keiner Reise; ihn mitzuzählen hieße, dieselbe Regel
    # in die andere Richtung zu verletzen (F20: als TAG voll, als EINTRAG nie).
    by_day: dict[str, str] = {}
    for eid in sorted(values, key=lambda i: (events[i].date_start, i)):
        by_day.setdefault(events[eid].date_start.date().isoformat(), eid)
    day_of = lambda i: events[i].date_start.date().isoformat()  # noqa: E731

    trips: dict[str, list] = {}
    for i in by_day.values():
        e = events[i]
        temp = dval(day_of(i), "temperature_c")
        if e.category != "trip" or temp is None:
            continue
        key = e.parent_event_id or i
        # **Der Name kommt von dem, wonach gefragt wurde** (Anmerkung 199).
        # Gruppiert wird über den Elternteil, benannt wurde bis hierher das
        # erste KIND — die Kachel „Wärmste Reise" sagte damit „Andalusien —
        # Tag 1". Sie traf ausgerechnet den Fall, für den diese Mittelung
        # gebaut ist: eine ungeteilte Reise ist ihr eigener Schlüssel und
        # hieß immer richtig, eine in Tage geschnittene nie. Fehlt der
        # Elternteil in `events` (undatiert, also nie in dieser Auswahl),
        # bleibt der Kindtitel — ein Name mit Zusatz ist mehr als keiner.
        entry = trips.setdefault(
            key, [0.0, 0, getattr(events.get(key), "title", None) or e.title])
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
            "days": len(day_wx),
            "sun_hours": sun_hours,
            "rain_days": rain_days,
            "rain_share": round(rain_days / len(day_wx) * 100) if day_wx else 0,
            "warmest_trip": warmest,
            "rain_days_per_year": [[y, n] for y, n in sorted(rain_per_year.items())],
        },
    }


def _empty_weather() -> dict:
    return {
        "extremes": {name: None for name, *_ in _EXTREMES},
        "weather": {"days": 0, "sun_hours": 0, "rain_days": 0, "rain_share": 0,
                    "warmest_trip": None, "rain_days_per_year": []},
    }
