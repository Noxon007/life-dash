# Frontend checks

The frontend is one file of vanilla JS with no build step and no test runner.
These scripts fill that gap for the failure classes that have actually bitten
this project — each one exists because something shipped broken.

Run them from the repository root (needs `npm i jsdom` once, anywhere on the
module path):

```bash
node tools/check-load.js            # page loads without throwing (catches TDZ, see CLAUDE.md)
node tools/check-shadowing.js       # nothing shadows the translation function t() — note 69
node tools/check-weather-summary.js # the weather record counts days, not entries — note 64
node tools/check-jobs-table.js      # the jobs table renders rows — note 69
node tools/check-basemaps.js        # background map selection and its guard rails — F13
```

node tools/check-i18n-containers.js # no translation wipes out a control — note 71
node tools/check-weather-line.js    # slim and full lists render the same weather — A36
node tools/check-a37-window.js      # no view loads the whole database — A37, note 81
node tools/check-a38-mobile.js      # no inline min-width, no max-height in vh — A38
node tools/check-a39-condense.js    # the timeline condenses before it pages — A39
node tools/check-a40-map-controls.js # no map control is silently inoperative — A40
node tools/check-a41-cities.js      # every city number can be opened — A41, note 94
node tools/check-a42-city-page.js   # a city opens a page, not an exit — A42, note 102
node tools/check-a46-visit-split.js # cutting confirmed visits needs a preview first — A46, note 116
node tools/check-photo-layer.js     # the photo layer says what it hides, and doubles nothing — A45
node tools/check-tl-granularity.js  # the condensation level goes to the server — A47
node tools/check-vector-basemap.js  # a vector map never fails silently — A48

Each exits non-zero on failure, so they can be chained in CI later (package R1).
`npm run check` runs all of them — including the last four, which until 0.35.0
had to be remembered by hand and therefore were not run.

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
