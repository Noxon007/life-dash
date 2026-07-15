# Life-Dash

Die durchsuchbare persönliche Lebensdatenbank — Erinnerungen, Orte, Reisen,
Konzerte & mehr als responsive PWA mit KI-gestützter Erfassung und Suche.

- **Konzept & Roadmap:** [docs/KONZEPT.md](docs/KONZEPT.md)
- **Backend/Architektur:** [backend/README.md](backend/README.md)
- **Deployment (Homelab):** [docs/DEPLOY.md](docs/DEPLOY.md)
- **Änderungen pro Version:** [CHANGELOG.md](CHANGELOG.md)

## Schnellstart

```bash
cp .env.example .env      # OIDC_ISSUER, OIDC_CLIENT_ID, SESSION_SECRET setzen
docker compose up -d      # Image: ghcr.io/noxon007/life-dash
```

Frontend/PWA: `http://<host>:8000/` · API-Docs: `/docs` · Health: `/health`

Lokale Entwicklung ohne Docker: siehe [backend/README.md](backend/README.md)
(`AUTH_MODE=dev`, uvicorn mit Reload).

## Stack

FastAPI + SQLAlchemy (SQLite oder PostgreSQL) · Vanilla-JS-PWA (vom Backend
ausgeliefert) · OIDC-Login via Pocket ID · KI über die Gemini API
(OpenAI-kompatibler Endpoint) · Releases als Docker-Image via GitHub Actions.

## Versionierung & Releases

[Semantic Versioning](https://semver.org/lang/de/) (`MAJOR.MINOR.PATCH`).
Während der `0.x`-Phase: Features → `MINOR`, Fixes → `PATCH`. Ein Release ist
ein Git-Tag `vX.Y.Z`; der Workflow baut daraus das Image mit den Tags
`X.Y.Z` (exakt), `X.Y` (mitlaufend) und `latest`. Auf dem Server auf eine
konkrete Version pinnen (`LIFEDASH_VERSION`), nicht `latest`. Änderungen werden
in [CHANGELOG.md](CHANGELOG.md) gepflegt.
