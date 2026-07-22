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

Each exits non-zero on failure, so they can be chained in CI later (package R1).
`npm run check` runs all of them.

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
