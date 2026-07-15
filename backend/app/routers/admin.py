"""Admin-Endpoints: Datenbank-Rohansicht (pgAdmin-artig), Zeilen bearbeiten
und Stufe-2/3-Neuberechnung."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import inspect, text

from app.auth import require_admin
from app.database import SessionLocal, engine
from app.services.enrichment import enrich_weather
from app.services.ingestion import reprocess_all

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


# --------------------------------------------------------------------------- #
# Neuberechnung / Enrichment
# --------------------------------------------------------------------------- #
@router.post("/recompute-events")
def recompute_events() -> dict:
    """Stufe 2 aus den Roh-Fragmenten neu berechnen (bestätigte bleiben)."""
    db = SessionLocal()
    try:
        count = reprocess_all(db)
    finally:
        db.close()
    return {"reprocessed_fragments": count}


@router.post("/enrich-weather")
def enrich_weather_endpoint(force: bool = Query(False, description="Alle neu berechnen")) -> dict:
    """Stufe-3-Wetter-Enrichment für verortete Events (Open-Meteo)."""
    db = SessionLocal()
    try:
        count = enrich_weather(db, force=force)
    finally:
        db.close()
    return {"enriched_events": count}


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
    return {"deleted": deleted, "total": sum(deleted.values())}


@router.post("/reindex-embeddings")
def reindex_embeddings(force: bool = Query(False, description="Alle neu berechnen")) -> dict:
    """Embeddings für Events (neu) berechnen — Stufe-3-Ableitung, gefahrlos.

    Nötig z. B. nach dem Aktivieren von OPENAI_EMBED_MODEL oder einem
    Modellwechsel: bestätigte Events werden vom Stufe-2-Reprocessing bewusst
    nicht angefasst und bekämen sonst nie ein Embedding.
    """
    from app.ai import get_provider
    from app.models import Event

    provider = get_provider()
    db = SessionLocal()
    try:
        count = 0
        for event in db.query(Event).all():
            # Python-seitig prüfen: fängt SQL NULL UND Alt-Zeilen mit JSON 'null'
            if event.embedding and not force:
                continue
            vec = provider.embed(f"{event.title}\n{event.description or ''}")
            if vec:
                event.embedding = vec
                count += 1
        db.commit()
    finally:
        db.close()
    return {"indexed_events": count}
