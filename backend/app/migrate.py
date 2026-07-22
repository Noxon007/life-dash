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
    "fragments": {"user_id": "VARCHAR(36)",
                  "capture_lat": "FLOAT", "capture_lng": "FLOAT"},
    # A39: `city` neben `country` — bis dahin steckte die Stadt nur als
    # Textbaustein im zusammengesetzten Namen und war nicht gruppierbar.
    # Anmerkung 110: `address` bewahrt die Roh-Bausteine des Geocoders
    # (Straße, Bezirk, PLZ, Region …). Bis dahin wurden sie verworfen, sobald
    # `short_name()` daraus einen Anzeigenamen gebaut hatte — und damit war ein
    # anderes Namensformat nur über einen neuen Nominatim-Lauf zu haben,
    # gedrosselt auf eine Abfrage je 1,2 Sekunden. Mit den Bausteinen ist es
    # eine reine Rechenoperation.
    "locations": {"user_id": "VARCHAR(36)", "country": "VARCHAR(64)",
                  "city": "VARCHAR(128)", "address": "JSON"},
    "events": {"user_id": "VARCHAR(36)", "embedding": "JSON", "note": "TEXT",
               "external_id": "VARCHAR(64)",
               "confirmed_at": "TIMESTAMP", "confirmed_by": "VARCHAR(16)",
               "parent_event_id": "VARCHAR(36)"},
    "entities": {"user_id": "VARCHAR(36)"},
    "jobs": {"params": "JSON"},
    # A35: Passwort-Hash für lokale Konten (NULL bei OIDC/dev)
    "users": {"password_hash": "VARCHAR(255)"},
    # F15: hochgeladene Bilder. `user_id` schließt die Lücke aus Anmerkung 57.
    "media_refs": {"user_id": "VARCHAR(36)", "mime": "VARCHAR(64)",
                   "bytes": "INTEGER", "width": "INTEGER", "height": "INTEGER",
                   "caption": "TEXT", "sort_order": "INTEGER",
                   "created_at": "TIMESTAMP"},
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
    # F15: Bestands-Medienverweise gehören dem Besitzer ihres Events.
    "media_refs.user_id": (
        "UPDATE media_refs SET user_id = ("
        "SELECT e.user_id FROM events e WHERE e.id = media_refs.event_id)"
    ),
}


# F18: Spalten, die nachträglich NULL erlauben müssen. Bis 0.33 hing jedes Bild
# zwingend an einem Ereignis; seit 0.34 kann es auch nur an einem Tag hängen.
#
# Das ist die erste Migration hier, die eine Spalte ÄNDERT statt eine
# hinzuzufügen — und die beiden Datenbanken gehen dabei getrennte Wege:
# PostgreSQL kann `DROP NOT NULL`, SQLite kann es nicht und verlangt den
# Neubau der Tabelle. Deshalb steht das nicht in `_MISSING_COLUMNS`.
_DROP_NOT_NULL: dict[str, tuple[str, ...]] = {"media_refs": ("event_id",)}


def _copy_expr(column) -> str:
    """Der SELECT-Ausdruck für eine Spalte beim Tabellen-Neubau.

    Nullbare Spalten werden unverändert übernommen. Für NOT-NULL-Spalten tritt
    ein typgerechter Ersatzwert an die Stelle eines vorgefundenen NULL — das
    entspricht dem, was das ORM beim Schreiben ohnehin eingesetzt hätte, und
    ist die einzige Stelle, an der der Umzug an Altdaten scheitern könnte.
    """
    name = f'"{column.name}"'
    if column.nullable:
        return name
    kind = column.type.__class__.__name__.lower()
    if "int" in kind:
        fallback = "0"
    elif "date" in kind or "time" in kind:
        fallback = "CURRENT_TIMESTAMP"
    else:
        fallback = "''"
    return f"COALESCE({name}, {fallback})"


def _relax_not_null(engine: Engine, insp) -> list[str]:
    """Macht die Spalten aus `_DROP_NOT_NULL` nullable — idempotent.

    SQLite kennt kein `ALTER COLUMN`. Der offizielle Weg ist der Tabellen-
    Neubau; er läuft in EINER Transaktion, damit ein Abbruch mittendrin nicht
    eine halbe Tabelle hinterlässt. Die neue Tabelle entsteht aus dem Modell
    (`create_all`), nicht aus handgeschriebenem DDL — sonst hätte das Schema
    zwei Quellen, die auseinanderlaufen können.
    """
    from app.models import Base

    applied: list[str] = []
    tables = set(insp.get_table_names())
    for table, columns in _DROP_NOT_NULL.items():
        if table not in tables:
            continue
        nullable = {c["name"]: c["nullable"] for c in insp.get_columns(table)}
        todo = [c for c in columns if nullable.get(c) is False]
        if not todo:
            continue
        if engine.dialect.name == "sqlite":
            model = Base.metadata.tables[table]
            keep = [c["name"] for c in insp.get_columns(table)
                    if c["name"] in model.columns]
            cols = ", ".join(f'"{c}"' for c in keep)
            # Beim Kopieren muss jede NOT-NULL-Spalte einen Wert bekommen.
            # Bestandszeilen können dort NULL stehen haben: Spalten wie
            # `sort_order` kamen per ADD COLUMN in die alte Tabelle, und das
            # füllt nichts nach — der Wert entstand bisher erst beim Schreiben
            # über das ORM. Die neue Tabelle verbietet NULL, der Umzug bräche
            # also genau bei den ältesten Zeilen ab.
            src = ", ".join(_copy_expr(model.columns[c]) for c in keep)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table}" RENAME TO "{table}__old"'))
                model.create(conn)
                conn.execute(text(
                    f'INSERT INTO "{table}" ({cols}) SELECT {src} FROM "{table}__old"'))
                conn.execute(text(f'DROP TABLE "{table}__old"'))
        else:
            with engine.begin() as conn:
                for col in todo:
                    conn.execute(text(
                        f'ALTER TABLE "{table}" ALTER COLUMN "{col}" DROP NOT NULL'))
        applied += [f"{table}.{c} (nullable)" for c in todo]
    return applied


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
    # F18: erst die Spalten, dann die Lockerung — der Neubau kopiert sonst ein
    # Schema, dem gerade hinzugefügte Spalten noch fehlen.
    applied += _relax_not_null(engine, inspect(engine))
    if "metrics" in existing_tables:
        ensure_weather_unique_index(engine)
    if "locations" in existing_tables:
        cleanup_searched_address_labels(engine)
    ensure_indexes(engine, existing_tables)
    return applied


# Fremdschlüssel-Indizes, die in frühen Versionen fehlten. Ohne sie lädt das
# Zeitstrahl-Eager-Loading (metrics/entities/media je Ereignis) mit vollen
# Tabellen-Scans — auf einem Raspberry Pi mit zehntausenden Ereignissen die
# eigentliche Bremse beim ersten Laden. `create_all` legt sie nur bei NEUEN
# Datenbanken an; hier kommen sie in bestehende nachträglich hinein.
_INDEXES: dict[str, list[tuple[str, str]]] = {
    "metrics": [("ix_metrics_event_id", "event_id")],
    "event_entity_links": [("ix_eel_event_id", "event_id"),
                           ("ix_eel_entity_id", "entity_id")],
    "media_refs": [("ix_media_event_id", "event_id"),
                   ("ix_media_user_id", "user_id")],
    "events": [("ix_events_date_start", "date_start")],
}


def ensure_indexes(engine: Engine, existing_tables: set[str]) -> None:
    for table, indexes in _INDEXES.items():
        if table not in existing_tables:
            continue
        with engine.begin() as conn:
            for name, column in indexes:
                conn.execute(text(
                    f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ("{column}")'))


def cleanup_searched_address_labels(engine: Engine) -> None:
    """A19: Das Alt-Label „Gesuchte Adresse — " aus bereits aufgelösten Orten
    und Besuchs-Titeln entfernen. Idempotent (WHERE greift nach dem REPLACE
    nicht mehr); nackte „Gesuchte Adresse"-Orte bleiben und laufen über
    „Ortsnamen auflösen" in reine Adressen."""
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE locations SET name = REPLACE(name, 'Gesuchte Adresse — ', '') "
            "WHERE name LIKE 'Gesuchte Adresse — %'"))
        conn.execute(text(
            "UPDATE events SET title = REPLACE(title, 'Besuch: Gesuchte Adresse — ', 'Besuch: ') "
            "WHERE title LIKE 'Besuch: Gesuchte Adresse — %'"))


def ensure_weather_unique_index(engine: Engine) -> None:
    """DB-seitiger Dubletten-Schutz (A11): pro Event höchstens EINE
    Wetter-Metrik je Kennzahl. Räumt vorhandene Dubletten auf (älteste Zeile
    gewinnt) und legt dann einen partiellen Unique-Index an — damit können
    auch zwei parallele Anreicherungs-Läufe keine Doppel-Zeilen erzeugen.
    Syntax ist in SQLite und PostgreSQL identisch."""
    with engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM metrics WHERE source = 'weather' AND id NOT IN ("
            "SELECT MIN(id) FROM metrics WHERE source = 'weather' "
            "GROUP BY event_id, \"key\")"
        ))
        conn.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS ux_metrics_weather '
            'ON metrics (event_id, "key") WHERE source = \'weather\''
        ))


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
