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

Each exits non-zero on failure, so they can be chained in CI later (package R1).
node tools/check-i18n-containers.js # no translation wipes out a control — note 71
