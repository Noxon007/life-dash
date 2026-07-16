# Life-Dash — Deployment ins Homelab (D1)

Runbook für das erste echte Deployment: GitHub-Repo → GHCR-Image → Server mit
Docker Compose, HTTPS via **Pangolin (Traefik)**, Login via **Pocket ID**.

---

## 1. GitHub-Repo & Release pushen (Windows-Dev-Rechner)

Auf github.com ein **öffentliches** Repo `life-dash` unter `Noxon007` anlegen
(ohne README/License, das Repo ist schon initialisiert). Dann Code und den
SemVer-Release-Tag pushen:

```powershell
cd d:\Python\life-dash
git remote add origin https://github.com/Noxon007/life-dash.git
git push -u origin main
git push origin v0.5.0
```

Der Tag-Push startet die Action **Docker Release**: sie baut das Multi-Arch-Image
und pusht es als `ghcr.io/noxon007/life-dash:0.5.0`, `:0.5` und `:latest`. Status
unter *Repo → Actions*. Nach dem ersten Lauf einmal prüfen, dass das Package
öffentlich ist (*Profil → Packages → life-dash → Package settings →
Visibility*) — dann zieht der Server es ohne Login.

**Neue Version veröffentlichen** (Versionsschema: [CHANGELOG.md](../CHANGELOG.md)):
committen, CHANGELOG ergänzen, `git tag v0.5.1` (Bugfix) bzw. `v0.6.0`
(Feature), Tag pushen. Auf dem Server dann `LIFEDASH_VERSION` in `.env`
hochsetzen und `docker compose pull && docker compose up -d`.

## 2. Pocket ID: OIDC-Client anlegen

In Pocket ID (läuft bereits) einen neuen OIDC-Client anlegen:

| Feld | Wert |
|---|---|
| Name | Life-Dash |
| Callback-URL | `https://life.example.com/api/auth/callback` (= `PUBLIC_BASE_URL` + `/api/auth/callback`) |
| Public Client (PKCE) | ja → `OIDC_CLIENT_SECRET` bleibt leer |

`OIDC_ISSUER` ist die Basis-URL von Pocket ID, `OIDC_CLIENT_ID` die generierte Client-ID.

## 2a. Hinweis: Raspberry Pi / ARM64

Das Image wird als Multi-Arch-Manifest gebaut (`linux/amd64` + `linux/arm64`) —
`docker compose pull` zieht auf einem Pi 5 automatisch die passende Variante,
kein Extra-Schritt nötig.

Die KI läuft ohnehin über die **Gemini API** (kein LLM-Dienst im Stack), der Pi
ist also nur der leichte App-Server — für FastAPI + SQLite/Postgres reicht er
locker. Der `db`-Service (offizielles `postgres:18-alpine`) läuft nativ auf
ARM64, keine Einschränkung.

## 3. Server vorbereiten

Docker + Compose-Plugin vorausgesetzt — das Image ist öffentlich, ein
Registry-Login ist nicht nötig:

```bash
mkdir -p /opt/life-dash && cd /opt/life-dash
# docker-compose.yml und .env.example aus dem Repo hierher kopieren
# (scp vom Dev-Rechner oder Download über die GitHub-Weboberfläche)
cp .env.example .env
```

`.env` ausfüllen — Minimum:

```ini
LIFEDASH_VERSION=0.6.0
PUBLIC_BASE_URL=https://life.example.com
OIDC_ISSUER=https://id.example.com
OIDC_CLIENT_ID=<aus Pocket ID>
SESSION_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
POSTGRES_PASSWORD=<eigenes DB-Passwort — PostgreSQL ist der Standard>
# KI über Gemini (Standardweg) — Key von https://aistudio.google.com/apikey:
AI_PROVIDER=openai
OPENAI_API_KEY=<Gemini-Key>
# AI_PROVIDER=mock lässt die KI weg (kein Key nötig) — für einen ersten Smoke-Test.
```

Die übrigen Gemini-Defaults (Base-URL, Modell, Embeddings) sind in
`.env.example` bereits gesetzt und müssen nur bei Abweichung angepasst werden.

Start:

```bash
docker compose pull
docker compose up -d
curl -s http://127.0.0.1:8000/health   # -> {"status": ...}
```

## 4. Pangolin: Resource anlegen

In Pangolin eine neue **Resource** für die gewünschte Domain
(z. B. `life.example.com`) anlegen:

- **Ziel:** `http://<server-ip-oder-newt-site>:8000` (der `LIFEDASH_PORT` aus `.env`).
- **HTTPS:** übernimmt Pangolin/Traefik automatisch.
- **Pangolin-eigene Authentifizierung für diese Resource deaktivieren** —
  Life-Dash hat den eigenen Pocket-ID-Login; sonst gibt es einen Doppel-Login
  und die PWA-/API-Aufrufe vom Handy scheitern am Pangolin-Auth-Redirect.

Die Domain muss exakt `PUBLIC_BASE_URL` entsprechen, sonst schlägt der
OIDC-Callback fehl. Uvicorn läuft mit `--proxy-headers`, damit hinter Traefik
Scheme/Client-IP stimmen.

## 5. Erster Login & Datenübernahme

- **Der erste OIDC-Login wird Admin** und adoptiert vorhandene
  Single-User-Altdaten (`app/migrate.py`) — also zuerst selbst einloggen,
  bevor andere Nutzer eingeladen werden.
- Bestandsdaten vom Dev-Rechner umziehen (Export/Import, JSON):
  1. Lokal (AUTH_MODE=dev): im Frontend **Einstellungen → Export** oder
     `GET /api/data/export` → JSON-Datei sichern.
  2. Auf dem Server einloggen und die Datei über **Einstellungen → Import**
     bzw. `POST /api/data/import` einspielen.

## 6. Datenbank: PostgreSQL (Standard) & Migration von SQLite

**PostgreSQL ist der Standard** — `docker compose up -d` startet App + DB,
das Schema wird beim ersten Start automatisch angelegt. Es genügt,
`POSTGRES_PASSWORD` in `.env` zu setzen; die `DATABASE_URL` baut die Compose
daraus selbst.

**Alle Daten liegen als Ordner neben der `docker-compose.yml`** (Bind-Mounts,
keine Docker-Volumes): `./db` ist das PostgreSQL-Datenverzeichnis, `./data`
sind die App-Daten (SQLite-DB beim Minimal-Setup). Die Ordner entstehen beim
ersten Start automatisch; `./db` gehört danach dem Container-User (uid 70) —
Lesen/Sichern also mit `sudo`.

**Bestehende SQLite-Installation migrieren** (ohne Dump-Konvertierung, über
den JSON-Export):

1. Vor dem Update: einloggen und JSON-Export ziehen (**Einstellungen → Export**).
2. In `.env`: `POSTGRES_PASSWORD` setzen und eine eventuell vorhandene
   `DATABASE_URL=sqlite:...`-Zeile **entfernen** (sonst bleibt SQLite aktiv).
3. `docker compose pull && docker compose up -d` — Postgres startet, Schema
   wird angelegt, die App wartet auf den DB-Healthcheck.
4. Einloggen (erster Login in der leeren DB = Admin) und den JSON-Export
   importieren. Die alte SQLite-DB (`./data/lifedash.db` bzw. das frühere
   Docker-Volume `lifedash-data`) bleibt als Rückfall erhalten, bis du sie
   löschst.

**SQLite weiterhin nutzen** (Minimal-Setup): `DATABASE_URL=sqlite:////data/lifedash.db`
in `.env` lassen und mit `docker compose up -d --no-deps app` nur die App starten.

**Upgrade von einem älteren Setup** (postgres:16 und/oder Docker-Volumes
statt Ordner): Postgres-Datenverzeichnisse sind nicht major-versions-
kompatibel, und ab Image-Version 18 zeigt der Mount auf `/var/lib/postgresql`
statt `.../data`. Der einfache Weg läuft über den JSON-Export:

1. Einloggen, JSON-Export ziehen (**Einstellungen → Export**).
2. `docker compose down` und Altbestand entfernen: früheres Docker-Volume
   mit `docker volume rm life-dash_lifedash-pg` (bzw. einen schon
   vorhandenen `./db`-Ordner mit `sudo rm -rf ./db`).
3. Aktualisierte `docker-compose.yml` deployen, `docker compose up -d` —
   Postgres 18 startet mit leerer DB im neuen Ordner `./db`, Schema wird
   angelegt.
4. Einloggen (erster Login = Admin) und den JSON-Export importieren.

## 7. Betrieb

```bash
docker compose logs -f app        # Logs
docker compose ps                 # Health-Status (Container hat HEALTHCHECK)
docker compose pull && docker compose up -d   # Update auf neuen Tag
```

Backup-Minimum: die Ordner `./db` (PostgreSQL, mit `sudo` — gehört uid 70)
bzw. `./data` (SQLite) neben der Compose-Datei sichern — oder regelmäßig den
JSON-Export ziehen, der ist vollständig und versionsunabhängig. Sauberer ist
ein Dump statt des rohen Ordners:
`docker compose exec db pg_dump -U lifedash lifedash > backup.sql`.
