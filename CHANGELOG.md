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

## [0.38.0] – 2026-07-22

### Fixed
- **Scrolling fast through the timeline no longer breaks the whole app.** With
  many photos on screen, image requests could occupy every database connection
  at once — and then *nothing* worked any more, including the timeline itself,
  which looked as if it were loading forever. Image requests now hand their
  connection back before they go and fetch the picture.
- **The map no longer drops points in silence.** Without “Merge points” it only
  ever drew the first 300 entries of a period, chronologically — so after a
  location import a single trip in the middle of the month simply was not
  there. The map now says how many points it is hiding, with one button to
  bring them back. (Nothing is dropped when merging is on.)

### Added
- **“Vaguely dated” is now visible where the work is.** The Today view has a
  second counter beside “waiting for review”: entries dated only by month, year
  or not at all. Two different backlogs, two numbers — “is this right?” and
  “when was this?” are not the same question. It only appears when there is
  something to do.
- **“On this day” can include imported location visits.** It always left them
  out, for a good reason — a day five years ago can hold thirty of them and the
  look-back turns into a list. But the choice was never offered. Now there is a
  switch, stored per device; the default is unchanged.
- **Address building blocks are kept.** Until now the parts a place name is
  built from were thrown away once the name was assembled, so changing the
  format meant asking the geocoder about every place again — throttled to one
  per 1.2 seconds. They are stored from now on, and reformatting those places
  is instant and needs no network at all. Places you already have get their
  parts back the next time the place-name run touches them.

### Changed
- **Photos in the timeline follow the zoom.** In week view the day strips are
  merged into one “pictures from this week”; from month view up you get a
  selection of twelve, labelled as one (“12 of 340 pictures”) so it never
  pretends to be complete. Day view is unchanged.
- **French Guiana stays France, and so does Réunion.** Recorded as a decision
  rather than an oversight: they really are French overseas departments — part
  of France and of the EU — and that is what the geocoder reports. The
  consequence is that a trip there counts towards Europe on the world map,
  which is the price of following politics rather than geography.

## [0.37.0] – 2026-07-22

### Added
- **Immich can now suggest entries, not just deliver pictures.** Pick a year,
  look at the preview, and Life-Dash turns your photos into **unconfirmed**
  proposals you can accept or reject like any other:
  - **A day with many pictures in one place** becomes one entry — “34 photos on
    12 July in Detmold”. The place comes from Immich's own geocoding, so no
    external service is asked.
  - **Every album** becomes a trip proposal — name, span and the places inside.
  - Nothing is ever confirmed for you, and nothing is created before you have
    seen the preview: the button stays locked until then.
- **The year list tells you where the treasure is.** It comes from Immich and
  shows how many photos each year holds — the years worth running are usually
  the old ones, where there is no location history at all and the photos are
  the only record left.
- **A rejected proposal stays rejected.** Reject “12 July in Detmold” and it
  will not come back on the next run, this year or in three years — even
  though rejecting deletes the entry itself.
- **Adding photos to a day does not duplicate it.** A proposal is identified by
  its *place in your life* — the date and location, or the album — not by which
  pictures happened to be in it.

### Changed
- Only **your own** photos, **with coordinates**, that sit in your **Immich
  timeline** are turned into day proposals. Screenshots and forwarded images
  carry no coordinates and cannot invent a place; other people's photos from a
  shared album cannot invent a day; archived and locked photos stay out
  entirely.
- **Shared albums are welcome** — an album is a named, bounded thing, and a
  shared one is usually a joint holiday. A proposal that comes from one **says
  so**, so taking over someone else's trip is a decision rather than an
  accident.
- A day that already has imported location visits still gets a photo proposal.
  A photo's coordinates are evidence; a location visit is an inference — the
  proposal is the more precise line, not a duplicate.
- This run is deliberately **not schedulable overnight**: it needs a year and a
  preview, and neither survives being skipped.
- New endpoints `GET /api/immich/years` and `POST /api/immich/preview`, and a
  new job type `immich_source`. No schema change.

## [0.36.0] – 2026-07-22

### Added
- **Capturing works without a connection.** Write something down on a train, in
  a cellar, on a mountain — it is kept on the device and sent by itself the
  moment there is network again. Until then it sits in a visible list on the
  capture page, with its full text and a counter next to “Capture”, so “where
  did my note go?” never becomes a question. Nothing is deleted until the
  server has confirmed it.
  - Entries the server genuinely *rejects* stop being retried and say why, with
    a button to discard them — endlessly resending something that will never be
    accepted is only a quieter way of losing it.
  - If your session has expired in the meantime, the text is kept too and goes
    out after you sign in.
- **Life-Dash appears in the share menu of other apps.** Share a link, a
  passage of text or a headline into Life-Dash and it lands in the capture
  field, ready to check and record. It is deliberately not recorded for you:
  what goes into your database is your decision.
- **Opening the app without a connection now shows the app.** Until now a
  missing network looked exactly like being signed out — you were left with a
  login screen that cannot be used without network, which is precisely the
  situation offline capture exists for. Now you get the capture page, a plain
  explanation, and everything that needs the server clearly marked as such.
- **A suggested journal entry for a day.** In the journal dialog, “Summarise
  the day” turns that day's confirmed events — with places, weather and photos
  — into a short draft in the first person. The draft appears **beside** your
  text, never inside it: you take it over, edit it, and save it yourself. The
  AI still never writes in your journal, and never saves anything.
  - Unconfirmed entries stay out of it and are counted instead (“3 unconfirmed
    skipped”), because a journal should not turn a guess into a memory.
  - A day with nothing to summarise says so, rather than producing an empty
    draft.

### Changed
- The manual entry form is shown as unavailable while there is no connection,
  instead of letting you fill it in and fail at the end. It saves straight into
  the life database, which is why it has no offline queue.
- `POST /api/ingest` accepts an optional `client_id`; sending the same one
  twice returns the first result with `duplicate: true` instead of recording
  the capture a second time. Without it, two identical captures stay two
  captures — a person can mean that.
- New endpoint `GET /api/journal/suggest?day=…`. It only reads.

## [0.35.0] – 2026-07-22

### Added
- **Cities open into a page of their own.** A city was the one entry in the
  collection that led *out* of it: clicking it jumped straight into a filtered
  timeline, while every animal and country opens a page. Now a city does too —
  a short description from Wikipedia, a map of the places you have been to
  there, the most recent entries, and how many there are in total. The timeline
  is still one button away, which is the right place for “all 342 of them”.
  - Descriptions are looked up **with the country**, so “Frankfurt” is the one
    on the Main and “Springfield” is a real town rather than a list of them.
  - A city that genuinely has no article is remembered as such and not asked
    about again every time you open it. After a month it is tried once more —
    an article can come into existence.
- **Badges no longer stop at platinum.** Platinum was the end of the road, and
  a database that covers a whole life reaches any fixed end eventually. Beyond
  it a badge keeps counting toward a next mark — “1,240 · next mark 2,500” — so
  the number never stops saying something. Where a collection genuinely *can*
  be finished — seven continents, the countries of the world — platinum stays
  the end, because there it is the truth.

### Changed
- **Wikipedia descriptions follow the app language.** They were always fetched
  from the German Wikipedia, so an English interface showed a German paragraph.
  Existing descriptions are refreshed the next time you open them after
  switching language.
- Weather badge thresholds were raised. “Frozen once” was never an achievement,
  and the numbers were set in the days when entries were typed by hand.
- The collection now offers `GET /api/cities/detail` and
  `POST /api/cities/describe`; achievements carry `beyond_top` and
  `marks_passed` beside the existing tier fields.

### Fixed
- **Weather badges counted entries, not days.** “Days with at least 10 hours of
  sunshine” counted every *visit* on such a day, so after a Google Timeline
  import a single sunny day could count thirty times — and collected sunshine
  hours were multiplied by the number of entries per day. This is the same
  mistake the weather statistics had to shed in 0.27.0; it had survived in the
  badges, which is why they arrived nearly complete after an import. The
  descriptions said “days” all along; now the counting does too.
- **The Cities tab was invisible.** It existed in the page but was written by
  hand next to a list that the app rebuilds from the modules as soon as they
  load — which happens a moment after every start. The tab was therefore gone
  in every real session, and the statistics tile pointing at it led nowhere.
- **Immich photos now belong to the day, not to a random visit of it.** After a
  Google Timeline import a day holds dozens of visits, each with a window of
  six hours either side, and three places in one city are all within the 25 km
  the place check allows — so a photo simply went to whichever visit happened to
  be looked at first. Worse, the timeline shows one condensed card per day and
  city, and that card is a different arbitrary visit: measured on a day with ten
  visits, four photos were attached and **none** of them were visible. Photos of
  such a day now hang on the date itself and appear in the day's photo strip,
  the place ceases to be part of the question, and entries you created yourself
  still get their own photos first. Existing links on imported visits are moved
  the next time the Immich run goes through — they are references, so nothing is
  lost.

## [0.34.0] – 2026-07-22

### Added
- **Photos can belong to a day.** Until now every picture had to hang on a
  single entry — the one place a photo most obviously belongs, “that day”, was
  the one place it could not go. A picture attached to a day appears as a strip
  in the timeline at that day, and “📷 Photo for a day” in the timeline bar
  attaches one. No day object is created for it: the day is the date the
  picture was taken, nothing more.
- **Cities are their own thing now.** Until now a city existed only as a piece
  of text inside a place name — and which pieces a name contains is your
  setting, so anyone who had switched “City” off had no cities at all. Every
  place now carries its city as a real field, filled by the existing “resolve
  place names” run (no new job to start, and each place is asked exactly once —
  places that genuinely have no city are remembered as such instead of being
  looked up again forever).
  - **“Cities visited”** joins the statistics tiles, with a
    **most-visited cities** chart beside the top places. Three streets in one
    city are three places and one city — both counts answer real questions, so
    both are shown.
  - **The timeline condenses imported visits.** With visits shown, a day after
    a Google Timeline import was dozens of near-identical lines. They now
    collapse into one entry per city and day — “Düsseldorf · 12 visits ·
    08:14–19:30” — which opens to the individual visits on click. Entries you
    created yourself are never merged, even two on the same day in the same
    city: they were entered separately, so they are meant separately.
  - **The cities can be opened.** “Cities visited” and every bar of the
    most-visited chart lead into the timeline, limited to that city — and the
    collection gained a **Cities** tab beside countries, listing every city
    with how many entries it holds and the years you were there. While the
    limit is active a chip names the city and switches it off again, so a
    shortened timeline always says why it is short. Places deliberately get no
    tab of their own: there are hundreds of them and more with every import,
    and a list you can never finish is what the map is for.

### Changed
- Place data returned by the API now includes `city`; `GET /api/events` gained
  `condense` and `city` parameters, and `GET /api/cities` lists the visited
  cities.
- **Long-running jobs now say what they are doing while they do it.** Only the
  Immich run reported progress; resolving place names, adding weather, imports
  and exports wrote one line when they started and one when they finished, and
  in between a slow run looked exactly like a hung one.
  - Every job writes a progress line with **speed and remaining time** — “340
    of 1,200 places (48/min, ~18 min left)”. The line appears at most every ten
    seconds, so a fast job cannot flood the log.
  - **Resolving place names reports every place**, old name to new one,
    including the city that was found and whether the result still has a
    defect. The geocoder is limited to about one request per second, so this
    can never be more than a line per second.
  - **Export and import report each section** (“Export: events — 12,013 rows”),
    and weather names the entries it could not get data for — the reason a run
    stops with “nothing to enrich” was previously nowhere to be found.
  - The **log view holds 2,000 lines** instead of 500, and follows along on its
    own while the tab is open. A single run of place names used to push
    everything else out of the buffer within minutes.

### Fixed
- **Resolving place names could stop while there was still work to do.** A
  place the geocoder cannot identify stayed in the queue and was asked again in
  every batch. On its own that only cost a request per round — but the failures
  gather at the front of the queue, and as soon as a whole batch consisted of
  them the run reported “not resolvable” and finished, leaving hundreds of
  places that would have resolved untouched. Each place is now tried at most
  once per run, and the closing line says how many could not be identified.
  Starting the run again retries them: a place unknown today may be known next
  month.
- **The weather run spent most of its time looking for work.** Before every
  batch of 25 entries it loaded the entire event table into memory to decide
  which entries still needed weather. On a database with thousands of entries
  that search cost more than the weather lookups themselves. The database now
  does the selecting.
- **The running version is readable on a phone again.** It lives in the sidebar
  footer, which the phone layout hides — so “which build am I looking at?” had
  no answer on the device where it is asked most. Version, account and sign-out
  now sit at the bottom of the “More” sheet, including the orange `-dev` mark
  and the build tooltip.

## [0.33.0] – 2026-07-22

### Changed
- **The app is usable on a phone.** The guiding principle said “mobile first”
  from the beginning; the layout never lived up to it, and this release
  measures the gap and closes it.
  - **The bottom bar carries four destinations plus “More”** instead of nine.
    Nine meant about 40 pixels each on a normal phone — below the size a
    fingertip can reliably hit — with labels at 10 pixels. Today, Timeline,
    Map and Capture stay in the bar; Statistics, Collection, World,
    Achievements and Settings open as a list with full-width rows and readable
    names. The badge for entries awaiting confirmation is mirrored onto
    “More”, so nothing is hidden behind it unnoticed.
  - **The entry dialog opens from the bottom and keeps its buttons visible.**
    It used to be capped at a height that assumed the browser's address bar
    was hidden, which put **Save** off the bottom of the screen — the most
    important button in the app was unreachable on the device most likely to
    be used. Every other height cap in the app had the same flaw and was
    corrected with it, including the photo lightbox and the log view.
  - **The settings rows fit the screen.** Their label column had a fixed
    width baked into each row, which no phone layout could override, so rows
    squeezed together or ran off sideways. Four more places carried the same
    defect and were found while fixing it.
  - **The map can use the whole screen.** The filters fold away behind a
    button that shows which period you are looking at, and the map takes the
    space they leave.
  - **Raw-data tables wrap** instead of forcing a sideways scroll through
    unbreakable lines.
- **The map controls say what they do — and admit when they cannot.** Under
  “Display” there were four controls whose names did not distinguish them:
  two different things were both called a “route”, and two of them regularly
  did nothing at all while still looking switched on.
  - **“Paths travelled”** (formerly “Timeline tracks”) draws the routes you
    actually took, as recorded by the timeline import.
  - **“Connect in order”** (formerly “Connect route”) draws a line through
    this period's places in the order they happened — not a route you
    travelled. When points are merged there is no order left to show, so the
    control now shows itself as struck through and says why, instead of
    staying lit and drawing nothing.
  - **“Merge points”** (formerly “Merge places”) is now the single switch for
    all condensing. Whether points are merged per place or by proximity
    depends on how far you are zoomed out — a technical detail you no longer
    have to know. Switching it off now really shows every visit, and the list
    says so when that runs into the display limit.
  - **The clustering threshold moved to Settings.** It protects performance
    on weaker devices; it is not something you decide while looking at a map.

### Added
- **A test build now says it is one.** When the app is not running a published
  version — a development image built from the main branch, or one you built
  yourself — the version in the sidebar reads `v0.33.0-dev` in amber instead
  of claiming to be the release, and its tooltip names the branch and commit
  it came from. `GET /health` gained `channel` (`release` or `dev`) and
  `display_version` alongside the unchanged `version` field.

## [0.32.0] – 2026-07-21

### Changed
- **The app no longer loads your whole life to show you the top of it.** Until
  now every view started by fetching every entry you have ever recorded. The
  timeline now asks for one page and loads more as you scroll, and each of the
  other views asks for exactly what it shows. Measured over HTTP on a database
  of 12,000 entries: the opening request went from **12.7 MB and 1.5 seconds to
  0.3 MB and 0.08 seconds**. Whether your database holds twelve thousand entries
  or two hundred thousand no longer decides how long the app takes to open — on
  a phone or a small home server most of all.
- **“On this day” no longer reads your whole history to find one date.** It
  used to load every dated entry — with all its weather readings — and pick the
  matching days in code. Since it sits on the opening view, that quietly became
  the slowest part of starting the app: measured at 3,000 hand-made entries,
  660 milliseconds, growing with your database. The calendar day is now
  selected in the database itself: **12 milliseconds**, same result.
- **The statistics are calculated where the data is.** Every number on the
  statistics tab — places, categories, milestones, moves, weather records,
  charts — used to be computed in your browser from that same complete list.
  They are now computed by the server and arrive as about two kilobytes instead
  of 26 megabytes, which also made that tab roughly fifteen times faster to
  open. **The numbers themselves are unchanged**, and the tests compare them
  against the previous rules, including the rule that weather belongs to a
  calendar day rather than to each entry of that day.
- **The map fetches its own points** instead of borrowing the timeline's, and
  only when you open it. Weather is fetched for the period you are looking at,
  because carrying it for every point on the map would have quadrupled the
  download for something only visible in the popup you click.
- The “today” tiles, the vague-dates list, the journal, and the print dialog
  now ask for the entries they need rather than sifting the complete list.
- **Hiding imported location visits now happens on the server.** After a
  Google Timeline import most of your database is visits, and the timeline
  hides them by default — filtering them in the browser meant paging through
  thousands of invisible entries to fill one screen. Measured on a database of
  12,000: six requests to show seven cards, now one. The “visits” switch also
  reports how many there really are, instead of how many happened to be loaded.

### Fixed
- Clicking a weather record on the statistics tab opens the entry again. It
  silently did nothing whenever that entry was not in memory — which, with the
  new paging, would have been most of the time.
- Narrowing the timeline to a single category now looks past the entries
  already on screen. It would otherwise have said “no entries” for anything
  rare — concerts, milestones — while they sat a page further back.
- The print range no longer shifts by your time zone. Asking for “1–30 June”
  quietly included the evening of 31 May and cut the last hours of 30 June.

### Infrastructure
- **A development image is now published from every push to the main branch**
  (`ghcr.io/…/life-dash:main`), so trying out a change no longer requires
  inventing a version number. Releases are unchanged: a `vX.Y.Z` tag still
  builds `X.Y.Z`, `X.Y` and `latest`. `GET /health` now also reports which
  commit an image was built from — with a development track, the version
  number alone no longer answers “what is running here?”.
- `docker-compose.yml` no longer defaults to a version from thirteen releases
  ago when no `.env` is present; it falls back to `latest`. Pinning a version
  in `.env` remains the recommendation for anything holding real data.

### Notes for upgraders
- No migration and no configuration change. The database is untouched.
- The list endpoint keeps its old behaviour when asked without a page or a
  time range, so exports, backups and any scripts against `/api/events` keep
  working exactly as before.

## [0.31.2] – 2026-07-21

### Changed
- **The first load is dramatically faster on a large database.** 0.31.0 shrank
  what was *sent*; this shrinks what the server has to *do*. Building the
  timeline used to load all sixteen weather readings of every entry as full
  database objects just to fold them into one value — measured on a fast
  machine, that alone was about 3 seconds at 12,000 entries. The timeline query
  now skips those rows entirely and fetches the weather in one lightweight pass,
  cutting the response from roughly 6 seconds to about 1.2 on that machine — and
  proportionally more on a Raspberry Pi. Several long-missing database indexes
  were added at the same time (they are created automatically on start).

### Notes for self-hosters
- If the first load is still slow for you, the remaining cost is simply having
  to send every entry at once. A faster machine (or moving the database from an
  SD card / SQLite to PostgreSQL) helps directly, because the work is now
  CPU- and disk-bound rather than wasted effort. Loading only the visible time
  range — so the size of your history stops mattering — is the planned next
  step if this is not enough.

## [0.31.1] – 2026-07-21

### Fixed
- **The same photo was being linked to many entries on the same day.** With a
  Google-timeline import there are often a dozen visits on one day, all sharing
  the same day-long window. A photo without GPS was attached to *every* one of
  them, and a photo with GPS to every visit within 25 km — so one picture could
  appear dozens of times and the linked-photo count ran far ahead of the number
  of actual photos. Now **each photo is linked once**, to the first matching
  entry, and a re-run never duplicates what is already there.
  - If you already ran the linking and see the same photos repeated, use
    **Settings → Immich → “Discard links”** and run **“Link photos”** once more.
    The connections are derived data, so discarding and rebuilding them is safe
    — your pictures in Immich are untouched.

### Notes
- This also keeps the photo volume — and therefore the size of the initial
  load addressed in 0.31.0 — under control, since one picture no longer
  multiplies across a day's entries.

## [0.31.0] – 2026-07-21

### Added
- **🎂 Your age on every entry.** Each entry now shows, discreetly, how old you
  were at the time — read from your “Birth” milestone (the one the first-run
  form creates). No separate profile field, so there is a single source of
  truth; entries with a vague date show “~” so the number never claims more
  than the data holds, and nothing appears before your birth or if no birth is
  recorded.

### Changed
- **The app opens much faster, especially on a phone.** The timeline used to
  download every entry with all its weather readings in one go — about
  two-thirds of that was raw weather rows the list never shows individually.
  It now fetches a slim version (the weather folded into one compact value per
  entry), which cuts the initial download by roughly 60 % (measured: ~19 MB
  down to ~8 MB at 12,000 entries). The timeline looks exactly the same; only
  the statistics view, which needs the raw figures, still loads the full set —
  and only when you open it. This is the fix behind the earlier “Failed to
  fetch” on mobile.

## [0.30.1] – 2026-07-20

### Fixed
- **The Immich linking job could run forever without doing anything.** Entries
  for which Immich has no matching photo stayed on the to-do list, so the job
  kept re-checking the same first batch over and over — no progress, no end, no
  error message. It now walks through every entry exactly once and finishes.
- **The Immich job now shows a progress bar and writes to the log** as it goes
  (how many entries checked, how many photos linked), instead of being a black
  box. Loading the candidate list is also much faster on a large database — it
  no longer makes two extra queries per entry.

### Changed
- **A slow load on a mobile network no longer says “Backend error”.** When the
  first big data request times out — most likely on a phone with a large
  database — the message now says so honestly and offers a “try again” link,
  rather than blaming the backend, which is actually fine. (The underlying
  cause, sending the whole event list at once, is a known item still to be
  addressed.)
- Weather auto-enrichment failures are no longer completely silent — they leave
  a debug-level trace, so “why does this entry have no weather?” is answerable.

## [0.30.0] – 2026-07-20

### Added
- **📊 Modules bring their own statistics.** Each trackable module (animals,
  trips, concerts, games, films, books …) now declares its figures in its own
  definition file, and the statistics view renders them automatically — a
  number for “different games played”, a per-year chart for “trips per year”,
  and so on. The upshot: **a new module gets statistics without any change to
  the app**, and games, films and books — which had none until now — show up
  on their own. Only modules you actually track appear, and a figure that would
  read “0” is left out until there is something to count.

### Notes
- Purely a computed view — nothing new is stored, and it counts only confirmed
  data, the same rule the achievements follow.

## [0.29.0] – 2026-07-20

### Added
- **🔑 Sign in without an identity provider.** Set `AUTH_MODE=local` and
  Life-Dash offers plain email-and-password accounts — no Authentik, Keycloak
  or the like required. On first visit you create an account and it becomes the
  administrator; further accounts are made under Settings → Users, and everyone
  can change their own password. This is now the simplest way to get started,
  and it is the groundwork the public demo and 1.0 stand on.
  - Passwords are hashed with **scrypt** and a random salt per password; the
    plain text is stored nowhere.
  - A wrong password and an unknown email give the **same** answer, so the
    login form cannot be used to find out which addresses have accounts.
  - Repeated failed attempts **lock that account for a while**, to blunt
    password guessing.
- **A gentle first-run form.** On an empty account the “Today” view offers to
  enter a birth date and home town, which become your first real entries. The
  birth date is recorded as a “Birth” milestone — an ordinary event, the same
  one the statistics already read your age from, and the one a future
  “age at each event” feature will use. Entirely optional and skippable.

### Notes for self-hosters
- New setting **`AUTH_MODE=local`** (the new default in the example config).
  OIDC continues to work unchanged with `AUTH_MODE=oidc`. Either way,
  **`SESSION_SECRET` must be set** — it signs the session cookies, and the app
  now warns at startup if it is still the placeholder.
- The Compose file no longer forces `OIDC_ISSUER`/`OIDC_CLIENT_ID` to be
  present, so a local-account setup starts with just `SESSION_SECRET` and
  `PUBLIC_BASE_URL`.
- One database column was added (`users.password_hash`, empty for OIDC/dev
  accounts) — applied automatically on start.

## [0.28.1] – 2026-07-20

### Fixed
- **The two “Today” tiles did nothing.** “Capture something” and “Go to the
  timeline” had no effect — the click handler was wired only to the statistics
  view, so the tiles added in 0.28.0 were never connected. Both work now, and
  so does “Waiting for review”.
- **Immich photos now hang on the individual days of a trip, not on the trip
  itself.** For a multi-day trip that has day sub-entries, the pictures belong
  to each day (exactly as the weather already does) — previously the first
  twelve landed on the trip and none on the days. If a trip has no day
  sub-entries, it still gets the photos as a whole. (You may want to discard the
  Immich links and run “link photos” again to move existing ones onto the days.)
- **A brief 502/503/504 from Immich no longer aborts the whole run.** A reverse
  proxy in front of Immich returns those under load or during a restart; Life-
  Dash now waits a moment and retries instead of stopping. The limit of twelve
  pictures per entry is unchanged — with photos now landing per day, that is
  twelve per day rather than twelve for a whole trip.

### Changed
- The release workflow uses the current GitHub Actions versions (checkout v6,
  the Docker actions v4/v6/v7), which run on Node.js 24 — clearing the
  deprecation warning about Node.js 20.

## [0.28.0] – 2026-07-20

### Added
- **🕰️ A “Today” view.** The look-back moved out of the timeline into a place
  of its own, together with what is waiting for you: how many suggestions need
  reviewing, how many entries you have and the span they cover, and a shortcut
  straight to capturing something. It is the view the app now opens on.
- **Delete my own data.** Every account can now remove everything that belongs
  to it — entries, items, places, routes, weather, uploaded photos and the raw
  inbox — without touching anyone else's data, and without needing an
  administrator. The account itself stays. It asks you to type a word first,
  and it really is irreversible, so take a backup with photos beforehand.

### Changed
- **The look-back stays a look-back.** It now shows at most three entries per
  year and says how many there were in total (“+9 more”), and it leaves out
  imported location visits. A day five years ago can hold thirty of those, and
  they were burying the memory the block exists to show.
- **Long-running actions leave a trail.** Building a backup, restoring one and
  deleting data now report their progress to the log as they go, table by table
  and file by file, instead of falling silent for minutes. Without that, a slow
  run and a stuck one look exactly the same.

## [0.27.0] – 2026-07-20

### Fixed
- **In English, several settings simply were not there.** The export options,
  the import threshold for uncertain visits, the building blocks for address
  formatting and the tracking selection all vanished as soon as the app was
  switched to English — the translation replaced the whole block they lived in,
  controls included. Broken since the app became bilingual in 0.20.0, which
  means the English version has never been fully usable. All of them are back,
  and a check now makes this impossible to repeat.
- **The weather record counted entries instead of days.** After a timeline
  import a single day holds dozens of visits that all share one weather
  reading, so a year could show more than 600 “rainy days”, the total hours of
  sunshine were multiplied by the number of entries per day, and the warmest
  trip was skewed towards whichever trip had the most entries. Everything in
  that panel now counts **calendar days**: one reading per day, taken from the
  earliest entry of that day that carries weather.

### Changed
- **The backup options now point the same way.** Both ticks mean “include”:
  *include photos* and *include imported Google timeline data*, both on by
  default, so the complete backup is what you get without thinking about it.
  Previously one tick added and the other removed — two lines apart.
- **Something visibly happens while data is loading.** A slim bar at the top of
  the window appears whenever a request is in flight, and the timeline shows
  placeholder cards while the first (potentially large) response is on its way.
  Quick requests do not flash it. This does not make anything faster — a very
  large database still takes its time — but waiting no longer looks like a
  crash.
- The Immich settings now say **which permissions the API key needs**:
  `asset.read`, `asset.view` and `server.about`. A key limited to those cannot
  delete or upload anything in Immich.

## [0.26.1] – 2026-07-20

### Fixed
- **The jobs table stayed empty as soon as any job existed** — so “link photos”
  looked as if it had done nothing, when in truth the job had started, run and
  finished. This affected **every** kind of background job (weather, place
  names, embeddings, recomputation), not just the new Immich one, and had been
  broken since 0.20.0 when the app became bilingual. Two other places had the
  same defect: an error message after changing a user's role or deleting a
  user, and the confirmation after deleting a row in the raw database view.
  A check now guards against this class of mistake so it cannot come back
  unnoticed.
- **A hint box in the settings overlapped the fields next to it** — the note
  about the stored Immich key, and the one about map attribution, were laid
  out as inline text but styled as boxes, so they covered their neighbours.

## [0.26.0] – 2026-07-20

### Added
- **📦 One file that really is your backup.** The export can now produce a
  **ZIP containing your data *and* your photos** — tick “with photos” under
  Settings → My data. Importing that archive brings everything back: entries,
  places, weather, and the image files themselves, previews included. This
  closes the gap that arrived with photo uploads in 0.24.0.
- **Restoring is repeatable.** Import the same archive twice and nothing
  changes — existing entries and existing files are recognised and skipped.
- The plain JSON export stays exactly as it was, and stays the right choice
  if you back up your media folder some other way: it is small, readable and
  easy to diff.

### Fixed
- **“Delete all data” has been broken since v0.9.0** and returned a server
  error instead of doing anything. It was never covered by a test; the full
  backup-and-restore run built for this release finally exercised it. It works
  again, now removes the image files along with the entries, and is covered by
  tests from here on.
- **Restoring on a different instance would have orphaned your photos.** Image
  records kept the *original* account's identity instead of being handed to the
  account doing the import, so after a restore the pictures belonged to nobody
  and could not be shown.

### Notes
- The archive is **streamed** in both directions — neither the export nor the
  import ever holds the whole thing in memory, so a library of many gigabytes
  works on a small machine.
- Previews are not stored in the archive (they can be rebuilt from the
  originals) and are regenerated during the import — the export stays smaller
  without losing anything.
- **Immich pictures are not in the archive.** They live in Immich and are
  backed up there; only the link is exported, and it can be rebuilt at any
  time.
- Archives are treated as foreign data: entries that try to escape the media
  folder are refused, and every file is verified to be an actual image before
  it is written.

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
