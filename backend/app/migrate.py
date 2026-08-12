"""Leichtgewichtige Schema-Migration (MVP, ohne Alembic).

Ergänzt fehlende Spalten in bestehenden Datenbanken per ALTER TABLE
(SQLite und Postgres können beide ADD COLUMN). Später ersetzt Alembic
diesen Mechanismus.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger("lifedash.migrate")

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
    # Anmerkung 148: `name_manual` schützt einen von Hand gesetzten Ortsnamen
    # vor dem nächsten Auflöse-Lauf. Bestandszeilen bekommen NULL, und NULL
    # zählt wie „nicht von Hand" — richtig, denn bis dahin konnte niemand
    # einen Ortsnamen von Hand setzen.
    "locations": {"user_id": "VARCHAR(36)", "country": "VARCHAR(64)",
                  "city": "VARCHAR(128)", "address": "JSON",
                  "name_manual": "BOOLEAN"},
    "events": {"user_id": "VARCHAR(36)", "embedding": "JSON", "note": "TEXT",
               "external_id": "VARCHAR(64)",
               "confirmed_at": "TIMESTAMP", "confirmed_by": "VARCHAR(16)",
               "parent_event_id": "VARCHAR(36)"},
    "entities": {"user_id": "VARCHAR(36)"},
    "jobs": {"params": "JSON"},
    # A35: Passwort-Hash für lokale Konten (NULL bei OIDC/dev)
    # Anmerkung 209: `sessions_valid_from` = der Schnitt, ab dem eine Sitzung
    # noch gilt. NULL heißt „nie widerrufen"; Bestandszeilen bekommen genau
    # das, und richtiger geht es nicht — vor dieser Spalte konnte niemand
    # widerrufen.
    "users": {"password_hash": "VARCHAR(255)", "sessions_valid_from": "TIMESTAMP"},
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

# Anmerkung 139: Tabellen, die es NICHT MEHR GIBT. Erste Migration, die etwas
# WEGNIMMT — deshalb steht hier ausdrücklich, warum das erlaubt ist.
#
# `photo_points` war Schicht 4: eine Ableitung, die vollständig auch in Immich
# steht (Anmerkung 57 — verwerfen und neu berechnen ist bei Ableitungen
# jederzeit erlaubt). Was in ihr stand, entsteht seit Anmerkung 139 als
# Ereignis; die Zeilen sind damit nicht verloren, sondern der Lauf legt sie neu
# an — an einem Ort, an dem sie zählen, gefiltert und exportiert werden.
#
# **Eine Tabelle mit Lebensdatenbank stünde hier nie.** Der Unterschied ist
# nicht der Aufwand, sondern die Frage, ob jemand die Zeile wiederherstellen
# kann, wenn das hier ein Fehler war. Bei einer Ableitung kann er das immer.
_DROPPED_TABLES: tuple[str, ...] = ("photo_points",)


def _drop_obsolete(engine: Engine, insp) -> list[str]:
    """Entfernt die Tabellen aus `_DROPPED_TABLES` — idempotent.

    Ohne diesen Schritt bliebe eine verwaiste Tabelle für immer in der
    betriebenen Datenbank stehen: `create_all` legt nur an, was fehlt, und
    löscht nie. Sie fiele bei jedem Backup, jedem `TRUNCATE`-Durchlauf und
    jedem `\\dt` auf und niemand wüsste mehr, wozu sie gehörte.
    """
    applied: list[str] = []
    tables = set(insp.get_table_names())
    for table in _DROPPED_TABLES:
        if table not in tables:
            continue
        with engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
        applied.append(f"{table} (entfernt)")
    return applied


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


def _drop_dangling_refs(conn, model) -> list[str]:
    """Verweise ins Leere auf NULL setzen — beim Tabellen-Neubau, und nur da.

    **Anmerkung 223.** Der Neubau kopiert die Zeilen in eine Tabelle, deren
    Schema STRENGER ist als das alte: `media_refs.user_id` hat seit dieser
    Runde einen Fremdschlüssel, vorher war es ein `VARCHAR(36)`, das zufällig
    wie eine Kennung aussah. Eine Altdatenbank, in der dort etwas steht, das
    kein Konto ist, hätte den Umbau damit zum Abbruch gebracht — und aus einer
    alten Unsauberkeit eine Instanz gemacht, die nicht mehr startet.

    **Ein Zeiger auf ein Konto, das es nicht gibt, ist keine Angabe, sondern
    ein Schaden.** NULL sagt genau dasselbe, nur ehrlich: „gehört niemandem".
    Verloren geht nichts — die Zeile war über diesen Verweis ohnehin für
    niemanden erreichbar.

    Nur für NULLABLE Spalten. Ist die Spalte Pflicht, bleibt der Abbruch
    richtig: dann wäre die Zeile ohne ihr Ziel gar keine Zeile, und das
    stillschweigend zu entscheiden steht einer Migration nicht zu.
    """
    notes: list[str] = []
    for col in model.columns:
        for fk in col.foreign_keys:
            if not col.nullable:
                continue
            target = fk.column.table.name
            n = conn.execute(text(
                f'UPDATE "{model.name}" SET "{col.name}" = NULL '
                f'WHERE "{col.name}" IS NOT NULL AND "{col.name}" NOT IN '
                f'(SELECT "{fk.column.name}" FROM "{target}")')).rowcount or 0
            if n:
                log.warning(
                    "%s.%s: %d Verweis(e) zeigten auf ein nicht vorhandenes %s "
                    "und stehen jetzt auf NULL", model.name, col.name, n, target)
                notes.append(f"{model.name}.{col.name} ({n} Waisen gelöst)")
    return notes


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
            # **Anmerkung 223: Fremdschlüssel für den Umbau AUS.** Seit sie
            # erzwungen werden, ist der Tabellen-Neubau der eine Ort, an dem
            # das schadet: `ALTER TABLE … RENAME` schreibt bei eingeschalteten
            # Fremdschlüsseln die Verweise ANDERER Tabellen auf den neuen Namen
            # um — hier also auf `media_refs__old`, das gleich danach fällt.
            # Genau dafür nennt die SQLite-Doku diesen Ablauf: Pragma aus,
            # umbauen, Pragma an, `foreign_key_check`.
            #
            # **Das Pragma geht an die DBAPI-Verbindung, nicht über
            # `exec_driver_sql`.** SQLite ignoriert `PRAGMA foreign_keys` in
            # einer offenen Transaktion, und SQLAlchemy 2.0 beginnt eine, sobald
            # irgendetwas über die `Connection` läuft (Autobegin). Der Aufruf
            # wäre also folgenlos gewesen — und zwar lautlos, was hier besonders
            # teuer ist: der Umbau hätte die Verweise anderer Tabellen auf
            # `…__old` umgeschrieben und die Tabelle danach gelöscht.
            #
            # Der Umbau selbst bleibt EINE Transaktion (ein Abbruch mittendrin
            # darf keine halbe Tabelle hinterlassen), und danach fragt
            # `foreign_key_check`, ob wirklich nichts ins Leere zeigt.
            with engine.connect() as conn:
                raw = conn.connection
                raw.execute("PRAGMA foreign_keys=OFF")
                try:
                    # **Vorher zählen, nachher vergleichen.** Die Frage ist
                    # „hat DIESER Umbau etwas zerrissen?" und nicht „ist in
                    # dieser Altdatenbank alles heil?". Eine Migration, die
                    # wegen einer Waise abbricht, die vorher schon da war,
                    # macht aus einer alten Unsauberkeit eine Instanz, die
                    # nicht mehr startet — der teurere Fehler.
                    with conn.begin():
                        conn.execute(text(
                            f'ALTER TABLE "{table}" RENAME TO "{table}__old"'))
                        model.create(conn)
                        conn.execute(text(
                            f'INSERT INTO "{table}" ({cols}) '
                            f'SELECT {src} FROM "{table}__old"'))
                        conn.execute(text(f'DROP TABLE "{table}__old"'))
                        applied += _drop_dangling_refs(conn, model)
                    broken = list(raw.execute("PRAGMA foreign_key_check"))
                    if broken:
                        raise RuntimeError(
                            f"Nach dem Umbau von {table} zeigen Verweise ins "
                            f"Leere: {broken[:5]}")
                finally:
                    raw.execute("PRAGMA foreign_keys=ON")
        else:
            with engine.begin() as conn:
                for col in todo:
                    conn.execute(text(
                        f'ALTER TABLE "{table}" ALTER COLUMN "{col}" DROP NOT NULL'))
        applied += [f"{table}.{c} (nullable)" for c in todo]
    return applied


def ensure_schema(engine: Engine) -> list[str]:
    """Bringt das Schema auf den Stand des Modells. Gibt die Änderungen zurück.

    **Anmerkung 219 — `create_all` gehört hierher und nicht daneben.** Es stand
    in `main.lifespan`, und zwar NACH diesem Aufruf. Die Folge war eine
    Reihenfolge, die auf einer bestehenden Datenbank stimmte und auf einer
    frischen nicht: `ensure_schema` erhob seine Tabellenliste, bevor es die
    Tabellen gab, und übersprang deshalb alles, was eine bestehende Tabelle
    voraussetzt — allen voran `ux_metrics_weather`, den Dublettenschutz aus
    A11. Der erschien erst beim ZWEITEN Start.

    Gesehen hat das niemand, weil der erste Start der einzige ist, bei dem es
    darauf ankommt: `SEED_DEMO` schreibt dann Wetter, und `enrich_weather`
    verlässt sich ausdrücklich auf den Index („der Unique-Index weist Dubletten
    aus parallelen Läufen ab"). Ein Schutz, der ab dem zweiten Start greift,
    ist genau die Sorte Stille, die dieses Projekt teuer bezahlt.

    Tabellen anzulegen ist dabei ungefährlich für Bestandsdaten: `create_all`
    legt nur an, was FEHLT, und fasst eine vorhandene Tabelle nie an — die
    ALTER-Schritte darunter bleiben also für sie zuständig.
    """
    from app.models import Base

    Base.metadata.create_all(bind=engine)
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
    applied += _drop_obsolete(engine, inspect(engine))
    if "metrics" in existing_tables:
        ensure_weather_unique_index(engine)
    # **Anmerkung 223: die Alt-Aufräumung läuft nur noch, wenn es etwas gibt.**
    # Beide Schritte darunter waren einmalige Nacharbeiten und liefen seitdem
    # bei JEDEM Start über die vollen Tabellen — zwei `UPDATE … LIKE` über
    # `locations` und `events`. Auf einem Raspberry Pi mit gewachsenem Bestand
    # ist das Startzeit für eine Arbeit, die vor Monaten erledigt war.
    #
    # Ein `SELECT EXISTS` statt eines `UPDATE` ist derselbe Scan — ABER er
    # bricht beim ersten Treffer ab, und wenn es keinen gibt, läuft er über den
    # Index bzw. einmal durch und schreibt nichts. Der Unterschied ist nicht
    # die Suche, sondern die Schreiblast und das WAL-Wachstum bei jedem Start.
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
    # F20: der Tages-Wetterspeicher wird IMMER über (Konto, Tag) gelesen —
    # `weather_day` vereinigt ihn mit den Ereignis-Metriken und gruppiert nach
    # Tag. Ohne Index ist das bei 14 600 Tagen ein voller Scan je Statistik.
    "day_metrics": [("ix_day_metrics_user_id", "user_id"),
                    ("ix_day_metrics_day", "day")],
    "baseline_locations": [("ix_baseline_user_id", "user_id")],
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


def cleanup_searched_address_labels(engine: Engine) -> int:
    """A19: Das Alt-Label „Gesuchte Adresse — " aus bereits aufgelösten Orten
    und Besuchs-Titeln entfernen. Idempotent (WHERE greift nach dem REPLACE
    nicht mehr); nackte „Gesuchte Adresse"-Orte bleiben und laufen über
    „Ortsnamen auflösen" in reine Adressen.

    **Anmerkung 223: erst fragen, dann schreiben.** Beide `UPDATE` liefen bei
    jedem Start über die vollen Tabellen. Sie fanden seit Monaten nichts und
    schrieben trotzdem eine Transaktion je Start ins WAL. Ein `EXISTS` davor
    kostet denselben Scan einmal, bricht aber beim ersten Treffer ab — und im
    Normalfall (nichts zu tun) bleibt es beim Lesen.

    Gibt zurück, wie viele Zeilen umbenannt wurden — für das Startprotokoll:
    eine Nacharbeit, die niemand meldet, ist eine, von der niemand weiß.
    """
    jobs = (
        ("locations", "name",
         "UPDATE locations SET name = REPLACE(name, 'Gesuchte Adresse — ', '') "
         "WHERE name LIKE 'Gesuchte Adresse — %'",
         "SELECT 1 FROM locations WHERE name LIKE 'Gesuchte Adresse — %' LIMIT 1"),
        ("events", "title",
         "UPDATE events SET title = REPLACE(title, 'Besuch: Gesuchte Adresse — ', 'Besuch: ') "
         "WHERE title LIKE 'Besuch: Gesuchte Adresse — %'",
         "SELECT 1 FROM events WHERE title LIKE 'Besuch: Gesuchte Adresse — %' LIMIT 1"),
    )
    changed = 0
    with engine.begin() as conn:
        for _table, _col, update, probe in jobs:
            if conn.execute(text(probe)).first() is None:
                continue
            changed += conn.execute(text(update)).rowcount or 0
    return changed


def ensure_weather_unique_index(engine: Engine) -> None:
    """DB-seitiger Dubletten-Schutz (A11): pro Event höchstens EINE
    Wetter-Metrik je Kennzahl. Räumt vorhandene Dubletten auf und legt dann
    einen partiellen Unique-Index an — damit können auch zwei parallele
    Anreicherungs-Läufe keine Doppel-Zeilen erzeugen. Syntax ist in SQLite und
    PostgreSQL identisch.

    **Welche der Dubletten gewinnt, ist willkürlich — aber fest.** Hier stand
    bis zur Anmerkung 199 „älteste Zeile gewinnt", und das war schlicht falsch:
    `id` ist eine UUID, `MIN(id)` also die lexikografisch kleinste und nicht
    die zuerst geschriebene (dieselbe Falle, die Anmerkung 106 beim
    Verdichtungs-Vertreter `min(id)` schon einmal gefunden hat). Folgenlos ist
    es trotzdem, und deshalb bleibt es: Dubletten entstehen nur, wenn zwei
    Läufe DENSELBEN Tag am DEMSELBEN Ort fragen, und beide bekommen dieselbe
    Antwort. Wer die Werte wirklich austauschen will, hat seit Anmerkung 186
    den ausdrücklichen Weg über `discard_weather`.

    **Anmerkung 223: das Aufräumen läuft nur, solange es den Index nicht gibt.**
    Der `DELETE` mit seiner `GROUP BY`-Unterabfrage ging bei JEDEM Start über
    die ganze Metrik-Tabelle — am Demo-Bestand 143.000 Zeilen, im Betrieb
    mehr. Er kann seit dem ersten Lauf nichts mehr finden: **der Index IST die
    Zusage**, Dubletten entstehen danach nicht wieder. Ihn trotzdem jedes Mal
    zu suchen, heißt eine einmalige Nacharbeit für eine dauerhafte zu halten.
    """
    insp = inspect(engine)
    have = {ix["name"] for ix in insp.get_indexes("metrics")}
    with engine.begin() as conn:
        if "ux_metrics_weather" not in have:
            conn.execute(text(
                "DELETE FROM metrics WHERE source = 'weather' AND id NOT IN ("
                "SELECT MIN(id) FROM metrics WHERE source = 'weather' "
                "GROUP BY event_id, \"key\")"
            ))
        conn.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS ux_metrics_weather '
            'ON metrics (event_id, "key") WHERE source = \'weather\''
        ))


def _adoptable_tables() -> list[str]:
    """Welche Tabellen Altdaten ohne Besitzer haben können — aus EINER Liste.

    **Anmerkung 223.** Hier stand die Aufzählung `fragments, locations, events,
    entities`, und `tracks` und `media_refs` fehlten. Beide haben eine nullbare
    `user_id`, beide werden überall über sie gefiltert — eine Zeile ohne
    Besitzer ist damit für immer unsichtbar: nicht im Zeitstrahl, nicht in der
    Statistik, **und nicht im Export**. Sie wäre auch beim Löschen des Kontos
    stehen geblieben.

    **Gefragt wird `wipe.WIPE_ORDER` und nicht das Schema.** Der erste Versuch
    nahm jede Tabelle mit nullbarer `user_id` — und griff damit `jobs` mit, das
    Lauf-Protokoll. Ein systemweiter Lauf (Neuberechnung, Embeddings) hat
    ausdrücklich KEINEN Besitzer; ihn dem ersten Konto zuzuschlagen wäre eine
    erfundene Aussage über die Vergangenheit. `wipe.py` beantwortet dieselbe
    Frage — „was gehört einem Konto?" — seit Anmerkung 219 an einer Stelle, und
    `WIPE_KEEPS` nennt `jobs` mit genau dieser Begründung.

    Dass diese Liste vollständig ist, prüft `test_wipe_covers_every_user_table`
    gegen `Base.metadata`. Eine neue Tabelle mit Besitzer ist damit von selbst
    dabei — und eine ohne bleibt es auch.
    """
    from app.wipe import WIPE_ORDER

    return [model.__table__.name for model, _key, _scope in WIPE_ORDER
            if "user_id" in model.__table__.columns
            and model.__table__.columns["user_id"].nullable]


def adopt_orphan_rows(engine: Engine, user_id: str) -> int:
    """Hängt Alt-Daten ohne user_id an den angegebenen Nutzer.

    Wird beim Anlegen des ERSTEN Nutzers aufgerufen, damit Daten aus der
    Single-User-Zeit nicht verwaist bleiben.
    """
    total = 0
    existing = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        for table in _adoptable_tables():
            if table not in existing:
                continue
            result = conn.execute(
                text(f'UPDATE "{table}" SET user_id = :uid WHERE user_id IS NULL'),
                {"uid": user_id},
            )
            n = result.rowcount or 0
            if n:
                log.info("Altdaten übernommen: %s — %d Zeile(n)", table, n)
            total += n
    return total
