# Life-Dash Backend

FastAPI-Backend für Life-Dash — die durchsuchbare Lebensdatenbank.
Aktuelle Version und Änderungen: [../CHANGELOG.md](../CHANGELOG.md).

## Schicht-Architektur

- **Roh-Eingang** (`Fragment`) — unveränderlich, wird nie automatisch gelöscht.
- **Vorschläge** (`unconfirmed`) — KI-strukturiert, warten auf Moderation.
- **Lebensdatenbank** (`confirmed`) — Maschinen ändern Bestätigtes nie;
  Anreicherung (z. B. Wetter) ist ausschließlich additiv.
- **Ableitungen** — Timeline, Karte, Suche, Statistik, Welt, Erfolge:
  jederzeit neu berechenbar, kein eigener Datenbestand.

## Multi-User & Auth (OIDC)

- Alle Daten sind nutzergebunden (`user_id` auf allen Schichten); jede API-Query ist gescoped.
- `AUTH_MODE=dev` (Default): kein Login, fester Dev-User mit Admin-Rolle — für lokale Entwicklung.
- `AUTH_MODE=oidc`: Authorization Code Flow mit **PKCE** gegen einen beliebigen
  standardkonformen OIDC-Provider (Authentik, Keycloak, Pocket ID, Zitadel, Auth0, …).
  - Beim Provider einen Client anlegen; Callback-URL: `<PUBLIC_BASE_URL>/api/auth/callback`.
  - Public Client reicht (Secret optional). Nötige Variablen: `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `SESSION_SECRET`, `PUBLIC_BASE_URL` (siehe `../.env.example`).
  - Nutzer entstehen beim ersten Login (JIT). **Der erste Nutzer wird Admin** und übernimmt vorhandene Single-User-Altdaten.
  - `OIDC_PROVIDER_NAME` setzt optional den Anzeigenamen auf dem Login-Screen.
- API-Clients können alternativ ein `Authorization: Bearer <token>` des Providers senden.

## Schnellstart (lokal, ohne Docker)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Danach:
- **Frontend (PWA):** http://127.0.0.1:8000/ — responsive, auf dem Smartphone installierbar
- API-Docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

Beim ersten Start werden im Dev-Modus Beispieldaten geseedet (`SEED_DEMO=true`).

## Docker

```bash
cp .env.example .env   # OIDC_*, SESSION_SECRET, POSTGRES_PASSWORD setzen
docker compose up -d   # App + PostgreSQL (SQLite: DATABASE_URL überschreiben)
```

Vollständiges Server-Deployment (GHCR-Image, Reverse Proxy, OIDC,
Datenübernahme): [../docs/DEPLOY.md](../docs/DEPLOY.md)

## Suche

`GET /api/search?q=…` — hybrid:
- **Volltext** über Titel, Beschreibung, Ortsname, Entity-Namen (immer aktiv).
- **Semantisch** über Event-Embeddings (Cosine) — aktiv, sobald `OPENAI_EMBED_MODEL`
  gesetzt ist; das Modell liefert derselbe OpenAI-kompatible Endpoint wie den Chat
  (oder ein eigener, siehe `OPENAI_EMBED_BASE_URL`). Ohne Embeddings: reiner Volltext.
  `SEMANTIC_MIN_SIMILARITY` ist modellabhängig und will nachkalibriert werden.
  Nach Modellwechsel: Admin → „🧠 Embeddings berechnen" (bzw. `POST /api/admin/reindex-embeddings?force=true`).

## Stack

| Ebene | Aktuell | Später (Konzept) |
|---|---|---|
| DB | SQLite (Datei) oder PostgreSQL | PostgreSQL + PostGIS + pgvector |
| KI | OpenAI-kompatible API (Anbieter frei) oder Mock-Provider | — |
| Auth | OIDC (beliebiger Provider) oder Dev-Modus | — |
| Geo | lat/lng-Felder + Nominatim-kompatibler Dienst | PostGIS |
| Deployment | uvicorn / Docker Compose | Docker Compose |

Die Modelle sind Postgres-kompatibel gehalten; `app/migrate.py` ergänzt neue Spalten
in bestehenden DBs (MVP-Migration, später Alembic).

## Struktur

```
app/
  main.py            App-Setup, Migration, Seed, Frontend-Mount
  config.py          Settings (.env) inkl. Auth/OIDC
  database.py        Engine/Session
  migrate.py         Mini-Migration (fehlende Spalten, Altdaten-Adoption)
  models.py          SQLAlchemy-Modelle (User + Stufe 1/2/3)
  schemas.py         Pydantic-Schemas
  auth.py            OIDC (PKCE, JWKS), Session-Cookies, Dependencies
  seed.py            Demo-Daten (Dev-Modus)
  ai/                KI-Provider (Mock, OpenAI-kompatibel, Embeddings)
  modules/           Modul-Registry (lädt YAML)
  data/              Statische Stammdaten (Länder: Name -> ISO -> Kontinent)
  services/          Ingestion-Pipeline, Geocoding, Wetter-Enrichment, Erfolge
  routers/           API-Endpoints (auth, ingest, events, search, moderation,
                     modules, tracks, jobs, data, world, achievements, admin)
modules/             YAML-Modul-Definitionen (trip, animal, country, … inkl. Erfolge)
../frontend/         Responsive PWA (wird vom Backend unter / ausgeliefert)
                     + world-countries.geojson (Länderflächen für die Weltkarte)
```
