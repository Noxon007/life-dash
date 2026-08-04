"""F21 — wo weiß ich gar nichts? (Anmerkung 145). Schicht 4, nichts gespeichert.

**Die Frage, die diese Datei beantwortet, hat F20 erst beantwortbar gemacht.**
Vorher hätte eine Lückenprüfung jeden Kindheitstag als Lücke gemeldet, und ein
Bericht mit sechstausend Einträgen ist kein Bericht. Seit ein Wohnort-Tag
*zählt* (Anmerkung 144, Entscheidung 2), ist die Antwort auf „wo ist eine
Lücke?" nicht mehr „wo habe ich nichts ERFASST", sondern **„wo weiß ich gar
nichts"** — und das ist die Frage, die gestellt wurde.

**Ein Tag gilt als bekannt, wenn irgendetwas über ihn bekannt ist:** ein
Eintrag (auch ein unbestätigter — ein Vorschlag für den 14. März ist ein
Hinweis, dass an dem Tag etwas war) oder ein Wohnort. Beides kommt aus
`services/baseline.py`, damit „welche Tage sind belegt" genau einmal
beantwortet wird.

**Nichts hiervon wird gespeichert, und das ist die wichtigste Zeile in dieser
Datei.** Anmerkung 145 hat den Grund vorweggenommen: eine gespeicherte Lücke
müsste bei jedem Import, jeder Löschung und jeder Zeitraum-Änderung nachgeführt
werden, und eine veraltete Lückenliste ist schlimmer als keine — sie schickt
jemanden auf die Suche nach Daten, die längst da sind.

**Die Ränder.** Gemessen wird zwischen dem **Geburts-Meilenstein** (F17) und
**heute**, wenn es einen gibt: dann ist bekannt, dass da ein Leben war, über
das nichts vorliegt, und genau danach wurde gefragt. Fehlt der Meilenstein,
bleibt es bei der alten Regel aus Anmerkung 156 — vom ersten bis zum letzten
bekannten Tag, denn die Zeit davor ist keine Lücke, sondern die Zeit vor dem
ersten Eintrag, und sie als Befund über ein Leben auszugeben wäre eine Aussage
über den Beginn der Aufzeichnung.
"""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.services import baseline
from app.services.stats_overview import find_birth

# Wie viele Strecken höchstens in eine Antwort gehen. Ein Bestand aus
# fünfhundert verstreuten Tagen hat fünfhundert Lücken; die längsten zwanzig
# beantworten „wo fange ich an?", die restlichen vierhundertachtzig sind eine
# Liste. Überschritten wird der Deckel nie stillschweigend — `stretch_count`
# und `unknown_days` stehen daneben (A40/Anmerkung 110).
TOP_N = 20


def known_days(db: Session, user_id: str, *, today: date_type | None = None
               ) -> tuple[set[date_type], int, int]:
    """(alle bekannten Tage, davon erfasst, davon abgeleitet).

    Die drei Zahlen kommen aus EINEM Durchgang, weil die Ansicht sie zusammen
    zeigt: „von 14 600 Tagen sind 312 erfasst und 2 190 abgeleitet" ist eine
    Auskunft, „312 Tage" allein wäre eine halbe.

    **Tage in der ZUKUNFT bleiben draußen**, und das ist keine Kosmetik: ein
    Eintrag mit falsch getipptem Jahr (2099 statt 1999) zöge sonst das Fenster
    dieses Berichts über siebzig Jahre auf und meldete sie als eine einzige
    riesige Lücke — ein Tippfehler als Befund über ein Leben. Ein geplanter
    Termin ist ebenfalls kein Wissen über Vergangenes. Die Grenze steht hier,
    an der Quelle, statt in jedem Aufrufer noch einmal.
    """
    today = today or date_type.today()
    recorded = {d for d in baseline.recorded_days(db, user_id) if d <= today}
    inferred = {d for d in baseline.inferred_days(db, user_id, today=today,
                                                  taken=recorded)
                if d <= today}
    return recorded | inferred, len(recorded), len(inferred)


def window(db: Session, user_id: str, days: set[date_type], *,
           today: date_type | None = None
           ) -> tuple[date_type | None, date_type | None, bool]:
    """(Anfang, Ende, ab-Geburt?) — der Zeitraum, über den gemessen wird.

    Die Unterscheidung ist der ganze Unterschied zwischen zwei Berichten:
    **mit** Geburts-Meilenstein wird über ein Leben berichtet, **ohne** ihn nur
    über den Zeitraum, in dem aufgezeichnet wurde. Beides ist richtig; was
    falsch wäre, ist das eine zu zeigen und das andere zu behaupten. Deshalb
    reist das Kennzeichen bis in die Anzeige mit.
    """
    today = today or date_type.today()
    birth = find_birth(db, user_id)
    start = None
    if birth and birth.get("date_start"):
        b = birth["date_start"]
        start = b.date() if isinstance(b, datetime) else b
    if start is not None and start <= today:
        return start, today, True
    if not days:
        return None, None, False
    return min(days), max(days), False


def stretches(db: Session, user_id: str, *, today: date_type | None = None,
              days: set[date_type] | None = None,
              bounds: tuple | None = None) -> list[dict]:
    """Jede zusammenhängende Strecke unbekannter Tage — chronologisch.

    `[{"from": "1994-03-02", "to": "1994-08-06", "days": 158}]`

    **Einzelne Tage werden nicht ausgesiebt.** Eine Mindestlänge wäre eine
    zweite, numerische Antwort auf die Frage, die diese Liste schon beantwortet
    — genau die Doppelregel, die Anmerkung 160 an anderer Stelle abgeschafft
    hat. Wer die kurzen nicht sehen will, liest die Liste von oben: sortiert
    wird beim Aufrufer nach Länge.
    """
    today = today or date_type.today()
    if days is None:
        days, _rec, _inf = known_days(db, user_id, today=today)
    else:
        # **Die Zukunftsgrenze gilt auch für übergebene Mengen.** `_streaks`
        # reicht seine eigene Tagesliste herein (sie liegt dort schon im
        # Speicher), und die ist NICHT gefiltert. Ein einziger Eintrag mit
        # vertipptem Jahr — 2999 statt 1999 — machte daraus ein Fenster über
        # tausend Jahre und einen Kalenderdurchlauf über 350 000 Tage, für eine
        # Kachel. Eine Zusage, die davon abhängt, dass der Aufrufer sie kennt,
        # ist keine.
        days = {d for d in days if d <= today}
    lo, hi = bounds if bounds is not None else window(db, user_id, days,
                                                     today=today)[:2]
    if lo is None or hi is None or hi < lo:
        return []
    out: list[dict] = []
    step = timedelta(days=1)
    day, run_from = lo, None
    while day <= hi:
        if day in days:
            if run_from is not None:
                out.append({"from": run_from.isoformat(),
                            "to": (day - step).isoformat(),
                            "days": (day - run_from).days})
                run_from = None
        elif run_from is None:
            run_from = day
        day += step
    if run_from is not None:
        out.append({"from": run_from.isoformat(), "to": hi.isoformat(),
                    "days": (hi - run_from).days + 1})
    return out


def longest(db: Session, user_id: str, *, today: date_type | None = None,
            days: set[date_type] | None = None,
            bounds: tuple | None = None) -> dict | None:
    """Die längste Lücke — oder None.

    **Die Kachel ist Platz 1 der Liste** (dasselbe Muster wie Anmerkung 156 bei
    den Wetter-Rekorden): die Rangliste in der Statistik und die Lücken-Ansicht
    lesen dieselbe Funktion. Zwei Fassungen von „was ist eine Lücke" liefen beim
    ersten Sonderfall auseinander, und die Sonderfälle stehen längst da — die
    Ränder hängen am Geburts-Meilenstein, und ein Wohnort-Tag ist keine Lücke.
    """
    rows = stretches(db, user_id, today=today, days=days, bounds=bounds)
    if not rows:
        return None
    return max(rows, key=lambda r: (r["days"], r["from"]))


def report(db: Session, user_id: str, *, today: date_type | None = None,
           limit: int = TOP_N) -> dict:
    """Alles, was die Lücken-Ansicht zeigt — in einem Durchgang.

    Die Jahresabdeckung fällt dabei ab: sie beantwortet „wo fange ich an?"
    besser als jede Liste, weil sie den ganzen Zeitraum auf einen Blick zeigt,
    statt zwanzig Strecken zu nennen und die anderen vierhundert zu verschweigen.
    """
    days, recorded, inferred = known_days(db, user_id, today=today)
    lo, hi, since_birth = window(db, user_id, days, today=today)
    out: dict = {
        "from": lo.isoformat() if lo else None,
        "to": hi.isoformat() if hi else None,
        "since_birth": since_birth,
        "total_days": 0, "known_days": 0, "unknown_days": 0,
        "recorded_days": recorded, "baseline_days": inferred,
        "stretches": [], "stretch_count": 0, "per_year": [],
    }
    if lo is None or hi is None:
        return out

    total = (hi - lo).days + 1
    # Nur die Tage IM Fenster zählen als bekannt. Ohne die Einschränkung wäre
    # ein Eintrag vor der Geburt (ein Tippfehler im Datum, ein Meilenstein der
    # Eltern) eine Abdeckung, die es nicht gibt — und die Summe „bekannt +
    # unbekannt" ergäbe nicht mehr die Länge des Zeitraums.
    inside = {d for d in days if lo <= d <= hi}
    out["total_days"] = total
    out["known_days"] = len(inside)
    out["unknown_days"] = total - len(inside)

    rows = stretches(db, user_id, today=today, days=days, bounds=(lo, hi))
    out["stretch_count"] = len(rows)
    out["stretches"] = sorted(rows, key=lambda r: (-r["days"], r["from"]))[:limit]

    # Jahresabdeckung: bekannte von möglichen Tagen je Jahr. Gerechnet über die
    # Ränder des Fensters, damit das erste und das letzte Jahr nicht als
    # unvollständig dastehen, nur weil der Zeitraum mitten in ihnen beginnt.
    per_year: dict[int, list[int]] = {}
    for year in range(lo.year, hi.year + 1):
        y_lo = max(lo, date_type(year, 1, 1))
        y_hi = min(hi, date_type(year, 12, 31))
        per_year[year] = [0, (y_hi - y_lo).days + 1]
    for d in inside:
        per_year[d.year][0] += 1
    out["per_year"] = [[y, k, n] for y, (k, n) in sorted(per_year.items())]
    return out
