"""Job-Übersicht & Gleichzeitigkeit (A11).

Lang laufende Aktionen (Wetter, Neuberechnung, Embeddings, Ortsnamen,
Importe) laufen als Batch-Schleifen im Frontend. Dieser Router macht daraus
sichtbare, gegeneinander gesperrte Jobs:

- start:    legt einen Job an — läuft bereits einer desselben Typs
            (mit frischem Heartbeat), gibt es 409 statt eines Doppel-Laufs.
- progress: Heartbeat + Fortschritt nach jedem Batch.
- finish:   Abschluss (done | stopped | error) mit Ergebnistext.

Verwaiste Jobs (Browser zu, Netz weg) blockieren nicht ewig: ohne Heartbeat
für STALE_SECONDS gilt ein Job als abgebrochen und wird beim nächsten
Start/Listen als `stopped` aufgeräumt.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import SessionLocal, get_db
from app.models import Job, User, UserRole

log = logging.getLogger("lifedash.jobs")

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

# Ohne Heartbeat so lange gilt ein "running"-Job als verwaist. Batches dauern
# Sekunden; 3 Minuten sind großzügig (auch für träge KI-/Nominatim-Antworten).
STALE_SECONDS = 180

JOB_TYPES = {
    "recompute": "KI-Vorschläge neu berechnen",
    "weather": "Wetter ergänzen",
    "embeddings": "Embeddings berechnen",
    "resolve_names": "Ortsnamen auflösen/formatieren",
    "immich": "Fotos aus Immich verknüpfen",
    "timeline_import": "Google-Timeline-Import",
    "data_import": "Daten-Import (JSON)",
}
# A22: Diese Typen laufen SERVERSEITIG als Background-Thread weiter, auch wenn
# der Browser zu ist. Importe bleiben client-getrieben (die Datei liegt dort).
SERVER_JOB_TYPES = ("weather", "embeddings", "resolve_names", "recompute", "immich")
# In Tests abgeschaltet (in-memory-DB verträgt keine fremden Threads)
WORKERS_ENABLED = True


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    status: str
    done: int
    remaining: int | None = None
    unit: str | None = None
    result: str | None = None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    started_by: str | None = None  # Anzeigename des Starters


class JobStart(BaseModel):
    type: str = Field(..., min_length=1, max_length=32)
    unit: str | None = Field(None, max_length=32)
    params: dict | None = None  # z. B. {"scope": "nonlatin"}


class JobProgress(BaseModel):
    done: int = 0
    remaining: int | None = None


class JobFinish(BaseModel):
    status: str = Field(..., pattern="^(done|stopped|error)$")
    result: str | None = Field(None, max_length=255)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stale_cutoff() -> datetime:
    # Naive UTC — die DateTime-Spalten sind naiv gespeichert
    return _now().replace(tzinfo=None) - timedelta(seconds=STALE_SECONDS)


def _reap_stale(db: Session) -> None:
    """Verwaiste running-Jobs (kein Heartbeat) als gestoppt markieren."""
    stale = (db.query(Job)
             .filter(Job.status.in_(("running", "stopping")),
                     Job.updated_at < _stale_cutoff())
             .all())
    for job in stale:
        job.status = "stopped"
        job.finished_at = job.updated_at
        job.result = (job.result or "") or "abgebrochen (kein Heartbeat)"
    if stale:
        db.commit()
        log.info("Jobs: %d verwaiste Läufe als gestoppt markiert", len(stale))


def _to_read(db: Session, job: Job) -> JobRead:
    out = JobRead.model_validate(job)
    starter = db.get(User, job.user_id) if job.user_id else None
    out.started_by = (starter.display_name or starter.email) if starter else None
    return out


@router.get("", response_model=list[JobRead])
def list_jobs(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[JobRead]:
    """Laufende und letzte Jobs (alle Nutzer — der Lock ist global, also soll
    auch sichtbar sein, WER gerade etwas laufen hat)."""
    _reap_stale(db)
    rows = (db.query(Job).order_by(Job.started_at.desc())
            .limit(max(1, min(limit, 100))).all())
    return [_to_read(db, j) for j in rows]


@router.post("/start", response_model=JobRead)
def start_job(
    payload: JobStart,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRead:
    """Startet einen Job — 409, wenn derselbe Typ bereits läuft.
    Server-Job-Typen (A22) laufen als Background-Thread weiter, auch wenn
    die Seite geschlossen wird; Importe bleiben client-getrieben."""
    _reap_stale(db)
    running = (db.query(Job)
               .filter(Job.type == payload.type,
                       Job.status.in_(("running", "stopping")))
               .first())
    if running:
        starter = db.get(User, running.user_id) if running.user_id else None
        who = (starter.display_name or starter.email) if starter else "unbekannt"
        label = JOB_TYPES.get(payload.type, payload.type)
        # gespeichert ist naive UTC -> in Serverzeit (TZ, z. B. Europe/Berlin)
        local = running.started_at.replace(tzinfo=timezone.utc).astimezone()
        raise HTTPException(
            409, f"„{label}“ läuft bereits (gestartet von {who}, "
                 f"{local:%H:%M} Uhr) — bitte warten oder dort stoppen.")
    job = Job(user_id=user.id, type=payload.type, unit=payload.unit,
              params=payload.params)
    db.add(job)
    db.commit()
    log.info("Job gestartet: %s (%s) von %s", payload.type, job.id[:8],
             user.display_name or user.email)
    if payload.type in SERVER_JOB_TYPES and WORKERS_ENABLED:
        spawn_worker(job.id)
    return _to_read(db, job)


def _own_running_job(db: Session, job_id: str, user: User) -> Job:
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Job nicht gefunden")
    return job


@router.post("/{job_id}/progress", response_model=JobRead)
def job_progress(
    job_id: str,
    payload: JobProgress,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRead:
    """Fortschritt + Heartbeat nach einem Batch."""
    job = _own_running_job(db, job_id, user)
    job.done = payload.done
    job.remaining = payload.remaining
    job.updated_at = _now().replace(tzinfo=None)  # expliziter Heartbeat
    db.commit()
    return _to_read(db, job)


@router.post("/{job_id}/stop", response_model=JobRead)
def job_stop(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRead:
    """A22: Fordert den Stopp eines Server-Jobs an (Starter oder Admin).
    Der Worker beendet sich nach dem laufenden Batch."""
    job = db.get(Job, job_id)
    if not job or (job.user_id != user.id and user.role != UserRole.admin):
        raise HTTPException(404, "Job nicht gefunden")
    if job.status == "running":
        job.status = "stopping"
        db.commit()
        log.info("Job-Stopp angefordert: %s (%s)", job.type, job.id[:8])
    return _to_read(db, job)


@router.post("/{job_id}/finish", response_model=JobRead)
def job_finish(
    job_id: str,
    payload: JobFinish,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRead:
    """Schließt einen Job ab (done | stopped | error)."""
    job = _own_running_job(db, job_id, user)
    if job.status == "running":
        job.status = payload.status
        job.result = payload.result
        job.finished_at = _now().replace(tzinfo=None)
        db.commit()
        log.info("Job beendet: %s (%s) — %s, %d verarbeitet",
                 job.type, job.id[:8], payload.status, job.done)
    return _to_read(db, job)


# --------------------------------------------------------------------------- #
# A22 — Serverseitige Worker: laufen im Background-Thread mit eigener
# DB-Session; Stopp über status='stopping' (wird pro Batch geprüft).
# --------------------------------------------------------------------------- #
def _naive_now() -> datetime:
    return _now().replace(tzinfo=None)


def _tick(db: Session, job_id: str, done_add: int, remaining: int | None) -> bool:
    """Fortschritt + Heartbeat; liefert True, wenn weitergemacht werden soll."""
    db.expire_all()
    job = db.get(Job, job_id)
    job.done += done_add
    job.remaining = remaining
    job.updated_at = _naive_now()
    db.commit()
    return job.status == "running"


def _run_weather(db: Session, job: Job) -> tuple[str, str]:
    from app.services.enrichment import enrich_weather

    while True:
        enriched, remaining = enrich_weather(db, limit=25)
        cont = _tick(db, job.id, enriched, remaining)
        if remaining <= 0:
            return "done", f"{db.get(Job, job.id).done} Events mit Wetter angereichert"
        # 0.15.1: Ohne Fortschritt sauber stoppen statt Open-Meteo endlos
        # anzufragen (z. B. Dienst nicht erreichbar oder Datum ohne Archiv)
        if enriched == 0:
            return "stopped", f"{remaining} nicht anreicherbar (Open-Meteo/Datum prüfen)"
        if not cont:
            return "stopped", "gestoppt"
        if enriched == 0:
            return "stopped", f"{remaining} nicht anreicherbar (Wetterdienst prüfen)"


def _run_embeddings(db: Session, job: Job) -> tuple[str, str]:
    from app.ai import get_provider
    from app.models import Event

    provider = get_provider()
    db.query(Event).update({Event.embedding: None}, synchronize_session=False)
    db.commit()
    while True:
        batch = (db.query(Event).filter(Event.embedding.is_(None))
                 .order_by(Event.created_at).limit(25).all())
        count = 0
        for event in batch:
            vec = provider.embed(f"{event.title}\n{event.description or ''}")
            if vec:
                event.embedding = vec
                count += 1
        db.commit()
        remaining = db.query(Event).filter(Event.embedding.is_(None)).count()
        cont = _tick(db, job.id, count, remaining)
        if remaining <= 0:
            return "done", f"{db.get(Job, job.id).done} Events neu indexiert"
        if not cont:
            return "stopped", "gestoppt"
        if count == 0:
            return "stopped", "kein Embedding-Modell konfiguriert/erreichbar"


def _run_recompute(db: Session, job: Job) -> tuple[str, str]:
    from app.services.ingestion import reprocess_pending, reset_reprocess

    total = reset_reprocess(db)
    _tick(db, job.id, 0, total)
    while True:
        processed, remaining, aborted = reprocess_pending(db, limit=5)
        cont = _tick(db, job.id, processed, remaining)
        if aborted:
            return "stopped", "KI-Kontingent erschöpft — später fortsetzen"
        if remaining <= 0:
            return "done", f"{db.get(Job, job.id).done} Fragmente neu verarbeitet"
        if not cont:
            return "stopped", "gestoppt"
        if processed == 0:
            return "stopped", f"{remaining} nicht verarbeitbar"


def _run_resolve_names(db: Session, job: Job) -> tuple[str, str]:
    from app.routers.tracks import resolve_place_names

    user = db.get(User, job.user_id)
    # A28: ohne scope läuft der Job über alle Mängel auf einmal. Alte
    # Job-Einträge, die noch einen Scope tragen, laufen unverändert weiter.
    scope = (job.params or {}).get("scope")
    what = f" ({scope})" if scope else ""
    while True:
        r = resolve_place_names(limit=25, scope=scope, db=db, user=user)
        cont = _tick(db, job.id, r.resolved, r.remaining)
        if r.remaining <= 0:
            return "done", f"{db.get(Job, job.id).done} Ortsnamen bearbeitet{what}"
        if not cont:
            return "stopped", "gestoppt"
        if r.resolved == 0:
            return "stopped", f"{r.remaining} nicht auflösbar{what}"


def _run_immich(db: Session, job: Job) -> tuple[str, str]:
    """P2.1: Fotos aus Immich verknüpfen.

    Die Kandidaten werden EINMAL am Anfang ermittelt und dann jedes Ereignis
    genau einmal geprüft. Der alte Lauf rief `link_batch` in einer Schleife und
    erwartete, dass die Kandidatenmenge schrumpft — sie tut es aber nur für
    Ereignisse, an denen tatsächlich ein Foto landet. Ereignisse OHNE passende
    Fotos blieben Kandidaten, der Stapel nahm immer wieder dieselben ersten 25:
    eine Endlosschleife ohne Fortschritt und ohne Fehlermeldung.
    """
    from sqlalchemy.exc import IntegrityError

    from app.services import immich as immich_api
    from app.services.immich_link import candidates, link_event

    user = db.get(User, job.user_id)
    cfg = immich_api.config_for(user)
    if cfg is None:
        return "stopped", ("Immich ist für dieses Konto nicht eingerichtet "
                           "(Verwaltung → Meine Daten → Immich).")
    url, key = cfg

    pending = candidates(db, user.id)
    total = len(pending)
    job.unit = "Ereignisse geprüft"
    db.commit()
    log.info("Immich-Lauf: %d Ereignisse zu prüfen (user=%s)",
             total, user.email or user.id)
    if not total:
        return "done", "Keine neuen Ereignisse zum Verknüpfen — alles aktuell."

    linked = ticked = 0
    for i, event in enumerate(pending, 1):
        try:
            linked += link_event(db, user, event, url, key)
            db.commit()
        except IntegrityError:
            db.rollback()      # paralleler Lauf war schneller — kein Schaden
        except immich_api.ImmichError as exc:
            db.rollback()
            log.warning("Immich-Lauf gestoppt bei %d/%d: %s", i, total, exc)
            return "stopped", f"{linked} Fotos verknüpft, dann Abbruch: {exc}"
        # Alle 10 Ereignisse Fortschritt schreiben (Balken) und ins Log —
        # ohne Spur ist ein langsamer Lauf von einem hängenden nicht zu
        # unterscheiden. done = geprüfte Ereignisse, remaining = die restlichen.
        if i % 10 == 0 or i == total:
            log.info("Immich-Lauf: %d/%d geprüft, %d Fotos verknüpft",
                     i, total, linked)
            if not _tick(db, job.id, i - ticked, total - i):
                return "stopped", f"{linked} Fotos verknüpft (gestoppt bei {i}/{total})."
            ticked = i

    return "done", f"{linked} Fotos an {total} geprüften Ereignissen verknüpft."


_RUNNERS = {
    "weather": _run_weather,
    "immich": _run_immich,
    "embeddings": _run_embeddings,
    "recompute": _run_recompute,
    "resolve_names": _run_resolve_names,
}


def _worker_main(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        status, result = _RUNNERS[job.type](db, job)
    except Exception as err:  # noqa: BLE001 — Fehler landet im Job-Ergebnis
        log.exception("Job-Worker-Fehler (%s)", job_id[:8])
        db.rollback()
        status, result = "error", str(err)[:250]
    try:
        db.expire_all()
        job = db.get(Job, job_id)
        if job and job.status in ("running", "stopping"):
            job.status = status
            job.result = result
            job.finished_at = _naive_now()
            db.commit()
            log.info("Job fertig: %s (%s) — %s: %s",
                     job.type, job_id[:8], status, result)
    finally:
        db.close()


def spawn_worker(job_id: str) -> None:
    threading.Thread(target=_worker_main, args=(job_id,), daemon=True).start()


# --------------------------------------------------------------------------- #
# A22 — Nachtplan: pro Nutzer und Job-Typ ein-/ausschaltbar (job_schedule in
# User.settings). Ein Ticker-Thread (main.py) ruft minütlich run_due_schedules.
# --------------------------------------------------------------------------- #
def run_due_schedules() -> None:
    db = SessionLocal()
    try:
        now = datetime.now()  # lokale Serverzeit (TZ, z. B. Europe/Berlin)
        for user in db.query(User).all():
            sched = (user.settings or {}).get("job_schedule") or {}
            for jtype, cfg in sched.items():
                if (jtype not in _RUNNERS or not cfg.get("enabled")
                        or now.hour != int(cfg.get("hour", 3))):
                    continue
                # Heute schon gelaufen (egal von wem)? Dann nicht erneut.
                last = (db.query(Job).filter(Job.type == jtype)
                        .order_by(Job.started_at.desc()).first())
                if last:
                    started_local = (last.started_at.replace(tzinfo=timezone.utc)
                                     .astimezone())
                    if started_local.date() == now.date():
                        continue
                    if last.status in ("running", "stopping"):
                        continue
                job = Job(user_id=user.id, type=jtype, unit="geplant", params=None)
                db.add(job)
                db.commit()
                log.info("Nachtplan: Job %s für %s gestartet", jtype,
                         user.display_name or user.email)
                spawn_worker(job.id)
    except Exception:  # noqa: BLE001 — Planer darf die App nie stören
        log.exception("Nachtplan-Fehler")
    finally:
        db.close()
