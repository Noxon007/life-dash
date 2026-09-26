# Life-Dash — roadmap

> **What this document is:** what is still open, and nothing else. The moment a
> package ships it leaves this file and its record goes to
> [`DECISIONS.md` Appendix A](DECISIONS.md#appendix-a--what-was-built-and-when).
>
> **Why that rule exists:** this chapter used to carry its own history, and
> three quarters of it was a list of things nobody had to decide again. A plan
> that also serves as a record cannot be read as a plan — the open half was
> only findable by scrolling past the closed one.
>
> What the system *is* → [`ARCHITECTURE.md`](ARCHITECTURE.md). Why it is that
> way → [`DECISIONS.md`](DECISIONS.md).

---

## 1. Where the project stands

**Life-Dash is a personal tool with exactly one operator, and it is going to
stay that way** (decided 2026-09-26, note 228). The repository is public, but it
is not a product: nothing here is built for a stranger's first ten minutes, and
there is no publication date to work towards.

All of group A (A1–A48) and group B through F21 are done, along with the Immich
connector in all three stages, the Google Timeline import, weather enrichment,
achievements, the residence and the gap report. The record of what each release
contained is in [Appendix A](DECISIONS.md#appendix-a--what-was-built-and-when).

### What that decision struck

The former release gate R1/R2 existed to get a stranger from zero to a working
instance. With no stranger, these are gone rather than postponed:

- **R1(b)** screenshots, a GIF and the “why not X” comparison in the README
- **R1(c)** a one-command start against versioned images *as a promise to
  others* — the images are built anyway (see §4), which is all one operator
  needs
- **R1(g)** the donation link
- **R2** the MkDocs documentation site. `docs/DEPLOY.md`, `.env.example` and
  the README remain the operating documentation.
- the promotion plan, the purge of the old tags, releases and ghcr images, and
  archiving the changelog at a 1.0 cut — all of them only made sense before a
  first public release

### What stays, and why

- **The hardening (R1d) stays exactly as built** — startup checks, CSP,
  security headers, log redaction, revocable sessions, the unprivileged
  container. A life database on a reachable server needs all of it, whoever
  else reads the code.
- **`SECURITY.md`, `CONTRIBUTING.md` and the issue templates stay.** The
  repository is public, and those are what a public repository should carry.
- **The demo dataset stays, as a test fixture rather than a showcase.** The CI
  job `live-check` and the measuring tools (`_measure_api.py DEMO=1`,
  `measure-timeline-chrome.js`) need a populated instance without a network;
  that was always half its job. It gets no further polish for its own sake —
  the open question about its weather running 5–7 K too cold is closed as not
  needed.

### The data: migrate by default, reset only when announced

**The project is still in its test phase** (note 231, which revises note 228).
The operated database is kept and migrated as a matter of course — but until
the operator declares the data final, a schema change that would be expensive
to migrate may instead mean *setting up fresh and importing the export*. Never
silently: a reset is proposed, with the reason, and the operator decides.

**That route is only acceptable because it loses nothing, and that was
measured, not assumed.** A real ZIP export written by v0.39.0 (entries with
place, note and entity, a multi-day trip, a fuzzy date, free-text captures, a
Google Timeline import, photos on an event and on a day) was imported into a
fresh instance of the current version: all 62 rows arrived, every shared field
identical, both photos restored with previews.
`tests/test_old_export_import.py` keeps that file and requires every future
version to read it.

What each kind of change costs:

| Change | Migration | Reset instead? |
|---|---|---|
| new column, new table | one line in `_MISSING_COLUMNS` / nothing | not worth it |
| new enum value (native type on PostgreSQL) | one `ALTER TYPE … ADD VALUE` step, first time about an hour | not worth it |
| rename, type change, restructuring a table | a hand-written, tested step | **the case for a reset** |

The guards that make the choice visible rather than silent:

- `tests/schema_snapshot.json` is the schema the operated database has *at
  least*; `test_schema_snapshot.py` migrates it and demands the model (note
  229). Red means “this does not reach the server by itself” — then either a
  migration step or an announced reset. The snapshot is rewritten only after
  the new state has run on the server (or after a reset).
- `test_old_export_import.py`: the escape hatch still opens.
- Every step runs on SQLite *and* PostgreSQL (`tools/pg-test.ps1`, CI) —
  PostgreSQL is what is operated.
- `migrate.py` stays additive and hand-written; a step that rebuilds a table
  gets a test that starts from the **old** shape (`test_f18_migration.py` is
  the model).
- Before an image with schema changes goes onto the server, and before any
  reset: the app's ZIP export *with photos* **and** a `pg_dump`
  ([DEPLOY.md §7, Backup](../DEPLOY.md#backup)). The dump is the way back to
  exactly the old state; the export is the way into a fresh one.

**When the operator declares the data final**, the reset column disappears and
migrating becomes the only route — nothing else in the setup has to change.

---

## 2. How work is ordered

**By usefulness in daily use, nothing else.** The old two-line rule (“only new
import connectors wait for 1.x”) existed to protect a 1.0 promise; without it,
every item below is simply backlog, and a package moves up when using the app
turns up a reason. Observations from real use still become numbered notes in
[`DECISIONS.md`](DECISIONS.md) first.

Effort: **S** = hours · **M** = about a day · **L** = several days. No package
blocks another except where stated.

---

## 3. Backlog

### P6.1 — a shared view across accounts · M–L

Two independent databases laid over each other: who was where and when on one
map, plus a tab for days spent together, the date of first meeting, the
furthest place per year.

**The tab is the easy half and needs no new data** — a day number plus
`Location.city` make “same city on the same day” a one-line intersection. The
half that decides everything is the `Share` row: from account, to account,
**scope** (*presence* — day and city only — / *events* / *everything*,
defaulting to presence, because none of the listed features reads a note),
granted at, revoked at. Per direction, revocable at any time, listable from one
screen, and the shared data is **read through the share at query time and never
copied**, so that revocation actually revokes and a deleted account takes its
data with it.

> **Nothing is to be prepared early.** The preparation that matters is already
> in place and consists of things this project did *not* do: no cross-account
> copying, `user_id` filtered at the query. A sharing feature built wrong is
> not a bug but a disclosure, and it is the one package here that a re-run
> cannot correct.

### F22 — the weather run asks one day at a time · S–M

`fetch_weather` sets `start_date` and `end_date` to the **same day**, so the run
makes one HTTP round trip per (place, day), strictly sequentially. A residence
period of twenty years is 7,298 requests at a **single** coordinate — near the
free tier's 10,000/day cap, and half an hour to an hour of waiting.

**An API key is not the fix and was checked before this was written.** It lifts
the open-access limits (600/min · 5,000/h · 10,000/day · 300,000/month) and
moves to `customer-api.open-meteo.com`, but a single request does not get
faster, and the paid plans are aimed at commercial use. The fix is in this
repository:

- **A date range instead of a day.** One request per residence period and year
  instead of 365 — the parameters already exist. This is the whole win for the
  residence days, where every day shares one coordinate.
- **Several coordinates per request** (`latitude=52.52,48.85&longitude=…`,
  documented) for the events, where each day has a different place.

Open-Meteo weights its quota by variables × time steps × locations, so the
**quota** use stays roughly the same; what collapses is the number of round
trips, and that is the waiting.

> **The trap this has to walk past.** The revision mark (`weather_rev`) must be
> set **per day**, including for days the batch returns nothing for — otherwise
> the endless-refetch trap gets its tenth edition, this time hidden inside a
> loop that looks like it only reads. And a request that fails as a whole must
> mark **nothing**, exactly as the single-day path does today.

Asked and deferred on 2026-08-04 (note 167's round); recorded so the measurement
does not have to be made twice.

### P5.2 — Whisper voice input · M

Server-side speech-to-text, also for voice memos as a file. Deliberately low:
it is the only item here that adds a heavy new runtime dependency — a model on
a machine that today is a Raspberry Pi — and the browser's own speech API works
in the meantime.

### New import sources

| No. | Package | Effort | Content |
|---|---|---|---|
| **P4.1** | **Health Connect import** | M | Upload of the Health Connect export: steps, heart rate and workouts → `Metric`; workout GPS → `Track`. Health Connect stores on-device only, with no cloud API, so this is a file import by necessity. |
| **P4.2** | **PSN connector** | M | An NPSSO token per user, sync via `psnawp`: games → `game` entities, trophies and play time → metrics. An unofficial API can break, so the connector stays isolated and stores its results as fragments. **Steam belongs here too** — its official Web API is stable and needs no hub. |
| **P2.8** | **Live location via OwnTracks/Overland** | M | A compatible receiving endpoint with a token per user: phones push location continuously, and visits and tracks are built from it as in the timeline import — the same condensation and duplicate rules. The manual Google export ritual eventually disappears. **Dawarich is deliberately not run alongside** (no second service, no duplicated data); it serves as a format reference. |
| **P2.10** | **Media consumption via Trakt as a hub** | M | **One connector against the Trakt API instead of six brittle ones.** Netflix, Prime Video, Disney+ and WOW have no public APIs, but established tools already push their exports into Trakt, and Jellyfin, Plex and Emby synchronise there anyway. So Life-Dash talks to one documented API and inherits the ecosystem. Watched entries become events, titles become entities, and the Trakt history ID keeps it idempotent. Escape hatch: a direct CSV upload for a Netflix history. |
| **P2.11** | **Import from Dawarich, Reitti and GPX** | S–M | The dedicated location trackers are far ahead of this map and will stay there. Instead of competing: read their exports. Both export GeoJSON/GPX, and a plain **GPX import** additionally covers watches, Komoot, Strava and every hiking app. It runs through the existing timeline-import path, not a second pipeline. |
| **P2.9** | **Import automation** | M | Once connectors exist: scheduled pulls via the job schedule, a watch folder for file exports, live push via P2.8. Rule from now on: for every new connector, automatability is considered up front. |

---


---

## 4. Versions

The two tracks stay, because they answer a question the operator has too —
*which state is running on my server?*

- **`:main`** is built from every push to `main`: for trying things out.
- **A SemVer tag** builds `:X.Y.Z`, `:X.Y` and `:latest` — a state worth pinning
  in `LIFEDASH_VERSION`.

**A tag is cut when the operator wants one**, not at a milestone. Several
packages may share a version; a version marks a difference the operator would
notice on upgrade, and every schema change is such a difference. At the tagged
commit `[Unreleased]` in the changelog must be empty. There is no 1.0 event
planned: the number stays in `0.x` until there is a reason to call the data
model stable. The natural moment is the one in §1 — when the operator declares
the data final and the reset route closes. That is a question of the data, not
of publication.

---

## 5. Open questions

Observations from real use become **numbered notes** in
[`DECISIONS.md`](DECISIONS.md), work packages become entries in this file.
**There is no ticket system** — one truth, and the one that gets read while
working.

**Nothing is currently open.** When a question is answered it keeps its answer
in the index rather than vanishing from it: a question that disappears the
moment it is decided takes with it the fact that it was ever asked. The
answered ones are listed with their resolutions in `DECISIONS.md`.
