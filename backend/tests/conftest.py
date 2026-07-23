"""Test-Fixtures: In-Memory-DB, sichere Settings (kein Netz, Mock-KI).

**Zwei Datenbanken, dieselben Tests.** Ohne Zutun läuft alles wie bisher auf
SQLite im Arbeitsspeicher — schnell, ohne Server, überall lauffähig. Betrieben
wird Life-Dash aber auf **PostgreSQL** (`docker-compose.yml` startet
`postgres:18-alpine`), und eine ganze Fehlerklasse ist damit bis jetzt
ungetestet: native Enum-Typen, JSON gegen JSONB, `round()` auf
`double precision`, der PostgreSQL-Zweig von `_relax_not_null` — Dinge, die auf
SQLite grün sind und beim ersten echten Start scheitern.

Steht `TEST_DATABASE_URL` in der Umgebung, läuft dieselbe Suite gegen diese
Datenbank:

    docker run -d --name lifedash-test -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=lifedash_test -p 55432:5432 postgres:18-alpine
    TEST_DATABASE_URL=postgresql+psycopg2://postgres:test@localhost:55432/lifedash_test \\
        <python> -m pytest tests -q

**Das Schema wird dabei gelöscht und neu angelegt**, weshalb hier zwei Riegel
sitzen (Anmerkung 76: es gab schon zweimal einen Weg, auf dem Tests die echte
Datenbank anfassen konnten): die URL darf nicht die betriebene sein, und der
Datenbankname muss `test` enthalten. Ein Tippfehler soll keine Lebensdatenbank
kosten.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# `app` importierbar machen, egal von wo pytest gestartet wird
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import User, UserRole  # noqa: E402

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


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


def _refuse_dangerous_url(url: str) -> None:
    """Zwei Riegel vor `drop_all`. Beide prüfen dasselbe von zwei Seiten: dass
    die Testdatenbank eine Testdatenbank IST — einmal über die Herkunft (nicht
    die betriebene URL), einmal über den Namen. Ein Riegel allein reicht nicht:
    `DATABASE_URL` ist beim Testlauf oft gar nicht gesetzt, dann fällt der
    erste ins Leere."""
    if url == settings.database_url:
        raise RuntimeError(
            "TEST_DATABASE_URL ist die betriebene DATABASE_URL. Die Testsuite "
            "löscht das Schema — das wäre die Lebensdatenbank gewesen.")
    name = url.rsplit("/", 1)[-1].split("?", 1)[0].lower()
    if "test" not in name:
        raise RuntimeError(
            f"TEST_DATABASE_URL zeigt auf die Datenbank '{name}'. Der Name muss "
            "'test' enthalten — die Testsuite legt ihr Schema neu an.")


@pytest.fixture(scope="session")
def _shared_engine():
    """Bei PostgreSQL EINE Engine für den ganzen Lauf: ein Schema je Test neu
    anzulegen kostet auf einem echten Server ein Vielfaches der Testzeit.
    Geleert wird stattdessen (siehe `db`). Ohne `TEST_DATABASE_URL` gibt es
    nichts zu teilen — dann bleibt alles wie bisher."""
    if not TEST_DATABASE_URL:
        yield None
        return
    _refuse_dangerous_url(TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _empty_all_tables(engine) -> None:
    """`TRUNCATE` über alle Tabellen auf einmal — mit `CASCADE`, weil die
    Reihenfolge sonst an den Fremdschlüsseln hängt und jede neue Tabelle die
    Liste hier zweitpflegen müsste."""
    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture()
def db(_shared_engine):
    if _shared_engine is None:
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
        return

    _empty_all_tables(_shared_engine)
    session = sessionmaker(bind=_shared_engine, autoflush=False)()
    yield session
    # Zurückrollen VOR dem Schließen: ein Test, der mit einer geplatzten
    # Transaktion endet, würde sonst die Verbindung so in den Pool zurückgeben.
    session.rollback()
    session.close()


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
