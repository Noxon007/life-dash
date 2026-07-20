"""Test-Fixtures: In-Memory-DB, sichere Settings (kein Netz, Mock-KI)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# `app` importierbar machen, egal von wo pytest gestartet wird
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import User, UserRole  # noqa: E402


@pytest.fixture(autouse=True)
def safe_settings(monkeypatch):
    """Tests laufen offline: Mock-KI, kein Geocoding, keine Embeddings,
    keine Job-Worker-Threads (in-memory-DB ist nicht thread-tauglich)."""
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(settings, "geocoding_enabled", False)
    monkeypatch.setattr(settings, "openai_embed_model", "")
    monkeypatch.setattr("app.routers.jobs.WORKERS_ENABLED", False)


@pytest.fixture(autouse=True)
def modules_loaded():
    """Die Modul-Registry wird sonst nur beim App-Start gefüllt — Tests, die
    deklarative Module brauchen (Achievements F6, Prompt-Regeln A7), stünden
    ohne sie vor einer leeren Registry."""
    from app.modules.registry import load_modules, registry
    if not registry.modules:
        load_modules()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def user(db):
    u = User(oidc_subject="test-sub", email="test@example.org",
             display_name="Testnutzer", role=UserRole.admin)
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def fake_weather(monkeypatch):
    """Ersetzt den Open-Meteo-Abruf; gibt die Liste der Aufrufe zurück."""
    calls: list[tuple] = []

    def _fake(lat, lng, when):
        calls.append((lat, lng, when))
        # Vollständiges Format (F3-Tageswerte + F12-Zusatzwerte) — sonst
        # gälte das Wetter als Alt-Bestand und würde beim nächsten Lauf
        # nachgerüstet (0.15.1 / 0.23.0)
        return {"temp_c": 21.5, "temp_min_c": 14.0, "temp_max_c": 29.0,
                "sun_h": 11.2, "rain_mm": 0.4, "snow_cm": 0.0,
                "wind_max_kmh": 18.4, "condition": "Klar",
                "apparent_max_c": 31.2, "apparent_min_c": 12.5, "rain_h": 1.0,
                "daylight_h": 15.8, "gust_max_kmh": 42.0, "uv_max": 6.4,
                "sunrise": "05:14", "sunset": "21:02"}

    monkeypatch.setattr("app.services.enrichment.fetch_weather", _fake)
    return calls
