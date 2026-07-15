# Life-Dash Backend

FastAPI-Backend für Life-Dash — die durchsuchbare Lebensdatenbank.
**Stand: P0 (Fundament) + P1 (MVP) umgesetzt.**

## Drei-Stufen-Architektur

- **Stufe 1** — Roh-Input (`Fragment`), unveränderlich.
- **Stufe 2** — KI-strukturierte, moderierte Daten (`Event`, `Entity`) mit `confirmed`-Status.
- **Stufe 3** — Berechnete Ansichten (Timeline, Karte, Suche, Statistik) aus Stufe 2.

## Multi-User & Auth (OIDC / Pocket ID)

- Alle Daten sind nutzergebunden (`user_id` in Stufe 1–3); jede API-Query ist gescoped.
- `AUTH_MODE=dev` (Default): kein Login, fester Dev-User mit Admin-Rolle — für lokale Entwicklung.
- `AUTH_MODE=oidc`: Authorization Code Flow mit **PKCE** gegen **Pocket ID**.
  - In Pocket ID einen Client anlegen; Callback-URL: `<PUBLIC_BASE_URL>/api/auth/callback`.
  - Public Client reicht (Secret optional). Nötige Variablen: `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `SESSION_SECRET`, `PUBLIC_BASE_URL` (siehe `../.env.example`).
  - Nutzer entstehen beim ersten Login (JIT). **Der erste Nutzer wird Admin** und übernimmt vorhandene Single-User-Altdaten.
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

## Docker (Homelab)

```bash
cp .env.example .env   # OIDC_*, SESSION_SECRET, POSTGRES_PASSWORD setzen
docker compose up -d   # App + PostgreSQL (SQLite: DATABASE_URL überschreiben)
```

Vollständiges Server-Deployment (GHCR-Image, Pangolin/Traefik, Pocket ID,
Datenübernahme): [../docs/DEPLOY.md](../docs/DEPLOY.md)

## Suche

`GET /api/search?q=…` — hybrid:
- **Volltext** über Titel, Beschreibung, Ortsname, Entity-Namen (immer aktiv).
- **Semantisch** über Event-Embeddings (Cosine) — aktiv, sobald `OPENAI_EMBED_MODEL`
  gesetzt ist. Standardweg: `gemini-embedding-2` über die Gemini API. Ohne
  Embeddings: reiner Volltext.
  Nach Modellwechsel: Admin → „🧠 Embeddings berechnen" (bzw. `POST /api/admin/reindex-embeddings?force=true`).

## MVP-Stack

| Ebene | Aktuell (MVP) | Später (Konzept) |
|---|---|---|
| DB | SQLite (Datei) | PostgreSQL + PostGIS + pgvector |
| KI | Gemini API (OpenAI-kompatibel) / Mock-Provider | lokales Ollama möglich |
| Auth | OIDC (Pocket ID) oder Dev-Modus | — |
| Geo | lat/lng-Felder + Nominatim | PostGIS |
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
  services/          Ingestion-Pipeline, Geocoding, Wetter-Enrichment
  routers/           API-Endpoints (auth, ingest, events, search, moderation, modules, admin)
modules/             YAML-Modul-Definitionen (trip, animal, country)
../frontend/         Responsive PWA (wird vom Backend unter / ausgeliefert)
```
