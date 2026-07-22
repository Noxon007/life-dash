# Life-Dash

Your searchable personal life database — memories, places, trips, concerts and
more, as a responsive PWA with AI-assisted capture and search.

- **Concept & roadmap:** [docs/KONZEPT.md](docs/KONZEPT.md)
- **Backend/architecture:** [backend/README.md](backend/README.md)
- **Deployment:** [docs/DEPLOY.md](docs/DEPLOY.md)
- **All settings:** [.env.example](.env.example)
- **Changes per version:** [CHANGELOG.md](CHANGELOG.md)

## Quick start

```bash
cp .env.example .env      # set OIDC_*, SESSION_SECRET, POSTGRES_PASSWORD
docker compose up -d      # app + PostgreSQL; image: ghcr.io/noxon007/life-dash
```

Frontend/PWA: `http://<host>:8000/` · API docs: `/docs` · Health: `/health`

Without an AI key the app runs in `mock` mode (rule-based capture) — that is
enough to try it out. Local development without Docker: see
[backend/README.md](backend/README.md) (`AUTH_MODE=dev`, uvicorn with reload).

The interface speaks **English and German**; a switch in the top bar changes
the language at any time (it follows your browser on first visit).

## How this was built

The entire implementation was written by Anthropic's Claude models — **Fable and
Opus** — from [docs/KONZEPT.md](docs/KONZEPT.md), with the author directing the
work, deciding the architecture, reviewing the result and running it daily. This
is stated up front rather than buried: if you are going to host a database of
your own life, you should know how the software was made.

This is currently a single-author project. Issues and questions are welcome;
pull requests are not being accepted yet.

## Stack

FastAPI + SQLAlchemy (SQLite or PostgreSQL) · vanilla-JS PWA (served by the
backend) · releases as a Docker image via GitHub Actions.

Life-Dash ties you to no vendor: sign-in works with **any standards-compliant
OIDC provider** (Authentik, Keycloak, Pocket ID, Zitadel …), the AI with **any
OpenAI-compatible API** (OpenAI, Gemini, locally via Ollama or LM Studio …) and
place lookup with **Nominatim or a compatible service**. What you use is
decided by your `.env` alone.

## Versioning & releases

[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`). During the
`0.x` phase: features → `MINOR`, fixes → `PATCH`. Changes are tracked in
[CHANGELOG.md](CHANGELOG.md).

Building and releasing are separate on purpose:

- **`:main`** — built from every push to the main branch. The current
  development state, for trying things out. No guarantees.
- **`vX.Y.Z`** — a git tag, and only that, is a release. It builds the image
  tags `X.Y.Z` (exact), `X.Y` (rolling within the minor) and `latest`.

On a server, pin a concrete version (`LIFEDASH_VERSION`) rather than `latest`,
and never run `:main` against data you care about. `GET /health` reports both
the declared version and the commit the image was built from.

## Documentation language

Documentation is maintained in **English**. Discussion and input may of course
happen in any language — translation happens when writing things down.

## License

Life-Dash is free software under the
**[GNU Affero General Public License v3.0](LICENSE)** (AGPL-3.0-or-later).
You may use, modify and redistribute Life-Dash — including as a hosted
service — as long as changes are published under the same license (the AGPL's
network copyleft explicitly covers SaaS operation). Details: [LICENSE](LICENSE).
