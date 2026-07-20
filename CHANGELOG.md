# Changelog

All notable changes to Life-Dash. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning follows
[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

While the version stays at `0.x`, the app counts as in development: new
features raise `MINOR`, bug fixes raise `PATCH`; breaking changes can occur in
any `MINOR`.

> This changelog is maintained in **English** from version 0.20.0 on. Earlier
> entries were translated once at that point; entries before 0.12.0 were
> additionally condensed, since they describe development history in internal
> package codes (see note 39 in the concept document).

## [Unreleased]

## [0.25.0] – 2026-07-20

### Added
- **🖼️ Immich photos next to your entries:** enter your Immich address and an
  API key under Settings → My data, press “link photos”, and Life-Dash finds
  the pictures that belong to each entry — by capture time, and by place when
  both sides know where they were. They appear alongside the photos you
  uploaded yourself and open in the same viewer.
- **Nothing is copied.** The pictures stay in Immich; Life-Dash only remembers
  which one belongs to which entry and passes previews through. Your API key
  stays on the server and is never sent back to the browser — the settings
  page only shows *whether* a key is stored.
- **A connection test**, so a typo in the address or key tells you immediately
  instead of turning into a run that mysteriously finds nothing.
- **“Discard links”** throws the associations away so the next run can rebuild
  them. Your pictures in Immich and the photos you uploaded yourself are never
  affected — only the machine-made connections are.
- The linking run works like the other background jobs: it survives a closed
  browser, can be stopped, and can be scheduled nightly.

### Notes
- Entries with a **vague date** (month, season, year, decade) are deliberately
  skipped. “Summer 2002” would collect photos at random, and a wrong picture on
  an entry is worse than no picture at all.
- At most 12 pictures are linked per entry — a holiday can hold three hundred,
  and those belong in Immich, not as a wall of tiles in your timeline.
- Photo clusters and albums becoming **entry suggestions** is the second half
  of this feature and is not in this release yet.

## [0.24.0] – 2026-07-20

### Added
- **📷 Photos, at last:** attach pictures to any entry — drag them onto the
  edit dialog, pick them from a file browser, or take one with the camera on a
  phone. Several per entry, each with its own caption. They appear on the
  timeline card, open in a full-screen viewer (arrow keys and swipe work), and
  need **no external service**: the files live on your own server.
- **The photo's own date and place are offered to you:** if a picture carries
  capture time or GPS coordinates, Life-Dash reads them and *asks* whether to
  use them. It never rewrites an entry on its own — that decision stays yours.
- **Printing with photos** — the missing half of the print view. Pick a range,
  tick “print photos”, and the pictures appear under their entries with their
  captions. Printing uses the small preview version, so the dialog does not
  choke on a page of full-resolution images.

### Changed
- **Uploaded pictures are protected like confirmed data.** Everything Life-Dash
  computes — weather, place names, embeddings — can be thrown away and rebuilt.
  A photo you uploaded cannot: it exists nowhere else. Recomputing your entries
  therefore never discards an entry that carries one, and no cleanup job
  touches the files. They disappear only when you delete the picture, the
  entry, or the account — and then the files really are removed, rather than
  being left behind on disk.
- **The export now tells you what it cannot carry.** A JSON export holds the
  details of every picture but not the image files. It says so in its own
  `media_note` field, the app repeats it where you upload, and
  [DEPLOY.md](docs/DEPLOY.md) now describes backup as two things to save, not
  one. A single archive containing both is coming (see the concept, A29).

### Fixed
- Picture records had no owner of their own — they were only reachable through
  their entry. That was harmless while nothing could be uploaded and is now
  closed properly, so no request can reach another account's pictures.

### Notes for self-hosters
- New setting **`MEDIA_DIR`** (default `/data/media` in Docker) with its own
  volume in `docker-compose.yml`. **Back it up separately from the database.**
  Also new: `MEDIA_MAX_MB` (default 25) and `MEDIA_THUMB_PX` (default 640).
- Two new Python dependencies: **Pillow** (image handling, previews, EXIF) and
  **python-multipart** (file uploads). `pip install -r requirements.txt` after
  updating, or just pull the new image.
- Accepted formats are JPEG, PNG, WebP and GIF. SVG is deliberately refused —
  it can contain scripts. Files are identified by opening them, not by
  trusting their name or what the browser claims.

## [0.23.0] – 2026-07-20

### Added
- **🌦️ Your weather record:** a new block in the statistics adds up what the
  weather already attached to your entries actually says — days carrying
  weather, total hours of sunshine, how many of your days were rainy, and your
  warmest trip. Plus a “rainy days per year” chart. **None of this needs a
  single new lookup:** the data has been sitting there since v0.14, and until
  now exactly one panel read it.
- **Six weather achievements:** sun worshipper, sunshine collector, bad-weather
  defier, frostbite, heat seeker and storm-hardened — in the familiar four
  tiers, computed from the weather already stored. They live in their own
  “Weather” module, so you can switch them off like any other module if that
  is not your thing.
- **Average temperature per country** in the world tab — visible in the map
  popup and on the country chips in the checklist.
- **More weather per day:** entries enriched from now on also record the
  **feels-like temperature**, **how long it rained** (not just how much),
  **sunrise, sunset and length of day**, plus **wind gusts** and the **UV
  index**. Five degrees with wind is a different memory from five degrees
  without, and on a trip to the far north the length of the day is half the
  story. The event line shows the feels-like value only when it differs
  noticeably from the thermometer — otherwise it would just repeat the number.
- Existing entries are **topped up additively** on the next weather run:
  nothing already stored is overwritten or recomputed.

### Fixed
- **Weather enrichment could have re-fetched the same day forever.** Life-Dash
  decided whether an entry still needed weather by checking which values were
  present — but a weather service does not return every value for every place
  and date (the UV index is missing from older archive years, for instance).
  Such an entry would have been queried again on every single run. Entries now
  record which generation of weather data they carry, so each one is fetched
  once and only once, whatever comes back.

## [0.22.0] – 2026-07-20

### Added
- **🗺️ Choose your background map:** every map — timeline, collection and
  world — now has a small selector in the top right. Besides the familiar
  style that follows the light/dark theme there are **OpenStreetMap**,
  **OpenTopoMap** for contour lines on hikes, and **satellite imagery**, which
  is what a holiday map usually wants. The choice applies to all maps at once
  and is kept per device, so the phone can show something different from the
  desktop.
- **Your own map source:** if you run your own tile server, or use a provider
  that needs a key, enter its address under Settings → Background map. It then
  appears in the selector like the built-in ones. There is a field for the
  attribution next to it — nearly every tile provider requires that notice in
  its terms of use, so Life-Dash shows it on the map.

### Changed
- Picking a map deliberately **overrides** the light/dark automation: if you
  chose satellite, switching the theme no longer throws you back to the
  street map. Only the “matching the theme” option keeps following it.

## [0.21.0] – 2026-07-20

### Added
- **🕰️ “On this day”:** the timeline now opens with a look-back — what
  happened on this calendar day one, five or twenty years ago, shown above
  today's entries. Multi-day trips count too: if you were in Mallorca on this
  day five years ago, the trip shows up even though it began a week earlier.
  The block appears only when there is actually something to show, stays out
  of the way while you search or filter, and can be dismissed for good with
  the ✕ (per device). Entries whose date is only known to the month or year
  are deliberately left out — “on this day” would be claiming a precision the
  data does not have.

### Changed
- **Resolving place names is one run again:** the drop-down asking whether to
  fix missing names, shorten long addresses or transliterate foreign scripts
  is gone. One button now handles all three in a single pass. Beyond the
  simpler screen this is mainly faster: a place affected by several of those
  problems — a Greek address is usually over-long as well — used to be looked
  up once per run, that is up to three times. Now every place is looked up at
  most once, which at OpenStreetMap's mandatory one-second delay saves hours
  on a large history.

## [0.20.0] – 2026-07-20

### Added
- **🇬🇧 The app speaks English:** a new language switch in the top right —
  one click toggles between German and English, and the choice is kept per
  device. On the very first visit the language follows your browser.
  Everything is translated: navigation, timeline, map, statistics, world,
  achievements, capture (AI and manual), all dialogs, messages and the
  explanatory texts in the settings area. Where a translation were ever to be
  missing, the German text appears instead — so no field can end up blank.
- **Place names follow the app language:** Life-Dash used to request
  addresses in German always. Now lookups follow your language setting: in
  English you get “Corfu, Greece” instead of “Korfu, Griechenland”, and for
  foreign scripts the English transliteration accordingly. The setting is
  stored on your account so the background place-name run knows it too.

### Changed
- **Documentation is now in English:** README, backend README, the deployment
  guide, the concept document and this changelog were translated once and are
  maintained in English from here on.

### Fixed
- **Switching language could stop halfway:** if part of the interface could not
  be rebuilt while switching (for example because the backend did not answer),
  the rest stayed in the old language. The parts are now rebuilt individually
  and no longer block each other.

## [0.19.0] – 2026-07-20

### Added
- **🖨️ Printing with a date range:** the print button in the timeline now
  opens a dialog: pick a range from/to (or go straight to **Everything**,
  **This year**, **Last 12 months**), plus switches for descriptions, notes
  and journal, imported location visits and unconfirmed proposals. The dialog
  shows in advance how many events it covers. What gets printed is a dedicated
  page containing **every** event in the range, grouped by day — collapsed
  groups and “show more” no longer matter, which used to be the biggest
  limitation.

### Changed
- **Life-Dash can be run anywhere:** the app was tailored to the author's own
  setup in several places — the sign-in service, the AI vendor and the reverse
  proxy were hardwired into examples, defaults and instructions. Now it holds
  throughout: Life-Dash speaks standards (sign-in via OIDC, AI via an
  OpenAI-compatible interface, place lookup via Nominatim), and which vendor
  you use is entirely your decision.
  - `.env.example` is the complete setup reference — **every** setting is
    documented there, with example values for several vendors instead of one
    default.
  - Without an AI key the app starts in “mock” mode (rule-based) instead of
    aborting the setup with an error.
  - User management only names your sign-in service if you configured it —
    otherwise a neutral text appears.
  - The guides (README, backend README, deployment) describe the procedure
    generally and list concrete products only as examples.
- **Map:** the idea collection “improve the map generally”, left open in 2026,
  is closed — height and fullscreen were done in 0.16.0, and further wishes
  will be picked up individually.

### Fixed
- **Outdated example configuration:** `backend/.env.example` still described
  settings that no longer exist (Ollama variables from an early version) and
  left out newer ones. The file now matches the actual configuration; the
  corresponding dead switches were removed.
- The default version in the deployment still pointed at 0.14.0 instead of the
  current release.

## [0.18.0] – 2026-07-20

### Added
- **🌍 World:** a new tab shows where you have been — a **world map with
  visited countries shaded** (the stronger the shade, the more events; clicking
  a country shows the count and the first and last visit) and a **checklist per
  continent** (“2 of 46 in Europe”) with the countries you visited. Clicking a
  continent expands what you are still missing. At the top are the key figures:
  countries visited, continents, share of the world and the most recently
  discovered country. This is fed by your countries in the collection — which
  come both from your own entries and from the location import. Different
  spellings of the same country (“USA” and “United States”) count as one; names
  that match no country are listed under the map so you can correct them.
  The country borders ship with the app — nothing is loaded from elsewhere.
- **🏆 Achievements:** a new tab with badges in four tiers — bronze, silver,
  gold, platinum. Included at launch: globetrotter, continent hopper, animal
  collector, observer, concert goer, stage collector, gourmet, frequent
  traveller, cinephile, bookworm, gamer and life chapters. Every badge shows
  the current value, a progress bar and how much is missing until the next
  tier; at the top you see achievements earned, points and what is close.
  Only what is confirmed in your life database counts — proposals trigger no
  achievements. Achievements are recomputed on every visit and store nothing
  themselves; if you do not track a topic, its badges are not shown.

## [0.17.0] – 2026-07-19

### Added
- **🖨️ Print the timeline:** a new “print” button in the timeline — prints the
  current view (with the chosen zoom, filters and search) in a light,
  print-friendly layout without navigation; the browser print dialog can also
  save it as a PDF. A first stage of the print view: you pick the range through
  the normal filters, and collapsed groups need expanding via “show more”
  beforehand.

## [0.16.0] – 2026-07-19

### Changed
- **The map uses the screen:** instead of a fixed 520 pixels the map now grows
  with the window (as does the stop list beside it), and a new **“⛶ fullscreen”**
  toggle shows it filling the screen (Esc exits).
- **One place-name run instead of three buttons:** “resolve place names”,
  “shorten addresses” and “transliterate foreign scripts” were already the same
  run on the server — now there is one button with a selection (missing names /
  long addresses / foreign scripts). The format building blocks
  (street/district/city/country) sit directly underneath.
- **“My data” is tidied up:** the tab is now divided into clear blocks —
  **backup & restore**, **imports**, **place names** and **tracking** — instead
  of one long grown list.
- **The login screen is now generic:** the sign-in text named a specific
  product; now a neutral SSO hint appears there. If you like, enter the name of
  your sign-in service via `OIDC_PROVIDER_NAME` in the `.env`.

## [0.15.2] – 2026-07-19

### Fixed
- **Place-name resolution copes better with the Nominatim rate limit:** when
  the geocoding service reports “429 Too many requests”, Life-Dash now waits
  the requested time and tries once more, instead of firing against the block
  every second; the gap between requests is slightly larger (1.2 s) so the
  block does not kick in at all.

### Added
- **Optional faster geocoding service:** the `.env` can name a
  Nominatim-compatible service with an API key (e.g. LocationIQ, free for 5,000
  requests a day instead of ~1 per second) — `GEOCODER_BASE_URL` +
  `GEOCODER_API_KEY`, nothing else changes. Without an entry everything stays
  on the public OpenStreetMap Nominatim.

## [0.15.1] – 2026-07-19

### Fixed
- **Older entries now get the new weather values too:** “add weather” used to
  skip every event that already had any weather — entries from before 0.14.0
  therefore stayed permanently without max/min temperature, sunshine hours,
  rain, snow and wind. The run now fills in the missing daily values
  **additively**: existing values (old temperature, condition) stay untouched
  and only the missing ones are added. Just start “🌤️ add weather” once (or let
  the nightly schedule do it).
- **The weather run stops cleanly instead of trying forever:** when the run
  made no progress (e.g. Open-Meteo unreachable or a date without archive
  data), it queried the same events in an endless loop. It now ends with a note
  on how many events could not be enriched.

## [0.15.0] – 2026-07-19

### Added
- **📖 Travel journal:** the timeline now has “write journal” — one formatted
  entry per day (Markdown: **bold**, headings, lists, quotes, links), with a
  preview in the editor. The entry appears as a day header above that day's
  events; if one already exists for the chosen day, it is loaded so you can
  continue writing. The AI never touches journal text. Comments on normal
  events can now be longer too and are displayed formatted as Markdown
  (rendered safely, without third-party libraries).
- **📅 Multi-day events with day entries:** a holiday stays ONE event but gets
  a “create day entries” button in the edit dialog: one event per day of the
  span (“Mallorca — day 3”), inheriting place and confirmation and getting
  **its own weather per day**. In the timeline the days stay collapsed under
  the main event (the chip “📅 N day entries” expands them; the day zoom shows
  them individually). The button is safe to use repeatedly — it only fills in
  missing days. When you delete the main event, Life-Dash asks whether the day
  entries go with it or remain as standalone events.
- **☀️ Light mode:** besides the dark one there is now a light appearance. The
  button in the top right switches between **auto** (following the system
  setting, live — e.g. at sunset), **light** and **dark**; the choice is stored
  per device. The maps change their tile style along with it.

## [0.14.0] – 2026-07-19

### Added
- **📍 Location while capturing:** quick capture and manual entry now have a
  location button — never automatic, only on click. In AI analysis your device
  location becomes a place suggestion when the text itself names no place (the
  text always wins); the raw coordinates travel into the raw inbox so a later
  recomputation knows them. In the manual form the button fills the place field
  with the current address (overwritable). Requires the browser's location
  permission (HTTPS).
- **The country collection fills up from imports:** when resolving place names
  the country is now taken along, stored with the place and linked as a country
  entry with all visits there — retroactively via “resolve place names” /
  “shorten addresses”. That finally makes “how many countries have I been to?”
  correct for imported movement data too.

### Changed
- **Fuller, more honest weather:** the pure **daily values** are now stored:
  max and min temperature separately, **sunshine hours**, **rain (mm)**,
  **snow (cm)**, **maximum wind (km/h)** and the daily condition. In event
  cards and map popups everything appears as one compact line (“12–17.4 °C ·
  drizzle · ☀️ 9.1 h · 🌧️ 5.1 mm”; wind only when notable). Weather already
  fetched stays unchanged — facts are never overwritten.
- **Statistics with weather extremes:** besides “hottest/coldest day” (which
  now use real daily max/min) there are new tiles for **sunniest**, **wettest**,
  **windiest** and **snowiest day** — clicking opens the respective event as
  usual.

### Fixed
- **The “what would you like to track?” window could not be closed:** the
  dialog used a wrong CSS class and stayed permanently visible.

## [0.13.0] – 2026-07-19

### Added
- **You decide what is tracked:** on first start Life-Dash asks which areas
  interest you (trips, animals, countries, artists, food, milestones, films,
  games, books) — changeable at any time under Settings → My data. Deselected
  areas disappear from the collection, filters, forms, statistics **and** the
  AI prompt (the AI stops proposing them); existing data is kept and reappears
  immediately once you select them again.
- **Runs now happen in the background on the server:** adding weather,
  recomputing AI proposals, embeddings and all place-name runs continue when
  you close the page. The jobs tab has a **stop button** per running job and a
  live refresh. New: a **nightly schedule** — selected runs start automatically
  once a day at the configured hour (switchable per run). File imports stay
  tied to the browser (the file lives there).
- **Three new collection areas: films, games, books** — the AI recognises such
  titles and creates collection entries.

### Changed
- **Modules are now fully declarative:** colours, emoji, category names,
  collection tabs, form options and the AI recognition rules come from the
  module definition files — a new area is therefore a single YAML file with no
  code change (the three new areas were created exactly that way).

## [0.12.0] – 2026-07-19

> From this version on, changelog entries are written in product language —
> without internal package codes (those live only in the concept).
> Version 0.11.0 was skipped.

### Fixed
- **The map was invisible on a phone:** a CSS bug collapsed the map area to
  height 0 in the mobile layout (the small collection map was not affected).
  On mobile the map now has a fixed height of 55 % of the screen.
- **Search without feedback:** when the server search failed (e.g. because the
  AI service for meaning-based search was unreachable), the app jumped to the
  timeline but silently filtered nothing. In that case a simple text search
  over title/description/place now steps in, and a note explains the
  limitation.
- **“Searched address” disappears:** this Google label only describes how the
  stay was detected and carries no value of its own. New imports create such
  visits as unnamed places (which get the plain address when resolved);
  existing “searched address — …” names and visit titles are cleaned up
  automatically at app start, and bare “searched address” places are resolved
  into real addresses by “resolve place names”.

### Added
- **Export with a selection:** when exporting data, a checkbox can leave out
  the entire Google Timeline part (imported visits, routes and their raw
  records) — for a handy backup of hand-curated entries without tens of
  thousands of import rows.

### Changed
- **Understandable language instead of jargon:** the interface no longer talks
  about “stage 1/2/3” — instead: **raw inbox** (your unchanged texts),
  **proposals** (AI drafts to confirm), **life database** (confirmed entries
  including facts such as weather) and **views** (everything computed). This
  affects statistics tiles, capture hints, admin actions and the database view;
  the button “recompute stage 2” is now called “recompute AI proposals”.

### Other
- **License:** as of this release Life-Dash is officially free software under
  **AGPL-3.0-or-later** (LICENSE file + README section; before that, no license
  meant “all rights reserved”).

## [0.10.1] – 2026-07-16

### Changed
- **Map clustering less aggressive:** the cluster radius was lowered from 45 to
  30 px — nearby points only bundle when they really crowd each other, and mini
  bubbles (“3”) spanning half a continent became far rarer. The tooltip on
  “cluster from N points” now explains the semantics: the threshold switches
  between individual markers/route and cluster mode; within cluster mode the
  map bundles depending on zoom (click/zoom splits bubbles).
- **Concept:** a license proposal was added (ch. 15, note 31) — recommending
  **AGPL-3.0** (the repo had no LICENSE = “all rights reserved”).

## [0.10.0] – 2026-07-16

### Added
- **A14 — settings with tabs instead of a scrolling page:** the former “admin &
  moderation” page is now called **“Settings”** and is divided into tabs:
  **📋 moderation** (queue, bulk confirm, vague dates), **📦 my data**
  (export/import, place-name actions, display format), **⏱️ jobs** — for all
  users; **⚙️ system** (the layer explanation, recomputation/weather/embeddings,
  data wipe), **👥 users**, **🗄️ database** and **📜 logs** for admins only.
  Every tab loads its data when opened.
- **A17 — log view in the UI:** a new admin tab “logs” shows the most recent
  app log lines (an in-memory ring buffer, max. 500 since process start) with a
  minimum level filter (DEBUG–ERROR) and a refresh button
  (`GET /api/admin/logs`). No file access, nothing is persisted —
  `docker logs` remains the complete source.

## [0.9.0] – 2026-07-16

### Added
- **A11 — jobs with a lock plus a job view:** long-running actions (weather,
  stage-2 recomputation, embeddings, place-name runs, timeline/JSON import) are
  now registered as **jobs** (`/api/jobs`): type, status, progress, started
  by/when, result. **One lock per job type** — if a second instance starts the
  same type (a second browser, a second user), it gets “already running
  (started by …)” instead of a double run with double API costs. Orphaned runs
  (browser closed) stop blocking after 3 minutes without a heartbeat. A new
  **jobs table** in the admin area shows running and recent runs (all users see
  it — the lock is global). Plus **DB-side duplicate protection for weather**: a
  partial unique index (`event_id`+`key` for `source=weather`) including a
  one-off cleanup of existing duplicate metrics; enrichment commits per event
  and skips collisions from parallel runs cleanly.
- **A4 — raw DB view with guard rails:** raw editing now validates against the
  model (enums only with valid values, JSON must parse, times/numbers are type
  checked, required columns cannot be emptied) — a 400 with a clear message
  instead of silent data corruption. **Follow-up recomputations** run
  automatically and are shown in the toast: title/description changed →
  embedding reset; time/place changed → weather follows the new facts.
  **Deletion guard rails:** fragments (the evidence archive) and users (→ user
  management) are locked in the raw view; deleting an event also clears
  metrics/media/links, deleting an entity clears its links, and deleting a place
  detaches affected events cleanly (instead of leaving orphaned references).
- **A18 — map clustering only above a threshold (configurable):** a new field
  “cluster from N points” on the map (default 50). Below it, individual markers
  or the numbered route; above it, bundling. Stored per user
  (`map_cluster_min` in the settings), limited to **10–300** — the upper bound
  protects performance (more individual markers freeze the browser after large
  imports).

### Fixed
- **A16 — month precision was missing from the vague dates:** “June holiday
  Denmark” (correctly stored as `month`) did not appear in the vague-date list —
  it filtered only season/year/decade/no date. `month` now counts.
- **API error messages in the UI:** the frontend now shows the backend reason
  (`detail`) instead of a bare status code — important for validation errors
  (A4) and “job already running” (A11).

### Tests
- New offline tests for A4 (enum/JSON/time validation, embedding reset, weather
  follow-up, deletion guard rails and cleanup), A11 (job lock, stale cleanup,
  weather unique index) and A18 (threshold clamping 10–300).

## [0.8.0] – 2026-07-16

### Added
- **A5 (remainder) — visit condensation:** repeated visits to the same place
  are bundled instead of listed individually. **Map:** from month view up, one
  marker and one list row per place (“59× home — …”, with a time span), so
  everyday places collapse automatically; switchable via the new chip
  **“🔁 merge places”**. In day/week the numbered route remains.
  **Timeline:** identical Google visits within a time group appear as one
  collective card (“🔁 59× visit: X”) that expands into individual cards on
  click — previously everyday places filled the 25-card cap of the groups
  entirely.
- **A12 — timeline import: semantic places → real addresses:** places the
  device export knows only as a label (“home”, “work”, “searched address” …)
  are now reverse geocoded — the label stays as a prefix (“home — Example
  Street 1, Detmold”); the place type (e.g. `home`) and separate `place_id`s
  (several homes over a lifetime) stay unchanged. This applies during import
  (auto-resolution of small amounts) and retroactively via “resolve place
  names”. Plus an optional import filter for **minimum location certainty**
  (`min_probability`): visits with an uncertain place assignment can be skipped
  during import; the result toast reports them.
- **Compact place names (configurable):** resolved addresses are no longer
  stored as the full Nominatim chain but assembled from structured building
  blocks: **street · district · city · country** — selectable per user via
  checkboxes in the admin area (`GET/PATCH /api/auth/me/settings`, a
  whitelist). Named places (restaurant, museum, station …) always keep their
  proper name in front. This applies to timeline resolution **and** forward
  geocoding (AI pipeline, manual entry, edit dialog). A new action
  **“📐 shorten addresses”** reformats existing long addresses
  (`resolve-names?scope=verbose`, a batch run with a stop button); visit events
  are renamed along with them, manually renamed ones stay untouched.
- **A6 — user management UI:** a new admin area “users”: a list of all accounts
  (name, email, role, data volume, member since), change the role via a
  dropdown, delete a user **together with all their data** (with a
  confirmation). Guard rails: your own account can neither be deleted nor
  demoted, and the last admin always remains
  (`GET/PATCH/DELETE /api/admin/users`).

### Fixed
- **Import auto-resolution did not rename fresh visit events:** during direct
  reverse geocoding of small place sets in the import, the just-created events
  were not found (a session without autoflush) — their titles stayed
  “visit: place (lat, lng)” even though the place had been resolved.

### Tests
- New offline tests for A12 (label prefix, idempotency, `field_overrides`
  protection, `min_probability`), A6 (last-admin guard, deletion including data
  rows, self-deletion block) and the place-name format (`short_name` building
  blocks, POI proper name, user setting, `scope=verbose`, settings whitelist).

## [0.7.0] – 2026-07-16

### Added
- **A9 — logging & observability:** a central logging configuration
  (`lifedash.*` loggers, a uniform format with timestamps), controlled via
  `LOG_LEVEL` (.env / Compose). Now logged: app start (version, auth/AI/DB
  mode), export/import with row counts, admin actions (recomputation,
  weather/embedding batches, raw-view changes, data wipe), geocoding/Open-Meteo
  errors and place-name resolution.
- **A10 — place names consistently in Latin script:** Nominatim is queried with
  a language chain plus `namedetails`, so names in local scripts (e.g. Greek)
  arrive transliterated. A new admin action resolves existing foreign-script
  names retroactively (`scope=nonlatin`).
- **A13 — show & edit times:** events with `date_precision = exact` now display
  their time (“12/07/2026, 14:30–16:05”), and the edit dialog has time fields.
- **A5 (map part) — marker clustering instead of a 300 cap:** the map now draws
  all points of a range and bundles nearby ones into clusters, instead of
  cutting off after 300 markers.
- **A8 — export feedback:** the data export reports success via a toast with
  content, size and filename — and reports failures too.

### Fixed
- **Silent precision downgrade while editing:** the edit dialog reset
  `exact` to `day` when saving, so times were lost.

## [0.6.0] – 2026-07-16

### Added
- **A1 — proper UI dialogs instead of browser popups:** all native
  `alert()`/`confirm()`/`prompt()` calls (~20 places) were replaced by toasts
  and a confirmation modal in the app's own style — including a typed
  confirmation for the data wipe.
- **A2 — progress bars for large imports:** the Google Timeline import and the
  JSON import run in stages with a visible progress bar; the import is
  idempotent, so an interrupted run can simply be repeated.
- **A3 — version number in the UI:** the sidebar shows the running version at
  the bottom left; it also appears in `/health` and in the OpenAPI document.
  The single source of truth is `backend/app/version.py`.

## [0.5.0] – 2026-07-16

### Added
- **P2.5 — bulk confirm:** the moderation queue can move many correct AI
  proposals into the life database at once — filtered by category, source,
  confidence and time range, with a mandatory preview before confirming.
- **P2.6 — invariant test “confirmed data is untouchable”:** automated offline
  tests ensure that recomputation never changes confirmed events.
- **P2.7 — confirmation provenance:** every event now stores **when** and
  **how** it was confirmed (manual/bulk/import), visible in the edit dialog;
  existing data was migrated.
- **P2.4 — auto enrichment after capture:** new events (AI analysis and manual
  entry) get their weather immediately; correcting time or place afterwards
  makes the weather follow.
- **P2.2 — Google Timeline import:** upload of the timeline export (device
  export and older Takeout formats), visits become events, routes become
  tracks. Idempotent — repeated imports create no duplicates.
- **Routes as a map layer:** timeline routes appear on the map as lines.
- **The four-layer model was refined** (concept ch. 3.1): inbox → proposal
  space → life database → derived.
- **A stop button and a request ticker for all admin runs:** stage-2
  recomputation, weather and embeddings can be stopped mid-run.
- **Place names for imported visits:** the device export contains no place
  names, so a resolution run fetches real addresses.
- **P2.3 — vague-date review:** the admin area lists all events with an
  imprecise date so they can be sharpened.
- **Statistics are clickable** (as in the collection): tiles lead to the
  matching events.

### Changed
- **PostgreSQL is now the Compose default** (no `--profile postgres` needed).
- **Data lives in folders next to the Compose file** (bind mounts instead of
  Docker volumes) — simpler to back up.
- **Performance for large imported data sets** (>10k timeline events).

## [0.4.0] – 2026-07-15

### Added
- **Linked items editable in the edit dialog** (e.g. “sea eagle” → “eagle”),
  so duplicates can be resolved by hand.

## [0.3.2] – 2026-07-15

### Fixed
- **The map was not displayed on mobile devices.** Leaflet now measures itself
  again after the view is shown.
- **The capture icon in the mobile navigation** had a stray blue circular
  background.

### Added
- **A visible loading overlay during AI analysis** (spinner plus text).

## [0.3.1] – 2026-07-15

### Fixed
- **OIDC login failed behind the reverse proxy with HTTP 403.** Server-to-server
  calls to the OIDC provider now send their own user agent, because some proxies
  and bot filters block urllib's default.

## [0.3.0] – 2026-07-15

### Changed
- **Versioning switched to SemVer** (`vMAJOR.MINOR.PATCH`) plus this changelog.
- **The Ollama service was removed from the Compose stack** (a local Ollama
  remains possible as an external endpoint).

## [0.2.0] – 2026-07-15

### Fixed
- **Multi-arch image** (`linux/amd64` + `linux/arm64`); v0.1 was amd64-only and
  would not start on ARM64 boards.

## [0.1.0] – 2026-07-15

### Added
- First release: the three-stage foundation (fragment → event/entity → views),
  AI extraction with a preview, timeline, map, statistics, collection, search,
  OIDC login with multi-user separation, Docker deployment.
