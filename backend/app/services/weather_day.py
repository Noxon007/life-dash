"""Die EINE Antwort auf „welches Wetter hatte dieser Tag?" (Anmerkung 119).

**Warum es diese Datei gibt.** Wetter ist eine Eigenschaft von (Tag, Ort),
gespeichert wird es aber je EREIGNIS — ein Tag mit fünf Besuchen trägt fünfmal
dasselbe Wetter, und ein Reisetag zwei verschiedene. Jede Stelle, die daraus
eine Tagesaussage machen musste, hat sich ihre eigene Regel gegeben:

* Zeitstrahl: das Wetter des Verdichtungs-Vertreters `min(id)` — willkürlich,
  denn ids sind UUIDs (dieselbe Falle wie in Anmerkung 106).
* Client-Sammelkarte: gar keins.
* Erfolge: `min` je Kalendertag (Anmerkung 103) — **aber die Schwelle wurde
  VOR der Verdichtung geprüft**, also entschied doch der günstigste Eintrag.
* Statistik-Bilanz: das ERSTE Ereignis des Tages, das Wetter hat (A31).

Vier Regeln für einen Begriff. Anmerkung 106 in seiner üblichen Form: eine
Regel, die an mehreren Orten steht, widerspricht sich still.

**Die Regel, ausgeschrieben.** Ein Tag hat genau einen Wetterwert je Schlüssel:

* **Zahlen: das Minimum über die Ereignisse des Tages.** Nicht, weil das
  Minimum „richtiger" wäre, sondern weil es das VORSICHTIGE ist — an einem Tag
  mit zwei Wetterregionen zählt die schwächere. Das kann einen Erfolg
  verzögern und nie vorzeitig auslösen, und die Richtung ist Absicht
  (Anmerkung 103: vorverdiente Abzeichen waren der Defekt).
* **Schwellen (Erfolge) prüfen weiter, ob der Tag die Bedingung ERREICHT
  hat** — dazu unten bei `day_value_query` mehr. Ob ein Tag zählt und welchen
  Wert er beisteuert, sind zwei Fragen; nur die zweite beantwortet das
  Minimum.
* **Texte (Bedingung, Sonnenauf-/-untergang) nur, wenn sich der Tag einig
  ist.** Ein alphabetisch kleinster Wetterzustand („Nebel" vor „Regen") wäre
  keine Auskunft, sondern eine Sortierung. Sind sie verschieden, steht dort
  nichts — und die Zahl der Regionen daneben sagt, warum.
* **`regions`** ist die Zahl der berührten Wetter-Gitterzellen (0,1° ≈ 11 km,
  siehe `sqlutil.weather_cell`). Sie ist der Grund, aus dem eine Tageszeile
  überhaupt mehrdeutig sein kann, und gehört deshalb neben den Wert: eine
  Ansicht, die nicht alles zeigen kann, muss das sagen (A40/Anmerkung 110).

Schicht 4 (Kap. 3.1): hier wird nichts gespeichert, alles bei jeder Abfrage neu
gerechnet. Die Tatsachen selbst bleiben unangetastet an ihren Ereignissen.
"""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, time

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import ConfirmState, Event, Location, Metric, Source
from app.sqlutil import day_parts, weather_cell

# Wetterwerte, die als Text gespeichert sind (`Metric.value_text`). Für sie
# gilt die Einigkeits-Regel oben statt des Minimums.
TEXT_KEYS = ("weather", "sunrise", "sunset")

# Interner Marker der Anreicherung — nie eine Auskunft (F12 `weather_rev`).
REVISION_KEY = "weather_rev"


def _iso(y, m, d) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _window(query, start, end):
    """Zeitfenster auf ganze Kalendertage aufziehen.

    `date_start` ist naiv gespeichert; `datetime.combine` liefert denselben
    Typ. Ohne das Aufziehen fiele bei `end=2026-07-23` alles nach Mitternacht
    dieses Tages heraus — also der ganze Tag außer seiner ersten Sekunde.
    """
    if start is not None:
        if isinstance(start, datetime):
            start = start.date()
        query = query.filter(Event.date_start >= datetime.combine(start, time.min))
    if end is not None:
        if isinstance(end, datetime):
            end = end.date()
        query = query.filter(Event.date_start <= datetime.combine(end, time.max))
    return query


def _base(db: Session, user_id: str, *, confirmed_only: bool):
    """Ereignisse mit Wetter-Metriken, auf ein Konto eingegrenzt.

    Die Nutzer-Einschränkung steht an der Abfrage und nicht am Aufrufer: A12
    verlangt sie ohne Ausnahme, sonst muss bei jeder Änderung neu begründet
    werden, warum diese eine Stelle sicher ist.
    """
    q = (db.query(Metric)
         .join(Event, Event.id == Metric.event_id)
         .filter(Event.user_id == user_id,
                 Event.date_start.isnot(None),
                 Metric.source == Source.weather,
                 Metric.key != REVISION_KEY))
    if confirmed_only:
        q = q.filter(Event.confirmed == ConfirmState.confirmed)
    return q


def day_values(db: Session, user_id: str, *, keys: tuple[str, ...] | None = None,
               start=None, end=None, confirmed_only: bool = False,
               ) -> dict[str, dict[str, float | str]]:
    """{"2026-07-23": {"temp_max_c": 24.1, "weather": "bewölkt"}} — die Regel oben.

    EINE Abfrage für Zahlen und Texte: gruppiert wird nach (Tag, Schlüssel),
    und `min(value_text) == max(value_text)` beantwortet die Einigkeitsfrage,
    ohne die Zeilen einzeln zu holen.
    """
    y, m, d = day_parts(Event.date_start)
    q = (_base(db, user_id, confirmed_only=confirmed_only)
         .with_entities(y.label("y"), m.label("m"), d.label("d"),
                        Metric.key.label("key"),
                        func.min(Metric.value).label("value"),
                        func.min(Metric.value_text).label("text_lo"),
                        func.max(Metric.value_text).label("text_hi"))
         .group_by(y, m, d, Metric.key))
    if keys:
        q = q.filter(Metric.key.in_(tuple(keys)))
    out: dict[str, dict[str, float | str]] = {}
    for row in _window(q, start, end).all():
        day = _iso(row.y, row.m, row.d)
        if row.value is not None:
            out.setdefault(day, {})[row.key] = row.value
        elif row.text_lo is not None and row.text_lo == row.text_hi:
            out.setdefault(day, {})[row.key] = row.text_lo
    return out


def day_regions(db: Session, user_id: str, *, start=None, end=None,
                confirmed_only: bool = False) -> dict[str, int]:
    """Wie viele Wetterregionen berührt jeder Tag? {"2026-07-23": 2}

    Gezählt werden nur verortete Ereignisse MIT Wetter — ein Eintrag ohne
    Koordinaten hat keine Region, und einer ohne Wetter sagt über das Wetter
    nichts aus. Sonst behauptete ein Tagebucheintrag ohne Ort, der Tag sei
    mehrdeutig gewesen.
    """
    y, m, d = day_parts(Event.date_start)
    q = (db.query(y.label("y"), m.label("m"), d.label("d"),
                  func.count(func.distinct(weather_cell(Location.lat, Location.lng)))
                  .label("n"))
         .select_from(Event)
         .join(Location, Event.location_id == Location.id)
         .join(Metric, and_(Metric.event_id == Event.id,
                            Metric.source == Source.weather,
                            Metric.key != REVISION_KEY))
         .filter(Event.user_id == user_id,
                 Event.date_start.isnot(None),
                 Location.lat.isnot(None), Location.lng.isnot(None))
         .group_by(y, m, d))
    if confirmed_only:
        q = q.filter(Event.confirmed == ConfirmState.confirmed)
    return {_iso(r.y, r.m, r.d): int(r.n) for r in _window(q, start, end).all()}


def day_weather(db: Session, user_id: str, *, start=None, end=None,
                confirmed_only: bool = False) -> dict[str, dict]:
    """Was die Oberfläche braucht: {"2026-07-23": {"values": {…}, "regions": 2}}.

    Zwei Abfragen statt einer, weil die Regionen aus den ORTEN kommen und die
    Werte aus den METRIKEN — in einem Join würde jede Metrik die Zahl der Orte
    vervielfachen (und `count(distinct …)` das nur zufällig überleben).
    """
    values = day_values(db, user_id, start=start, end=end,
                        confirmed_only=confirmed_only)
    regions = day_regions(db, user_id, start=start, end=end,
                          confirmed_only=confirmed_only)
    return {day: {"values": vals, "regions": regions.get(day, 1)}
            for day, vals in values.items()}


def day_value_query(db: Session, user_id: str, key: str, *,
                    confirmed_only: bool = True,
                    min_value: float | None = None,
                    max_value: float | None = None):
    """Eine Zeile je Kalendertag: (y, m, d, value) — für die Erfolge (F11/F19).

    Bleibt bewusst eine QUERY und kein Dict: die Aufrufer zählen und summieren
    darüber in SQL (`func.count`/`func.sum` über die Subquery), und ein Bestand
    mit 12 000 Ereignissen soll dafür nicht durch Python.

    **Zwei Fragen, zwei Antworten — und das ist Absicht.**

    *Ob* der Tag zählt, entscheidet die Schwelle, und dafür genügt EIN Eintrag:
    ein Tag, an dem irgendwo, wo der Nutzer war, elf Stunden die Sonne schien,
    ist ein Sonnentag gewesen; das abzuerkennen, weil er abends weitergefahren
    ist, verschwiege eine Tatsache. `test_f19_badges.py` hält das seit 0.35
    ausdrücklich fest — beim Umbau nach Anmerkung 119 stand hier kurz eine
    Fassung, die Abzeichen wieder aberkannt hätte.

    *Welchen Wert* er beisteuert, ist davon unabhängig: immer `min`, der
    vorsichtige, damit eine Summe an einem Reisetag nicht das Beste aus zwei
    Regionen addiert.

    **Deshalb `having` und nicht `filter`.** Als Vorfilter geschrieben ändert
    die Schwelle beides zugleich: sie wählt den Tag aus UND wirft die Einträge
    weg, die den Wert vorsichtig gemacht hätten (bei 11 h und 3 h käme mit
    `min: 10` der Wert 11 heraus, nicht 3). Heute fällt das nicht auf, weil
    keine Kennzahl gleichzeitig schwellt und summiert — aber genau so sehen die
    Fallen aus, die dieses Projekt sich stellt: zwei Bedeutungen in einem
    Ausdruck, folgenlos bis zur nächsten Modul-Datei.
    """
    y, m, d = day_parts(Event.date_start)
    q = (_base(db, user_id, confirmed_only=confirmed_only)
         .with_entities(y.label("y"), m.label("m"), d.label("d"),
                        func.min(Metric.value).label("value"))
         .filter(Metric.key == key, Metric.value.isnot(None))
         .group_by(y, m, d))
    # „irgendein Eintrag des Tages erreicht die Schwelle" — für „mindestens"
    # ist das der größte Wert des Tages, für „höchstens" der kleinste.
    if min_value is not None:
        q = q.having(func.max(Metric.value) >= float(min_value))
    if max_value is not None:
        q = q.having(func.min(Metric.value) <= float(max_value))
    return q
