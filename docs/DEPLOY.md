# Life-Dash — deployment

Runbook for your own deployment: GHCR image → server with Docker Compose →
HTTPS behind a reverse proxy → sign-in via your OIDC provider.

The products named here are **examples, not requirements**. Life-Dash speaks
standards only: OIDC for sign-in, an OpenAI-compatible API for the AI,
Nominatim for geocoding. What you fill those slots with is decided in your
`.env` — the complete reference for it is [.env.example](../.env.example).

If you do not want to build the image yourself, skip step 1: the official
images are public at `ghcr.io/noxon007/life-dash`.

---

## 1. Build your own image (optional)

Only needed if you run a fork or roll out your own changes. Create a repo on
GitHub, push the code and a SemVer tag:

```bash
git remote add origin https://github.com/<your-account>/life-dash.git
git push -u origin main
git push origin v0.20.0
```

Pushing the tag starts the **Docker Release** action: it builds the multi-arch
image (`linux/amd64` + `linux/arm64`) and pushes it as
`ghcr.io/<your-account>/life-dash:0.20.0`, `:0.20` and `:latest`. Status under
*Repo → Actions*. After the first run, check that the package is public
(*Profile → Packages → life-dash → Package settings → Visibility*) — then your
server pulls it without a registry login. Point the `image:` path in
`docker-compose.yml` at your account.

**Publishing a new version** (versioning scheme: [CHANGELOG.md](../CHANGELOG.md)):
commit, update the CHANGELOG, `git tag v0.20.1` (fix) or `v0.21.0` (feature),
push the tag. On the server, raise `LIFEDASH_VERSION` in `.env` and run
`docker compose pull && docker compose up -d`.

## 2. Sign-in: local accounts or OIDC

Life-Dash has two ways to sign people in. Pick one with `AUTH_MODE`.

### The simple path: `AUTH_MODE=local`

Email and password, no identity provider required. On first visit the app asks
you to create an account — **the first one becomes the administrator**. Further
accounts are created by an admin under Settings → Users; each person can then
change their own password. Passwords are stored hashed with scrypt (a random
salt per password); the plain text is never kept.

This is the least-effort setup — you only need `SESSION_SECRET` and
`PUBLIC_BASE_URL`. Skip the OIDC section entirely.

> Two things to know: the failed-login lockout is per process, so behind
> multiple workers it is a baseline rather than a hard guarantee; and there is
> no “forgot password” flow — an admin sets a new account up if someone is
> locked out of their only admin login, so keep a second admin or your
> `SESSION_SECRET` safe.

### The SSO path: `AUTH_MODE=oidc` — create an OIDC client

Life-Dash works with any standards-compliant OIDC provider — Authentik,
Keycloak, Pocket ID, Zitadel, Auth0 and others. Create a client there:

| Field | Value |
|---|---|
| Name | Life-Dash |
| Callback URL | `https://life.example.com/api/auth/callback` (= `PUBLIC_BASE_URL` + `/api/auth/callback`) |
| Public client (PKCE) | yes → leave `OIDC_CLIENT_SECRET` empty |

`OIDC_ISSUER` is the provider's base URL (`/.well-known/openid-configuration`
must be reachable there), `OIDC_CLIENT_ID` the generated client ID. With
`OIDC_PROVIDER_NAME` you can show the name of your sign-in service on the login
screen; without it, a neutral SSO hint is displayed.

No OIDC provider at hand? `AUTH_MODE=dev` starts without a login using a fixed
admin user — for local tests only, **never run it publicly reachable**.

## 2a. Note: ARM64 / single-board computers

The image is built as a multi-arch manifest (`linux/amd64` + `linux/arm64`) —
`docker compose pull` picks the right variant automatically, no extra step.

A single-board computer (e.g. a Raspberry Pi 5) is plenty for FastAPI +
SQLite/Postgres, as long as the AI runs through an external API and no LLM
computes locally. The `db` service (official `postgres:18-alpine`) runs
natively on ARM64.

## 3. Prepare the server

Docker and the Compose plugin are assumed — the image is public, so no registry
login is needed:

```bash
mkdir -p /opt/life-dash && cd /opt/life-dash
# copy docker-compose.yml and .env.example from the repo here
# (scp from your dev machine or download via the GitHub web UI)
cp .env.example .env
```

Fill in `.env` — the minimum:

```ini
LIFEDASH_VERSION=0.20.0
PUBLIC_BASE_URL=https://life.example.com
OIDC_ISSUER=https://id.example.com
OIDC_CLIENT_ID=<client ID from your OIDC provider>
SESSION_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
POSTGRES_PASSWORD=<your own DB password — PostgreSQL is the default>
```

That is enough to run the app — the AI stays in `mock` mode (rule-based, no key
needed). For real AI analysis, add an OpenAI-compatible endpoint, for example:

```ini
AI_PROVIDER=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=<your key>
OPENAI_MODEL=gpt-4o-mini
# Optional: semantic search
OPENAI_EMBED_MODEL=text-embedding-3-small
```

Other vendors (Gemini, local Ollama, LM Studio …) differ only in base URL and
model name — examples are in [.env.example](../.env.example). If you use
embeddings, retune `SEMANTIC_MIN_SIMILARITY` to your model; the default of 0.4
is calibrated for bge-m3.

Start:

```bash
docker compose pull
docker compose up -d
curl -s http://127.0.0.1:8000/health   # -> {"status": ...}
```

## 4. Set up the reverse proxy

Life-Dash listens on `LIFEDASH_PORT` (8000 by default) and expects a reverse
proxy in front of it terminating TLS — Traefik, Caddy, nginx, Pangolin or
whatever you run. All it needs is:

- **Target:** `http://<server-ip>:8000` (the `LIFEDASH_PORT` from `.env`).
- **HTTPS** for the public domain.
- **Forwarded proxy headers** (`X-Forwarded-Proto`, `X-Forwarded-For`):
  uvicorn runs with `--proxy-headers` so scheme and client IP are correct.

Two pitfalls:

- The domain must match `PUBLIC_BASE_URL` **exactly**, otherwise the OIDC
  callback fails.
- If your proxy can put its **own authentication** in front (Traefik
  ForwardAuth, Authelia, Pangolin auth …), turn it **off** for this
  application. Life-Dash brings its own OIDC login; otherwise you get a double
  login, and PWA/API calls from a phone fail on the proxy's auth redirect.

## 5. First login & migrating data

- **The first OIDC login becomes admin** and adopts existing single-user legacy
  data (`app/migrate.py`) — so log in yourself before inviting other users.
- Moving existing data from a dev machine (export/import, JSON):
  1. Locally (AUTH_MODE=dev): in the frontend **Settings → Export** or
     `GET /api/data/export` → save the JSON file.
  2. Log in on the server and load the file via **Settings → Import** or
     `POST /api/data/import`.

## 6. Database: PostgreSQL (default) & migrating from SQLite

**PostgreSQL is the default** — `docker compose up -d` starts app + DB, and the
schema is created automatically on first start. Setting `POSTGRES_PASSWORD` in
`.env` is enough; Compose builds the `DATABASE_URL` from it.

**All data lives in folders next to `docker-compose.yml`** (bind mounts, not
Docker volumes): `./db` is the PostgreSQL data directory, `./data` holds app
data (the SQLite DB in a minimal setup). The folders appear on first start;
`./db` then belongs to the container user (uid 70) — read and back it up with
`sudo`.

**Migrating an existing SQLite installation** (no dump conversion, via the JSON
export):

1. Before updating: log in and take a JSON export (**Settings → Export**).
2. In `.env`: set `POSTGRES_PASSWORD` and **remove** any
   `DATABASE_URL=sqlite:...` line (otherwise SQLite stays active).
3. `docker compose pull && docker compose up -d` — Postgres starts, the schema
   is created, the app waits for the DB health check.
4. Log in (first login into the empty DB = admin) and import the JSON export.
   The old SQLite DB (`./data/lifedash.db`, or the earlier Docker volume
   `lifedash-data`) stays as a fallback until you delete it.

**Keep using SQLite** (minimal setup): leave
`DATABASE_URL=sqlite:////data/lifedash.db` in `.env` and start only the app
with `docker compose up -d --no-deps app`.

**Upgrading from an older setup** (postgres:16 and/or Docker volumes instead of
folders): Postgres data directories are not compatible across major versions,
and from image version 18 the mount points at `/var/lib/postgresql` instead of
`.../data`. The simple path goes through the JSON export:

1. Log in, take a JSON export (**Settings → Export**).
2. `docker compose down` and remove the old state: the earlier Docker volume
   with `docker volume rm life-dash_lifedash-pg` (or an existing `./db` folder
   with `sudo rm -rf ./db`).
3. Deploy the updated `docker-compose.yml`, run `docker compose up -d` —
   Postgres 18 starts with an empty DB in the new `./db` folder and the schema
   is created.
4. Log in (first login = admin) and import the JSON export.

## 7. Operations

```bash
docker compose logs -f app        # logs
docker compose ps                 # health status (the container has a HEALTHCHECK)
docker compose pull && docker compose up -d   # update to a new tag
```

### Backup

**Two things have to be saved, not one.**

1. **The database** — the folders `./db` (PostgreSQL, with `sudo`, owned by
   uid 70) or `./data` (SQLite) next to the Compose file. Cleaner than the raw
   folder is a dump:
   `docker compose exec db pg_dump -U lifedash lifedash > backup.sql`.
2. **The media folder** (`MEDIA_DIR`, `./media` by default) — every photo you
   uploaded lives there and **nowhere else**.

**Or take one archive instead of both.** Since v0.26.0 the app can export a
**ZIP containing the data *and* the image files** (Settings → My data →
Export, with “with photos” ticked). Importing that archive restores both,
including previews, and can be repeated without creating duplicates. That is
the simplest complete backup, and the one to use if you only want to remember
one thing.

> ⚠️ **The plain JSON export is still not a full backup.** It carries
> everything the database holds, including the details of every uploaded
> picture — but not the image files. Restoring only from JSON gives you
> entries whose photos are gone. The export says so in its own `media_note`
> field. It remains the right choice if you back up `MEDIA_DIR` by other
> means: it is small, readable and diffable.

Uploaded photos are **primary data**: unlike weather or place names, nothing
can recompute them. Treat `MEDIA_DIR` with the same care as the database.
