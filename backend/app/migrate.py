"""Leichtgewichtige Schema-Migration (MVP, ohne Alembic).

Ergänzt fehlende Spalten in bestehenden Datenbanken per ALTER TABLE
(SQLite und Postgres können beide ADD COLUMN). Später ersetzt Alembic
diesen Mechanismus.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# Tabelle -> {Spalte: SQL-Typ}
_MISSING_COLUMNS: dict[str, dict[str, str]] = {
    "fragments": {"user_id": "VARCHAR(36)"},
    "locations": {"user_id": "VARCHAR(36)"},
    "events": {"user_id": "VARCHAR(36)", "embedding": "JSON", "note": "TEXT",
               "external_id": "VARCHAR(64)",
               "confirmed_at": "TIMESTAMP", "confirmed_by": "VARCHAR(16)"},
    "entities": {"user_id": "VARCHAR(36)"},
}

# Einmalige Nacharbeiten, wenn eine Spalte NEU angelegt wurde (Bestandsdaten).
# P2.7: bereits bestätigte Events bekommen eine plausible Provenienz —
# Import-Besuche waren automatisch bestätigt, alles andere war manuell;
# als Zeitpunkt dient die letzte Änderung (genauer geht es rückwirkend nicht).
_BACKFILLS: dict[str, str] = {
    "events.confirmed_by": (
        "UPDATE events SET "
        "confirmed_at = updated_at, "
        "confirmed_by = CASE WHEN source = 'google_timeline' "
        "THEN 'import' ELSE 'manual' END "
        "WHERE confirmed = 'confirmed'"
    ),
}


def ensure_schema(engine: Engine) -> list[str]:
    """Fügt fehlende Spalten hinzu. Gibt die durchgeführten Änderungen zurück."""
    insp = inspect(engine)
    applied: list[str] = []
    existing_tables = set(insp.get_table_names())
    for table, columns in _MISSING_COLUMNS.items():
        if table not in existing_tables:
            continue  # wird von create_all frisch angelegt
        have = {c["name"] for c in insp.get_columns(table)}
        for col, sqltype in columns.items():
            if col in have:
                continue
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {sqltype}'))
                backfill = _BACKFILLS.get(f"{table}.{col}")
                if backfill:
                    conn.execute(text(backfill))
            applied.append(f"{table}.{col}")
    return applied


def adopt_orphan_rows(engine: Engine, user_id: str) -> int:
    """Hängt Alt-Daten ohne user_id an den angegebenen Nutzer.

    Wird beim Anlegen des ERSTEN Nutzers aufgerufen, damit Daten aus der
    Single-User-Zeit nicht verwaist bleiben.
    """
    total = 0
    with engine.begin() as conn:
        for table in ("fragments", "locations", "events", "entities"):
            result = conn.execute(
                text(f'UPDATE "{table}" SET user_id = :uid WHERE user_id IS NULL'),
                {"uid": user_id},
            )
            total += result.rowcount or 0
    return total
