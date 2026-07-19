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
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Job, User

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
    "timeline_import": "Google-Timeline-Import",
    "data_import": "Daten-Import (JSON)",
}


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
             .filter(Job.status == "running", Job.updated_at < _stale_cutoff())
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
    """Startet einen Job — 409, wenn derselbe Typ bereits läuft."""
    _reap_stale(db)
    running = (db.query(Job)
               .filter(Job.type == payload.type, Job.status == "running")
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
    job = Job(user_id=user.id, type=payload.type, unit=payload.unit)
    db.add(job)
    db.commit()
    log.info("Job gestartet: %s (%s) von %s", payload.type, job.id[:8],
             user.display_name or user.email)
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
