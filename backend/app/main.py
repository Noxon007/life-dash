"""FastAPI-App: Setup, Startup (Migration, Module laden, Demo-Seed), Frontend-Auslieferung."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth import get_dev_user
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.migrate import ensure_schema
from app.modules.registry import load_modules
from app.routers import admin, auth, data, events, ingest, moderation, modules, search, tracks
from app.seed import seed_demo


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    yield


app = FastAPI(
    title="Life-Dash API",
    version="0.2.0",
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
app.include_router(search.router)
app.include_router(moderation.router)
app.include_router(modules.router)
app.include_router(data.router)
app.include_router(tracks.router)
app.include_router(admin.router)


@app.get("/health", tags=["System"])
def health() -> dict:
    return {
        "status": "ok",
        "ai_provider": settings.ai_provider,
        "auth_mode": settings.auth_mode,
        "database": settings.database_url.split("://")[0],
    }


# Frontend (responsive PWA) — zuletzt gemountet, damit /api/* & /docs gewinnen
if settings.frontend_dir.exists():
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
