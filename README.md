# Life-Dash

Die durchsuchbare persönliche Lebensdatenbank — Erinnerungen, Orte, Reisen,
Konzerte & mehr als responsive PWA mit KI-gestützter Erfassung und Suche.

- **Konzept & Roadmap:** [docs/KONZEPT.md](docs/KONZEPT.md)
- **Backend/Architektur:** [backend/README.md](backend/README.md)
- **Deployment (Homelab):** [docs/DEPLOY.md](docs/DEPLOY.md)

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
ausgeliefert) · OIDC-Login via Pocket ID · KI über jeden OpenAI-kompatiblen
Endpoint (Gemini, Ollama, …) · Releases als Docker-Image via GitHub Actions.
