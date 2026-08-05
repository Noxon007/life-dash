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

import math
from datetime import date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Event, Location, MediaRef, Metric, Source
from app.services import baseline, gaps
from app.services import stats_overview as ov
from app.sqlutil import day_number

TOP_N = 10


def _merge_baseline(rows: list[dict], extra: dict[str, int]) -> list[dict]:
    """Abgeleitete Tage in eine fertige Rangliste einrechnen (F20).

    **Die Rangfolge entsteht danach neu, und das ist der Punkt.** Wer den
    Wohnort erst nach dem `LIMIT 10` addierte, bekäme eine Liste, in der ein
    Ort mit 2 190 abgeleiteten Tagen fehlt, weil er ohne sie nicht unter die
    ersten zehn kam — der Deckel hätte dann die Antwort entschieden, nicht die
    Zahl. Deshalb liefern die Abfragen unten mehr Zeilen, als die Liste zeigt.

    Addieren ist erlaubt, weil die beiden Tagesmengen disjunkt sind: der
    Wohnort füllt nur Lücken (`services/baseline.py`). Die EINTRÄGE bleiben
    unberührt — ein abgeleiteter Tag ist kein Eintrag, und ihn als einen zu
    zählen wäre genau die Vermischung, gegen die Anmerkung 143 die zweite Zahl
    überhaupt eingeführt hat.
    """
    if not extra:
        return rows[:TOP_N]
    by_name = {r["name"]: r for r in rows}
    for name, n in extra.items():
        cur = by_name.get(name)
        if cur is None:
            by_name[name] = {"name": name, "days": n, "events": 0}
        else:
            cur["days"] += n
    out = sorted(by_name.values(),
                 key=lambda r: (-r["days"], -r["events"], r["name"]))
    return out[:TOP_N]


# Wie viele Zeilen die Abfragen holen, bevor der Wohnort eingerechnet wird.
# Großzügig statt exakt: exakt wäre „alle", und für eine Liste von zehn Zeilen
# den ganzen Ortsbestand zu holen ist der teurere Fehler. Ein Wohnort hebt
# einen Ort um höchstens seine Tageszahl — dass der dann nicht unter den ersten
# fünfzig ohne ihn wäre, hieße, dass es fünfzig Orte mit noch mehr Tagen gibt,
# und dann ist er auch mit ihm keine Antwort auf „Top 10".
_PRE_N = 50


# --------------------------------------------------------------------------- #
# Ranglisten über Orte, Städte, Länder, Jahre, Kategorien
# --------------------------------------------------------------------------- #
def _ranked(db: Session, user_id: str, column, *extra_filters,
            baseline_days: dict[str, int] | None = None) -> list[dict]:
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
            .limit(_PRE_N if baseline_days else TOP_N).all())
    out = [{"name": str(k), "days": days, "events": events}
           for k, days, events in rows]
    return _merge_baseline(out, baseline_days or {})


def _place_ranking(db: Session, user_id: str,
                   baseline_days: dict[str, int] | None = None) -> list[dict]:
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
    top = sorted(merged.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
    rows = [{"name": n, "days": d, "events": e} for n, (d, e) in top]
    # F20: dieselbe Kürzung auch für den Wohnort — er läuft hier über
    # `_short_place`, nicht über den rohen Namen, sonst stünde „Musterweg 1,
    # Bad Segeberg, Deutschland" neben „Musterweg 1" als zweiter Ort.
    extra: dict[str, int] = {}
    for name, n in (baseline_days or {}).items():
        short = ov._short_place(name)
        if short:
            extra[short] = extra.get(short, 0) + n
    return _merge_baseline(rows, extra)


# --------------------------------------------------------------------------- #
# Serien: die Tage als Kalender lesen
# --------------------------------------------------------------------------- #
def _days(db: Session, user_id: str) -> list[date]:
    """Alle Kalendertage, an denen etwas bekannt ist — aufsteigend.

    Die einzige Stelle hier, die wirklich Zeilen in den Prozess holt — und sie
    darf es: es sind die TAGE, nicht die Einträge. Zwanzig Jahre lückenlos sind
    7 300 Werte; zwanzigtausend Ereignisse wären es nicht.

    **F20: die Wohnort-Tage zählen mit.** Sie sind kein Eintrag, aber sie sind
    Wissen über den Tag — und die Serie fragt „wie lange am Stück weiß ich, wo
    ich war", nicht „wie lange am Stück habe ich getippt". Die Abfrage selbst
    steht seitdem in `services/baseline.py`, weil dort auch die Ableitung
    darauf zugreift; zwei Fassungen von „welche Tage sind belegt" wären genau
    die stille Doppelregel, an der die Ableitung hängt.
    """
    days = baseline.recorded_days(db, user_id)
    days |= set(baseline.inferred_days(db, user_id, taken=days))
    return sorted(days)


def _streaks(db: Session, user_id: str) -> dict:
    """Längste Serie, längste Lücke, längste erfasste Reise.

    **Die Lücke rechnet diese Datei seit F21 nicht mehr selbst** — sie fragt
    `services/gaps.py`, und zwar dieselbe Funktion, aus der die Lücken-Ansicht
    ihre Liste zieht. Die Kachel ist damit Platz 1 der Liste, dasselbe Muster
    wie bei den Wetter-Rekorden (Anmerkung 156): zwei Fassungen von „was ist
    eine Lücke" liefen beim ersten Sonderfall auseinander, und die Sonderfälle
    stehen längst da — die Ränder hängen am Geburts-Meilenstein, und ein
    Wohnort-Tag ist keine Lücke mehr (Anmerkung 144/145).

    Die SERIE bleibt hier: sie liest dieselbe Tagesmenge, beantwortet aber die
    umgekehrte Frage, und für die gibt es keinen zweiten Leser.
    """
    days = _days(db, user_id)
    out: dict = {"longest_run": None, "longest_gap": None, "longest_trip": None}
    if not days:
        return out

    best_run = (days[0], days[0], 1)
    run_start, run_len = days[0], 1
    for prev, cur in zip(days, days[1:]):
        if (cur - prev).days == 1:
            run_len += 1
            if run_len > best_run[2]:
                best_run = (run_start, cur, run_len)
        else:
            run_start, run_len = cur, 1
    out["longest_run"] = {"from": best_run[0].isoformat(),
                          "to": best_run[1].isoformat(), "days": best_run[2]}
    # Die Tagesmenge wird weitergereicht statt neu geholt: sie steht hier schon
    # im Speicher, und ein zweiter Kalenderdurchlauf über vierzig Jahre für
    # dieselbe Menge wäre der Preis dafür, die Regel an einer Stelle zu haben —
    # er muss nicht bezahlt werden.
    out["longest_gap"] = gaps.longest(db, user_id, days=set(days))

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
    # F20: EINMAL rechnen, viermal verwenden. Der Kalenderdurchlauf ist billig,
    # aber vier Durchläufe wären vier Stellen, an denen „was ist ein
    # abgeleiteter Tag" beantwortet wird (Anmerkung 106).
    b = baseline.day_counts(db, user_id)
    day_key = day_number(Event.date_start)
    year_rows = (db.query(func.extract("year", Event.date_start).label("y"),
                          func.count(func.distinct(day_key)),
                          func.count(Event.id))
                 .filter(Event.user_id == user_id, Event.date_start.isnot(None))
                 .group_by("y")
                 .order_by(func.count(func.distinct(day_key)).desc(),
                           func.count(Event.id).desc(), "y")
                 .limit(_PRE_N if b["years"] else n).all())

    return {
        "weather": _weather_tops(db, user_id, n),
        "places": _place_ranking(db, user_id, b["places"]),
        # Der Leerstring heißt „nachgesehen, gibt es hier nicht" (A39) und ist
        # keine Stadt — er fällt hier genauso weg wie NULL.
        "cities": _ranked(db, user_id, Location.city,
                          Event.location_id == Location.id, Location.city != "",
                          baseline_days=b["cities"]),
        "countries": _ranked(db, user_id, Location.country,
                             Event.location_id == Location.id,
                             Location.country != "",
                             baseline_days=b["countries"]),
        "years": _merge_baseline(
            [{"name": str(int(y)), "days": d, "events": e} for y, d, e in year_rows],
            {str(y): n for y, n in b["years"].items()}),
        # **Kategorien bekommen den Wohnort NICHT**, und das ist keine Lücke:
        # ein abgeleiteter Tag hat keine Kategorie. Ihm eine zu geben — und sei
        # es „event" — hieße, eine Aussage zu erfinden, die niemand gemacht hat.
        "categories": _ranked(db, user_id, Event.category),
        "streaks": _streaks(db, user_id),
        "photos": _photo_stats(db, user_id, n),
        "farthest": _farthest_from_home(db, user_id),
        "reach": _reach_per_year(db, user_id),
        "baseline_days": b["total"],
    }


def _farthest_from_home(db: Session, user_id: str) -> dict | None:
    """**Anmerkung 189 — wie weit war ich je von zu Hause weg?**

    Die Frage ist erst beantwortbar, seit es Wohnorte gibt: „weit weg" braucht
    ein Bezugssystem, und ein Lebensmittelpunkt wandert. Gemessen wird deshalb
    gegen den Wohnort, der AN DIESEM TAG galt — nicht gegen den heutigen. Sonst
    wäre die Kindheit an der Ostsee eine Fernreise, sobald jemand nach München
    zieht.

    **Gruppiert wird über ORTE, nicht über Ereignisse.** Der entfernteste Punkt
    ist eine Eigenschaft des Orts; zwanzigtausend Ereignisse dafür in den
    Prozess zu holen hieße, dieselbe Koordinate hundertmal zu rechnen. Ein
    Bestand hat Hunderte Orte und Zehntausende Einträge.

    Ohne Wohnort gibt es keine Antwort — und dann steht hier `None` statt einer
    Null, die wie „war nie weg" aussieht.
    """
    periods = baseline.spans(db, user_id)
    if not periods:
        return None
    best: dict | None = None
    for start, end, row in periods:
        home = row.location
        if home is None or home.lat is None or home.lng is None:
            continue
        rows = (db.query(Location.name, Location.city, Location.country,
                         Location.lat, Location.lng,
                         func.min(Event.date_start).label("first"))
                .join(Event, Event.location_id == Location.id)
                .filter(Event.user_id == user_id,
                        Event.date_start >= datetime.combine(start, time.min),
                        Event.date_start <= datetime.combine(end, time.max),
                        Location.lat.isnot(None), Location.lng.isnot(None))
                .group_by(Location.id, Location.name, Location.city,
                          Location.country, Location.lat, Location.lng).all())
        for name, city, country, lat, lng, first in rows:
            km = _haversine_km(home.lat, home.lng, lat, lng)
            if best is None or km > best["km"]:
                best = {"km": round(km, 1),
                        "place": ov._short_place(name) or name,
                        "city": city, "country": country,
                        "date": first.date().isoformat() if first else None,
                        "home": row.label or (ov._short_place(home.name)
                                              or home.name)}
    return best


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Luftlinie in Kilometern.

    In Python und nicht in SQL: `sin`/`cos` sind in SQLite nur vorhanden, wenn
    es mit `SQLITE_ENABLE_MATH_FUNCTIONS` gebaut wurde — eine Abfrage, die auf
    der einen Datenbank rechnet und auf der anderen abstürzt, ist genau die
    Dialektfalle, für die es `tools/pg-test.ps1` gibt. Gerechnet wird ohnehin
    über Orte, nicht über Ereignisse (siehe oben).
    """
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _reach_per_year(db: Session, user_id: str) -> list[dict]:
    """Wie viele verschiedene Länder und Städte je Jahr — Reichweite statt Menge.

    **Der Wohnort zählt mit**, und das ist keine Kleinigkeit: ein Jahr, das
    jemand ganz zu Hause verbracht hat, stünde sonst mit „0 Länder" da, obwohl
    er in einem war. Dieselbe Regel wie überall seit F20 — wer eine Zahl über
    TAGE oder über ORTE bildet, muss ihn mitzählen (nur Zahlen über EINTRÄGE
    dürfen es nicht).
    """
    rows = (db.query(func.extract("year", Event.date_start).label("y"),
                     Location.country, Location.city)
            .join(Location, Event.location_id == Location.id)
            .filter(Event.user_id == user_id, Event.date_start.isnot(None))
            .distinct().all())
    by_year: dict[int, tuple[set, set]] = {}
    for year, country, city in rows:
        lands, towns = by_year.setdefault(int(year), (set(), set()))
        if country:
            lands.add(country)
        if city:
            towns.add(city)
    for start, end, row in baseline.spans(db, user_id):
        loc = row.location
        if loc is None:
            continue
        for year in range(start.year, end.year + 1):
            lands, towns = by_year.setdefault(year, (set(), set()))
            if loc.country:
                lands.add(loc.country)
            if loc.city:
                towns.add(loc.city)
    return [{"year": y, "countries": len(lands), "cities": len(towns)}
            for y, (lands, towns) in sorted(by_year.items())]


def _photo_stats(db: Session, user_id: str, n: int) -> dict:
    """**Anmerkung 189 — was von den Fotos zu sagen ist.**

    Bis hierher gab es über Medien keine einzige Zusammenfassung. Sie sind
    dabei die zweitgrößte Menge im Bestand: nach einem Immich-Abgleich stehen
    zehntausende Verweise da, und niemand konnte fragen, in welchem Jahr sie
    liegen.

    **Der Tag eines Fotos ist `captured_at`, ersatzweise das Datum seines
    Ereignisses.** Beides kommt vor, und zwar aus einem Grund (F18): ein Bild
    kann an einem Ereignis hängen ODER an einem Tag. Nur eines von beiden zu
    lesen ließe die halbe Sammlung aus einer Statistik verschwinden, die
    vollständig aussieht.

    **Hochgeladen und verknüpft werden getrennt gezählt** (Anmerkung 57): ein
    hochgeladenes Bild ist Lebensdatenbank, ein Immich-Verweis eine Ableitung,
    die ein Abgleich jederzeit neu bildet. Eine gemeinsame Zahl verspräche
    einen Bestand, von dem ein Teil woanders liegt — und der Unterschied ist
    genau der, den ein Backup merkt.
    """
    day_of = func.coalesce(MediaRef.captured_at, Event.date_start)
    base = (db.query(MediaRef)
            .outerjoin(Event, MediaRef.event_id == Event.id)
            .filter(MediaRef.user_id == user_id))

    total = base.count()
    if not total:
        return {"total": 0, "uploads": 0, "linked": 0, "events_with_photo": 0,
                "events_total": 0, "first": None, "last": None,
                "years": [], "days": [], "bytes": 0}

    kinds = dict(db.query(MediaRef.provider, func.count(MediaRef.id))
                 .filter(MediaRef.user_id == user_id)
                 .group_by(MediaRef.provider).all())
    # Nur Hochgeladenes belegt Platz auf DIESER Platte — ein Immich-Verweis
    # ist ein paar Zeichen. Sie zusammenzuzählen wäre eine Größenangabe über
    # ein fremdes System.
    size = (db.query(func.sum(MediaRef.bytes))
            .filter(MediaRef.user_id == user_id,
                    MediaRef.provider == "local").scalar() or 0)

    dated = base.filter(day_of.isnot(None))
    span = dated.with_entities(func.min(day_of), func.max(day_of)).one()
    years = (dated.with_entities(func.extract("year", day_of).label("y"),
                                 func.count(MediaRef.id))
             .group_by("y").order_by("y").all())
    days = (dated.with_entities(day_number(day_of).label("d"),
                                func.count(MediaRef.id).label("n"))
            .group_by("d").order_by(func.count(MediaRef.id).desc(), "d")
            .limit(n).all())

    def _iso(num) -> str:
        num = int(num)
        return f"{num // 10000:04d}-{num // 100 % 100:02d}-{num % 100:02d}"

    return {
        "total": total,
        "uploads": int(kinds.get("local", 0)),
        "linked": total - int(kinds.get("local", 0)),
        # „An wie vielen deiner Einträge hängt ein Bild?" — die Zahl ist erst
        # mit ihrem Nenner eine Aussage.
        "events_with_photo": (db.query(func.count(func.distinct(MediaRef.event_id)))
                              .filter(MediaRef.user_id == user_id,
                                      MediaRef.event_id.isnot(None)).scalar() or 0),
        "events_total": (db.query(func.count(Event.id))
                         .filter(Event.user_id == user_id).scalar() or 0),
        "first": span[0].date().isoformat() if span[0] else None,
        "last": span[1].date().isoformat() if span[1] else None,
        "bytes": int(size),
        "years": [{"year": int(y), "count": int(c)} for y, c in years],
        "days": [{"day": _iso(d), "count": int(c)} for d, c in days],
    }


def _weather_tops(db: Session, user_id: str, n: int) -> dict[str, list[dict]]:
    """Zu jeder Rekord-Kachel die vollen `n` Plätze — ein Tag je Zeile.

    Die Rangfolge selbst steht in `stats_overview._extreme_tops` — dieselbe
    Funktion, die die Kachel füllt. Hier wird nur mit einem anderen `n`
    gefragt (Anmerkung 156). **Dass ein Tag nur einmal vorkommt, ist deshalb
    keine Regel dieser Datei** (Anmerkung 161): stünde sie hier, hätte die
    Kachel darüber sie nicht, und Platz 1 der Liste wäre wieder ein anderes
    Ereignis als die Kachel — genau die Trennung, gegen die Anmerkung 156
    diese Funktion zusammengelegt hat.
    """
    events, values, val, card = ov.weather_values(db, user_id)
    if not values:
        return {name: [] for name, *_ in ov._EXTREMES}
    return ov._extreme_tops(events, values, val, card, n)
