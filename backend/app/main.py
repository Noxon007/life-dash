"""FastAPI-App: Setup, Startup (Migration, Module laden, Demo-Seed), Frontend-Auslieferung."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth import get_dev_user
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.migrate import ensure_schema
from app.modules.registry import load_modules
from app.routers import (
    achievements,
    admin,
    auth,
    data,
    events,
    ingest,
    jobs,
    media,
    moderation,
    modules,
    search,
    tracks,
    world,
)
from app.seed import seed_demo
from app.version import APP_VERSION

# Zentrales Logging (A9): ein Format für alle lifedash.*-Logger, Level per
# LOG_LEVEL steuerbar. uvicorn behält seine eigenen Handler (Access-Log).
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("lifedash")

# A17: Ring-Puffer für die Log-Ansicht im Admin-Panel — hängt am
# "lifedash"-Logger und fängt damit alle lifedash.*-Meldungen
from app.logbuffer import ring  # noqa: E402

logging.getLogger("lifedash").addHandler(ring)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Life-Dash %s startet — auth=%s, ai=%s, db=%s, log_level=%s",
             APP_VERSION, settings.auth_mode, settings.ai_provider,
             settings.database_url.split("://")[0], settings.log_level.upper())
    # A35: Bei echter Anmeldung (local/oidc) signiert das Standard-Secret die
    # Session-Cookies — wer es kennt, fälscht eine fremde Sitzung. Laut,
    # damit es niemand produktiv übersieht. (Die Härtung von dev-Modus in
    # Produktion folgt mit R1.)
    if (settings.auth_mode in ("local", "oidc")
            and settings.session_secret == "dev-secret-change-me"):
        log.warning("SESSION_SECRET ist noch der Standardwert — bei %s-Login "
                    "UNBEDINGT setzen (python -c \"import secrets; "
                    "print(secrets.token_urlsafe(48))\").", settings.auth_mode)
    # Module aus YAML laden
    load_modules()
    # Bestehende Tabellen um neue Spalten ergänzen (user_id, embedding)
    ensure_schema(engine)
    # Tabellen anlegen (MVP: create_all; später Alembic-Migrationen)
    Base.metadata.create_all(bind=engine)
    # Demo-Daten — nur im Dev-Modus (im OIDC-Betrieb gehören Daten einem echten Nutzer)
    if settings.seed_demo and settings.auth_mode == "dev":
        db = SessionLocal()
        try:
            seed_demo(db, get_dev_user(db))
        finally:
            db.close()
    # A22: Nachtplan-Ticker — prüft minütlich, ob geplante Jobs fällig sind
    import threading
    import time as _time

    from app.routers.jobs import run_due_schedules

    def _schedule_ticker() -> None:
        while True:
            _time.sleep(60)
            run_due_schedules()

    threading.Thread(target=_schedule_ticker, daemon=True).start()
    yield


app = FastAPI(
    title="Life-Dash API",
    version=APP_VERSION,
    description="Durchsuchbare Lebensdatenbank — Drei-Stufen-Architektur (Roh → Struktur → Ansichten).",
    lifespan=lifespan,
)

# CORS: Das Frontend wird vom Backend selbst ausgeliefert (same-origin).
# Die Liste erlaubt zusätzlich lokale Dev-Setups mit separatem Frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.public_base_url.rstrip("/"),
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(events.router)
app.include_router(media.router)      # F15: Bilder an Events
app.include_router(search.router)
app.include_router(moderation.router)
app.include_router(modules.router)
app.include_router(data.router)
app.include_router(tracks.router)
app.include_router(jobs.router)
app.include_router(world.router)
app.include_router(achievements.router)
app.include_router(admin.router)


@app.get("/health", tags=["System"])
def health() -> dict:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "ai_provider": settings.ai_provider,
        "auth_mode": settings.auth_mode,
        "database": settings.database_url.split("://")[0],
    }


# Frontend (responsive PWA) — zuletzt gemountet, damit /api/* & /docs gewinnen
if settings.frontend_dir.exists():
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
