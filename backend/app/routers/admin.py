"""Admin-Endpoints: Datenbank-Rohansicht (pgAdmin-artig, mit Leitplanken —
A4), Zeilen bearbeiten und Stufe-2/3-Neuberechnung."""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from dateutil import parser as dateparser
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import DateTime as SADateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float as SAFloat
from sqlalchemy import Integer as SAInteger
from sqlalchemy import Table, func, select, text
from sqlalchemy.orm import Session

from app import logbuffer
from app.auth import require_admin
from app.database import Base, SessionLocal, engine, get_db
# Anmerkung 219: Die halbe Modell-Liste stand hier nur, weil `delete_row` seine
# abhängigen Tabellen von Hand aufzählte. Seit sie aus `Base.metadata` kommen,
# braucht diese Datei die Klassen nicht mehr — und der Import, der sie noch
# nannte, hätte beim Lesen weiter behauptet, hier gäbe es eine solche Liste.
from app.models import Event, Fragment, Source, User, UserRole
from app.services.enrichment import auto_enrich_events, enrich_weather
from app.schemas import AdminCreateUser
from app.services.ingestion import reprocess_pending, reset_reprocess
from app.services import media as media_svc
from app.wipe import WIPE_ORDER, is_delete_word, wipe_user_rows

log = logging.getLogger("lifedash.admin")

# Alle Admin-Endpoints erfordern die Admin-Rolle (Rohdaten-Ansicht ist
# nutzerübergreifend — bewusst nur für den Administrator).
router = APIRouter(
    prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)]
)


def _require_table(name: str) -> Table:
    """Liefert die Modell-Tabelle — nur bekannte Tabellen, keine SQL-Injection."""
    table = Base.metadata.tables.get(name)
    if table is None:
        raise HTTPException(status_code=404, detail="Tabelle nicht gefunden")
    return table


def _clean(v: Any) -> Any:
    """Wert JSON-serialisierbar machen (datetime, dict etc. -> str)."""
    if v is None or isinstance(v, (int, float, bool, str)):
        return v
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


# --------------------------------------------------------------------------- #
#  Anmerkung 208: Geheimnisse in der Rohansicht
# --------------------------------------------------------------------------- #
# Der vierte offene Punkt aus Anmerkung 200: die Rohansicht gab
# `users.password_hash` und den Immich-Schlüssel heraus — denselben Wert, den
# `_settings_view` mit einer ausdrücklichen Begründung NICHT zurückgibt („ein
# Schlüssel, der bei jedem Laden der Einstellungsseite durchs Netz geht, ist
# einer, den man auch weglassen könnte"). Eine Regel, die an einer Stelle gilt
# und an ihrer Zwillingsstelle nicht — das Muster, das die Anmerkungen 199, 200
# und 201 alle drei gefunden haben.
#
# EINE Liste, von beiden Richtungen gelesen: das LESEN schwärzt, das SCHREIBEN
# lehnt ab. Nur zu schwärzen wäre die halbe Antwort — wer einen Passwort-Hash
# nicht sehen, ihn aber SETZEN darf, übernimmt jedes Konto der Instanz mit
# einem Hash, den er selbst kennt.
#
# Die Liste nennt zwei Sorten, weil es zwei gibt: ganze Spalten, und Schlüssel
# INNERHALB einer JSON-Spalte. Der Immich-Schlüssel ist die zweite Sorte — er
# steht in `users.settings`, und eine Prüfung auf Spaltennamen hätte ihn nie
# gefunden.
SECRET_COLUMNS: dict[str, set[str]] = {
    "users": {"password_hash"},
}
# (Tabelle, Spalte) -> Pfade in das JSON, deren Wert nicht herausgeht.
SECRET_JSON_PATHS: dict[tuple[str, str], list[tuple[str, ...]]] = {
    ("users", "settings"): [("immich", "api_key")],
}
REDACTED = "***"


def _redact_json(value: Any, paths: list[tuple[str, ...]]) -> Any:
    """Kopiert das JSON und ersetzt die genannten Pfade — ohne das Original
    anzufassen: es hängt an einem lebenden ORM-Objekt."""
    if not isinstance(value, dict):
        return value
    out = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    for path in paths:
        node = out
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict) and node.get(path[-1]) not in (None, ""):
            node[path[-1]] = REDACTED
    return out


def redact_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Die Leseseite der Liste."""
    secret_cols = SECRET_COLUMNS.get(table, set())
    out: dict[str, Any] = {}
    for col, value in row.items():
        if col in secret_cols:
            out[col] = REDACTED if value not in (None, "") else value
        elif (table, col) in SECRET_JSON_PATHS:
            out[col] = _clean(_redact_json(value, SECRET_JSON_PATHS[(table, col)]))
        else:
            out[col] = _clean(value)
    return out


def reject_secret_writes(table: str, columns: set[str]) -> None:
    """Die Schreibseite derselben Liste.

    JSON-Spalten sind hier ganz gesperrt statt pfadgenau: wer `settings`
    schreibt, schickt das ganze Dokument, und ein geschwärztes `***` würde als
    neuer Schlüssel zurückgeschrieben. Der richtige Weg steht in der Meldung.
    """
    blocked = sorted((columns & SECRET_COLUMNS.get(table, set()))
                     | {c for c in columns if (table, c) in SECRET_JSON_PATHS})
    if blocked:
        raise HTTPException(
            400,
            f"{', '.join(blocked)}: Geheimnisse werden über die Rohansicht weder "
            "gelesen noch geschrieben. Passwörter ändert der Nutzer selbst "
            "(Konto → Passwort), den Immich-Schlüssel die Einstellungsseite.")


@router.get("/tables")
def list_tables(db: Session = Depends(get_db)) -> list[dict]:
    """Alle Tabellen mit Zeilenanzahl."""
    return [
        {"name": t.name, "rows": db.execute(select(func.count()).select_from(t)).scalar()}
        for t in Base.metadata.sorted_tables
    ]


@router.get("/tables/{name}")
def read_table(
    name: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Rohe Zeilen einer Tabelle (read-only)."""
    table = _require_table(name)
    total = db.execute(select(func.count()).select_from(table)).scalar()
    rows = db.execute(select(table).limit(limit).offset(offset)).mappings().all()
    return {
        "table": name,
        "columns": [c.name for c in table.columns],
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": [redact_row(name, dict(r)) for r in rows],
    }


def _coerce_value(table: str, col, raw: Any) -> Any:
    """Validiert/normalisiert einen Roh-Wert aus der UI für die Spalte (A4).

    Enums nur mit gültigen Werten, JSON muss parsen, Zeiten müssen Zeiten
    sein, Zahlen Zahlen — sonst 400 statt stiller Datenkorruption."""
    if raw == "" or raw is None:
        if not col.nullable:
            raise HTTPException(400, f"{table}.{col.name} darf nicht leer sein")
        return None
    if isinstance(col.type, SAEnum):
        allowed = list(col.type.enums)
        if str(raw) not in allowed:
            raise HTTPException(400, f"{table}.{col.name}: ungültiger Wert {raw!r} "
                                     f"— erlaubt: {', '.join(allowed)}")
        return str(raw)
    if isinstance(col.type, SADateTime):
        try:
            return dateparser.isoparse(str(raw))
        except (ValueError, OverflowError):
            raise HTTPException(400, f"{table}.{col.name}: keine gültige Zeitangabe "
                                     f"({raw!r}, erwartet ISO, z. B. 2026-07-12T14:30:00)")
    if isinstance(col.type, SAFloat):
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{table}.{col.name}: keine Zahl ({raw!r})")
    if isinstance(col.type, SAInteger):
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{table}.{col.name}: keine ganze Zahl ({raw!r})")
    if col.type.__class__.__name__.upper().startswith("JSON"):
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{table}.{col.name}: kein gültiges JSON ({raw!r})")
    return raw


def _event_side_effects(db: Session, event_id: str, changed: set[str]) -> list[str]:
    """Folge-Neuberechnungen nach Roh-Änderungen an einem Event (A4):
    Titel/Beschreibung -> Embedding neu; Zeit/Ort -> Wetter folgt den neuen
    Fakten (derselbe Pfad wie bei der Nutzer-Korrektur, P2.4)."""
    notes: list[str] = []
    event = db.get(Event, event_id)
    if not event:
        return notes
    if changed & {"title", "description"}:
        event.embedding = None
        notes.append("Embedding zurückgesetzt (nächster Embedding-Lauf berechnet neu)")
    if changed & {"date_start", "date_end", "location_id"}:
        for m in [m for m in event.metrics if m.source == Source.weather]:
            event.metrics.remove(m)  # delete-orphan räumt die Zeile ab
        db.flush()
        enriched = auto_enrich_events(db, [event])
        notes.append("Wetter neu geholt" if enriched
                      else "Wetter entfernt (später über „Wetter ergänzen“ nachtragen)")
    db.commit()
    return notes


@router.patch("/tables/{name}/{row_id}")
def update_row(
    name: str,
    row_id: str,
    values: dict[str, Any] = Body(..., description="Spalte -> neuer Wert"),
    db: Session = Depends(get_db),
) -> dict:
    """Ändert Spalten einer Zeile (per id) — mit Typ-/Enum-Validierung und
    Folge-Neuberechnungen statt stiller Invarianten-Verletzung (A4)."""
    table = _require_table(name)
    if "id" not in table.columns:
        raise HTTPException(status_code=400, detail="Tabelle hat keine id-Spalte")

    reject_secret_writes(name, {c for c in values if c in table.columns})
    updates = {
        col: _coerce_value(name, table.columns[col], v)
        for col, v in values.items() if col in table.columns and col != "id"
    }
    if not updates:
        raise HTTPException(status_code=400, detail="Keine gültigen Spalten zum Ändern")

    result = db.execute(
        table.update().where(table.c.id == row_id).values(**updates)
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="Zeile nicht gefunden")
    db.commit()
    log.info("Rohansicht: UPDATE %s id=%s Spalten=%s", name, row_id, sorted(updates))

    side_effects: list[str] = []
    if name == "events":
        side_effects = _event_side_effects(db, row_id, set(updates))

    row = db.execute(select(table).where(table.c.id == row_id)).mappings().first()
    return {"updated": True,
            "side_effects": side_effects,
            "row": redact_row(name, dict(row))}


# Lösch-Leitplanken (A4): Diese Tabellen sind über die Rohansicht gesperrt —
# mit Begründung und Verweis auf den richtigen Weg.
_DELETE_BLOCKED = {
    "fragments": "Fragmente sind das Beweisarchiv (Eingang, Kap. 3.1) und werden "
                 "nie über die Rohansicht gelöscht.",
    "users": "Nutzer bitte über die Nutzerverwaltung löschen — die entfernt auch "
             "alle zugehörigen Daten und schützt den letzten Admin.",
}


# --------------------------------------------------------------------------- #
#  Anmerkung 219 — was an einer gelöschten Zeile hängt
# --------------------------------------------------------------------------- #
# Hier stand eine `if name == …`-Kette, und sie war die DRITTE Antwort im
# Projekt auf „was hängt an einem Ereignis?" — neben `wipe.WIPE_ORDER` und
# `photo_points.delete_events`. Die beiden anderen waren vollständig, diese
# nicht: `events.parent_event_id`, `tracks.event_id` und
# `baseline_locations.location_id` fehlten. Gemessen am laufenden Stand hieß das
# `{'deleted': True, 'side_effects': []}` — und danach zeigte ein Tages-Kind auf
# ein Ereignis, das es nicht mehr gab. Auf SQLite lautlos, auf PostgreSQL ein
# Abbruch. Ein Protokoll, das einen Erfolg meldet, den es nicht gab, ist teurer
# als keins (`wipe.py`, Kopf).
#
# **WELCHE Spalten es gibt, fragt jetzt das Schema** (`_dependents`) und nicht
# mehr diese Datei. Eine neue Tabelle mit einem neuen Verweis ist damit von
# selbst mitgeprüft — dieselbe Bauart wie `test_wipe_covers_every_user_table`:
# eine Spalte, nach der niemand fragt, kann kein Test vermissen.
#
# **WAS mit ihnen geschieht, kann das Schema nicht wissen** und steht deshalb
# hier. Drei Antworten, und die dritte ist eine Weigerung:
#
#   "cascade"  — die Zeile kann ohne ihr Ziel nicht existieren und geht mit
#                (ein Messwert ohne Ereignis ist keine gerettete Hälfte)
#   "detach"   — sie steht für sich; der Verweis wird auf NULL gesetzt. So
#                entscheidet es der Lösch-Dialog für Tages-Kinder
#                (`with_children=False`) und `photo_points` für Wege: „der Weg
#                ist eine eigene Aufzeichnung und keine Ableitung dieses
#                Ereignisses"
#   "refuse"   — sie ist Lebensdatenbank und verschwindet nicht als
#                NEBENWIRKUNG einer anderen Löschung
#
# Die Nullbarkeit allein hätte als Regel nicht gereicht: `media_refs.event_id`
# ist nullable und wird trotzdem mitgelöscht, weil `delete_row` vorher die
# DATEIEN entfernt — ein abgehängter Verweis zeigte danach auf nichts.
ON_DELETE: dict[tuple[str, str], str] = {
    # → events
    ("metrics", "event_id"): "cascade",
    ("event_entity_links", "event_id"): "cascade",
    ("media_refs", "event_id"): "cascade",
    ("events", "parent_event_id"): "detach",
    ("tracks", "event_id"): "detach",
    # → entities
    ("event_entity_links", "entity_id"): "cascade",
    # → locations
    ("events", "location_id"): "detach",
    ("baseline_locations", "location_id"): "refuse",
}

# Menschenlesbarer Name je Tabelle — für den Satz in `side_effects`. Die SPALTE
# steht mit dabei, weil `events` auf zwei Weisen auf sich selbst und auf
# `locations` zeigt: „2 Ereignisse abgehängt" ließe offen, welcher Verweis
# gemeint ist, und dies ist die ROHANSICHT — hier liest jemand Spaltennamen.
_TABLE_LABELS = {
    "metrics": "Metriken", "media_refs": "Medien-Verweise",
    "event_entity_links": "Objekt-Verknüpfungen", "events": "Ereignisse",
    "tracks": "Wege", "baseline_locations": "Wohnorte",
}

# Wohin ein „refuse" verweist: WO die Zeile richtig bearbeitet wird.
# Eine Weigerung ohne Weg ist eine Sackgasse.
_REFUSE_HINT = {
    "baseline_locations": "Dieser Ort ist als Wohnort eingetragen (F20). Ein "
                          "Wohnort ist Lebensdatenbank und verschwindet nicht "
                          "als Nebenwirkung — erst den Zeitraum unter "
                          "„Wohnorte“ ändern oder entfernen, dann den Ort.",
}


def _dependents(table_name: str) -> list[tuple[str, str]]:
    """(Tabelle, Spalte) jedes Fremdschlüssels, der auf DIESE Tabelle zeigt.

    Aus `Base.metadata` gelesen, nicht aufgezählt — dieselbe Technik wie
    `data._user_scoped_refs`. Selbstverweise (`events.parent_event_id`) sind
    eingeschlossen und waren genau die Hälfte, die von Hand gefehlt hat.
    """
    out: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            for fk in col.foreign_keys:
                if fk.column.table.name == table_name:
                    out.append((table.name, col.name))
    return sorted(out)


def all_dependent_columns() -> list[tuple[str, str]]:
    """Jeder Verweis auf eine Tabelle, die über die Rohansicht LÖSCHBAR ist.

    Die Grundlage des Wächters (`test_anm219_review.py`). Gesperrte Tabellen
    bleiben draußen: auf sie zeigende Spalten kommen hier nie zur Sprache, und
    für sie eine Antwort zu verlangen wäre eine Pflege ohne Anlass.
    """
    out: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        if table.name in _DELETE_BLOCKED:
            continue
        out += _dependents(table.name)
    return sorted(set(out))


def _clear_dependents(db: Session, table_name: str, row_id: str) -> list[str]:
    """Räumt alles ab, was auf diese Zeile zeigt — und sagt, was es getan hat."""
    notes: list[str] = []
    for dep_table, column in _dependents(table_name):
        action = ON_DELETE.get((dep_table, column))
        if action is None:
            # Kann nur passieren, wenn jemand eine Tabelle anlegt und den
            # Wächter überspringt. Lieber ein klarer Abbruch als eine Waise.
            raise HTTPException(
                500, f"{dep_table}.{column} zeigt auf {table_name}, aber es ist "
                     "nicht hinterlegt, was damit geschehen soll (ON_DELETE).")
        dep = Base.metadata.tables[dep_table]
        label = _TABLE_LABELS.get(dep_table, dep_table)
        if action == "refuse":
            n = db.execute(select(func.count()).select_from(dep)
                           .where(dep.c[column] == row_id)).scalar() or 0
            if n:
                raise HTTPException(409, _REFUSE_HINT.get(
                    dep_table, f"{n} Zeile(n) in {dep_table} zeigen hierher."))
            continue
        if action == "cascade":
            n = db.execute(dep.delete().where(dep.c[column] == row_id)).rowcount or 0
            if n:
                notes.append(f"{n} {label} mitgelöscht ({column})")
        else:                       # detach
            n = db.execute(dep.update().where(dep.c[column] == row_id)
                           .values(**{column: None})).rowcount or 0
            if n:
                notes.append(f"{n} {label} abgehängt ({column})")
    return notes


@router.delete("/tables/{name}/{row_id}")
def delete_row(name: str, row_id: str, db: Session = Depends(get_db)) -> dict:
    """Löscht eine Zeile (per id) aus der Rohansicht — inklusive Aufräumen
    abhängiger Zeilen, damit keine verwaisten Verweise zurückbleiben (A4)."""
    table = _require_table(name)
    if name in _DELETE_BLOCKED:
        raise HTTPException(status_code=400, detail=_DELETE_BLOCKED[name])
    if "id" not in table.columns:
        raise HTTPException(status_code=400, detail="Tabelle hat keine id-Spalte")

    side_effects: list[str] = []
    if name == "events":
        # F15: erst die DATEIEN, dann die Zeilen — nach dem Löschen der Zeilen
        # ist nicht mehr feststellbar, welche gemeint waren (Anmerkung 59).
        n_files = media_svc.purge_for_events(db, [row_id])
        if n_files:
            side_effects.append(f"{n_files} Bilddateien gelöscht")
    side_effects += _clear_dependents(db, name, row_id)

    result = db.execute(table.delete().where(table.c.id == row_id))
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="Zeile nicht gefunden")
    db.commit()
    log.info("Rohansicht: DELETE %s id=%s (%s)", name, row_id,
             "; ".join(side_effects) or "keine Folgeänderungen")
    return {"deleted": True, "side_effects": side_effects}


# --------------------------------------------------------------------------- #
# Neuberechnung / Enrichment — alle Lang-Läufer arbeiten in Batches:
# das Frontend ruft nach, zeigt einen Anfragen-Ticker und kann zwischen den
# Batches stoppen (Fortschritt bleibt, da pro Batch/Fragment committet wird).
# --------------------------------------------------------------------------- #
@router.post("/recompute-events/reset")
def recompute_events_reset() -> dict:
    """Markiert Fragmente für die Stufe-2-Neuberechnung (bestätigte bleiben)."""
    db = SessionLocal()
    try:
        total = reset_reprocess(db)
    finally:
        db.close()
    log.info("Neuberechnung vorbereitet: %d Fragmente markiert", total)
    return {"total": total}


@router.post("/recompute-events")
def recompute_events(limit: int = Query(5, ge=1, le=50)) -> dict:
    """Verarbeitet einen Batch markierter Fragmente (1 KI-Anfrage je Fragment)."""
    db = SessionLocal()
    try:
        processed, remaining, aborted = reprocess_pending(db, limit=limit)
    finally:
        db.close()
    log.info("Neuberechnungs-Batch: %d verarbeitet, %d offen%s",
             processed, remaining, " (abgebrochen: Quota)" if aborted else "")
    return {"processed": processed, "remaining": remaining, "aborted": aborted}


@router.post("/enrich-weather")
def enrich_weather_endpoint(limit: int = Query(25, ge=1, le=200)) -> dict:
    """Wetter-Batch für Events ohne Wetter (Open-Meteo, 1 Anfrage je Event).

    Bewusst über den GANZEN Bestand: das ist der Admin-Weg (und der der Tests).
    Der Knopf in der Oberfläche startet den Job `weather`, und der bleibt beim
    eigenen Konto (`enrich_weather(user_id=…)`, Anmerkung 115).
    """
    db = SessionLocal()
    try:
        enriched, remaining = enrich_weather(db, limit=limit)
    finally:
        db.close()
    log.info("Wetter-Batch: %d Events angereichert, %d offen", enriched, remaining)
    return {"enriched_events": enriched, "remaining": remaining}


# Hinweis: Wetter ist FAKTEN-Anreicherung (Schicht 3, ARCHITECTURE Kap. 3.1) —
# historisches Wetter ändert sich nicht. Es gibt daher bewusst keinen
# „Wetter neu berechnen"-Endpoint mehr, nur das Ergänzen fehlender Werte.


@router.post("/wipe-data")
def wipe_data(confirm: Annotated[str, Body(embed=True)] = "") -> dict:
    """Löscht ALLE Lebensdaten (Stufe 1–3) unwiderruflich. Nutzer-Konten bleiben.

    Erreichbar nur für Admins (Router-Dependency) — und seit 0.40 auch nur mit
    getipptem Losungswort. Bis dahin stand die Nachfrage allein im Frontend:
    ein einzelnes `POST` ohne Rumpf leerte die Instanz. Für den unwiderruflichsten
    Endpunkt des Systems war das die falsche Stelle für die einzige Bremse.
    Welche Wörter gelten, steht in `app.wipe` — dieselbe Regel wie beim
    Konto-Weg, der sie vorher anders schrieb.
    """
    if not is_delete_word(confirm):
        raise HTTPException(
            400, "Zum Bestätigen bitte LÖSCHEN eingeben — das lässt sich nicht rückgängig machen.")
    deleted: dict[str, int] = {}
    # F15: Erst merken, WELCHE Dateien es gibt — nach dem Löschen der Zeilen
    # ist das nicht mehr feststellbar. Gelöscht werden sie aber erst danach:
    # scheitert das Aufräumen der Datenbank, wären sonst die Bilder weg und
    # die Daten noch da. Verwaiste Dateien sind die harmlose Richtung.
    db = SessionLocal()
    try:
        doomed = media_svc.list_uploads(db)
    finally:
        db.close()
    # Reihenfolge beachtet die Fremdschlüssel (Kinder zuerst) — sie steht in
    # `app.wipe`, weil der Konto-Weg dieselbe braucht und eine zweite Kopie
    # genau so auseinanderläuft, wie sie es getan hat: `baseline_locations`
    # fehlte in beiden, aufgefallen ist es erst auf PostgreSQL.
    order = [table for _model, table, _scope in WIPE_ORDER]
    # A34: je Tabelle eine Zeile ins Log. Ein Rundumschlag über eine große
    # Datenbank dauert; ohne Spur ist er von einem Hänger nicht zu unterscheiden.
    log.warning("Alle Daten löschen: beginne (%d Bilddateien vorgemerkt)", len(doomed))
    with engine.begin() as conn:
        for table in order:
            result = conn.execute(text(f'DELETE FROM "{table}"'))
            deleted[table] = result.rowcount or 0
            log.info("  %s: %d Zeilen gelöscht", table, deleted[table])
    files = media_svc.purge_files(doomed)
    log.warning("ALLE Lebensdaten gelöscht: %d Zeilen, %d Bilddateien (%s)",
                sum(deleted.values()), files,
                ", ".join(f"{k}={v}" for k, v in deleted.items() if v))
    return {"deleted": deleted, "total": sum(deleted.values()), "media_files": files}


@router.post("/reset-embeddings")
def reset_embeddings() -> dict:
    """Setzt alle Event-Embeddings auf NULL (Vorbereitung der Neuberechnung,
    z. B. nach einem Modellwechsel)."""
    db = SessionLocal()
    try:
        total = db.query(Event).update({Event.embedding: None},
                                       synchronize_session=False)
        db.commit()
    finally:
        db.close()
    log.info("Embeddings zurückgesetzt: %d Events", total)
    return {"total": total}


@router.post("/reindex-embeddings")
def reindex_embeddings(limit: int = Query(25, ge=1, le=200)) -> dict:
    """Embedding-Batch für Events ohne Embedding (1 KI-Anfrage je Event).

    Volle Neuberechnung: vorher /reset-embeddings. Liefert remaining, damit
    das Frontend nachrufen bzw. stoppen kann. `indexed_events` == 0 bei noch
    `remaining` > 0 heißt: Embedding-Modell nicht konfiguriert/erreichbar.
    """
    from app.ai import get_provider

    provider = get_provider()
    db = SessionLocal()
    try:
        batch = (db.query(Event)
                 .filter(Event.embedding.is_(None))
                 .order_by(Event.created_at)
                 .limit(limit).all())
        count = 0
        for event in batch:
            vec = provider.embed(f"{event.title}\n{event.description or ''}")
            if vec:
                event.embedding = vec
                count += 1
        db.commit()
        remaining = db.query(Event).filter(Event.embedding.is_(None)).count()
    finally:
        db.close()
    log.info("Embedding-Batch: %d indexiert, %d offen", count, remaining)
    return {"indexed_events": count, "remaining": remaining}


# --------------------------------------------------------------------------- #
# Log-Ansicht (A17) — letzte Log-Zeilen aus dem Ring-Puffer
# --------------------------------------------------------------------------- #
@router.get("/logs")
def read_logs(
    level: str = "INFO",
    limit: int = Query(300, ge=1, le=logbuffer.CAPACITY),
) -> list[dict]:
    """Letzte App-Log-Zeilen (seit Prozessstart). `level` filtert auf
    Mindest-Schwere. Nur Admin — Logs sind nutzerübergreifend.

    Die Obergrenze ist die Puffergröße selbst: mehr kann es nicht geben, und
    eine zweite Zahl daneben wäre bei der nächsten Änderung wieder falsch."""
    min_no = getattr(logging, level.upper(), logging.INFO)
    rows = [r for r in logbuffer.ring.buffer if r["levelno"] >= min_no]
    return rows[-limit:]


# --------------------------------------------------------------------------- #
# Nutzerverwaltung (A6) — Nutzerliste, Rollen ändern, Nutzer löschen
# --------------------------------------------------------------------------- #
@router.get("/users")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    """Alle Nutzer mit Rolle und Datenumfang (fürs Admin-Panel).
    Konten entstehen per OIDC-Login (JIT) oder — bei AUTH_MODE=local — durch
    Registrierung/Admin-Anlage (A35)."""
    return [
        {
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role.value,
            # A35: woher stammt das Konto? Für das Admin-Panel sichtbar.
            "auth": ("local" if u.oidc_subject.startswith("local:")
                     else "dev" if u.oidc_subject == "dev-user" else "oidc"),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "events": db.query(Event).filter(Event.user_id == u.id).count(),
            "fragments": db.query(Fragment).filter(Fragment.user_id == u.id).count(),
        }
        for u in db.query(User).order_by(User.created_at).all()
    ]


@router.post("/users")
def create_user(
    payload: AdminCreateUser,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """A35: ein Admin legt ein weiteres lokales Konto an.

    Nur bei AUTH_MODE=local — bei OIDC entstehen Konten beim ersten Login des
    jeweiligen Nutzers, ein Passwort gäbe es dort nicht.
    """
    from app import auth as auth_mod
    from app.config import settings as settings_mod

    if settings_mod.auth_mode != "local":
        raise HTTPException(
            400, "Konten von Hand anlegen geht nur bei AUTH_MODE=local; "
                 "bei OIDC entstehen sie automatisch beim ersten Login.")
    if "@" not in payload.email:
        raise HTTPException(400, "Bitte eine gültige E-Mail-Adresse angeben")
    if auth_mod.find_local_user(db, payload.email) is not None:
        raise HTTPException(409, "Ein Konto mit dieser E-Mail existiert bereits")
    from app.services.password import MIN_LENGTH
    if len(payload.password) < MIN_LENGTH:
        raise HTTPException(400, f"Das Passwort braucht mindestens {MIN_LENGTH} Zeichen")
    new = auth_mod.create_local_user(db, email=payload.email, password=payload.password,
                                     name=payload.display_name, role=payload.role)
    log.info("Nutzerverwaltung: Konto %s angelegt (%s) von %s",
             new.email, new.role.value, admin.email or admin.id)
    return {"id": new.id, "email": new.email, "role": new.role.value}


@router.patch("/users/{user_id}")
def update_user_role(
    user_id: str,
    role: UserRole = Body(..., embed=True),
    db: Session = Depends(get_db),
) -> dict:
    """Ändert die Rolle eines Nutzers. Der letzte Admin kann nicht
    herabgestuft werden — sonst sperrt sich das System selbst aus."""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Nutzer nicht gefunden")
    if (target.role == UserRole.admin and role != UserRole.admin
            and db.query(User).filter(User.role == UserRole.admin).count() <= 1):
        raise HTTPException(400, "Der letzte Admin kann nicht herabgestuft werden")
    target.role = role
    db.commit()
    log.info("Nutzerverwaltung: Rolle von %s -> %s",
             target.email or user_id, role.value)
    return {"id": target.id, "role": target.role.value}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Löscht einen Nutzer MITSAMT all seinen Lebensdaten (Stufe 1–3).
    Das eigene Konto ist gesperrt — so bleibt immer mindestens ein Admin."""
    if user_id == admin.id:
        raise HTTPException(400, "Das eigene Konto kann nicht gelöscht werden")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Nutzer nicht gefunden")

    # F15: Bilddateien vor den Datensätzen — sonst bleiben sie auf der Platte.
    # F18: über den NUTZER, nicht über seine Ereignisse — Bilder können an
    # einem Tag statt an einem Ereignis hängen und wären sonst übersehen worden.
    deleted: dict[str, int] = {"media_files": media_svc.purge_for_user(db, user_id)}
    # Reihenfolge und Tabellenliste stehen in `app.wipe` — hier stand bis 0.39
    # die dritte handgeschriebene Kopie derselben Regel, und sie hatte
    # dieselbe Lücke wie die beiden anderen (`baseline_locations`,
    # `day_metrics`). Hier wog sie am schwersten: die Zeilen zeigen auch auf
    # `users`, das gleich darauf gelöscht wird — auf PostgreSQL scheiterte
    # also nicht nur ein Teil, sondern der ganze Vorgang.
    deleted |= wipe_user_rows(db, user_id, log)
    db.delete(target)
    db.commit()
    log.warning("Nutzer gelöscht: %s (%d Datenzeilen: %s)",
                target.email or user_id, sum(deleted.values()),
                ", ".join(f"{k}={v}" for k, v in deleted.items() if v))
    return {"deleted": deleted, "total": sum(deleted.values())}
