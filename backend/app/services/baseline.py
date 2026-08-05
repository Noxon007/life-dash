"""F20 — aus einem Wohnort werden Tage. Schicht 4, nichts gespeichert.

**Die eine Regel dieser Datei.** Ein Tag, der in den Zeitraum eines Wohnorts
fällt und an dem KEIN Eintrag steht, gilt als Tag an diesem Ort. Steht dort ein
Eintrag — irgendeiner —, gewinnt der Eintrag und der Wohnort schweigt.

Daraus folgt die Eigenschaft, an der die halbe Umsetzung hängt: **die
Ereignistage und die Wohnort-Tage sind disjunkt.** Nichts muss zusammengeführt,
gewichtet oder entschieden werden; eine Zahl über Tage ist immer die Summe
beider Mengen, und ein Tageswetter kommt entweder aus dem einen oder aus dem
anderen Speicher, nie aus beiden. Das ist keine Vereinfachung im Nachhinein,
sondern der Grund, aus dem „nur Lücken füllen" so entschieden wurde
(Anmerkung 144, Entscheidung 3). `test_f20_baseline.py` nagelt es fest, weil
jede Stelle, die die beiden Mengen addiert, still doppelt zählte, sobald es
nicht mehr gilt.

**Warum hier nichts gespeichert wird.** Die Alternative wäre eine Tabelle mit
einer Zeile je Tag — und die müsste bei jedem Import, jeder Löschung und jeder
Änderung eines Zeitraums nachgeführt werden. Anmerkung 145 hat den Satz für die
Lückenprüfung schon aufgeschrieben: *eine veraltete Ableitung ist schlimmer als
keine, weil sie jemanden nach Daten suchen lässt, die längst da sind.* Der
Preis ist ein Kalenderdurchlauf je Abfrage; bei vierzig Jahren sind das 14 600
Schleifendurchläufe gegen eine Menge im Arbeitsspeicher, also der billigere Teil
jeder Statistik, die ihn braucht.

**Der Wohnort selbst ist Lebensdatenbank** (`models.BaselineLocation`), die
Tage daraus sind es nicht. Diese Datei darf deshalb jederzeit anders rechnen;
die eingetragene Aussage bleibt davon unberührt.
"""
from __future__ import annotations

import math
from datetime import date as date_type
from datetime import datetime, time, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.models import BaselineLocation, Event

# Ein Zeitraum ohne Enddatum reicht bis heute (siehe Modell-Kommentar). Wer
# „heute" übergibt, kann das in Tests festhalten, ohne die Uhr zu stellen.
Span = tuple[date_type, date_type, BaselineLocation]

# **Anmerkung 197 — wie nah „zu Hause" ist.** 150 m ist die Größenordnung
# eines Häuserblocks: die Nebenstraße, auf die ein Geräte-Export den
# Wohnungsschlüssel legt, liegt darin; das Café zwei Querstraßen weiter nicht.
# Bewusst eine Konstante und keine Einstellung — eine Zahl, die jeder Nutzer
# anders setzt, macht aus einer Rangliste eine Aussage über die Einstellung.
HOME_RADIUS_KM = 0.15


def _as_date(value) -> date_type | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_type):
        return value
    return date_type.fromisoformat(str(value)[:10])


def load(db: Session, user_id: str) -> list[BaselineLocation]:
    """Alle Wohnorte eines Kontos, chronologisch, mit ihrem Ort.

    `selectinload` und nicht faul: jeder Aufrufer braucht Name, Stadt, Land und
    Koordinate des Orts — ohne das Vorladen wäre eine Liste von zwölf
    Lebensabschnitten zwölf Nachfragen.
    """
    return (db.query(BaselineLocation)
            .options(selectinload(BaselineLocation.location))
            .filter(BaselineLocation.user_id == user_id)
            .order_by(BaselineLocation.date_start.asc()).all())


def spans(db: Session, user_id: str, *, today: date_type | None = None,
          rows: list[BaselineLocation] | None = None) -> list[Span]:
    """Die Zeiträume als (Anfang, Ende, Wohnort) — Ende immer gesetzt.

    Ein offener Zeitraum endet HEUTE und nicht in der Zukunft: „seit 2019 wohne
    ich hier" ist keine Aussage über morgen. Ein Zeitraum, dessen Ende vor
    seinem Anfang läge, wird übersprungen statt korrigiert — er ist ein
    Dateneingabefehler, und stillschweigend zu tauschen hieße, eine falsche
    Eingabe unsichtbar zu machen.
    """
    today = today or date_type.today()
    out: list[Span] = []
    for row in (rows if rows is not None else load(db, user_id)):
        start = _as_date(row.date_start)
        end = _as_date(row.date_end) or today
        if start is None or end < start:
            continue
        out.append((start, min(end, today), row))
    return out


def recorded_days(db: Session, user_id: str, *, start: date_type | None = None,
                  end: date_type | None = None) -> set[date_type]:
    """Alle Kalendertage mit mindestens einem datierten Eintrag.

    Die einzige Abfrage hier, die wirklich Zeilen holt — und sie darf es: es
    sind die TAGE, nicht die Einträge (dieselbe Begründung wie in
    `stats_toplists`, das diese Funktion seit F20 mitbenutzt, statt sie ein
    zweites Mal aufzuschreiben).

    **Unbestätigte zählen mit.** Ein Vorschlag für den 14. März ist ein Hinweis,
    dass an dem Tag etwas war; ihn zu übergehen hieße, den Wohnort über einen
    Tag reden zu lassen, über den die Datenbank bereits etwas Besseres weiß.
    """
    q = (db.query(func.distinct(func.date(Event.date_start)))
         .filter(Event.user_id == user_id, Event.date_start.isnot(None)))
    if start is not None:
        q = q.filter(Event.date_start >= datetime.combine(start, time.min))
    if end is not None:
        q = q.filter(Event.date_start <= datetime.combine(end, time.max))
    out: set[date_type] = set()
    for (d,) in q.all():
        # SQLite gibt `date()` als Text zurück, PostgreSQL als `date`.
        if d is not None:
            out.add(d if isinstance(d, date_type) else _as_date(d))
    return out


def inferred_days(db: Session, user_id: str, *, start: date_type | None = None,
                  end: date_type | None = None, today: date_type | None = None,
                  rows: list[BaselineLocation] | None = None,
                  taken: set[date_type] | None = None,
                  ) -> dict[date_type, BaselineLocation]:
    """{Tag: Wohnort} für die Tage, die der Wohnort füllt — Lücken only.

    `taken` erlaubt dem Aufrufer, die Menge der erfassten Tage einmal zu holen
    und mehrfach zu benutzen; ohne das führe die Statistik dieselbe Abfrage
    viermal.
    """
    periods = spans(db, user_id, today=today, rows=rows)
    if not periods:
        return {}
    lo = min(s for s, _e, _b in periods)
    hi = max(e for _s, e, _b in periods)
    if start is not None:
        lo = max(lo, start)
    if end is not None:
        hi = min(hi, end)
    if hi < lo:
        return {}
    if taken is None:
        taken = recorded_days(db, user_id, start=lo, end=hi)
    out: dict[date_type, BaselineLocation] = {}
    step = timedelta(days=1)
    for s, e, row in periods:
        day = max(s, lo)
        last = min(e, hi)
        while day <= last:
            if day not in taken and day not in out:
                out[day] = row
            day += step
    return out


def inferred_day_clause(db: Session, user_id: str, day_col):
    """Dieselbe Frage wie `inferred_days`, aber als SQL-Bedingung über `day_col`.

    **Anmerkung 185 — warum es diese Regel zweimal gibt.** `inferred_days` holt
    die Tage in den Arbeitsspeicher; das geht überall dort, wo ohnehin über sie
    iteriert wird. `weather_day` kann das nicht: seine Auskunft ist eine QUERY,
    über der die Erfolge in SQL zählen und summieren, und ein Bestand mit 12 000
    Ereignissen soll dafür nicht durch Python.

    Zwei Fassungen einer Regel laufen still auseinander — das ist in diesem
    Projekt der teuerste Defekt, den es gibt. Deshalb stehen sie in DERSELBEN
    Datei nebeneinander, und `test_f20_baseline.py` prüft sie auf demselben
    Bestand gegeneinander: was die eine liefert, muss die andere liefern.

    Die Regel, ausgeschrieben: der Tag liegt in einem Zeitraum, er liegt nicht
    in der Zukunft (ein offenes Ende reicht bis HEUTE, nicht bis morgen — siehe
    `spans`), und an ihm steht kein Eintrag.
    """
    today = func.current_date()
    covered = (db.query(BaselineLocation.id)
               .filter(BaselineLocation.user_id == user_id,
                       BaselineLocation.date_start <= day_col,
                       day_col <= today,
                       or_(BaselineLocation.date_end.is_(None),
                           day_col <= BaselineLocation.date_end))
               .exists())
    # Der Tag darf keinen Eintrag tragen — die Lückenregel, die diese Datei
    # überhaupt trägt. Als Anti-Join und nicht als `EXISTS` je Zeile: ein
    # Bestand mit vierzig Jahren Wohnort trägt sechsstellig viele Tageswerte,
    # und `date()` über einer Spalte kann kein Index bedienen.
    taken = (db.query(func.date(Event.date_start))
             .filter(Event.user_id == user_id, Event.date_start.isnot(None))
             .distinct().scalar_subquery())
    return covered & day_col.notin_(taken)


def overlaps(periods: list[Span], start: date_type, end: date_type | None,
             *, ignore_id: str | None = None, today: date_type | None = None
             ) -> BaselineLocation | None:
    """Der erste Zeitraum, der sich mit (start, end) schneidet — oder None.

    **Ein Wohnort zur Zeit** (Anmerkung 144, Entscheidung 4). Geprüft wird im
    Endpunkt, nicht im Schema: „diese Spanne schneidet jene" schreiben SQLite
    und PostgreSQL verschieden, und eine Bedingung, die nur auf einer der beiden
    Datenbanken greift, ist keine.
    """
    end = end or (today or date_type.today())
    for s, e, row in periods:
        if ignore_id is not None and row.id == ignore_id:
            continue
        if s <= end and start <= e:
            return row
    return None


# --------------------------------------------------------------------------- #
# Anmerkung 197 — ein Ort im Umkreis des Wohnorts heißt wie der Wohnort
# --------------------------------------------------------------------------- #
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Luftlinie in Kilometern.

    In Python und nicht in SQL: `sin`/`cos` sind in SQLite nur vorhanden, wenn
    es mit `SQLITE_ENABLE_MATH_FUNCTIONS` gebaut wurde — eine Abfrage, die auf
    der einen Datenbank rechnet und auf der anderen abstürzt, ist genau die
    Dialektfalle, für die es `tools/pg-test.ps1` gibt. Gerechnet wird ohnehin
    über ORTE, nicht über Ereignisse: es sind Hunderte, nicht Zehntausende.
    """
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def home_naming(db: Session, user_id: str, *,
                rows: list[BaselineLocation] | None = None):
    """Gibt eine Funktion `(name, lat, lng) -> name` zurück.

    **Der gemeldete Fall.** In den Top-Orten standen „Barmbeker Straße 13 ·
    0 Einträge · 1.142 Tage" (der eingetragene Wohnort) und „Knickweg ·
    1.161 Einträge · 665 Tage" (was der Geräte-Export für dieselbe Wohnung
    hielt) als zwei Orte untereinander. Es ist einer.

    **Die Regel: der Name, den ein MENSCH gegeben hat, gewinnt.** Ein Wohnort
    ist eine eingetragene Aussage, ein rückwärts geokodierter Straßenname eine
    Vermutung der Maschine — und Maschinen bekommen in diesem Programm nicht
    das letzte Wort über Bestätigtes. Umgeschrieben wird deshalb nicht der
    gespeicherte Ort, sondern nur, wie er in einer Rangliste HEISST (Schicht 4);
    Karte, Filter und Bestand bleiben unberührt.

    **Ohne Koordinate keine Zusammenlegung.** Nach Namensähnlichkeit zu raten
    („Knickweg" klingt nicht nach „Barmbeker Straße") ginge nicht, und nach
    Stadt zusammenzulegen wäre zu grob — der halbe Bezirk hieße dann Zuhause.

    Zurück kommt eine FUNKTION und keine fertige Liste, weil zwei Ansichten sie
    lesen: die Balken im Überblick und die Rangliste darunter. Zwei
    Umbenennungsregeln wären zwei Antworten auf dieselbe Frage — genau das, was
    `_place_ranking` schon bei der Kürzung vermeidet.
    """
    homes = [(row.location.lat, row.location.lng, row.location.name)
             for row in (rows if rows is not None else load(db, user_id))
             if row.location is not None and row.location.lat is not None
             and row.location.lng is not None and row.location.name]

    def named(name: str | None, lat: float | None, lng: float | None) -> str | None:
        if not homes or lat is None or lng is None:
            return name
        for h_lat, h_lng, h_name in homes:
            if haversine_km(lat, lng, h_lat, h_lng) <= HOME_RADIUS_KM:
                return h_name
        return name

    return named


# --------------------------------------------------------------------------- #
# Was die Statistik braucht: Tage je Ort, Stadt, Land, Jahr
# --------------------------------------------------------------------------- #
def day_counts(db: Session, user_id: str, *, today: date_type | None = None,
               taken: set[date_type] | None = None) -> dict:
    """Die abgeleiteten Tage, aufgeschlüsselt wie die Statistik sie braucht.

    `{"total": n, "places": {…}, "cities": {…}, "countries": {…},
      "years": {…}, "per_baseline": {id: n}, "first": date, "last": date}`

    **Alles aus EINEM Kalenderdurchlauf.** Vier getrennte Aufschlüsselungen
    wären vier Durchläufe über dieselben 14 600 Tage — und, schlimmer, vier
    Stellen, an denen „was ist ein abgeleiteter Tag" beantwortet wird. Anmerkung
    106 in der Form, in der sie in diesem Projekt am häufigsten auftritt.

    Die Ortsnamen kommen ungekürzt heraus; gekürzt wird dort, wo auch die
    Ereignis-Orte gekürzt werden (`stats_overview._short_place`) — sonst stünde
    derselbe Ort zweimal in einer Liste, einmal lang und einmal kurz.
    """
    rows = load(db, user_id)
    days = inferred_days(db, user_id, today=today, rows=rows, taken=taken)
    out: dict = {"total": len(days), "places": {}, "cities": {},
                 "countries": {}, "years": {}, "per_baseline": {},
                 "first": None, "last": None}
    for day, row in days.items():
        loc = row.location
        out["per_baseline"][row.id] = out["per_baseline"].get(row.id, 0) + 1
        out["years"][day.year] = out["years"].get(day.year, 0) + 1
        if out["first"] is None or day < out["first"]:
            out["first"] = day
        if out["last"] is None or day > out["last"]:
            out["last"] = day
        if loc is None:
            continue
        for bucket, value in (("places", loc.name), ("cities", loc.city),
                              ("countries", loc.country)):
            # Der Leerstring heißt „nachgesehen, gibt es hier nicht" (A39) und
            # ist so wenig eine Stadt wie NULL.
            if value:
                out[bucket][value] = out[bucket].get(value, 0) + 1
    return out
