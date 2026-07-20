# Life-Dash — Deployment

Runbook für ein eigenes Deployment: GHCR-Image → Server mit Docker Compose →
HTTPS über einen Reverse Proxy → Login über deinen OIDC-Provider.

Die genannten Produkte sind **Beispiele, keine Voraussetzung**. Life-Dash
spricht nur Standards: OIDC fürs Login, eine OpenAI-kompatible API für die KI,
Nominatim fürs Geocoding. Womit du die belegst, entscheidest du in der `.env` —
die vollständige Referenz dazu ist [.env.example](../.env.example).

Wer das Image nicht selbst bauen will, überspringt Schritt 1: die offiziellen
Images liegen öffentlich unter `ghcr.io/noxon007/life-dash`.

---

## 1. Eigenes Image bauen (optional)

Nur nötig, wenn du einen Fork betreibst oder eigene Änderungen ausrollst.
Repo auf GitHub anlegen, Code und einen SemVer-Tag pushen:

```bash
git remote add origin https://github.com/<dein-account>/life-dash.git
git push -u origin main
git push origin v0.19.0
```

Der Tag-Push startet die Action **Docker Release**: sie baut das Multi-Arch-Image
(`linux/amd64` + `linux/arm64`) und pusht es als
`ghcr.io/<dein-account>/life-dash:0.19.0`, `:0.19` und `:latest`. Status unter
*Repo → Actions*. Nach dem ersten Lauf prüfen, dass das Package öffentlich ist
(*Profil → Packages → life-dash → Package settings → Visibility*) — dann zieht
der Server es ohne Registry-Login. In der `docker-compose.yml` den `image:`-Pfad
auf deinen Account umstellen.

**Neue Version veröffentlichen** (Versionsschema: [CHANGELOG.md](../CHANGELOG.md)):
committen, CHANGELOG ergänzen, `git tag v0.19.1` (Bugfix) bzw. `v0.20.0`
(Feature), Tag pushen. Auf dem Server dann `LIFEDASH_VERSION` in `.env`
hochsetzen und `docker compose pull && docker compose up -d`.

## 2. OIDC-Client anlegen

Life-Dash funktioniert mit jedem standardkonformen OIDC-Provider — Authentik,
Keycloak, Pocket ID, Zitadel, Auth0 und andere. Dort einen Client anlegen:

| Feld | Wert |
|---|---|
| Name | Life-Dash |
| Callback-URL | `https://life.example.com/api/auth/callback` (= `PUBLIC_BASE_URL` + `/api/auth/callback`) |
| Public Client (PKCE) | ja → `OIDC_CLIENT_SECRET` bleibt leer |

`OIDC_ISSUER` ist die Basis-URL des Providers (dort muss
`/.well-known/openid-configuration` erreichbar sein), `OIDC_CLIENT_ID` die
generierte Client-ID. Mit `OIDC_PROVIDER_NAME` kannst du den Namen deines
Anmeldedienstes auf dem Login-Screen anzeigen lassen; ohne die Variable steht
dort ein neutraler SSO-Hinweis.

Kein OIDC-Provider zur Hand? `AUTH_MODE=dev` startet ohne Login mit einem festen
Admin-Nutzer — nur für lokale Tests, **niemals öffentlich erreichbar betreiben**.

## 2a. Hinweis: ARM64 / Einplatinenrechner

Das Image wird als Multi-Arch-Manifest gebaut (`linux/amd64` + `linux/arm64`) —
`docker compose pull` zieht automatisch die passende Variante, kein Extra-Schritt.

Für FastAPI + SQLite/Postgres reicht ein Einplatinenrechner (z. B. Raspberry Pi 5)
locker, solange die KI über eine externe API läuft und kein LLM lokal rechnet.
Der `db`-Service (offizielles `postgres:18-alpine`) läuft nativ auf ARM64.

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
LIFEDASH_VERSION=0.19.0
PUBLIC_BASE_URL=https://life.example.com
OIDC_ISSUER=https://id.example.com
OIDC_CLIENT_ID=<Client-ID aus deinem OIDC-Provider>
SESSION_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
POSTGRES_PASSWORD=<eigenes DB-Passwort — PostgreSQL ist der Standard>
```

Damit läuft die App bereits — die KI bleibt im Modus `mock` (regelbasiert,
kein Schlüssel nötig). Für echte KI-Analyse zusätzlich einen
OpenAI-kompatiblen Endpoint eintragen, zum Beispiel:

```ini
AI_PROVIDER=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=<dein Schlüssel>
OPENAI_MODEL=gpt-4o-mini
# Optional: semantische Suche
OPENAI_EMBED_MODEL=text-embedding-3-small
```

Andere Anbieter (Gemini, lokales Ollama, LM Studio …) unterscheiden sich nur in
Basis-URL und Modellnamen — Beispiele stehen in [.env.example](../.env.example).
Wer Embeddings nutzt, sollte `SEMANTIC_MIN_SIMILARITY` zum Modell passend
nachziehen; der Standard 0.4 ist für bge-m3 kalibriert.

Start:

```bash
docker compose pull
docker compose up -d
curl -s http://127.0.0.1:8000/health   # -> {"status": ...}
```

## 4. Reverse Proxy einrichten

Life-Dash lauscht auf `LIFEDASH_PORT` (Standard 8000) und erwartet davor einen
Reverse Proxy, der TLS terminiert — Traefik, Caddy, nginx, Pangolin oder was du
sonst betreibst. Nötig ist nur:

- **Ziel:** `http://<server-ip>:8000` (der `LIFEDASH_PORT` aus `.env`).
- **HTTPS** für die öffentliche Domain.
- **Weiterreichen der Proxy-Header** (`X-Forwarded-Proto`, `X-Forwarded-For`):
  Uvicorn läuft mit `--proxy-headers`, damit Scheme und Client-IP stimmen.

Zwei Stolperfallen:

- Die Domain muss **exakt** `PUBLIC_BASE_URL` entsprechen, sonst schlägt der
  OIDC-Callback fehl.
- Falls dein Proxy eine **eigene Authentifizierung** davorschalten kann
  (Traefik ForwardAuth, Authelia, Pangolin-Auth …), schalte sie für diese
  Anwendung **ab**. Life-Dash bringt seinen eigenen OIDC-Login mit; sonst gibt
  es einen Doppel-Login, und die PWA-/API-Aufrufe vom Handy scheitern am
  Auth-Redirect des Proxys.

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
