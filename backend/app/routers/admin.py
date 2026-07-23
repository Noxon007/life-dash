"""Admin-Endpoints: Datenbank-Rohansicht (pgAdmin-artig, mit Leitplanken —
A4), Zeilen bearbeiten und Stufe-2/3-Neuberechnung."""
from __future__ import annotations

import json
import logging
from typing import Any

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
from app.models import (
    Entity,
    Event,
    EventEntityLink,
    Fragment,
    Location,
    MediaRef,
    Metric,
    PhotoPoint,
    Source,
    Track,
    User,
    UserRole,
)
from app.services.enrichment import auto_enrich_events, enrich_weather
from app.schemas import AdminCreateUser
from app.services.ingestion import reprocess_pending, reset_reprocess
from app.services import media as media_svc

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
        "rows": [{k: _clean(v) for k, v in dict(r).items()} for r in rows],
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
            "row": {k: _clean(v) for k, v in dict(row).items()}}


# Lösch-Leitplanken (A4): Diese Tabellen sind über die Rohansicht gesperrt —
# mit Begründung und Verweis auf den richtigen Weg.
_DELETE_BLOCKED = {
    "fragments": "Fragmente sind das Beweisarchiv (Eingang, Kap. 3.1) und werden "
                 "nie über die Rohansicht gelöscht.",
    "users": "Nutzer bitte über die Nutzerverwaltung löschen — die entfernt auch "
             "alle zugehörigen Daten und schützt den letzten Admin.",
}


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
        n_files = media_svc.purge_for_events(db, [row_id])   # F15: erst die Dateien
        if n_files:
            side_effects.append(f"{n_files} Bilddateien gelöscht")
        for model, label in ((Metric, "Metriken"), (MediaRef, "Medien-Verweise"),
                             (EventEntityLink, "Objekt-Verknüpfungen")):
            n = (db.query(model).filter(model.event_id == row_id)
                 .delete(synchronize_session=False))
            if n:
                side_effects.append(f"{n} {label} mitgelöscht")
    elif name == "entities":
        n = (db.query(EventEntityLink).filter(EventEntityLink.entity_id == row_id)
             .delete(synchronize_session=False))
        if n:
            side_effects.append(f"{n} Event-Verknüpfungen mitgelöscht")
    elif name == "locations":
        n = (db.query(Event).filter(Event.location_id == row_id)
             .update({Event.location_id: None}, synchronize_session=False))
        if n:
            side_effects.append(f"{n} Events sind jetzt ohne Ort")

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


# Hinweis: Wetter ist FAKTEN-Anreicherung (Schicht 3, KONZEPT Kap. 3.1) —
# historisches Wetter ändert sich nicht. Es gibt daher bewusst keinen
# „Wetter neu berechnen"-Endpoint mehr, nur das Ergänzen fehlender Werte.


@router.post("/wipe-data")
def wipe_data() -> dict:
    """Löscht ALLE Lebensdaten (Stufe 1–3) unwiderruflich. Nutzer-Konten bleiben.

    Die Bestätigungs-Nachfrage passiert im Frontend; dieser Endpoint ist
    nur für Admins erreichbar (Router-Dependency)."""
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
    # Reihenfolge beachtet die Fremdschlüssel (Kinder zuerst)
    order = ["metrics", "media_refs", "event_entity_links", "tracks", "events",
             "entities", "locations", "fragments"]
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

    event_ids = select(Event.id).where(Event.user_id == user_id).scalar_subquery()
    deleted: dict[str, int] = {}
    # F15: Bilddateien vor den Datensätzen — sonst bleiben sie auf der Platte.
    # F18: über den NUTZER, nicht über seine Ereignisse — Bilder können an
    # einem Tag statt an einem Ereignis hängen und wären sonst übersehen worden.
    deleted["media_files"] = media_svc.purge_for_user(db, user_id)
    # Kinder zuerst (Fremdschlüssel): Metriken/Medien/Links hängen an Events
    deleted["metrics"] = (db.query(Metric)
                          .filter(Metric.event_id.in_(event_ids))
                          .delete(synchronize_session=False))
    # F18: ebenfalls über den Nutzer — ein Bild am Tag hat kein Ereignis, über
    # das es hier erwischt würde, und bliebe als Datensatz ohne Besitzer zurück.
    deleted["media_refs"] = (db.query(MediaRef)
                             .filter(MediaRef.user_id == user_id)
                             .delete(synchronize_session=False))
    # A45: Fotopunkte hängen an gar keinem Ereignis — sie sind über `user_id`
    # allein erreichbar. Dieselbe Falle wie bei F18 (Anmerkung 106), nur eine
    # Tabelle weiter: wer Medien über Ereignisse sucht, findet sie nicht.
    deleted["photo_points"] = (db.query(PhotoPoint)
                               .filter(PhotoPoint.user_id == user_id)
                               .delete(synchronize_session=False))
    deleted["event_entity_links"] = (db.query(EventEntityLink)
                                     .filter(EventEntityLink.event_id.in_(event_ids))
                                     .delete(synchronize_session=False))
    deleted["tracks"] = (db.query(Track).filter(Track.user_id == user_id)
                         .delete(synchronize_session=False))
    deleted["events"] = (db.query(Event).filter(Event.user_id == user_id)
                         .delete(synchronize_session=False))
    deleted["entities"] = (db.query(Entity).filter(Entity.user_id == user_id)
                           .delete(synchronize_session=False))
    deleted["locations"] = (db.query(Location).filter(Location.user_id == user_id)
                            .delete(synchronize_session=False))
    deleted["fragments"] = (db.query(Fragment).filter(Fragment.user_id == user_id)
                            .delete(synchronize_session=False))
    db.delete(target)
    db.commit()
    log.warning("Nutzer gelöscht: %s (%d Datenzeilen: %s)",
                target.email or user_id, sum(deleted.values()),
                ", ".join(f"{k}={v}" for k, v in deleted.items() if v))
    return {"deleted": deleted, "total": sum(deleted.values())}
