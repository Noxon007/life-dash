"""F18 — die erste Migration, die eine Spalte ÄNDERT statt eine anzulegen.

`media_refs.event_id` war bis 0.33 NOT NULL. PostgreSQL kann das mit
`DROP NOT NULL` lockern, SQLite nicht — dort muss die Tabelle neu gebaut
werden, und dabei kann man Daten verlieren. Genau deshalb steht dieser Test
hier: er baut eine Datenbank im **alten** Zustand auf, lässt die Migration
darüber laufen und prüft, dass danach (a) NULL erlaubt ist und (b) jede Zeile
mit allen Feldern noch da ist.

Das ist die Sorte Zusage, die Paket R1(f) für alle Migrationen verlangt — und
die man nur einmal falsch machen muss, um fremde Daten zu beschädigen.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text

from app.migrate import ensure_schema

# Das Schema, wie 0.33 es angelegt hat — verkürzt auf das, was der Neubau
# anfassen muss. `event_id` ist hier NOT NULL, wie im Original.
#
# `events` trägt bewusst die Spalten, die frühere Migrationen erwarten
# (`updated_at`, `source`, `confirmed`) und die, deren Fehlen einen Backfill
# auslösen würde (`confirmed_at`, `confirmed_by`). Sonst prüfte dieser Test
# nebenbei die halbe Migrationsgeschichte mit und bräche an deren Stelle statt
# an seiner eigenen.
OLD_SCHEMA = """
CREATE TABLE events (
    id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36), title VARCHAR(255),
    source VARCHAR(32), confirmed VARCHAR(16),
    confirmed_at DATETIME, confirmed_by VARCHAR(16), updated_at DATETIME
);
CREATE TABLE media_refs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36),
    event_id VARCHAR(36) NOT NULL REFERENCES events(id),
    provider VARCHAR(32),
    external_id VARCHAR(255),
    captured_at DATETIME,
    mime VARCHAR(64),
    bytes INTEGER,
    width INTEGER,
    height INTEGER,
    caption TEXT,
    sort_order INTEGER,
    created_at DATETIME
);
"""


@pytest.fixture()
def old_db(tmp_path):
    """Eine Datei-Datenbank im Zustand von 0.33, mit einem Bild darin."""
    engine = create_engine(f"sqlite:///{tmp_path/'old.db'}")
    with engine.begin() as conn:
        for stmt in OLD_SCHEMA.strip().split(";"):
            if stmt.strip():
                conn.execute(text(stmt))
        conn.execute(text("INSERT INTO events (id, user_id, title) "
                          "VALUES ('e1', 'u1', 'Urlaub')"))
        conn.execute(text(
            "INSERT INTO media_refs (id, user_id, event_id, provider, external_id,"
            " captured_at, mime, bytes, width, height, caption, sort_order, created_at)"
            " VALUES ('m1', 'u1', 'e1', 'local', 'foto.jpg', '2026-07-05 08:14:00',"
            " 'image/jpeg', 4096, 800, 600, 'Am Strand', 2, '2026-07-05 09:00:00')"))
    return engine


def _nullable(engine, table, column) -> bool:
    return {c["name"]: c["nullable"] for c in inspect(engine).get_columns(table)}[column]


def test_event_id_starts_out_not_null(old_db):
    """Prüft die Ausgangslage — ohne sie prüfte der Test unten nichts."""
    assert _nullable(old_db, "media_refs", "event_id") is False


def test_migration_allows_photos_without_an_event(old_db):
    ensure_schema(old_db)
    assert _nullable(old_db, "media_refs", "event_id") is True
    with old_db.begin() as conn:
        conn.execute(text(
            "INSERT INTO media_refs (id, user_id, provider, external_id, captured_at,"
            " sort_order, created_at)"
            " VALUES ('m2', 'u1', 'local', 'tag.jpg', '2026-07-06 10:00:00',"
            " 0, '2026-07-06 10:00:00')"))
        assert conn.execute(text(
            "SELECT count(*) FROM media_refs WHERE event_id IS NULL")).scalar() == 1


def test_rows_with_null_in_a_now_required_column_survive(old_db):
    """Die Falle, die dieser Test gefunden hat: `sort_order` und `created_at`
    kamen in alten Datenbanken per ADD COLUMN dazu und stehen dort bei
    Bestandszeilen auf NULL — das Modell verbietet NULL inzwischen. Ohne
    Ersatzwert bräche der Umzug ausgerechnet bei den ÄLTESTEN Bildern ab,
    also bei denen, die am längsten unersetzlich sind."""
    with old_db.begin() as conn:
        conn.execute(text(
            "INSERT INTO media_refs (id, user_id, event_id, provider, external_id)"
            " VALUES ('alt', 'u1', 'e1', 'local', 'uralt.jpg')"))
        assert conn.execute(text(
            "SELECT sort_order IS NULL FROM media_refs WHERE id='alt'")).scalar() == 1

    ensure_schema(old_db)

    with old_db.begin() as conn:
        row = conn.execute(text(
            "SELECT external_id, sort_order FROM media_refs WHERE id='alt'")).one()
    assert row[0] == "uralt.jpg"
    assert row[1] == 0


def test_migration_keeps_every_field_of_existing_rows(old_db):
    """Der Neubau kopiert Zeilen um — hier zählt jedes einzelne Feld, nicht
    nur die Zeilenzahl. Eine vertauschte Spaltenreihenfolge fiele sonst erst
    auf, wenn jemand seine Bildunterschriften vermisst."""
    ensure_schema(old_db)
    with old_db.begin() as conn:
        row = conn.execute(text(
            "SELECT id, user_id, event_id, provider, external_id, captured_at,"
            " mime, bytes, width, height, caption, sort_order FROM media_refs"
        )).one()
    assert row == ("m1", "u1", "e1", "local", "foto.jpg", "2026-07-05 08:14:00",
                   "image/jpeg", 4096, 800, 600, "Am Strand", 2)


def test_migration_is_idempotent(old_db):
    """Zweiter Start derselben Version darf nichts mehr tun — sonst würde die
    Tabelle bei jedem Start neu gebaut."""
    first = ensure_schema(old_db)
    second = ensure_schema(old_db)
    assert any("media_refs.event_id" in a for a in first)
    assert not any("media_refs.event_id" in a for a in second)
    with old_db.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM media_refs")).scalar() == 1


def test_no_leftover_table_after_rebuild(old_db):
    ensure_schema(old_db)
    assert "media_refs__old" not in inspect(old_db).get_table_names()
