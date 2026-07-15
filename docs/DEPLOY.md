# Life-Dash — Deployment ins Homelab (D1)

Runbook für das erste echte Deployment: GitHub-Repo → GHCR-Image → Server mit
Docker Compose, HTTPS via **Pangolin (Traefik)**, Login via **Pocket ID**.

---

## 1. GitHub-Repo anlegen & v0.1 pushen (Windows-Dev-Rechner)

Auf github.com ein **öffentliches** Repo `life-dash` unter `Noxon007` anlegen
(ohne README/License, das Repo ist schon initialisiert). Dann:

```powershell
cd d:\Python\life-dash
git remote add origin https://github.com/Noxon007/life-dash.git
git push -u origin main
git push origin v0.1
```

Der Tag-Push startet die Action **Docker Release**: sie baut das Image und
pusht es als `ghcr.io/noxon007/life-dash:v0.1` und `:latest`. Status unter
*Repo → Actions*. Nach dem ersten Lauf einmal prüfen, dass das Package
öffentlich ist (*Profil → Packages → life-dash → Package settings →
Visibility*) — dann zieht der Server es ohne Login.

**Neue Version veröffentlichen:** committen, `git tag v0.2`, beide pushen —
auf dem Server dann `LIFEDASH_VERSION=v0.2` in `.env` setzen und
`docker compose pull && docker compose up -d`.

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
kein Extra-Schritt nötig. Zwei Punkte trotzdem beachten:

- **`--profile ai` (lokales Ollama) nicht auf dem Pi nutzen.** Ohne GPU ist
  Inferenz für ein 12B-Modell (`gemma3:12b`) auf einem Pi 5 unbrauchbar
  langsam. Stattdessen `OPENAI_BASE_URL` entweder auf die Gemini API oder auf
  einen bestehenden Ollama-Host im Netzwerk (z. B. die RTX-5070-Ti-Maschine)
  zeigen lassen — der Pi ist dann nur der leichte App-Server, die KI läuft
  woanders.
- **`--profile postgres`** (offizielles `postgres:16-alpine`) läuft nativ auf
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
LIFEDASH_VERSION=v0.1
PUBLIC_BASE_URL=https://life.example.com
OIDC_ISSUER=https://id.example.com
OIDC_CLIENT_ID=<aus Pocket ID>
SESSION_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
AI_PROVIDER=openai            # oder mock zum reinen Ausprobieren
OPENAI_BASE_URL=...           # Gemini oder Ollama, siehe .env.example
```

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

## 6. Optional: PostgreSQL statt SQLite

SQLite (Default) reicht für den Start. Umstieg später ohne Dump-Konvertierung
über denselben Export/Import-Weg:

1. JSON-Export ziehen (wie oben).
2. In `.env`:
   ```ini
   DATABASE_URL=postgresql+psycopg2://lifedash:<passwort>@db:5432/lifedash
   POSTGRES_PASSWORD=<passwort>
   ```
3. `docker compose --profile postgres up -d` — Schema wird beim Start angelegt.
4. Einloggen (wieder: erster Login = Admin) und JSON importieren.

## 7. Betrieb

```bash
docker compose logs -f app        # Logs
docker compose ps                 # Health-Status (Container hat HEALTHCHECK)
docker compose pull && docker compose up -d   # Update auf neuen Tag
```

Backup-Minimum: das Volume `lifedash-data` (SQLite-DB) bzw. `lifedash-pg`
sichern — oder regelmäßig den JSON-Export ziehen, der ist vollständig und
versionsunabhängig.
