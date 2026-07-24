# Life-Dash backend

FastAPI backend for Life-Dash — the searchable life database.
Current version and changes: [../CHANGELOG.md](../CHANGELOG.md).

## Layer architecture

- **Raw inbox** (`Fragment`) — immutable, never deleted automatically.
- **Proposals** (`unconfirmed`) — AI-structured, waiting for moderation.
- **Life database** (`confirmed`) — machines never change what is confirmed;
  enrichment (e.g. weather) is strictly additive.
- **Derived** — timeline, map, search, statistics, world, achievements:
  rebuildable at any time, holding no data of their own.

## Multi-user & auth (OIDC)

- All data is user-scoped (`user_id` on every layer); every API query is scoped.
- `AUTH_MODE=dev` (default): no login, a fixed dev user with the admin role — for local development.
- `AUTH_MODE=oidc`: authorization code flow with **PKCE** against any
  standards-compliant OIDC provider (Authentik, Keycloak, Pocket ID, Zitadel, Auth0, …).
  - Create a client at your provider; callback URL: `<PUBLIC_BASE_URL>/api/auth/callback`.
  - A public client is enough (secret optional). Required variables: `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `SESSION_SECRET`, `PUBLIC_BASE_URL` (see `../.env.example`).
  - Users are created on first login (JIT). **The first user becomes admin** and adopts any existing single-user legacy data.
  - `OIDC_PROVIDER_NAME` optionally sets the display name on the login screen.
- API clients may alternatively send an `Authorization: Bearer <token>` from the provider.

## Quick start (local, without Docker)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then:
- **Frontend (PWA):** http://127.0.0.1:8000/ — responsive, installable on a phone
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

On first start in dev mode, demo data is seeded (`SEED_DEMO=true`).

## Docker

```bash
cp .env.example .env   # set OIDC_*, SESSION_SECRET, POSTGRES_PASSWORD
docker compose up -d   # app + PostgreSQL (SQLite: override DATABASE_URL)
```

Full server deployment (GHCR image, reverse proxy, OIDC, data migration):
[../docs/DEPLOY.md](../docs/DEPLOY.md)

## Search

`GET /api/search?q=…` — server-side full-text search across title,
description, place name, and linked item names, scoped to the calling user,
newest first.

Semantic (embedding) search was removed on 2026-07-24: it required an AI
service, loaded every embedded event into the app process, and computed cosine
in pure Python — the only path that did not scale past ~20k events, and it took
the whole response down (500) when the embed service was unavailable. If it ever
returns, it belongs in the database as a layer-4 derivation with a vector index
(pgvector), not in the process (see KONZEPT ch. 15).

## Interface language (F10)

German is the source of truth in `frontend/index.html`; the `I18N_EN` catalog
holds English only. A missing key falls back to the German text, so a lagging
catalog can never produce an empty label. Three ways to mark text:
`data-i18n` (HTML content), `data-i18n-title` / `data-i18n-ph` (attributes),
`t('key', 'German text')` (JavaScript). AI prompts are unaffected — they live
in the backend. The chosen language is also stored on the account and drives
`Accept-Language` for place-name lookups.

## Stack

| Layer | Today | Later (concept) |
|---|---|---|
| DB | SQLite (file) or PostgreSQL | PostgreSQL + PostGIS + pgvector |
| AI | OpenAI-compatible API (any vendor) or mock provider | — |
| Auth | OIDC (any provider) or dev mode | — |
| Geo | lat/lng fields + Nominatim-compatible service | PostGIS |
| Deployment | uvicorn / Docker Compose | Docker Compose |

The models are kept Postgres-compatible; `app/migrate.py` adds new columns to
existing databases (MVP migration, Alembic later).

## Structure

```
app/
  main.py            app setup, migration, seed, frontend mount
  config.py          settings (.env) incl. auth/OIDC
  database.py        engine/session
  migrate.py         mini migration (missing columns, legacy data adoption)
  models.py          SQLAlchemy models (user + all layers)
  schemas.py         Pydantic schemas
  auth.py            OIDC (PKCE, JWKS), session cookies, dependencies
  seed.py            demo data (dev mode)
  ai/                AI providers (mock, OpenAI-compatible, embeddings)
  modules/           module registry (loads YAML)
  data/              static reference data (countries: name -> ISO -> continent)
  services/          ingestion pipeline, geocoding, weather enrichment, achievements
  routers/           API endpoints (auth, ingest, events, search, moderation,
                     modules, tracks, jobs, data, world, achievements, admin)
modules/             YAML module definitions (trip, animal, country, … incl. achievements)
../frontend/         responsive PWA (served by the backend at /)
                     + world-countries.geojson (country shapes for the world map)
```
