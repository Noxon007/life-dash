"""Admin-Endpoints: Datenbank-Rohansicht (pgAdmin-artig), Zeilen bearbeiten
und Stufe-2/3-Neuberechnung."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import inspect, text

from app.auth import require_admin
from app.database import SessionLocal, engine
from app.services.enrichment import enrich_weather
from app.services.ingestion import reprocess_pending, reset_reprocess

log = logging.getLogger("lifedash.admin")

# Alle Admin-Endpoints erfordern die Admin-Rolle (Rohdaten-Ansicht ist
# nutzerübergreifend — bewusst nur für den Administrator).
router = APIRouter(
    prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)]
)


def _require_table(name: str) -> list[str]:
    """Prüft, dass die Tabelle existiert, und liefert ihre Spaltennamen."""
    insp = inspect(engine)
    if name not in insp.get_table_names():
        raise HTTPException(status_code=404, detail="Tabelle nicht gefunden")
    return [c["name"] for c in insp.get_columns(name)]


@router.get("/tables")
def list_tables() -> list[dict]:
    """Alle Tabellen mit Zeilenanzahl."""
    insp = inspect(engine)
    out: list[dict] = []
    with engine.connect() as conn:
        for name in insp.get_table_names():
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
            out.append({"name": name, "rows": count})
    return out


@router.get("/tables/{name}")
def read_table(
    name: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Rohe Zeilen einer Tabelle (read-only). Tabellenname wird gegen die
    real existierenden Tabellen geprüft -> keine SQL-Injection möglich."""
    columns = _require_table(name)
    with engine.connect() as conn:
        total = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
        rows = (
            conn.execute(
                text(f'SELECT * FROM "{name}" LIMIT :limit OFFSET :offset'),
                {"limit": limit, "offset": offset},
            )
            .mappings()
            .all()
        )
    # Werte JSON-serialisierbar machen (datetime, dict etc. -> str)
    def _clean(v):
        if v is None or isinstance(v, (int, float, bool, str)):
            return v
        return str(v)

    return {
        "table": name,
        "columns": columns,
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": [{k: _clean(v) for k, v in dict(r).items()} for r in rows],
    }


@router.patch("/tables/{name}/{row_id}")
def update_row(
    name: str,
    row_id: str,
    values: dict[str, Any] = Body(..., description="Spalte -> neuer Wert"),
) -> dict:
    """Ändert Spalten einer Zeile (per id). Rohe DB-Bearbeitung im Admin-Panel."""
    columns = _require_table(name)
    if "id" not in columns:
        raise HTTPException(status_code=400, detail="Tabelle hat keine id-Spalte")

    updates = {k: v for k, v in values.items() if k in columns and k != "id"}
    if not updates:
        raise HTTPException(status_code=400, detail="Keine gültigen Spalten zum Ändern")

    set_clause = ", ".join(f'"{col}" = :{col}' for col in updates)
    params = dict(updates)
    params["_row_id"] = row_id
    with engine.begin() as conn:
        result = conn.execute(
            text(f'UPDATE "{name}" SET {set_clause} WHERE "id" = :_row_id'), params
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Zeile nicht gefunden")
        log.info("Rohansicht: UPDATE %s id=%s Spalten=%s", name, row_id, sorted(updates))
        row = conn.execute(
            text(f'SELECT * FROM "{name}" WHERE "id" = :_row_id'), {"_row_id": row_id}
        ).mappings().first()
    return {"updated": True, "row": {k: (v if v is None or isinstance(v, (int, float, bool, str)) else str(v)) for k, v in dict(row).items()}}


@router.delete("/tables/{name}/{row_id}", status_code=204, response_model=None)
def delete_row(name: str, row_id: str) -> None:
    """Löscht eine Zeile (per id) aus der Rohansicht."""
    columns = _require_table(name)
    if "id" not in columns:
        raise HTTPException(status_code=400, detail="Tabelle hat keine id-Spalte")
    with engine.begin() as conn:
        result = conn.execute(
            text(f'DELETE FROM "{name}" WHERE "id" = :_row_id'), {"_row_id": row_id}
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Zeile nicht gefunden")
    log.info("Rohansicht: DELETE %s id=%s", name, row_id)


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
    """Wetter-Batch für Events ohne Wetter (Open-Meteo, 1 Anfrage je Event)."""
    db = SessionLocal()
    try:
        enriched, remaining = enrich_weather(db, limit=limit)
    finally:
        db.close()
    log.info("Wetter-Batch: %d Events angereichert, %d offen", enriched, remaining)
    return {"enriched_events": enriched, "remaining": remaining}


# Hinweis: Wetter ist FAKTEN-Anreicherung (Schicht 3, KONZEPT Kap. 3.1) —
# historisches Wetter ändert sich nicht. Es gibt daher bewusst keinen
# „Wetter neu berechnen"-Endpoint mehr, nur das Ergänzen fehlender Werte.


@router.post("/wipe-data")
def wipe_data() -> dict:
    """Löscht ALLE Lebensdaten (Stufe 1–3) unwiderruflich. Nutzer-Konten bleiben.

    Die Bestätigungs-Nachfrage passiert im Frontend; dieser Endpoint ist
    nur für Admins erreichbar (Router-Dependency)."""
    deleted: dict[str, int] = {}
    # Reihenfolge beachtet die Fremdschlüssel (Kinder zuerst)
    order = ["metrics", "media_refs", "event_entity_links", "tracks", "events",
             "entities", "locations", "fragments"]
    with engine.begin() as conn:
        for table in order:
            result = conn.execute(text(f'DELETE FROM "{table}"'))
            deleted[table] = result.rowcount or 0
    log.warning("ALLE Lebensdaten gelöscht: %d Zeilen (%s)",
                sum(deleted.values()),
                ", ".join(f"{k}={v}" for k, v in deleted.items() if v))
    return {"deleted": deleted, "total": sum(deleted.values())}


@router.post("/reset-embeddings")
def reset_embeddings() -> dict:
    """Setzt alle Event-Embeddings auf NULL (Vorbereitung der Neuberechnung,
    z. B. nach einem Modellwechsel)."""
    from app.models import Event

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
    from app.models import Event

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
