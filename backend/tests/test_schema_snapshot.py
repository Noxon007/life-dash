"""Anmerkung 229 — die betriebene Datenbank kommt bei jedem Schema mit.

Die betriebene Datenbank wird migriert (Anmerkung 228); während der
Testphase darf ein teurer Umbau stattdessen ein ANGESAGTER Neuaufbau mit
Export-Rückspiel sein (Anmerkung 231). Beides setzt voraus, dass man merkt,
wann ein Schema die Datenbank nicht von selbst erreicht. **Jeder andere
Test beginnt mit einem FRISCHEN Schema** (`create_all`) — eine Spalte, die in
`models.py` zu einer bestehenden Tabelle kommt und in
`migrate._MISSING_COLUMNS` fehlt, ist dort vorhanden und in jedem Test grün.
Fehlen tut sie nur in einer Datenbank, die älter ist als sie: in genau der
einen, auf die es ankommt. Gemeldet hätte sich das beim ersten Zugriff auf dem
Server.

Dasselbe gilt stiller für **native Enum-Typen**: `Enum(Source)` ist auf
PostgreSQL ein eigener Typ mit fester Werteliste. Ein neuer Wert in der
Python-Aufzählung erreicht eine bestehende Datenbank nie — `create_all` fasst
vorhandene Typen nicht an, und `ALTER TYPE … ADD VALUE` steht nirgends. Auf
SQLite ist ein Enum ein `VARCHAR` ohne Prüfung; dort ist davon gar nichts zu
sehen.

**Die Historie war sauber** (geprüft über alle Stände von `models.py`): alle 21
nachträglich hinzugekommenen Spalten stehen in `_MISSING_COLUMNS`, die
Aufzählungen sind seit v0.1 unverändert. Dieser Test schützt die Zukunft.

`schema_snapshot.json` beschreibt, welches Schema die betriebene Datenbank
**mindestens** hat. Der Test baut daraus eine Datenbank, lässt `ensure_schema`
darüberlaufen und verlangt, dass danach jede Spalte, jede Nullbarkeit und —
auf PostgreSQL — jeder Enum-Wert aus `models.py` da ist.

**Wann der Schnappschuss neu geschrieben wird:** erst, wenn die betriebene
Datenbank nachweislich auf dem neuen Stand ist (also nach dem Einspielen).
Vorher neu geschrieben, prüft er die Migration gegen sich selbst. Ein
veralteter Schnappschuss ist dagegen harmlos — er verlangt nur, von weiter
hinten zu migrieren.

    <python> tests/test_schema_snapshot.py --write     (aus backend/)
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import Enum, create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import migrate  # noqa: E402
from app.models import Base  # noqa: E402

SNAPSHOT = Path(__file__).with_name("schema_snapshot.json")
_PG_SCHEMA = "schema_snapshot_test"


def describe(metadata) -> dict:
    """Das Schema als Daten: Spalten mit Typ je Dialekt, Nullbarkeit, Schlüssel,
    dazu die Werte jeder Aufzählung."""
    from sqlalchemy.dialects import postgresql, sqlite

    out: dict = {"tables": {}, "enums": {}}
    for table in metadata.sorted_tables:
        cols = {}
        for c in table.columns:
            cols[c.name] = {
                "sqlite": c.type.compile(dialect=sqlite.dialect()),
                "postgresql": c.type.compile(dialect=postgresql.dialect()),
                "nullable": bool(c.nullable),
                "pk": bool(c.primary_key),
            }
            if isinstance(c.type, Enum):
                out["enums"][c.type.name] = list(c.type.enums)
        out["tables"][table.name] = cols
    return out


def build(engine, snap: dict) -> None:
    """Eine Datenbank im Zustand des Schnappschusses — nur Tabellen, Spalten und
    Typen, bewusst ohne Indizes und Fremdschlüssel: gefragt ist, ob die
    Migration die SPALTEN nachzieht."""
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            for name, values in snap["enums"].items():
                vals = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
                conn.execute(text(f'CREATE TYPE "{name}" AS ENUM ({vals})'))
        for table, cols in snap["tables"].items():
            parts = [f'"{c}" {d[dialect]}{"" if d["nullable"] else " NOT NULL"}'
                     for c, d in cols.items()]
            pk = [c for c, d in cols.items() if d["pk"]]
            if pk:
                parts.append("PRIMARY KEY (" + ", ".join(f'"{c}"' for c in pk) + ")")
            conn.execute(text(f'CREATE TABLE "{table}" ({", ".join(parts)})'))


def gaps(engine) -> list[str]:
    """Was `models.py` verlangt und die Datenbank nicht hat."""
    insp = inspect(engine)
    have_tables = set(insp.get_table_names())
    out: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in have_tables:
            out.append(f"Tabelle {table.name} fehlt")
            continue
        have = {c["name"]: c for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have:
                out.append(f"{table.name}.{col.name} fehlt — Eintrag in "
                           f"migrate._MISSING_COLUMNS?")
            # Nur die eine Richtung ist ein Defekt: verlangt das Modell NULL
            # und die Datenbank verbietet es, scheitert jedes Einfügen ohne
            # Wert. Umgekehrt schreibt das ORM ohnehin einen.
            elif col.nullable and not have[col.name]["nullable"]:
                out.append(f"{table.name}.{col.name} ist in der Datenbank NOT NULL, "
                           f"im Modell nullbar — Eintrag in migrate._DROP_NOT_NULL?")
    if engine.dialect.name == "postgresql":
        rows = engine.connect().execute(text(
            "SELECT t.typname, e.enumlabel FROM pg_type t "
            "JOIN pg_enum e ON e.enumtypid = t.oid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = current_schema()")).all()
        labels: dict[str, set[str]] = {}
        for name, label in rows:
            labels.setdefault(name, set()).add(label)
        for name, values in describe(Base.metadata)["enums"].items():
            for v in values:
                if v not in labels.get(name, set()):
                    out.append(f"Enum {name} kennt '{v}' nicht — native Aufzählung "
                               f"auf PostgreSQL, braucht ALTER TYPE … ADD VALUE")
    return out


@pytest.fixture()
def blank(tmp_path):
    """Eine LEERE Datenbank desselben Dialekts, den die Suite gerade fährt.

    Auf PostgreSQL ein eigenes Schema: die Suite teilt sich eine Datenbank, und
    deren `public` ist schon mit dem frischen Schema belegt — genau dem, das
    hier nicht gemeint ist."""
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        engine = create_engine(f"sqlite:///{tmp_path / 'snapshot.db'}")
        yield engine
        engine.dispose()
        return
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{_PG_SCHEMA}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{_PG_SCHEMA}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={_PG_SCHEMA}"})
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{_PG_SCHEMA}" CASCADE'))
    admin.dispose()


def _snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_the_snapshot_migrates_to_the_model(blank):
    """Die Zusage selbst: aus dem Stand der betriebenen Datenbank wird mit
    `ensure_schema` der Stand von `models.py`."""
    build(blank, _snapshot())
    migrate.ensure_schema(blank)
    assert gaps(blank) == []


def test_no_column_changed_its_type_under_the_snapshot():
    """Einen Typwechsel kann `migrate.py` gar nicht ausdrücken — es kennt nur
    ADD COLUMN, das Lockern von NOT NULL und das Entfernen einer Tabelle. Ein
    `String(64)` → `String(128)` wäre auf einer frischen Datenbank richtig und
    auf der betriebenen die alte Grenze (PostgreSQL: „value too long").
    Wer das hier rot sieht, braucht einen handgeschriebenen Schritt — und
    schreibt den Schnappschuss erst neu, wenn der auf dem Server gelaufen ist."""
    snap = _snapshot()["tables"]
    now = describe(Base.metadata)["tables"]
    changed = [
        f"{t}.{c}: {snap[t][c][d]} → {now[t][c][d]} ({d})"
        for t in snap if t in now
        for c in snap[t] if c in now[t]
        for d in ("sqlite", "postgresql")
        if snap[t][c][d] != now[t][c][d]
    ]
    assert changed == []


# --- Die Probe auf den Wächter --------------------------------------------
#
# Mit einem Schnappschuss, der dem Modell gleicht, wäre der erste Test auch
# dann grün, wenn `gaps` gar nichts prüfte. Deshalb drei Stände, die der
# betriebenen Datenbank etwas NEHMEN.

def _without(column_table: str, column: str) -> dict:
    snap = copy.deepcopy(_snapshot())
    del snap["tables"][column_table][column]
    return snap


def test_a_column_the_database_lacks_is_added(blank):
    """Der Weg, den eine echte neue Spalte nimmt — auf BEIDEN Dialekten, denn
    der SQL-Typ in `_MISSING_COLUMNS` ist handgeschrieben."""
    assert "sessions_valid_from" in migrate._MISSING_COLUMNS["users"]
    build(blank, _without("users", "sessions_valid_from"))
    migrate.ensure_schema(blank)
    assert gaps(blank) == []


def test_a_column_without_a_migration_is_reported(blank, monkeypatch):
    """Der Defekt, den dieser Test finden soll: die Spalte ist im Modell, aber
    niemand hat sie in `_MISSING_COLUMNS` eingetragen."""
    cols = dict(migrate._MISSING_COLUMNS)
    cols["users"] = {k: v for k, v in cols["users"].items() if k != "sessions_valid_from"}
    monkeypatch.setattr(migrate, "_MISSING_COLUMNS", cols)
    build(blank, _without("users", "sessions_valid_from"))
    migrate.ensure_schema(blank)
    assert any("users.sessions_valid_from fehlt" in g for g in gaps(blank))


def test_an_enum_value_the_database_lacks_is_reported(blank):
    if blank.dialect.name != "postgresql":
        pytest.skip("native Aufzählungen gibt es nur auf PostgreSQL — "
                    "dort läuft die Probe (tools/pg-test.ps1, CI)")
    snap = copy.deepcopy(_snapshot())
    snap["enums"]["source"] = [v for v in snap["enums"]["source"] if v != "api"]
    build(blank, snap)
    migrate.ensure_schema(blank)
    assert any("Enum source kennt 'api' nicht" in g for g in gaps(blank))


if __name__ == "__main__":
    if "--write" not in sys.argv:
        sys.exit(__doc__)
    SNAPSHOT.write_text(json.dumps(describe(Base.metadata), indent=1, ensure_ascii=False)
                        + "\n", encoding="utf-8")
    print(f"geschrieben: {SNAPSHOT}")
