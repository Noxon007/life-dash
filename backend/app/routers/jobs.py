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
from app.joblog import Progress
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
    "immich_source": "Ereignisse aus Immich vorschlagen",
    "timeline_import": "Google-Timeline-Import",
    "data_import": "Daten-Import (JSON)",
}
# A22: Diese Typen laufen SERVERSEITIG als Background-Thread weiter, auch wenn
# der Browser zu ist. Importe bleiben client-getrieben (die Datei liegt dort).
SERVER_JOB_TYPES = ("weather", "embeddings", "resolve_names", "recompute",
                    "immich", "immich_source")
# Diese Läufe bearbeiten die Daten GENAU EINES Kontos (`job.user_id`) — sie
# gehören in der Oberfläche unter „Meine Daten", nicht unter System. Der Rest
# (`recompute`, `embeddings`) rechnet über den ganzen Bestand.
#
# Der Unterschied ist nicht kosmetisch: „heute schon gelaufen" im Nachtplan
# darf für diese Typen nur den EIGENEN Lauf zählen, sonst nimmt der erste
# Nutzer allen anderen den Termin weg (Anmerkung 115). Die Sperre beim Start
# bleibt trotzdem global — sie schützt nicht die Daten, sondern das Kontingent
# bei Open-Meteo/Nominatim/Immich, und das hängt an der Instanz, nicht am Konto.
USER_SCOPED_TYPES = ("weather", "resolve_names", "immich", "immich_source")
# In Tests abgeschaltet (in-memory-DB verträgt keine fremden Threads)
WORKERS_ENABLED = True

# Lebenszeichen je laufendem Job. Bewusst hier und nicht in jedem Runner: durch
# `_tick` läuft JEDER Fortschritt — der der Server-Worker wie der, den ein
# client-getriebener Import (Timeline, JSON) über /progress meldet. Ein Eintrag
# lebt so lange wie der Lauf; aufgeräumt wird beim Abschluss und beim Einsammeln
# verwaister Jobs.
_BEATS: dict[str, Progress] = {}


def _beat(job: Job) -> Progress:
    """Fortschrittsprotokoll dieses Jobs — bei Bedarf angelegt."""
    p = _BEATS.get(job.id)
    if p is None:
        label = f"{JOB_TYPES.get(job.type, job.type)} ({job.id[:8]})"
        p = _BEATS[job.id] = Progress(log, label, unit=job.unit or "Einträge")
    return p


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
        _BEATS.pop(job.id, None)
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
    # Auch der Import spricht: er läuft im Browser, aber sein Fortschritt gehört
    # ins Server-Log — dort steht der Rest des Laufs (Ortsnamen, Wetter) auch.
    _beat(job).beat(job.done, payload.remaining)
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
        _BEATS.pop(job.id, None)
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
    _beat(job).beat(job.done, remaining)
    return job.status == "running"


def _run_weather(db: Session, job: Job) -> tuple[str, str]:
    from app.services.enrichment import enrich_weather

    while True:
        enriched, remaining = enrich_weather(db, limit=25, user_id=job.user_id)
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
    from app.routers.tracks import resolve_names_batch

    user = db.get(User, job.user_id)
    # A28: ohne scope läuft der Job über alle Mängel auf einmal. Alte
    # Job-Einträge, die noch einen Scope tragen, laufen unverändert weiter.
    scope = (job.params or {}).get("scope")
    what = f" ({scope})" if scope else ""
    # Anmerkung 96: Jeder Ort wird in EINEM Lauf höchstens einmal versucht —
    # dieselbe Kur, die Anmerkung 77 dem Immich-Lauf verordnet hat. Ohne diese
    # Menge sammeln sich die unauflösbaren Orte vorne in der Warteschlange, bis
    # ein ganzer Batch aus ihnen besteht; dann meldet der Lauf „nicht auflösbar"
    # und hört auf, obwohl hunderte auflösbare Orte dahinter warten.
    tried: set[str] = set()
    while True:
        r = resolve_names_batch(db, user, limit=25, scope=scope, skip=tried)
        cont = _tick(db, job.id, r.resolved, r.remaining)
        if r.remaining <= 0:
            done = db.get(Job, job.id).done
            note = f", {len(tried)} nicht auflösbar" if tried else ""
            return "done", f"{done} Ortsnamen bearbeitet{what}{note}"
        if not cont:
            return "stopped", "gestoppt"
        if r.resolved == 0:
            # Jetzt heißt das wirklich, was es sagt: der Batch bestand aus
            # Orten, die noch nie versucht wurden, und keiner ging.
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
    from app.services.immich_link import (candidates, day_candidates,
                                          detach_machine_links, link_target,
                                          linked_asset_ids, targets)

    user = db.get(User, job.user_id)
    cfg = immich_api.config_for(user)
    if cfg is None:
        return "stopped", ("Immich ist für dieses Konto nicht eingerichtet "
                           "(Verwaltung → Meine Daten → Immich).")
    url, key = cfg

    # Anmerkung 106: Bestehende Verweise an importierten Besuchen lösen, bevor
    # `seen` gefüllt wird — sonst gälten genau die Fotos, um die es geht, als
    # bereits vergeben, und die Korrektur erreichte die Bestandsdaten nie.
    detach_machine_links(db, user.id)

    todo = targets(db, user.id)
    n_events = sum(1 for kind, _ in todo if kind == "event")
    n_days = len(todo) - n_events
    total = len(todo)
    job.unit = "Ereignisse und Tage geprüft"
    db.commit()
    # Entduplizierung über den ganzen Lauf: jedes Foto genau einmal, am ersten
    # passenden Ereignis. Vorbelegt mit dem, was schon hängt — so verdoppelt
    # auch ein erneuter Lauf nichts.
    seen = linked_asset_ids(db, user.id)
    log.info("Immich-Lauf: %d Ereignisse und %d Tage zu prüfen, %d Fotos "
             "bereits verknüpft (user=%s)", n_events, n_days, len(seen),
             user.email or user.id)
    if not total:
        return "done", "Keine neuen Ereignisse zum Verknüpfen — alles aktuell."

    linked = ticked = 0
    for i, (kind, item) in enumerate(todo, 1):
        try:
            linked += link_target(db, user, kind, item, url, key, seen)
            db.commit()
        except IntegrityError:
            db.rollback()      # paralleler Lauf war schneller — kein Schaden
        except immich_api.ImmichError as exc:
            db.rollback()
            log.warning("Immich-Lauf gestoppt bei %d/%d: %s", i, total, exc)
            return "stopped", f"{linked} Fotos verknüpft, dann Abbruch: {exc}"
        # Alle 10 Einheiten Fortschritt schreiben (Balken) und ins Log — ohne
        # Spur ist ein langsamer Lauf von einem hängenden nicht zu
        # unterscheiden. done = geprüfte Einheiten, remaining = die restlichen.
        if i % 10 == 0 or i == total:
            log.info("Immich-Lauf: %d/%d geprüft, %d Fotos verknüpft",
                     i, total, linked)
            if not _tick(db, job.id, i - ticked, total - i):
                return "stopped", f"{linked} Fotos verknüpft (gestoppt bei {i}/{total})."
            ticked = i

    return "done", (f"{linked} Fotos verknüpft — {n_events} Ereignisse und "
                    f"{n_days} Tage geprüft.")


def _run_immich_source(db: Session, job: Job) -> tuple[str, str]:
    """P2.1 Stufe 2: aus Immich-Fotos Ereignis-VORSCHLÄGE machen — ein Jahr.

    Jahresweise, weil eine zwanzig Jahre alte Bibliothek sonst vierstellig
    viele Vorschläge in eine Warteschlange kippt, die für Dutzende gebaut ist
    (Anmerkung 107). Das Jahr steht in `params` — ohne Jahr kein Lauf: „alles"
    wäre genau der Fall, den die Aufteilung verhindern soll.

    Der Lauf scannt NEU statt die Vorschau zu übernehmen. Zwischen Ansehen und
    Bestätigen kann sich etwas geändert haben, und `scan_year` ist die eine
    Stelle, an der die sieben Fälle geprüft werden.
    """
    from app.services import immich as immich_api
    from app.services import immich_source as source

    user = db.get(User, job.user_id)
    cfg = immich_api.config_for(user)
    if cfg is None:
        return "stopped", ("Immich ist für dieses Konto nicht eingerichtet "
                           "(Verwaltung → Meine Daten → Immich).")
    year = (job.params or {}).get("year")
    # Bereich prüfen wie der Vorschau-Endpunkt: `params` kommt vom Client, und
    # `datetime(99999, 1, 1)` wäre kein Lauf, sondern ein Absturz mit
    # Stapelspur statt einer Auskunft.
    if not isinstance(year, int) or not 1900 <= year <= 2200:
        return "error", "Ohne gültiges Jahr kein Lauf — bitte ein Jahr auswählen."
    url, key = cfg

    job.unit = "Vorschläge angelegt"
    db.commit()
    # Der Scan läuft, BEVOR es etwas zu zählen gibt — bei einer großen
    # Bibliothek Minuten. Ohne Lebenszeichen dazwischen gilt der Job nach
    # STALE_SECONDS als verwaist, und der Lauf hätte die ganze Arbeit gemacht,
    # um danach „gestoppt" zu melden. `_tick(…, 0, None)` schlägt den Puls,
    # ohne einen Fortschritt zu behaupten, den es noch nicht gibt.
    try:
        proposals = source.scan_year(db, user, year, url, key,
                                     heartbeat=lambda: _tick(db, job.id, 0, None))
    except immich_api.ScanAborted:
        return "stopped", f"{year}: Suche abgebrochen — nichts angelegt."
    except immich_api.ImmichError as exc:
        return "stopped", f"Immich antwortet nicht: {exc}"

    if not proposals:
        return "done", f"{year}: nichts Neues vorzuschlagen."

    total = len(proposals)
    created = 0
    # In Blöcken anlegen und festschreiben: bricht der Lauf ab, ist das
    # Angelegte da und der Rest kommt beim nächsten Mal — die Plätze sind
    # stabil, ein zweiter Lauf schlägt nichts doppelt vor.
    for i in range(0, total, 20):
        block = proposals[i:i + 20]
        created += source.create_proposals(db, user, block)
        db.commit()
        if not _tick(db, job.id, len(block), total - (i + len(block))):
            return "stopped", f"{created} Vorschläge angelegt (gestoppt)."
    days = sum(1 for p in proposals if p.kind == "day")
    return "done", (f"{year}: {created} Vorschläge angelegt "
                    f"({days} Fototage, {total - days} Alben) — alle unbestätigt.")


_RUNNERS = {
    "weather": _run_weather,
    "immich": _run_immich,
    "immich_source": _run_immich_source,
    "embeddings": _run_embeddings,
    "recompute": _run_recompute,
    "resolve_names": _run_resolve_names,
}


def _worker_main(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        _beat(job).start(note=f"Typ {job.type}")
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
            # Eine Schlusszeile, nicht zwei: `finish` trägt Typ, Kennung, Dauer,
            # Status und Ergebnis — das alte „Job fertig" sagte dasselbe ohne Dauer.
            _beat(job).finish(f"{status} — {result}")
    finally:
        _BEATS.pop(job_id, None)
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
                # Läuft dieser Typ gerade (egal von wem)? Dann nicht daneben —
                # die Sperre aus `start_job` gilt auch für den Planer.
                if (db.query(Job)
                        .filter(Job.type == jtype,
                                Job.status.in_(("running", "stopping")))
                        .first()):
                    continue
                # Heute schon gelaufen? Bei kontogebundenen Läufen zählt nur
                # der EIGENE (Anmerkung 115): sonst erledigt der erste Nutzer
                # den Termin für alle, und die Ereignisse aller anderen bleiben
                # ohne Wetter, Ortsnamen und Fotos — still, Nacht für Nacht.
                q = db.query(Job).filter(Job.type == jtype)
                if jtype in USER_SCOPED_TYPES:
                    q = q.filter(Job.user_id == user.id)
                last = q.order_by(Job.started_at.desc()).first()
                if last:
                    started_local = (last.started_at.replace(tzinfo=timezone.utc)
                                     .astimezone())
                    if started_local.date() == now.date():
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
