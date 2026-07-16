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
    """Tests laufen offline: Mock-KI, kein Geocoding, keine Embeddings."""
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(settings, "geocoding_enabled", False)
    monkeypatch.setattr(settings, "openai_embed_model", "")


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
        return {"temp_c": 21.5, "condition": "Klar"}

    monkeypatch.setattr("app.services.enrichment.fetch_weather", _fake)
    return calls
