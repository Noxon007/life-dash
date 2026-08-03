"""Anmerkung 156 — die dritte Statistik-Ansicht: Ranglisten.

**Warum ein eigener Endpunkt und nicht ein paar Felder mehr in `overview`.**
Der Überblick wird bei jedem Öffnen des Reiters geholt; diese Listen erst,
wenn jemand sie ansieht. Das ist dieselbe Regel, mit der A37 die Karte von der
Startseite getrennt hat: eine Ansicht bezahlt, was sie zeigt.

**Warum die Zahlen anders aussehen als die Balken daneben.** Die Diagramme
zeigen acht Einträge und einen Wert je Zeile — sie sind ein Bild. Eine Liste
ist eine Auskunft, also stehen hier **beide** Zahlen (Tage und Einträge,
Anmerkung 143/148) und zehn statt acht Zeilen.

**Was hier NICHT passiert.** Es wird nichts gespeichert und nichts geraten.
Jede Zahl ist eine Abfrage über den Bestand (Schicht 4), und wo eine Aussage
nicht sicher ist — etwa „längste Reise" —, steht sie unter dem Namen, unter dem
sie stimmt: die längste ERFASSTE Reise, nicht die längste, die stattfand.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Event, Location, Metric, Source
from app.services import stats_overview as ov
from app.sqlutil import day_number

TOP_N = 10


# --------------------------------------------------------------------------- #
# Ranglisten über Orte, Städte, Länder, Jahre, Kategorien
# --------------------------------------------------------------------------- #
def _ranked(db: Session, user_id: str, column, *extra_filters) -> list[dict]:
    """Tage UND Einträge je Wert einer Spalte, absteigend nach Tagen.

    Beide Zahlen in einer Abfrage: zwei Abfragen wären zwei Zeitpunkte und
    damit zwei Bestände — bei einem laufenden Import genügt das für eine Liste,
    in der die Einträge nicht zu den Tagen passen.
    """
    day_key = day_number(Event.date_start)
    rows = (db.query(column.label("k"),
                     func.count(func.distinct(day_key)),
                     func.count(Event.id))
            .filter(Event.user_id == user_id, Event.date_start.isnot(None),
                    column.isnot(None), *extra_filters)
            .group_by(column)
            # Tage, dann Einträge, dann der Wert selbst. Die dritte Stufe ist
            # nicht Kosmetik: ohne sie wäre die Reihenfolge bei Gleichstand die
            # der Datenbank und damit zwischen zwei Aufrufen verschieden (siehe
            # `_extreme_tops`). Die zweite ist die Aussage — stehen zwei
            # Kategorien bei einem Tag gleich, ist die mit mehr Einträgen die
            # gemeinte Antwort, nicht die alphabetisch erste.
            .order_by(func.count(func.distinct(day_key)).desc(),
                      func.count(Event.id).desc(), column.asc())
            .limit(TOP_N).all())
    return [{"name": str(k), "days": days, "events": events}
            for k, days, events in rows]


def _place_ranking(db: Session, user_id: str) -> list[dict]:
    """Orte — mit derselben Kürzung wie die Balken daneben (`_short_place`).

    Die Kürzung ist der Grund, warum das hier nicht `_ranked` sein kann: eine
    Nominatim-Langadresse wird auf ihren ersten Bestandteil gekürzt
    („Kaiserstraße 5, Düsseldorf, Deutschland" → „Kaiserstraße 5"), und diese
    Zusammenfassung passiert in Python. **Zwei Ortslisten mit zwei
    Kürzungsregeln wären zwei Antworten auf dieselbe Frage** — die Balken und
    diese Liste stehen untereinander und widersprächen sich.
    """
    day_key = day_number(Event.date_start)
    rows = (db.query(Location.name,
                     func.count(func.distinct(day_key)),
                     func.count(Event.id))
            .join(Event, Event.location_id == Location.id)
            .filter(Event.user_id == user_id, Event.date_start.isnot(None),
                    Location.name.isnot(None))
            .group_by(Location.name).all())
    merged: dict[str, list[int]] = {}
    for name, days, events in rows:
        short = ov._short_place(name)
        if not short:
            continue
        # **Die Tage werden addiert, und das ist eine Näherung.** Zwei Adressen
        # derselben Straße an EINEM Tag zählen hier zwei Tage. Genau zu rechnen
        # hieße, die Tagesmenge je gekürztem Namen zu bilden — also alle Tage
        # in den Prozess zu holen, für eine Liste von zehn Zeilen. Die Balken
        # daneben rechnen seit Anmerkung 143 genauso; eine zweite, genauere
        # Zahl an derselben Stelle wäre der teurere Fehler.
        cur = merged.setdefault(short, [0, 0])
        cur[0] += days
        cur[1] += events
    top = sorted(merged.items(),
                 key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))[:TOP_N]
    return [{"name": n, "days": d, "events": e} for n, (d, e) in top]


# --------------------------------------------------------------------------- #
# Serien: die Tage als Kalender lesen
# --------------------------------------------------------------------------- #
def _days(db: Session, user_id: str) -> list[date]:
    """Alle Kalendertage mit mindestens einem datierten Eintrag, aufsteigend.

    Die einzige Stelle hier, die wirklich Zeilen in den Prozess holt — und sie
    darf es: es sind die TAGE, nicht die Einträge. Zwanzig Jahre lückenlos sind
    7 300 Werte; zwanzigtausend Ereignisse wären es nicht.
    """
    rows = (db.query(func.distinct(func.date(Event.date_start)))
            .filter(Event.user_id == user_id, Event.date_start.isnot(None))
            .all())
    out: list[date] = []
    for (d,) in rows:
        if d is None:
            continue
        # SQLite gibt `date()` als Text zurück, PostgreSQL als `date`. Beides
        # kommt hier an, je nachdem, worauf betrieben wird.
        out.append(d if isinstance(d, date) else date.fromisoformat(str(d)[:10]))
    return sorted(out)


def _streaks(db: Session, user_id: str) -> dict:
    """Längste Serie, längste Lücke, längste erfasste Reise.

    **Die Lücke wird nur ZWISCHEN dem ersten und letzten Tag gemessen.** Die
    Zeit vor dem ersten Eintrag ist keine Lücke, sondern die Zeit vor dem
    ersten Eintrag — sie als „längste Lücke: 8 000 Tage" auszugeben wäre eine
    Aussage über den Beginn der Aufzeichnung, verkleidet als Befund über das
    Leben. (Was mit ihr wäre, hängt an Anmerkung 144, und die ist offen.)
    """
    days = _days(db, user_id)
    out: dict = {"longest_run": None, "longest_gap": None, "longest_trip": None}
    if not days:
        return out

    best_run = (days[0], days[0], 1)
    run_start, run_len = days[0], 1
    best_gap = None
    for prev, cur in zip(days, days[1:]):
        step = (cur - prev).days
        if step == 1:
            run_len += 1
            if run_len > best_run[2]:
                best_run = (run_start, cur, run_len)
        else:
            run_start, run_len = cur, 1
            missing = step - 1
            if best_gap is None or missing > best_gap[2]:
                best_gap = (prev + timedelta(days=1), cur - timedelta(days=1), missing)
    out["longest_run"] = {"from": best_run[0].isoformat(),
                          "to": best_run[1].isoformat(), "days": best_run[2]}
    if best_gap:
        out["longest_gap"] = {"from": best_gap[0].isoformat(),
                              "to": best_gap[1].isoformat(), "days": best_gap[2]}

    # Längste ERFASSTE Reise: das mehrtägige `trip`-Ereignis mit der größten
    # Spanne. Bewusst nicht „die längste Zeit am Stück außerhalb des
    # Heimatorts" — das wäre eine Ableitung aus importierten Besuchen, und die
    # antwortet auf „wo war ich" statt auf „was war eine Reise". Mehrtägig
    # entsteht seit A46 nur noch von Hand, also ist es genau das, was jemand
    # als Reise gemeint hat.
    trip = (db.query(Event.id, Event.title, Event.date_start, Event.date_end)
            .filter(Event.user_id == user_id, Event.category == "trip",
                    Event.date_start.isnot(None), Event.date_end.isnot(None))
            .all())
    best = None
    for eid, title, start, end in trip:
        span = (end.date() - start.date()).days + 1
        if span < 2:
            continue
        if best is None or span > best["days"]:
            best = {"id": eid, "title": title, "days": span,
                    "from": start.date().isoformat(), "to": end.date().isoformat()}
    out["longest_trip"] = best
    return out


# --------------------------------------------------------------------------- #
def compute_toplists(db: Session, user_id: str, n: int = TOP_N) -> dict:
    """Alle Ranglisten der dritten Statistik-Ansicht in einer Antwort."""
    day_key = day_number(Event.date_start)
    year_rows = (db.query(func.extract("year", Event.date_start).label("y"),
                          func.count(func.distinct(day_key)),
                          func.count(Event.id))
                 .filter(Event.user_id == user_id, Event.date_start.isnot(None))
                 .group_by("y")
                 .order_by(func.count(func.distinct(day_key)).desc(),
                           func.count(Event.id).desc(), "y")
                 .limit(n).all())

    return {
        "weather": _weather_tops(db, user_id, n),
        "places": _place_ranking(db, user_id),
        # Der Leerstring heißt „nachgesehen, gibt es hier nicht" (A39) und ist
        # keine Stadt — er fällt hier genauso weg wie NULL.
        "cities": _ranked(db, user_id, Location.city,
                          Event.location_id == Location.id, Location.city != ""),
        "countries": _ranked(db, user_id, Location.country,
                             Event.location_id == Location.id,
                             Location.country != ""),
        "years": [{"name": str(int(y)), "days": d, "events": e}
                  for y, d, e in year_rows],
        "categories": _ranked(db, user_id, Event.category),
        "streaks": _streaks(db, user_id),
    }


def _weather_tops(db: Session, user_id: str, n: int) -> dict[str, list[dict]]:
    """Zu jeder Rekord-Kachel die vollen `n` Plätze.

    Die Rangfolge selbst steht in `stats_overview._extreme_tops` — dieselbe
    Funktion, die die Kachel füllt. Hier wird nur mit einem anderen `n`
    gefragt (Anmerkung 156).
    """
    events, values, val, card = ov.weather_values(db, user_id)
    if not values:
        return {name: [] for name, *_ in ov._EXTREMES}
    return ov._extreme_tops(values, val, card, n)
