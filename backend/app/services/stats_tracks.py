"""Anmerkung 189 — was aus den zurückgelegten Wegen zu holen ist.

**Warum das eine eigene Datei und ein eigener Reiter ist.** Diese Zahlen haben
eine andere HERKUNFT als alles andere in der Statistik. Alles übrige rechnet
über das, was der Nutzer erfasst oder eingetragen hat; hier steht ausschließlich,
was ein Google-Timeline-Export hergab. Das ist kein Detail, sondern der
Unterschied zwischen „so war es" und „so hat ein fremdes System es
aufgezeichnet":

* Eine Fahrt ohne Telefon in der Tasche gibt es nicht.
* Die Fortbewegungsart ist Googles **Vermutung** (`walk|drive|cycle|run|
  transit|unknown`) — ein Fußweg im Bus zählt gern als Radfahrt.
* Die Strecke kommt aus dem Export; fehlt sie dort, wird sie hier aus der
  Punktfolge gerechnet (`routers/tracks.py`), also als Summe von Luftlinien
  zwischen Messpunkten. Bei grober Aufzeichnung ist das ZU WENIG (Kurven
  fallen weg), bei GPS-Rauschen im Stand zu viel.
* Zeiträume ohne Export fehlen ganz — und eine Jahressumme sieht nicht anders
  aus als ein Jahr, in dem jemand zu Hause geblieben ist.

Deshalb steht die Warnung nicht im Kleingedruckten, sondern über den Zahlen,
und deshalb sind diese Zahlen NICHT in den Ranglisten gelandet, wo sie neben
erfassten Tatsachen stünden, als wären sie welche (A40, und derselbe Satz wie
bei der Wetterquelle in Anmerkung 186).

**Gerechnet wird in SQL**, weil ein Timeline-Import sechsstellig viele Segmente
anlegen kann. `points` wird dabei nie geladen — die Punktfolge ist das größte
Feld der Tabelle und für eine Summe ohne Belang.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Track

# Wie viele Jahre und Einzelwege die Antwort höchstens trägt. Kein Größen-
# schutz, sondern eine Ansichtsgrenze: die Liste ist eine Rangliste.
TOP_N = 10


def compute_tracks(db: Session, user_id: str) -> dict:
    """Kilometer je Fortbewegungsart und je Jahr, plus die längsten Einzelwege.

    `{"total_km", "count", "first", "last", "modes": [...], "years": [...],
      "longest": [...]}`

    **Wege ohne Strecke zählen mit, aber nur als Anzahl.** `distance_m` kann
    `NULL` sein (ein Segment ohne verwertbare Punkte). Sie in die Summe zu
    ziehen ginge nicht, sie aus der ZAHL der Wege zu nehmen wäre eine zweite
    Auswahl für dieselbe Frage — die Antwort auf „wie viele Wege" darf nicht
    davon abhängen, ob eine Strecke dabeisteht.
    """
    base = db.query(Track).filter(Track.user_id == user_id)
    count = base.count()
    if not count:
        return {"total_km": 0.0, "count": 0, "first": None, "last": None,
                "modes": [], "years": [], "longest": []}

    total_m = (db.query(func.sum(Track.distance_m))
               .filter(Track.user_id == user_id).scalar() or 0)
    span = (db.query(func.min(Track.date_start), func.max(Track.date_end))
            .filter(Track.user_id == user_id).one())

    mode_rows = (db.query(Track.activity_type, func.count(Track.id),
                          func.sum(Track.distance_m))
                 .filter(Track.user_id == user_id)
                 .group_by(Track.activity_type)
                 .order_by(func.sum(Track.distance_m).desc().nullslast()).all())
    year_rows = (db.query(func.extract("year", Track.date_start).label("y"),
                          func.count(Track.id), func.sum(Track.distance_m))
                 .filter(Track.user_id == user_id)
                 .group_by("y").order_by("y").all())
    long_rows = (db.query(Track.date_start, Track.activity_type,
                          Track.distance_m)
                 .filter(Track.user_id == user_id,
                         Track.distance_m.isnot(None))
                 .order_by(Track.distance_m.desc())
                 .limit(TOP_N).all())

    km = lambda m: round((m or 0) / 1000, 1)  # noqa: E731
    return {
        "total_km": km(total_m),
        "count": count,
        "first": span[0].date().isoformat() if span[0] else None,
        "last": span[1].date().isoformat() if span[1] else None,
        # `None` bleibt `None` und wird nicht zu „unbekannt" gemacht: die
        # Oberfläche übersetzt, der Server behauptet nichts.
        "modes": [{"mode": mode, "count": int(c), "km": km(m)}
                  for mode, c, m in mode_rows],
        "years": [{"year": int(y), "count": int(c), "km": km(m)}
                  for y, c, m in year_rows],
        "longest": [{"date": d.date().isoformat(), "mode": mode, "km": km(m)}
                    for d, mode, m in long_rows],
    }
