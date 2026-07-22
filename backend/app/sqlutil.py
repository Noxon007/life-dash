"""Kleine SQL-Bausteine, die in beiden Dialekten gleich funktionieren.

Der Testlauf ist SQLite, die Anlage des Autors PostgreSQL — ein Unterschied,
den `test_a37_postgres_dialect.py` schon einmal teuer gemacht hat. Was hier
steht, wurde deshalb bewusst aus einem Router herausgezogen: sobald eine
zweite Stelle dieselbe Frage stellt („welcher Kalendertag ist das?"), darf es
nicht zwei Antworten geben.
"""
from __future__ import annotations

from sqlalchemy import func


def day_parts(col):
    """Jahr/Monat/Tag eines Zeitstempels — dialektneutral.

    `date(x)` gibt es so nur in SQLite, `x::date` nur in Postgres; `extract`
    können beide. Gedacht zum Gruppieren: `group_by(*day_parts(Event.date_start))`
    fasst alles zusammen, was am selben Kalendertag liegt.
    """
    return (func.extract("year", col), func.extract("month", col),
            func.extract("day", col))
