# Contributing

Thank you for looking. Please read the next two paragraphs before you write
code — they will save you an evening.

## This is a single-author project, and pull requests are not being accepted

Not “not yet”, and not a comment on your work. Life-Dash is written and
maintained by one person, and every part of it is accompanied by a written
reason in [`docs/internal/DECISIONS.md`](docs/internal/DECISIONS.md) — over two
hundred numbered notes recording what was found, what was decided, and what was
deliberately *not* built. Reviewing a change means checking it against that
record, and doing it properly takes longer than writing the change did. A
maintainer who merges faster than they can review is producing a codebase they
no longer understand.

So: **pull requests will be closed, politely and without review.** If you have
found something, an issue is worth far more to this project than a patch.

## What is genuinely useful

**Bug reports.** Especially the quiet kind. The recurring defect in this project
is not breakage but *silence* — a number that is wrong by a whole year, a run
that reports success for work it skipped, a view that cannot show everything and
does not say so. If something looks slightly off and you cannot prove it, say so
anyway; several of the notes in the decisions log started exactly like that.

**Security reports** go through [`SECURITY.md`](SECURITY.md), privately, never
as a public issue.

**Questions and ideas** belong in
[Discussions](https://github.com/Noxon007/life-dash/discussions), not in issues.
An idea is not a defect, and mixing the two makes the issue list unreadable —
the list is meant to answer “what is broken?” at a glance.

**Forks are welcome and always will be.** The licence is AGPL-3.0-or-later; take
it wherever you like, as long as the people you serve it to can get the source.

## What this project deliberately does not do

Asking for these is fine — but the answer is written down, so you know it before
you ask:

- **No multi-user social layer.** Accounts exist so that a household can run one
  instance; they are not a network. A shared view between two accounts is
  planned, read through a revocable share and never copied.
- **No cloud service, no hosted version, no account on anyone's server.** The
  entire premise is that this data lives on hardware you control.
- **No mobile app.** It is a PWA: installable, offline-capable, one codebase.
- **No tracking, no telemetry, no analytics, no crash reporting.** The app makes
  no request you did not configure. Everything it talks to — AI endpoint,
  geocoder, weather, Immich, map tiles — is named by you in `.env` or the
  settings, and none of it is preset to a vendor.
- **No “AI assistant” that rewrites your entries.** Machines propose; you
  confirm. Confirmed records are never changed by a machine, and enrichment such
  as weather is only ever *additive*. That rule is the spine of the data model,
  not a preference.
- **No competing with dedicated location trackers.** Dawarich, Reitti and the
  rest are far ahead on that one job. The plan is to *read their exports*, not
  to replace them.
- **No plugin system.** New sources are code, with tests, in this repository.
  A plugin API is a promise about internals that are still moving.
- **No build step in the frontend.** It is one HTML file with vanilla JS, and
  that is deliberate: it can be read, and it can be served.

## If you are here to run it, not to change it

- Deployment: [`docs/DEPLOY.md`](docs/DEPLOY.md)
- Every setting: [`.env.example`](.env.example)
- What changed: [`CHANGELOG.md`](CHANGELOG.md)
- Why it is built this way: [`docs/internal/DECISIONS.md`](docs/internal/DECISIONS.md)

## If you fork it anyway (and you should feel free)

The things worth knowing before you touch anything:

- Tests: `cd backend && python -m pytest tests -q` (offline; mock AI, geocoding
  off). Against real PostgreSQL: `pwsh tools/pg-test.ps1`.
- Frontend guards: `cd tools && npm run check` — jsdom checks for the failure
  classes that have actually shipped broken here.
- **Run every new check once against the broken state.** A guard that has never
  been red is a guard that proves a function *exists*, not that anyone calls it.
  That rule has caught more in this repository than any single test.
