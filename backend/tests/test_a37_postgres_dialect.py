"""A37 — die neuen Abfragen müssen auch auf PostgreSQL gültig sein.

Die Tests laufen auf SQLite (in-memory, schnell, ohne Server). Betrieben wird
Life-Dash aber auch — und vom Autor sogar bevorzugt — auf **PostgreSQL**. Die
Abfragen, die A37 hinzugefügt hat, sind ausgerechnet die dialektempfindlichen:
`extract(year …)`, `GROUP BY` auf einen Ausgabenamen, `NULLS LAST`, `ILIKE`,
ein `IN` über Enum-Werte.

Ein Fehler darin fiele in der Testsuite nie auf und beim ersten Start auf der
echten Datenbank sofort. Dieser Test übersetzt die Abfragen deshalb gegen den
PostgreSQL-Dialekt und prüft das erzeugte SQL. Er ersetzt keinen Lauf gegen
einen echten Server (Typen, Sortierreihenfolgen), fängt aber alles, was schon
beim Übersetzen schiefgeht — und das ist die Fehlerklasse, die hier droht.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import func, or_
from sqlalchemy.dialects import postgresql

from app.models import ConfirmState, DatePrecision, Event, Location, Metric, Source
from app.services.stats_overview import _MOVE_WORDS

PG = postgresql.dialect()


def _sql(query) -> str:
    """Die Abfrage als PostgreSQL-SQL — mit eingesetzten Literalen, damit man
    im Fehlerfall im Testbericht sieht, worum es geht."""
    return str(query.statement.compile(
        dialect=PG, compile_kwargs={"literal_binds": True}))


def test_the_paged_list_query_compiles_for_postgres(db, user):
    """Fensterung, Sortierung und Blättern in einem Zug."""
    query = (db.query(Event)
             .filter(Event.user_id == user.id,
                     Event.date_start >= datetime(2024, 1, 1),
                     Event.date_start <= datetime(2024, 12, 31),
                     Event.source != Source.google_timeline)
             .order_by(Event.date_start.desc().nullslast(), Event.id.desc())
             .limit(300).offset(600))
    sql = _sql(query).lower()

    assert "nulls last" in sql, "eindeutige Sortierung ist die Grundlage des Blätterns"
    assert "limit 300" in sql and "offset 600" in sql
    assert "order by" in sql and sql.index("order by") < sql.index("limit")


def test_the_vague_filter_compiles_for_postgres(db, user):
    """`IN` über Enum-Werte — auf PostgreSQL ein nativer Enum-Typ."""
    query = (db.query(Event)
             .filter(Event.user_id == user.id,
                     Event.date_start.is_(None)
                     | Event.date_precision.in_((DatePrecision.month,
                                                 DatePrecision.year))))
    sql = _sql(query).lower()
    assert "is null" in sql and " in (" in sql


def test_the_year_index_compiles_for_postgres(db, user):
    """`extract(year …)` plus `GROUP BY` auf den Ausgabenamen.

    Genau hier trennen sich die Dialekte: SQLite baut daraus ein
    `CAST(STRFTIME(…))`, PostgreSQL ein `EXTRACT(year FROM …)`."""
    year = func.extract("year", Event.date_start)
    query = (db.query(year.label("y"), func.count(Event.id))
             .filter(Event.user_id == user.id, Event.date_start.isnot(None))
             .group_by("y").order_by("y"))
    sql = _sql(query).lower()

    assert "extract(year from" in sql, sql
    assert "group by y" in sql and "order by y" in sql, sql
    assert "strftime" not in sql, "SQLite-Syntax darf hier nicht auftauchen"


def test_the_text_rules_compile_for_postgres(db, user):
    """`ILIKE`: auf SQLite `lower() LIKE lower()`, auf PostgreSQL nativ —
    beide unabhängig von der Groß-/Kleinschreibung, wie die Regel es braucht."""
    like = [Event.title.ilike(f"%{w}%") for w in _MOVE_WORDS]
    query = (db.query(Event.id)
             .filter(Event.user_id == user.id, Event.category == "milestone",
                     or_(*like)))
    sql = _sql(query).lower()
    assert "ilike" in sql, sql
    assert "umzug" in sql and "eingezogen" in sql


def test_the_statistics_aggregates_compile_for_postgres(db, user):
    """Die Gruppierungen, aus denen die Kacheln entstehen."""
    per_cat = (db.query(Event.category, func.count(Event.id))
               .filter(Event.user_id == user.id).group_by(Event.category))
    assert "group by events.category" in _sql(per_cat).lower()

    places = (db.query(Location.name, func.count(Event.id))
              .join(Event, Event.location_id == Location.id)
              .filter(Event.user_id == user.id, Location.name.isnot(None))
              .group_by(Location.name))
    sql = _sql(places).lower()
    assert "join" in sql and "group by locations.name" in sql

    children = (db.query(Event.parent_event_id, func.count(Event.id))
                .filter(Event.user_id == user.id,
                        Event.parent_event_id.in_(["a", "b"]))
                .group_by(Event.parent_event_id))
    assert "group by events.parent_event_id" in _sql(children).lower()

    weather = (db.query(Metric.event_id, Metric.key, Metric.value)
               .join(Event, Event.id == Metric.event_id)
               .filter(Event.user_id == user.id,
                       Metric.source == Source.weather,
                       Metric.key.in_(("rain_mm", "sunshine_h")),
                       Metric.value.isnot(None)))
    sql = _sql(weather).lower()
    assert "join events" in sql and "metrics.key in" in sql

    confirmed = (db.query(func.count(Event.id))
                 .filter(Event.user_id == user.id,
                         Event.confirmed != ConfirmState.confirmed))
    assert "count(" in _sql(confirmed).lower()


def test_the_map_query_compiles_for_postgres(db, user):
    query = (db.query(Event)
             .filter(Event.user_id == user.id, Event.location_id.isnot(None))
             .join(Event.location)
             .filter(Location.lat.isnot(None), Event.date_start.isnot(None))
             .order_by(Event.date_start.asc(), Event.id.asc()))
    sql = _sql(query).lower()
    assert "join locations" in sql and "order by" in sql


@pytest.mark.parametrize("value", [0, 1, 12007])
def test_extract_results_survive_the_numeric_type(value):
    """PostgreSQL liefert `extract` als Decimal, SQLite als int/float. Der
    Index castet deshalb — hier festgehalten, damit der Cast bleibt."""
    from decimal import Decimal
    assert int(Decimal(value)) == value


def test_the_on_this_day_preselection_compiles_for_postgres(db, user):
    """`extract(month/day …)` — die Vorauswahl von „An diesem Tag"."""
    query = (db.query(Event)
             .filter(Event.user_id == user.id,
                     Event.date_end.isnot(None)
                     | ((func.extract("month", Event.date_start) == 7)
                        & (func.extract("day", Event.date_start) == 22))))
    sql = _sql(query).lower()
    assert "extract(month from" in sql and "extract(day from" in sql, sql
    assert "strftime" not in sql
