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

## Getting started — a sensible order

A fresh instance is empty, and it fills up from several directions that build on
each other. This is the order that works; it is also the order of the sections
under **Admin → My data**, so you can simply work down the page. None of it is
mandatory, and every run can be repeated as often as you like — each one only
fills in what is missing.

**First, write one thing down.** Type a sentence into *Capture* (“12 July 2026,
Detmold, saw an eagle”) and confirm the proposal in *Admin → Moderation*. That
is the whole pipeline in thirty seconds — raw text → AI proposal → your
confirmed record — and it makes the imports below much easier to judge.

1. **Pick your modules** (*What do you track?*). They decide which categories,
   filters and statistics exist, and what the AI is asked to look for.
   Unticking one hides it; nothing is deleted.
2. **Import your Google timeline.** This is the big one: years of visits become
   entries and movements become routes, and everything after this step feeds on
   the dates and coordinates it brings. Export from the phone (Android:
   *Settings → Location → Location services → Timeline → Export timeline data*);
   old Takeout exports work too. Importing twice creates no duplicates. Stays
   from before 0.39 that crossed midnight became two-day entries — the button
   right below the import cuts them into days, and says beforehand how many
   entries become how many rows.
3. **Resolve place names.** Imported visits arrive as `Place (53.49, 10.00)`.
   The run turns them into addresses via OpenStreetMap, and it is deliberately
   throttled — start it early, let it work in the background. Manually renamed
   places are never touched.
4. **Connect Immich**, if you have it. Four things, in this order: *test the
   connection*, then **propose entries from photos** (one year at a time, with a
   mandatory preview) and confirm what you want in *Moderation*, then **link
   photos**, which attaches pictures to the entries that now exist, and finally
   **locate photos** — that one puts every geotagged picture on the map as its
   own point and creates no entries at all. Photos stay in Immich; Life-Dash
   stores references, and the API key it needs is read-only.

   Albums are *not* proposed automatically. An album would become one multi-day
   entry with a single point on the map, and the twin of the trip you enter
   yourself — better the other way round: you create the trip, and the photos
   attach themselves to it. If you want to look at your albums anyway, there is
   a tick box next to the run.
5. **Split multi-day entries into days**, if trips and albums have produced
   them. Each day becomes its own entry, so each day can carry its own weather
   and its own photos.
6. **Add weather.** Last on purpose: it asks an archive (Open-Meteo) about each
   located, dated entry exactly once and keeps the answer forever, so it pays
   off most when the entries above already exist. It only ever adds — nothing
   you confirmed is overwritten.
7. **Take a backup** (*Backup & restore*, with photos = a ZIP). Do this once the
   instance holds something you would miss.

Steps 3, 4 and 6 also run unattended: the **Jobs** tab has a nightly schedule
per run type, which is the sensible setting once the first pass is done.

Once there is something to look at, two switches are worth knowing. On the map
and in the timeline, **📷 Photos** turns the located pictures on — off by
default, because twenty years of library is tens of thousands of markers. And
the timeline's **Condense by** picker decides how coarsely a day is summarised:
country, city, district, or every entry on its own.

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
