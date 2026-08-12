# Frontend checks

The frontend is one file of vanilla JS with no build step and no test runner.
These scripts fill that gap for the failure classes that have actually bitten
this project — each one exists because something shipped broken.

Run them from the repository root (needs `npm i jsdom` once, anywhere on the
module path):

```bash
cd tools && npm run check     # all of them, in order
node tools/check-load.js ../frontend/index.html   # or one on its own
```

**The list of guards lives in `package.json`, not here.** This page carried its
own copy until the pre-release review, and by then it named two scripts that no
longer existed (`check-a46-visit-split.js`, `check-photo-layer.js`) and left out
half of the rest — a reader following it got *file not found* for the first and
no hint at all about the other twenty. A second list of the same fact drifts
silently, which is this project's recurring defect rather than brokenness.

**What each guard protects is in its own header**, in the first paragraph, along
with the note or package that paid for it — that is the one place that cannot
fall out of step with the code it checks. `npm run check` is what CI runs, so a
guard that is not in `package.json` is not run at all: adding a file is not
enough, it has to go in that line.

Each exits non-zero on failure. Every one of them was written against the broken
state first — a guard that has never been red is a guard that proves the
function *exists*, not that the caller *uses* it.

**A guard checks a state; make sure it is one that occurs.** `check-a41-cities.js`
asserted the cities tab existed in the markup and passed for a whole release
while the tab was destroyed by `applyModules()` a moment after every real page
load (note 102). It now drives that function first and asserts afterwards.

## Against a running server

All of the above use stubbed responses: they prove what the app *asks for*, not
that it copes with what comes back. `live-check.js` closes that gap and needs a
smoke server (never the real database):

```bash
cd backend
DATABASE_URL="sqlite:///./_smoke.db" AUTH_MODE=dev AI_PROVIDER=mock \
  python -m uvicorn app.main:app --port 8123
node ../tools/live-check.js http://127.0.0.1:8123
```

It asserts the promises of A37 that must hold at any size — no unbounded list
fetch, totals from the server, the map on its own endpoint, no unhandled
errors — so it passes against an empty database and against a large one. It is
deliberately **not** part of `npm run check`, which must run without a server.

## Against an Immich stand-in

`immich_double.py` is a small HTTP server that answers the way the real Immich
does — the DTOs from its OpenAPI spec, `nextPage` as a *string* token, an
`exifInfo` block with and without coordinates, foreign and archived assets mixed
in, and a rejection of timestamps that arrive without a timezone. `smoke_a45.py`
drives the connector against it.

```bash
python tools/immich_double.py &          # from the repository root
python tools/smoke_a45.py
```

This exists because of note 109: unit tests replace `search_assets_paged`
wholesale, so the entire client edge — URL building, headers, paging, timestamp
format, the exif block — is unreachable for them, and that edge is where three
of the five findings in 0.37.0 sat. The double covers paging past the first
page, the ownership and visibility filters, the midnight case from note 111
(`localDateTime` must win over `fileCreatedAt`), the district derivation from
the user's own places, and the four condensation levels over real HTTP.

Rule for every future connector: **run one HTTP double that keeps to the real
DTOs.** Twenty lines, and it reaches what a mock by construction cannot.

## Upgrading an existing database

> **This one is on notice.** R1(f) — a tested upgrade path out of a 0.x database
> — was struck on 2026-08-09, and the tags this script starts from are deleted
> before publication (ROADMAP §5). It defaults to `v0.38.0`; once that tag is
> gone it falls back to a hard-coded commit, and after the cut it needs a commit
> hash passed by hand or it does nothing useful. Kept because `migrate.py` still
> does what it does — but it is no longer part of any gate.

`upgrade-check.sh` is the one check a fresh database cannot give you: it builds
a database with the **previous** release's code, then opens the same file with
the current one and asserts that the new tables and columns arrived, that the
existing rows are untouched, and that the new endpoints answer.

```bash
bash tools/upgrade-check.sh            # from the repository root, defaults to v0.38.0
bash tools/upgrade-check.sh v0.37.0    # or any other starting point
```

It uses a throwaway git worktree and a scratch database, never the real one.
Two things it had to learn the hard way and that apply to any such script:
SQLite runs in **WAL mode**, so copying only the `.db` file copies a stale
state — the `-wal` file has to come along; and the old code **seeds demo data**
into an empty database, so anything counted has to be counted by a targeted
query rather than a total.
