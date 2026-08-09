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

**Everything built so far is in daily use by its author, and nobody else.** All
of group A (A1–A48) and group B through F21 are done, along with the Immich
connector in all three stages, the Google Timeline import, weather enrichment,
achievements, the residence and the gap report. The record of what
each release contained is in [Appendix A](DECISIONS.md#appendix-a--what-was-built-and-when).

Work currently accumulates on `main` **without a version number**. The
`:main` image is what the author runs; a SemVer tag exists so that a *user*
can tell two states apart, and until publication there is exactly one operator,
who does not need a number to test.

---

## 2. Two rules that decide where a package sits

**Only new import connectors wait for the 1.x line.** 1.0 is defined by
exclusion as *the complete tool for capturing and exploring a life by hand* — a
connector widens the intake, not the concept. A package that improves capture
or exploration is therefore not a 1.x candidate at all; it belongs before 1.0
or nowhere.

**An inserted release needs a schema consequence *and* an observed complaint.**
Anything else rides on `main` with no version of its own. A version number is
for a difference a user would notice on upgrade.

Effort: **S** = hours · **M** = about a day · **L** = several days. No package
blocks another except where stated.

---

## 3. Ahead of 1.0

### R1 — ready for publication · L

The gate before any promotion. **Part a is built** (note 203); six left, in order:

| | Part | Why it is in the gate |
|---|---|---|
| **b** | **Screenshots and a short GIF in the README**, plus the “why not X” comparison | The one thing a stranger looks at before deciding to install. |
| **c** | **A genuine one-command start** — `docker compose up` against versioned ghcr images instead of a local build | “Ten minutes from zero to a populated instance” is the 1.0 promise; a build step breaks it. |
| **d** | **Hardening** — `AUTH_MODE=dev` impossible to start accidentally in a production-shaped environment · no secrets in logs · pinned base images · Dependabot · `SECURITY.md` | The dev mode is the sharpest edge currently shipped. |
| **e** | **Project files** — `CONTRIBUTING.md` stating this is a single-author project not currently accepting pull requests · issue templates · questions to Discussions · a short “what this project deliberately does not do” | Says no once, in writing, instead of once per stranger. |
| **f** | **A tested upgrade path** from an older database | Migrations become promises the moment strangers run this. Until then they are only convenient. |
| **g** | A discreet **donation link** in the README — deliberately **not** in the app interface, and deliberately not before there is something worth funding | |

### R2 — a documentation site · M

The README has quietly become the only entry point and is doing three jobs:
the pitch, the installation, and a step-by-step guide in a deliberate order.
That is two jobs too many for the page a stranger judges the project by.

**MkDocs Material, built from Markdown in this repository, served by GitHub
Pages** — no web space needed, and a custom domain can be put in front later.
Not Docusaurus: that is a Node/React build with a four-figure dependency count,
and this project has no build step and no npm in the application at all.
Versioned docs, i18n and React components in pages are precisely what it does
not need before 1.0. Shape: overview · install · features · guides ·
administration · development.

> **The real risk is not writing the pages, it is the second copy.**
> `.env.example` is the setup reference, the README carries the sensible
> order, the CHANGELOG carries what changed, the module YAMLs carry the
> categories. A site that repeats any of them creates a second place the same
> fact can be wrong in — and documentation drift is silent, which is this
> project's recurring defect rather than brokenness.
>
> **The rule is therefore: move or generate, never copy.** `DEPLOY.md`
> *dissolves into* the install section rather than being mirrored by it; the
> settings page is checked against `.env.example` **in both directions** by a
> guard (an undocumented key and an invented key are both defects); the job
> catalogue is generated from `JOB_TYPES` rather than hand-written.
> `ARCHITECTURE.md` and `DECISIONS.md` stay out of the navigation and are
> linked from a “design decisions” page — they are working documents, and
> publishing them as documentation would turn every note in them into a
> promise.

Screenshots come last, after the demo mode, for the same reason the README's
do: taken from an unfinished feature set they would be redone every release.
Runs on `main` without a version of its own — a documentation site is the
definition of something no user notices on upgrade.

---

## 4. Behind 1.0 — the 1.x line

Narrowed to **new import sources** plus three named exceptions. Everything else
that was once parked here has moved forward.

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

Server-side speech-to-text, also for voice memos as a file. **The one package
kept behind 1.0 despite not being an import:** it is the only remaining item
that adds a heavy new runtime dependency — a model on a machine that today is a
Raspberry Pi — the browser API works meanwhile, and the demo dataset does not
render it.

### New import sources — deliberately last

| No. | Package | Effort | Content |
|---|---|---|---|
| **P4.1** | **Health Connect import** | M | Upload of the Health Connect export: steps, heart rate and workouts → `Metric`; workout GPS → `Track`. Health Connect stores on-device only, with no cloud API, so this is a file import by necessity. |
| **P4.2** | **PSN connector** | M | An NPSSO token per user, sync via `psnawp`: games → `game` entities, trophies and play time → metrics. An unofficial API can break, so the connector stays isolated and stores its results as fragments. **Steam belongs here too** — its official Web API is stable and needs no hub. |
| **P2.8** | **Live location via OwnTracks/Overland** | M | A compatible receiving endpoint with a token per user: phones push location continuously, and visits and tracks are built from it as in the timeline import — the same condensation and duplicate rules. The manual Google export ritual eventually disappears. **Dawarich is deliberately not run alongside** (no second service, no duplicated data); it serves as a format reference. |
| **P2.10** | **Media consumption via Trakt as a hub** | M | **One connector against the Trakt API instead of six brittle ones.** Netflix, Prime Video, Disney+ and WOW have no public APIs, but established tools already push their exports into Trakt, and Jellyfin, Plex and Emby synchronise there anyway. So Life-Dash talks to one documented API and inherits the ecosystem. Watched entries become events, titles become entities, and the Trakt history ID keeps it idempotent. Escape hatch: a direct CSV upload for a Netflix history. |
| **P2.11** | **Import from Dawarich, Reitti and GPX** | S–M | The dedicated location trackers are far ahead of this map and will stay there. Instead of competing: read their exports. Both export GeoJSON/GPX, and a plain **GPX import** additionally covers watches, Komoot, Strava and every hiking app. It runs through the existing timeline-import path, not a second pipeline. |
| **P2.9** | **Import automation** | M | Once connectors exist: scheduled pulls via the job schedule, a watch folder for file exports, live push via P2.8. Rule from now on: for every new connector, automatability is considered up front. |

---

## 5. Release plan

**What 1.0 means here.** Not “feature complete” — a *promise*: the data model
is stable, the upgrade path from an older database is tested, semantic
versioning applies from then on, and a stranger goes from zero to a populated,
working instance in ten minutes. 1.0 is therefore the **publication version**;
everything that does not serve that promise is pushed to 1.x on purpose.

**Ordering principle:** features first, while the data model is still cheap to
change → then the demo dataset, which freezes what the features look like →
then hardening, packaging and the project surface. The demo data comes after
the features deliberately: seeded from an unfinished feature set, it would be
rebuilt every release.

| Version | Theme | Contains |
|---|---|---|
| **0.40.0** | **The last 0.x — whatever daily use turns up, plus the demo mode** | **The demo dataset (R1a) is built** (note 203): thirty-two invented years — five places lived in, twenty-nine trips across six continents, concerts, sightings, journal entries, imported paths, weather for every day and a collection that is deliberately not maxed out, behind one flag and without a network call. No planned feature content beyond it. Everything else that has gathered on `main` since 0.39.0 rides along. This is the release that unblocks everything public — and the only 0.x a stranger will ever see. |
| **1.0.0** | **Publication** — three stages on `main`, one tag | **(i) Hardening and operations** (R1c/d/f): `AUTH_MODE=dev` unstartable in a production-shaped environment · no secrets in logs · pinned base images · Dependabot · `SECURITY.md` · versioned ghcr images and a genuine `docker compose up` · the upgrade path from 0.40 tested end to end · backup and restore documented, media folder included. **(ii) Project surface** (R1b/e/g and R2): README with screenshots and a GIF · the documentation site · the comparison table · `CONTRIBUTING.md` · issue templates · “what this project deliberately does not do” · the donation link. **(iii) Freeze and fresh-install pass**: no new features — walk the stranger's path from an empty machine, fix what it turns up, verify every `.env.example` key is real and every documented command works. |

None of the three 1.0 stages gets a version of its own: a user notices none of
them on upgrade. Then promotion, in order: selfh.st → r/selfhosted →
awesome-selfhosted → Show HN → Fediverse/Lemmy/r/quantifiedself.

**Pace.** There is no deadline, and the plan is written accordingly: nothing
that belongs in a 1.0 is deferred to make a date.

### The version history is being cut before publication (2026-08-04)

Forty-nine tags exist across 154 commits, starting at `v0.1` — the result of
building before the two-track model existed, when a SemVer tag was the only way
to get an image onto one's own server. **Before the repository is published,
the old tags, GitHub releases and ghcr image versions are deleted.** None of
them is installable: the tested upgrade path is R1(f) and does not exist yet,
so an old image leads to a database that goes nowhere.

What survives the cut is the record, which was never the tags: the reasoning in
[`DECISIONS.md`](DECISIONS.md), the release-by-release account in its
[Appendix A.4](DECISIONS.md#a4-releases-0210--0390), and the user-facing
history in the changelog — which is archived rather than deleted at the 1.0 cut
(`CHANGELOG.md` starts at 1.0.0, everything before it moves to
`docs/CHANGELOG-0.x.md`). The git history itself is untouched: it is 28 MB, and
`DECISIONS.md` cites commits by hash.

---

## 6. Open questions

Observations from real use become **numbered notes** in
[`DECISIONS.md`](DECISIONS.md), work packages become entries in this file.
**There is no ticket system** — one truth, and the one that gets read while
working.

**Nothing is currently open.** When a question is answered it keeps its answer
in the index rather than vanishing from it: a question that disappears the
moment it is decided takes with it the fact that it was ever asked. The
answered ones are listed with their resolutions in `DECISIONS.md`.
