## [Unreleased]

### Added

- **Your age, exactly.** The statistics tab now has a block showing the time
  since you were born in years, months, weeks, days, hours, minutes and
  seconds, with the seconds running while the tab is open. Each cell counts the
  whole elapsed time in its own unit — “1,847 weeks”, not “34 years and 2
  weeks”. It appears once your birth is entered as a milestone.
- **The timeline lists every year of your life at once.** In the *Year* and
  *Decade* views you no longer page your way backwards: every year that has
  anything in it is listed straight away, with its real count, and clicking one
  fetches exactly that year. Before, a page was 300 entries — which, after a
  timeline import, covers a few days and produces a single heading, so the list
  stayed too short to scroll and reaching 2004 meant pressing “load older
  entries” a hundred times. The count beside each year matches what you have
  switched on: hide the automatically recorded entries and the year says how
  many are left, not how many exist. Paging still works exactly as before in
  *Day*, *Week* and *Month*, where there is no such overview to build.
- **The residence can be switched off in the timeline.** Until now the
  derived days were always there — in a year without any entries the timeline
  consisted of nothing else, and there was no handle. The switch says how many
  days it is contributing, and it sits in the same place in both views.
- **Map and timeline now have one row of switches instead of two.** *Layers*
  and *Categories* looked like two questions side by side and were a question
  and its sub-question: the category chips only ever filtered what the *By
  hand* switch turned off as a whole, so switching every category off and
  switching *By hand* off were two ways to the same result. Now one row —
  **What is on the map** / **What the timeline shows** — lists everything that
  can appear, each with the mark it carries, plus *all* and *none* for the
  whole row. *By hand* is gone; the categories are that switch. Nothing is
  fetched that you have not asked for: with no category picked, your own
  entries are not requested from the server at all, exactly as before.
- **On a phone the map can be paged without opening the filters.** The button
  that names the period now has ‹ and › beside it, so a day or a week is one
  tap away — until now both arrows sat inside the collapsed panel, and with
  the panel open the map is half the size. At the first and last period the
  arrows say so instead of quietly doing nothing.
- **Place names in Greek or Cyrillic script are now written out in Latin
  letters.** OpenStreetMap only has a German or English name for the well-known
  places; a lane on Antipaxos or a chapel near Gaios has just its local name,
  and until now that name stayed as it came — unreadable in the timeline, and
  reported again by every single run of *Resolve place names*, because asking
  once more could never change it. They are now transliterated (ELOT 743, the
  same spelling Greek street signs and passports use): “Ελευθερίου Βενιζέλου”
  becomes “Eleftheriou Venizelou”, “Αγία Κυριακή” becomes “Agia Kyriaki”. **A
  name OpenStreetMap does have keeps precedence** — “München” stays “München”
  and does not become “Minchen”. Scripts without a table (Japanese, Arabic,
  Hebrew, Thai) are left out of the name instead, but only while something
  remains that still names the place: if only the country would be left, the
  original name stays, because a place you cannot read is still better than a
  place called “Japan”. Cities are spelled the same way everywhere, so the
  collection no longer counts one town twice. Existing places are fixed by the
  usual *Resolve place names* run and without a single lookup — the address
  parts are already stored, so it is arithmetic rather than a request.
- **Everything that takes a moment now says so, the same way everywhere.** One
  progress panel over a blurred page: what is running, what it is doing right
  now, how far along it is, roughly how much longer, and a cancel button. It
  covers the backup import, the Google Timeline import, the AI analysis and
  every view that has to fetch something — including “Today”, which used to keep
  filling itself in after the page already looked finished. Cancelling stops
  between steps and keeps what has been done; starting again continues from
  there. Short waits are unaffected: the panel only appears once something takes
  longer than a third of a second, so a quick view change looks exactly as it
  did. Runs that continue on the server when you close the page — weather, place
  names, recompute, Immich — are unchanged and stay in the *Jobs* tab, which is
  now the actual dividing line: **the Jobs tab is what survives closing the
  page; the panel is what does not.**
- **The place names that cannot be resolved are now listed by name.** “9
  unresolvable” was true and led nowhere — running again gives the same nine,
  because a spot OpenStreetMap does not know will not be known tomorrow either.
  *My data → Place names* now lists them with their coordinates, a link to that
  point on the map, how many entries hang there, and the reason: never asked
  yet, asked and nothing came back, name in a foreign script, or an answer that
  does not fit your chosen format. **You can type the name yourself** — a forest
  hut, a field track, a plot with no address — and a name you typed is never
  overwritten by a later run. The visits at that place are renamed with it.
- **Pick a place on the map instead of typing its name.** A 🗺️ button sits next
  to the place field when you record something, when you edit an entry and when
  you enter a residence: click the map, and *that* point is what gets
  stored — the address is looked up afterwards and is only the label. Typing a
  name still works exactly as before, but then the name is the statement and the
  coordinate is looked up from it, which puts the entry at whatever point
  OpenStreetMap has for that name, usually the middle of the town rather than
  the house. It also makes places that have no findable address possible at all:
  the hut in the woods, the parents' house on a road the map does not know. That
  matters most for a residence, where a missing coordinate means
  thousands of derived days never get their weather. Edit the name afterwards
  and the picked point is released again — otherwise the field would say one
  thing and the stored point another.
- **A “Gaps” view in the statistics: where do you know nothing at all?** The
  fourth tab beside Numbers, Charts and Rankings answers the one question a life
  database cannot answer by looking at what it has. It shows how much of the
  period is accounted for, how much of that is recorded versus derived from a
  residence, a coverage bar per year, and the longest stretches with
  nothing in them. **Clicking a stretch carries its dates into the residence
  form** — a gap is empty by definition, so jumping into the timeline there
  would show nothing, while one residence period can fill a hundred days at once.
  If you have entered your birth as a milestone the view covers your whole life;
  if not it covers only the period you recorded in, and says so rather than
  quietly reporting a smaller number as if it were the whole story.
  “Longest gap” in the rankings is now the first row of that list — the same
  computation, so the two can no longer disagree at the edges.
- **Residence periods show on the map too**, as their own layer with its own
  switch (🏠 Residence). **One mark per period, not per day** — six years at your
  parents' house are two thousand derived days at a single coordinate, and
  drawing them individually would be a dot with weight rather than a map; the
  number of days is in the popup. A period appears in every view its span
  overlaps, as the same teardrop the map uses everywhere else but in a colour
  of its own, so what was inferred never looks like something you recorded.
  **Years in which only the residence exists can now be reached.** The map's
  period strip used to be built from entries alone, so 1993 — a year with a
  residence and nothing recorded — could not be selected at all, in any
  zoom level: the one layer that had something to say about that year was
  unreachable. Day, week, month, year and decade now all offer those periods,
  the map moves to the mark instead of staying where the last period left it,
  and the list beside the map names the place rather than reporting “0 stops”.
- **A residence for the years you never recorded.** Under *My data →
  Residences* you enter a period and a place — “from my birth until 2006
  I was at my parents' house in Bad Segeberg”. Every day in that period that has
  **no** entry then counts as a day at that place: it appears in the timeline,
  counts in the statistics, on the world map and towards the badges, and gets
  its weather on the next weather run. Twenty years of “nothing recorded” become
  twenty years of “here, and this is how it was”.
  **No entries are created for this.** The period stays a single row, so
  correcting it later recomputes everything instead of leaving thousands of
  wrong entries behind that nothing is allowed to touch. A day with a real entry
  always wins, periods may not overlap, and every derived day is visibly marked
  as derived — in the timeline, in the year summaries and in the numbers beside
  them, a derived day is a *day* and never an *entry*.
- **Every geotagged photo now becomes an entry of its own — on the map with
  its picture, in the timeline as plain text.** Until now a whole day with
  photos in one place became a single summary entry (“34 photos in Detmold”),
  while a separate, switchable layer drew the individual dots. Two mechanisms
  for the same pictures, and the map could not decide which one it was showing.
  Now there is one: “Events from photos” under *My data → Immich* creates one
  confirmed entry per picture, exactly the way an imported Google visit has
  always worked. **On the map** you get a dot where the picture was taken, with
  a thumbnail in its popup. **In the timeline** you get the fact and not the
  picture — “Photo in Detmold”, with same-day-same-place rows folded into one
  (“12× Photo in Detmold”). That is deliberate: twelve thumbnails per row
  across twenty years is a wall, not a memory, and the pictures of a day are
  already in the photo strip above.
- **The photo layer has its own switch now.** “🛰️ Auto-detected” covers Google
  visits, “📷 Photos” covers Immich — with its own count each. They used to
  share one switch, which made sense while both produced roughly the same
  number of rows; with hundreds of visits against tens of thousands of photos
  it no longer does.
- **A clean-up button for the old photo-day summary entries.** It appears only
  if you have any, shows you which entries it would remove before it removes
  anything, and touches nothing else. Your photo entries and everything you
  entered by hand stay exactly where they are.
- **Days lead, entries stand beside them.** The world tab, top places, most
  visited cities and the city pages now show *how many days* you were
  somewhere, with the entry count in small type next to it. With mass imports
  in the picture, “312 entries in France” had quietly become a statement about
  the import rather than about France — thirty visits in one day are one day.
  Both numbers stay, because “how many films did I watch” still wants entries.
- **Clicking a weather record now takes you to that day.** The “hottest day”
  tile and its siblings used to open the edit dialog for whichever single entry
  happened to carry the reading. They now narrow the timeline to the whole day,
  with a chip that names the date and the reason and can be clicked away again.
- **The collection can be sorted — by days or by name.** It was always
  alphabetical, which at three hundred cities is no order at all: the first
  screen showed whichever places happen to start with A. The choice is
  remembered and applies to every tab.
- **Every collection tile now leads with days.** Countries, animals, artists,
  dishes — all of them read “40 days · 41 entries” now, the way cities and the
  world map already did. “11 203 entries in Germany” was a statement about your
  photo library, not about your life; both numbers stay, because “how many
  films” still wants entries.
- **The statistics tab is now three views.** *Numbers* (all the tiles),
  *Charts* (the bar charts) and *Rankings*. It used to be one page with forty
  tiles, six charts and two panels at once — everything present, nothing
  emphasised. Your choice of view is remembered.
- **Rankings: the top ten instead of just the record.** Every weather tile —
  hottest day, strongest gust, shortest day — now has its full top ten behind
  it, and clicking a row takes you to that day. Plus top places, cities,
  countries, years and categories by days, and your longest streaks: the
  longest run of consecutive days with entries, the longest gap without any,
  and your longest recorded trip.
- **A demo mode: an invented life, thirty-two years of it, behind one switch.**
  `SEED_DEMO=true` fills a fresh instance with around 8,500 entries — five
  places lived in, twenty-nine trips across six continents, concerts, meals,
  animals seen, journal entries, imported paths, weather for every day and a
  collection of achievements that is emphatically *not* maxed out. It takes a
  few seconds and needs no internet connection at all: the weather is invented
  too, plausible for the latitude and the season, and the same every time it is
  built. It comes with about 460 pictures, so the photo strips, the lightbox,
  pictures on a day and the photo statistics have something to show — they are
  generated colour fields with the place and date written across them, and they
  say “Demo-Bild” on their face, because an invented picture that looked like a
  real photograph is not something a life database should put in front of you.
  Everything and everyone in it is fictional. It only happens on a fresh
  instance in development mode, and never on top of data you already have.
- **Kilometres from your imported paths — in a tab of their own.** *Statistics →
  Paths* adds up what the Google Timeline import brought: your total distance,
  split by mode of travel and by year, and the longest single paths. Those
  figures had been sitting in the database since the first import and were never
  added up. They live in their own tab, with the warning above them rather than
  below, because they are the only numbers here that do not come from what you
  recorded: no phone in your pocket means no journey, the mode of travel is
  Google's guess, and a year without an export looks exactly like a year you
  spent at home. Useful as an order of magnitude, not as an odometer.
- **Three more things your data already knew.** *How long* it rained is now a
  record of its own beside *how much* — a downpour of twenty minutes and a
  drizzle lasting eighteen hours can bring the same millimetres. **Your photos**
  finally have a summary: how many there are, how many you uploaded yourself
  against how many are linked from Immich, how many of your entries carry a
  picture (with the total beside it, not just the count), the oldest and newest,
  and the days with the most. And **how far you have ever been from home** —
  measured against the residence that applied *on that day*, because a centre of
  life moves; plus how many countries and cities each year of your life touched.
- **Timeline and map: what evidence and what is proven now look different.**
  Photos and visits found by Google or Immich are evidence — they used to
  appear as “unconfirmed” cards mixed in among your confirmed entries. They no
  longer do: a proposal only joins the timeline once you have actually
  confirmed it in moderation. Until then, a small hint (“N proposals waiting”)
  links there instead of showing the card itself. The photo and visit layers
  themselves (toggled on/off) are unaffected — they were never proposals to
  begin with, just evidence of where you were and what was photographed.
- **Year and decade view now group by month and year instead of listing every
  card.** A year used to list every single entry — and once a repeated
  location visit spans more than a single day, sorting it purely by time
  and bundling it by place pull in different directions, so the more a year
  or decade condensed imported visits, the less the order actually held. Year
  view now shows one row per month (event count, day count, main place),
  decade view one row per year; clicking a row expands it — a year's row into
  its months, a month's row into the familiar day-by-day view with its photo
  strip.
- **Immich: a day with enough photos in one place becomes a confirmed entry
  directly — the same way an imported Google visit always has.** Until now it
  became an unconfirmed proposal that needed a separate trip to Moderation,
  even though the two connectors are the same kind of evidence (a machine
  measuring where you were). The mandatory preview before creating anything is
  unchanged — if anything it matters more now, since there is no review step
  left afterwards. Everywhere Google visits were hidden by default, bundled per
  day and place, and counted (“🛰️ N automatically detected”), Immich photo-day
  entries now are too, so this does not flood the timeline with individual
  cards. Albums are no longer offered as a source at all (they were off by
  default already); the Immich API key this connector asks for now needs four
  read-only permissions instead of five.
- **A greeting on the Today page.** A short line at the top now greets you by
  time of day and name and shows today's date, above the “on this day” look-back.
- **“In the timeline” button on every collection entry, not just cities.**
  Opening a country, animal or artist in the collection now offers the same jump
  into the timeline that city pages already had.
- **System tab: links to the API docs and the health page.** A small
  “Diagnostics & links” block points to the interactive API (`/docs`) and the
  one-line status page (`/health`) — the latter is the right target for an
  uptime monitor.
- **“My data”: each section now says what it does to your data.** Every step
  carries a small coloured badge — *setting*, *creates proposals*, *enriches*,
  *changes confirmed data*, *read only*, *writes*, *deletes for good* — the same
  idea the Immich block already used, now across the whole page.
- **“All years” for both Immich runs.** Locating photos and suggesting entries
  could only be done one year at a time, which for a twenty-year library meant
  twenty rounds of the same handful of clicks. Both now offer *All years* as an
  entry in the year picker. Locating photos simply works through them in the
  background, ticking off each year as it goes, and can be stopped at any point
  — everything already done stays done. Suggesting entries keeps its rule that
  nothing is created before you have seen it: the preview walks the years one by
  one, shows a running total while it does, and can be cancelled — and the run
  is then given exactly the years the preview covered.
- **“My data” now shows what is running, right where you started it.** A strip
  at the top of the page names the current run, its progress and a stop button,
  and the last finished run stays there with its result. Starting a run no
  longer jumps to the Jobs tab.
- **The timeline's day heading now carries the weather of that day.** Until now
  the weather only ever sat on individual cards, so a day with several imported
  visits showed whichever of them the condensation happened to pick — and a
  bundled card (“4× Home”) showed no weather at all. The day now says it once,
  in one place, and days that touch more than one weather region say that too
  instead of passing one of the values off as “the” weather.

### Changed

- **The five statistics views are now laid out alike.** *Numbers*, *Charts*,
  *Rankings*, *Gaps* and *Tracks* each set their own spacing, so switching
  between them felt like switching between five pages: blocks sat flush against
  each other in some views and far apart in others. Every view now uses one
  spacing, every block on them is a panel with a heading — including the two
  tile groups, which now say what they show (*Overview* and *Weather records*)
  instead of running into each other as one long set of numbers. In *Gaps*,
  *Coverage per year* and *Longest gaps* now stand side by side at the same
  height and both scroll after ten rows, like every other ranking; before that,
  one of them grew to forty rows next to a neighbour that stopped at ten. *What
  is missing* also shows its share as a bar, so “7,298 of 12,437 days” can be
  read without doing the arithmetic.
- **“Farthest from home” no longer scrolls inside itself.** It stands alone
  across the full width, so there was never a neighbouring panel it could have
  stretched — the scrollbar hid rows for no reason. It now uses that width:
  each place you have lived is its own block, and the blocks stand side by side
  as long as there is room and underneath each other when there is not. The
  panels that share a row still cap at ten rows, because there the point is
  that neither pulls the other out of shape.
- **The statistics tab was made to fit a phone again.** Nothing scrolls inside
  a panel any more — on a screen showing one panel at a time there is nothing
  to line it up with, and a box that scrolls inside a scrolling page is easy to
  get lost in. The panels have narrower margins and the figures are a size
  smaller, so a tile has as much room for its label as it had before the panels
  arrived.
- **A general polish of the interface.** Cards, panels and dialogs now sit on
  their background with a slight shadow rather than a single hairline — most
  noticeable in the light theme, where a white card on light grey used to be
  hard to make out. Tabs respond to the mouse pointer, buttons respond to being
  pressed, all figures use fixed-width digits so columns line up and the ticking
  seconds no longer make the age cell wobble, and percentages no longer wrap on
  narrow columns. Between about 860 and 1150 pixels wide, the tile grids use
  three columns instead of four — four fit arithmetically and cut the labels in
  half.
- **“Farthest from home” now answers the question for every place you have
  lived.** It used to be a single line for your whole life, and that only ever
  described the residence you happened to travel furthest from. You now get the
  three furthest destinations **per residence**, with the period beside it — the
  longest trip from your parents' house is a different piece of information from
  the longest trip from where you live today, not an earlier draft of it. A
  residence with nothing recorded says so rather than being left out.
- **The “Moves” tile is now “Residences”.** It used to count milestones whose
  text contained “moved”, so it read 0 for most people while several flats with
  date ranges sat under *My data*. It counts those rows now, and clicking it
  takes you to the form where you enter them.
- **The loading views say what they are doing instead of counting.** *Statistics
  → 3 / 4* never moved, because one of the four requests takes longer than the
  other three together — a number that looks like a promise about the remaining
  wait but is not one. Every view now names what it is working on in a sentence,
  including the collections, the world map and the badges, which previously
  showed nothing but their own title. Long runs that really do have a known
  amount of work — backup import, timeline import, discarding photo events —
  keep their bar and their *X of Y*.
- **The Immich run counts its two phases separately.** The progress used to read
  “241 events and months checked”, which is a total over two different things
  and tells you neither. It now says “2 events checked” while it works through
  your entries and starts again at “12 months checked · ~228 to go” for the
  library pass.
- **The two Immich runs are now one.** *Link photos* and *Create events from
  photos* were separate buttons with a year picker and a mandatory preview
  between them — and they asked Immich the same question, each answering half
  of it, so whether a day ended up with pictures depended on which run had gone
  last and how far. One button now walks your whole library: every photo of
  yours with coordinates becomes an event, and **all** photos are attached to
  their calendar day. The first run takes a while and keeps going in the
  background; after that it only touches months whose photo count has changed.
- **The preview before creating photo events is gone.** It asked you to look at
  a year's worth of proposals before the run was allowed to start, which in
  practice nobody does with thousands of them. Instead there is a way back:
  *Discard photo events* removes everything the run created, and it asks with
  the number first. Discarding the photo *links* is separate and stays
  question-free — those are only references, and the next run rebuilds them.
- **Discarding photo events now shows what it is doing.** It used to delete
  everything in a single request: the page just sat there, sometimes for
  minutes, with no way to tell whether anything was still happening. It works in
  batches now and shows the same progress display as the other long runs —
  a bar, *X of Y*, a rough time left, and a stop button that takes effect
  between batches without bringing back what is already gone. It also appears in
  the *Jobs* tab while it runs. *Discard links* is a single step and cannot be
  broken up, but it no longer leaves you guessing either: the page dims and says
  it is working.
- **The bundled demo now shows the things it ships with.** The invented life
  used to consist entirely of single days, so *Longest trip* stayed empty, no
  trip had day entries under it, and *Split multi-day* found nothing to do.
  Trips are now a period with their days beneath them, and a few imported stays
  are left whole so that button has something to demonstrate. Everyday
  places — the market, the station, the swimming pool — repeat instead of
  being a new random point each time, which is both what a location history
  actually looks like and the reason the place ranking now reads as a ranking:
  87 places instead of 3,675, of which all but a handful have real names. The
  handful that do not are what *Resolve place names* is for, and it now
  offers them instead of reporting nothing to do. Invented weather got a
  proper spread as well: the windiest day in thirty-two years was 36 km/h in
  every build, because that was the highest value the generator could produce.
- **“Baseline location” is now called “residence”.** The old name described the
  mechanism — a fallback for days nothing else says anything about — rather than
  the thing you actually enter. It also makes the point of it legible: enter
  every place you have lived, leave the last period open-ended, and every day
  from your birth to today is covered without anything to maintain. Only the
  wording changed; your periods, the days derived from them, and the rule behind
  them are untouched. A day with any entry on it still belongs to that entry and
  not to your residence.
- **A new mark: a bee.** It forages, stores what it brings in cells, and dances
  the location of where it has just been — collecting, keeping each thing as its
  own record, and saying *where*. The honeycomb beside it stands for the
  collection rather than the collecting and turns up where the app talks about
  what has been gathered. Both are explained in the README. If your browser or
  phone still shows the old symbol, it is coming from the offline cache and will
  be replaced on the next visit.
- **The map's layer buttons count the period you are looking at.** They used to
  name the whole database — “🛰️ 13,291 auto-detected”, in a month that holds
  forty of them. Each button now says how much of its layer is on the map right
  now; the total is still there, in the tooltip. A layer you have switched off
  reads zero, because that is how much of it you are seeing.
- **The map starts by showing everything.** Every point on its own instead of
  merged bubbles, all layers and categories on, photos included — and the
  connecting line between places *off*, because over a thousand points it is a
  tangle rather than a route. Photos were off by default because they used to be
  tens of thousands of individual map markers; they have been drawn on a single
  canvas for a while now, so the reason had gone and only the habit was left.
  Everything is still one click away, and a choice you make is remembered.
- **The first-entry form asks for your place of birth, not your home town.** A
  home town is a period of time, and periods of time belong to the residence
  location, which has proper from/to dates and a view of its own — as a dateless
  milestone it landed nowhere in the timeline and counted as a “move” in the
  statistics. Date and place of birth now make **one** entry, because that is
  what they are.
- **Long-running actions show their numbers everywhere.** The weather run, the
  place-name run, the AI passes and the recompute already knew how far along
  they were; they only ever told the button, which is the one thing you do not
  look at while waiting. They now use the same panel as the timeline import:
  bar, “34,523 / 39,662”, an estimate, and a line saying what is happening.
  Switching an admin tab or a view shows what it is fetching, too.
- **Both delete buttons ask for the same word.** “My data” wanted `LOESCHEN`,
  “System” wanted `LÖSCHEN`. Both now ask for the word in your interface
  language — `LÖSCHEN` in German, `DELETE` in English — and the server accepts
  either along with the umlaut-free spelling. A typed confirmation is a brake
  against a misclick, not a password, and a brake you cannot operate on your
  keyboard is a wall. The system-wide delete is also checked by the server now,
  not only by the browser.
- **The effect badges under *My data* all sit in the same spot now** — at the
  right-hand end of the heading of whatever they describe. They used to be in
  three different places (beside the section heading, at the end of a card
  header, and underneath a button), so the one label that tells you what a run
  will do to your data had to be hunted for each time.
- **Less text.** The explanation of why photo albums are not used as a source is
  gone, along with the sentences that described how earlier versions behaved.
- **A residence period is no longer cut off after its label.** “Elternhaus ·
  Mözen, Deutschland · 25.9.1991 – 25.9.2011 · 7,298 days” shared a 105-pixel
  column with the bar charts, so everything after the name disappeared.
- **The map draws every point now — the 300 limit is gone.** “Every point” used
  to stop at 300 and tell you how many it was hiding. That was never a limit
  about your data: each entry was drawn as a marker *plus* a numbered circle on
  top of it, and fifteen thousand entries meant thirty thousand things for the
  browser to keep alive. The photo layer next to it had been drawing twenty
  thousand dots without that cost for a while; the entries use the same
  approach now, so there is nothing left to leave out and nothing left to
  announce.
- **The sequence number only appears when “Connect in order” is on.** A number
  on every point is the caption of a line — without the line it answered a
  question nobody asked, and in year or decade view it did so on top of
  thousands of points at once. It also stops above 120 points, where numbered
  circles are a pattern rather than an order.
- **One mark per entry instead of two.** A pin and a coloured circle in the same
  spot were saying the same thing twice; the circle stayed, because it carries
  the category colour.
- **The labels above the merged bubbles are gone.** They were meant as a bonus
  for the biggest ones and became a row of overlapping boxes exactly where the
  map is busiest. The name is in the popup and in the list beside the map.
- **Merged points are a teardrop now, sized by how much is in them.** A place you
  went to fifty times draws a bigger mark than one you went to twice, in the
  colour of whatever you mostly did there — and its tip sits exactly on the
  place, so a big mark still says *here* rather than *roughly here*. A single
  entry stays a round dot, so the shape tells you whether there is one thing or
  several before you read a number. The same mark is used whether you merged by
  proximity or per place, and the same size means the same count in every
  period.
- **“By proximity” and “per place” now look the same.** They were two different
  bubbles — one blue with a number from the clustering library, one in the
  colour of what you did there — for the same statement, depending only on
  which level you had picked.
- **The map's controls are rebuilt around the two questions they answer.**
  The “Display” row used to hold four different kinds of thing at once — which
  layers are drawn, a line drawn *over* them, a merge mode, and fullscreen —
  all looking alike because they were all chips. It is now **“Layers”** (where
  what you see comes from: by hand, Google, photos, paths) and **“How dense”**;
  fullscreen moved into the corner of the map. Each layer switch carries the
  colour it has on the map, so there is nothing left to decode.
- **“Merge points” became four named steps: every point · by proximity · per
  place · per city.** The old switch quietly did three different things
  depending on how far you were zoomed out — and switching it *off* was also
  what made the map hide everything past the first 300 points, which it never
  said. Now the step you pick is the step you get, the zoom level no longer
  changes what it means, and the 300 limit belongs to “every point” alone and
  is written on it. **“Per city” is new**, for the question “which cities was I
  in that year?”.
- **When the map does show a selection, it now spreads it across the whole
  period** instead of taking the first 300 by date. In a busy month that used
  to mean everything after the first few days was missing while the map looked
  complete.
- **Places you visited a lot now look like it.** A place with 59 visits used to
  draw the same marker as one with two, and the number only appeared once you
  clicked. It is now a circle whose *area* is the count, in the colour of
  whatever you mostly did there, with the name on the biggest ones. The same
  applies to the proximity clusters, which used to be near-identical bubbles
  with a number in them.
- **Photos are no longer orange.** They shared a colour with imported Google
  visits — two shades of orange for the two things on that map you most want to
  tell apart. Photo dots are cyan now, in both light and dark themes, and the
  photo switch shows the same colour.
- **Removed: the “merge map points above N” setting.** With four named steps on
  the map itself, a number in the settings page answering the same question was
  a second, invisible answer to it.
- **The map loads about half as much, twice as fast.** At twenty thousand
  entries opening the map tab moved 6.1 MB in 0.64 s; it is now 2.7 MB in
  0.19 s. Nothing was dropped: photo dots are simply sent as dots — a position,
  a time and the picture they belong to — instead of as complete entries with
  a title, a category and a place record the map never displays. What you see
  and what you can click is unchanged.
- **The concept document has been split.** `docs/KONZEPT.md` keeps what
  Life-Dash is and where it is going; the numbered decisions with their
  reasoning moved into **`docs/DECISIONS.md`**. Nothing was deleted and the
  numbering is unbroken — two audiences, two documents.
- **“Days with weather” is gone from the weather record.** It counted how far
  the weather run had got, which says something about the run and nothing about
  your life. The other three tiles are unchanged.
- **Vague dates in moderation are one block now.** The heading and a separate
  bordered box were merged into a single header with a plain sub-line.
- **Logs are clearer.** The manual “refresh” button is gone (the view already
  updates on its own every few seconds), and the text now distinguishes the two
  controls: the dropdown filters only what is *shown*, while `LOG_LEVEL` in the
  `.env` decides what the server records at all — set to `INFO`, there are no
  `DEBUG` lines for the dropdown to reveal.
- **Photo strips in the timeline now show at most twelve pictures — at every
  zoom level.** Previously a single day or a single week showed *all* of its
  photos, so a photo-heavy day could draw hundreds of thumbnails and the
  timeline stuttered. Every strip now shows up to twelve, spread evenly across
  the day or week, and says how many there are in total when it has left some
  out. Tap any of them to browse.
- **The “Delete all my data” button is easier to see.** It was a plain link
  with no background; it now sits on a red-tinted background with a red border,
  matching the seriousness of what it does.
- **The Immich section is now a numbered flow instead of one stacked panel.**
  Its three runs — attaching photos to entries you already have, proposing new
  entries from photo days, and placing photo points on the map — did different
  things but looked like one block, and two near-identical year pickers made it
  worse. Each run is now its own card in the order you use them (connect → attach
  → propose → locate), and each card carries a small badge in its header saying
  what it does to your data: *attaches* (changes nothing), *creates proposals*
  (goes to moderation), *map only* (a layer you can discard). Only one year
  picker is on show now — on “propose”, where the preview needs it; locating
  photos simply runs over all years, with the single-year choice tucked under
  *Advanced*. No run, setting or key changed — only the layout.
- **Clearer button labels.** “Start run” for resolving place names is now
  “Resolve place names”, and the two “Take a look” preview buttons now say
  “Show preview”, so each button names what it does. The *Advanced* expanders in
  “My data” also got more room to breathe.
- **“My data” reads more calmly.** Each of the seven steps kept a full paragraph
  of explanation next to its button — accurate, but a wall of text. The buttons
  now carry a single sentence of what they do; the detailed how-and-why has moved
  into the README guide (“Getting started — a sensible order”), which each step
  points to. Every step now leads with one primary button, and the controls you
  set once and rarely touch again — the import-confidence filter, the address
  display format, the one-off “cut older data into days” repair — sit behind a
  small **Advanced** toggle instead of being always open. Nothing was removed and
  no run changed — only the reading. The map and its controls are untouched for
  now.
- **The map now draws all your photo points instead of a selection.** The old
  ceiling of 5000 points per answer already bit at an ordinary collection of
  8000 located photos, so the map was condensing in everyday use while nothing
  was actually tight — and a limit that fires normally teaches you to overlook
  its message, which is the one thing it exists for. What made 5000 necessary
  was drawing, not data: each dot used to be its own element in the page. The
  dots now go onto a canvas, which moves that threshold by an order of
  magnitude, and the ceiling is a safety net at 50 000. If it ever does apply,
  the points are picked evenly across the period rather than from its
  beginning, the full allowance is used (an even step of “every second point”
  showed 4060 of 8120 while 5000 were allowed), and the note on the map says
  what you are looking at.
- **“Locate photos” now says why a picture got no point.** The run reported
  “2016 photos read, 17 newly located” and left open the one question you ask
  when reading it: what happened to the other 1999? The two possible answers —
  “my library simply carries no GPS” and “the API key points at somebody else’s
  account” — call for completely different steps, and until now they looked
  identical. The result line breaks the difference down (“without a point: 1950
  without coordinates, 40 belonging to someone else, 9 not in the Immich
  timeline”) and additionally names how many points were already there and
  unchanged — without that number a second run over the same year reads like a
  failed first one.

### Removed

- **The nightly *Embeddings* run.** It could be ticked in the job schedule, and
  every night it recomputed the search index for every single entry — one
  request to your AI provider per entry, so a grown collection meant tens of
  thousands of them. **Nothing read the result:** search has been plain full
  text for several versions, and the button that used to start this run by hand
  was taken out with it. What was left was a checkbox whose only effect was a
  bill. The calculation itself stays in place for a future search that runs
  inside the database; it is simply no longer scheduled. A tick you set earlier
  stops working on its own — you do not have to find it.
- **The `SEMANTIC_MIN_SIMILARITY` setting.** It belonged to the semantic search
  that is gone, and nothing had read it since. The `OPENAI_EMBED_*` settings
  stay, and the example file now says plainly that nothing consumes them yet.
- **The two clean-up runs for data from earlier versions:** “Advanced: cut older
  data into days” under Imports, and the Immich card “Remove old photo-day
  summary entries”. New imports have cut visits into days by themselves for a
  while, and step B replaced the photo-day summaries — the buttons were a
  changelog on screen. Their endpoints are still there if a run is ever needed.
- **The “Strongest sun” (UV) statistics tile.** It could never fill: the weather
  archive used for past dates carries no UV values at all, so the tile stayed
  empty no matter how much weather you added.
- **Four weather records that could not tell two days apart:** *Sunniest day*,
  *Longest rain*, *Longest day* and *Shortest day*, each with its ranking.
  Every one of them is capped, and the cap is what they showed — sunshine
  cannot last longer than daylight, so every cloudless day around midsummer
  ties at the same number; a day has 24 hours, and a day that rains through is
  not rare; and the length of a day is a property of the calendar, so the tile
  named the solstice no matter what happened. The rankings underneath made it
  plain: ten places, one value. Hours of sunshine still count towards the
  yearly total in the weather balance, and all the values are still shown on
  the individual entry.
- **The “Days with the most photos” ranking.** A day's photo strip holds at most
  twelve pictures, so the list showed twelve for every day in it — that is our
  own limit, not a statement about the day you took the most photos.
- **The “Build embeddings” button in the System tab.** With the AI-based search
  gone (see above), it had nothing left to do.
- **The “Go to the timeline” tile on the Today page.** It was a navigation
  shortcut dressed up as a statistic; the bottom navigation already goes there.
- **The “🧭 Vector map” background map, and its settings block.** It was the one
  map option that did nothing until you had first copied a style URL out of
  another program's admin settings, and it brought its own troubles: a slow
  first paint when the map switched to week or month, missing icons in
  third-party styles, and a dependency on WebGL that older devices do not
  offer. The three built-in maps — OpenStreetMap, topography, satellite — and
  **🔧 Custom map** for your own tile server are unchanged. If you had chosen
  the vector map, your maps quietly fall back to the standard one; the style
  URL was only ever stored on your device and needs no cleaning up. Two of the
  four map libraries the page loads disappear with it.

### Fixed

- **The page no longer scrolls sideways on a phone.** In the statistics tab the
  whole page could be pushed left and right. The age block's largest figure —
  “1,135,849,203 seconds”, one word the browser is not allowed to break — set a
  minimum width for its column, and two columns of that are wider than a phone.
  Every grid in the app shared the rule that caused it; all of them can now
  become narrower than their contents, and the age block takes its size from
  the width of your screen instead of a fixed number, so it does not have to
  break at all.
- **Adding weather to a large backlog no longer slows down as it goes.** Before
  each batch of twenty-five, the run looked through every located, dated entry
  you have — including the ones it had already finished — to work out what was
  left. The further a run got, the longer each step took: with ten thousand
  finished entries the search alone cost three seconds, and it ran again for
  every batch. It now asks the database for the unfinished ones directly, which
  takes eight milliseconds at the same size. Which entries a run picks up is
  unchanged.
- **The job history no longer shows an old run as if you could start it.** The
  entry left behind by the former *Create events from photos* run said just
  that, in German, while the English interface called it something else again
  (*Place photos on the map*). Both now name it the same way and say it is old
  and part of *Fetch photos from Immich*.
- **Restoring a backup no longer depends on the order inside the file.** A trip
  and the day entries under it could be written in either order; on a SQLite
  installation with strict database checks the day entry could arrive before
  the trip it belongs to and stop the restore.
- **Uploaded photos land in the data volume when the image is started
  directly.** With `docker compose` they always did; started by hand, they went
  next to the program instead — lost on the next update, and unwritable to
  begin with, so the first upload failed.
- **Starting up no longer rescans the whole database for work finished months
  ago.** Two one-off clean-ups from earlier versions ran their full table scan
  at every start.
- **Data from before accounts existed is fully adopted by the first account.**
  Routes and photos were left behind, which made them invisible everywhere —
  including in the export.
- **Places without a resolved name are no longer cut off mid-coordinate.**
  Where the map service knows no address, the coordinate itself is the name —
  “Ort (54.358, 10.123)”. Anywhere a place name was shortened for display
  (weather records, rankings, map popups, the moderation list) that name was
  cut at its first comma, so half a number was left standing: “Ort (54.358”.
- **“Warmest trip” now counts every day of the trip.** If anything else had
  been recorded earlier the same day — a run, a diary entry, an animal you
  saw — that day silently dropped out of the average. On a full stock that was
  roughly one trip day in four.
- **The *Top years* ranking says something again.** It was ordered by days, and
  since your residence fills every gap, every full year has 365 or 366 of them
  — so the list showed the leap years first, and a year with a single entry
  could outrank a year with hundreds. It now ranks by how much you recorded,
  and shows that number; the days stay beside it.
- **A damaged backup file now gets an explanation instead of an error page.**
  Importing a file whose contents were the wrong shape ended in a server error
  with no indication of what was wrong. The import now names the section it
  could not read and what it expected there. A file that is not a Life-Dash
  export at all is refused outright rather than reported as an import of
  nothing.
- **Days can be edited in the raw table view again.** Changing a residence
  period's start or end date there — or a day of stored weather — failed with a
  server error instead of saving.
- **An entry can no longer end before it begins.** Both dates are checked
  against each other now, whether you set them together or change just one of
  them afterwards; residence periods have always been checked this way. Dates
  far outside a human lifetime (a mistyped year like 9999) are refused too,
  with the allowed range named in the message.
- **The statistics tab opens in about a second instead of a quarter of a
  minute.** On a full life's worth of entries it was taking roughly fifteen
  seconds to appear, and the rankings underneath another fourteen — long enough
  that it looked like nothing was happening. One of the queries behind the
  weather tiles was searching the whole event table once for every event it
  looked at, and on a database holding one person's data that search could never
  narrow anything down. It now asks the question the other way round and is
  effectively instant. **The numbers are unchanged** — every tile, ranking and
  chart shows exactly what it showed before, down to the last decimal.
- **Changing your password no longer signs you out of the app you are in.**
  Changing it ends every other session, which is the whole point — but it was
  also ending the one doing the changing, so the next click landed on the login
  screen. For the same reason, signing in again within a second or two of
  *sign out everywhere* was refused. Both worked exactly as intended
  afterwards; the app just did not believe the freshly issued session was
  newer than the cut-off.
- **Deleting a place that is a residence is now refused instead of quietly
  breaking it.** In the raw table view under *Administration*, deleting such a
  place left the residence period pointing at nothing: its days kept counting
  towards your totals but belonged to no city and no country any more, and the
  page reported that nothing else had been affected. It now says which
  residence is in the way and sends you there first. In the same view,
  deleting an event now detaches its day entries and its recorded routes
  instead of leaving them pointing at something that is gone — and the summary
  afterwards names each thing it touched.
- **The nightly schedule no longer stops at the first account that fails.**
  With more than one account, an error on one of them cancelled the run for
  every account after it — silently, and every night. Each account is now on
  its own.
- **A brand-new installation is protected against duplicate weather values from
  its very first start**, rather than from the second one onwards.
- **The app identifies itself correctly when looking up place names.**
  It was announcing a version number that never existed, which is the kind of
  thing the free OpenStreetMap service is entitled to turn away.
- **The status page no longer tells anonymous visitors how the instance is
  secured.** It is meant to be reachable without a login so an uptime monitor
  can watch it; it does not need to say which login method is switched on or
  which database is behind it.
- **The app can be used with a keyboard.** The nine entries in the navigation
  could only be clicked: `Tab` skipped straight past them, and a screen reader
  announced them as plain text rather than as something you can activate. They
  are now reachable in order, respond to `Enter` and `Space`, show a clear
  focus outline, and say which view is currently open. The same applies to the
  entries behind *More* on a phone.
- **`Esc` and a click beside the box now close every dialog.** Before, `Esc`
  closed exactly one of the six and a click on the background closed three —
  which gesture worked depended on which dialog was open. The welcome dialog
  keeps its deliberate exception: it stays until you have chosen something.
- **An open dialog now keeps the keyboard.** `Tab` used to walk straight out of
  it and on into the page behind the darkened background, where you could reach
  and press buttons you could not see — including while a run was in progress,
  behind an overlay that says the page is not usable right now. `Tab` and
  `Shift+Tab` now cycle within the dialog on top, opening one moves the cursor
  into it so a screen reader reads out what it is, and closing it puts the
  cursor back on the button you opened it from instead of at the top of the
  page. With a mouse none of this was noticeable; with a keyboard it was the
  difference between usable and not.
- **Several texts stayed German with the interface set to English.** The only
  button in the welcome dialog, the first entry in the precision dropdown, the
  sentence around the import threshold, and the labels that screen readers
  read out for the arrow and fullscreen buttons on the map and in the photo
  viewer. Jumping from the statistics to an entity also put a German heading
  back on an English interface.
- **Attaching a photo to a day now opens a calendar.** It used to ask you to
  type a date as `YYYY-MM-DD` into a bare browser prompt — the last place in
  the app that did, while every other date field opens a picker.
- **Scrolling on a phone stays where you put it.** Wiping past the end of a
  dialog or the stop list used to scroll the page behind it, which left the
  dialog standing still while the background moved. Dialogs, the sheet and the
  side lists now keep the scroll to themselves.
- **In landscape, the interface no longer disappears under the camera notch.**
  The bottom bar already allowed for it; the top bar and the content did not,
  so on a phone with a notch the outermost navigation entry and part of the
  header sat underneath it.
- **The map no longer stutters while scrolling on a phone.** Every show and
  hide of the browser's address bar made the map re-measure itself and reload
  tiles; it now does that once, after the movement has settled.
- **“Reduce motion” is now respected throughout.** The system setting only
  reached two of the seven animations, and not the two that move the most: the
  panel sliding up from the bottom and the transition on every view change.
- **The day's weather in the timeline is quiet again.** It was meant to sit
  beside the date in a muted tone and had been showing in the full heading
  colour, competing with the heading it belongs to.
- **The number of photo events is visible again.** It disappeared from the
  Immich settings when the preview was removed, so there was no way to see
  whether the run had created anything — the discard button now says how many
  entries it would remove, and the confirmation names the current number rather
  than one read earlier.
- **The two buttons under *Advanced: undo* are laid out properly.** They were
  crammed into the narrow button column together with their explanations, whose
  boxes were torn apart across every line break.
- **The statistics tab loads again on larger collections.** On PostgreSQL the
  weather statistics could stop finishing altogether — the database ran at full
  CPU and the page eventually gave up with a gateway timeout, while the same
  data on SQLite was merely slow. The query that fetches the events carrying
  weather was written in a shape the PostgreSQL planner cannot turn into a
  join, so past a certain collection size it started re-reading the whole
  metrics table once per event. It asks the same question in two steps now, and
  the answer is unchanged.
- **A day that has only photos now shows up in the timeline at all.** Days were
  listed from your entries, so a day with pictures and nothing written down had
  no heading and no photo strip — even though the photos had been linked. This
  is why photos sometimes appeared only while the automatically recorded
  entries were switched on: the strip was riding along on some other entry of
  that day.
- **Every day with photos now gets its photo strip, not just days that already
  had an entry.** *Link photos* used to build its list of days from your
  entries, so a day covered only by your residence — no trip, no imported
  visit, nothing written down — was never asked about, and years of ordinary
  days stayed without a single picture beside them. The same went for a day
  whose only entry was something you noted by hand: that entry collects photos
  taken near it, and anything shot further afield that day found no place. The
  run now asks Immich which days have photos at all, and fills them. Photos
  still go to a matching entry first; the day only picks up what is left over.
- **Linking photos got dramatically cheaper, and stops asking about days it has
  already seen.** The run used to send Immich one request per day — for a long
  record that is thousands of requests every time, including for days it had
  already found empty, because an empty day left no trace. It now asks month by
  month and remembers how many photos each month held, so a month that has not
  changed is skipped entirely and one you upload new pictures to comes back on
  its own. Discarding your Immich links clears that memory too, so rebuilding
  them works as expected.
- **The statistics tab opens noticeably faster.** The weather balance — days
  with weather, hours of sunshine, rainy days, the bar chart per year — was
  worked out by pulling every weather value of every day of your life into
  memory and counting there. On a thirty-year record that is a hundred and
  fifty thousand values for four numbers and a chart. The database does the
  counting now. Every figure is unchanged, to the last decimal.
- **Exporting your data no longer waits on other accounts.** On an instance
  with more than one person, your backup read everyone's weather values and
  links in order to pick out your own — measured at a third of the export time
  for data that never reaches your file. Nothing about the file changes; it is
  simply your data that gets read.
- **The *World* tab is no longer German-only.** With the interface in English
  it still said “Nordamerika” and listed “Deutschland”, “Frankreich”,
  “Vereinigte Staaten” — the one tab whose names come from a reference table
  rather than from the interface, and the table was only ever asked for its
  German side. Countries, continents and the checklist of places you have not
  been are now in the language you have chosen, and the checklist is sorted by
  the names you actually see. Names that could not be matched to any country
  keep their spelling exactly as recorded: that list exists so you can correct
  it in the collection.
- **Switching language left the *World* tab and the *Rankings* in the old
  one.** Both are named by the server, and it was still being told the previous
  choice at the moment they were re-fetched — so half the screen switched and
  half did not, until the next reload. The rankings had a second reason to get
  stuck: they are remembered until your data changes, and switching language
  does not change your data, so they counted as already loaded.
- **Just after midnight, the journal opened yesterday.** The *Journal* button
  worked out “today” from the clock in Greenwich rather than from yours, so in
  Central European Time everything between midnight and 1 a.m. — 2 a.m. in
  summer — opened the previous day, with yesterday's text already in the field.
  The same slip put the wrong default date in *photo for a day*, and let the
  last day of an ongoing residence drop off the map for those first hours.
- **A login lockout now lets go again.** After five wrong passwords an address
  was blocked for fifteen minutes, as intended — but the counter never reset, so
  once the block expired a single further typo locked the address for another
  fifteen minutes, and again after that. The lockout now clears with its
  waiting time, and a run of failed attempts that has gone quiet for fifteen
  minutes no longer counts towards the next one.
- **The backup now carries the weather of your residence days too.** The export
  took the weather attached to your entries and left behind the weather attached
  to the days a residence fills — so a restored account was missing exactly
  those years in which nothing is recorded but where you lived. The file looked
  complete, which is what made it worth fixing: nothing said anything was
  missing. Restoring into an account that already has day weather is safe; the
  same day is not stored twice.
- **“Warmest trip” names the trip again, not its first day.** For a trip that
  had been split into single days the tile read “Andalusia — day 1”. The
  average was always right; only the label came from the wrong entry.
- **Top places, cities and animals no longer change order between two visits.**
  Where two entries have the same count, the list now decides alphabetically
  instead of leaving it to the database — which also means the bars and the
  ranking below them in the same tab can no longer disagree about which of two
  equal places comes first.
- **Importing a Google timeline no longer reports intact segments as
  unreadable.** A clean device export could claim that dozens of segments could
  not be read, when in fact they had been merged into the routes they belong to.
- **A country now appears once, under one name.** “Deutschland · 14,087
  entries” and “Germany · 2,685 entries” stood one under the other in *Top
  countries* — the same country, named by two sources: OpenStreetMap answers in
  the language you are using, Immich always labels its photos in English. The
  lists now speak the language of the interface, and the stored places are left
  as their source wrote them. This also corrects a figure rather than just a
  label: *Reach per year* counts **different** countries, so two spellings in
  the same year made it one country too many.
- **Your home is one place in the statistics, not two.** A residence you
  entered and what a device export made of the same address — usually the side
  street — were listed as separate places, one with all the days and no
  entries, the other the other way round. Anything within 150 m of a residence
  now counts as that residence, in both the bars and the list, and the name you
  typed wins over the one a geocoder guessed. Only the statistics are affected;
  the map, the filters and the stored entries are untouched.
- **Days that only have photo entries now show their photos.** *Photo in
  Groningen* stood in the timeline without a single picture beside it: the
  “Photos of this day” strip existed, but it was only ever filled by the
  separate *Link photos* run, which asks Immich about every day one at a time.
  The photo-entry run now builds the strip straight from the pictures it has
  just read — same twelve per day, spread across the day, no extra request.
- **The statistics panels no longer leave large empty gaps.** *Farthest from
  home* is one line and sat next to *Reach per year*, which is forty — the grid
  stretched the short panel to the tall one's height, so most of it was empty
  white. The short summaries now sit together in one row, the long list has
  moved in with the rankings, and any list longer than ten lines scrolls inside
  its panel with the total shown in its heading, so every panel is the same
  height and nothing is cut off.
- **The years in which only your residence is recorded now appear in the
  weather statistics.** Rainy days, hours of sunshine and every weather record
  were computed over days that carry an *entry* — so a year with nothing but a
  residence produced no bar at all, even though its weather has been in the
  database all along and the badges have been counting it since day one. A day
  filled by your residence can now hold a record too; it says that it is
  derived instead of borrowing the look of something you wrote down. *Warmest
  trip* is unchanged and still asks about trips, because a residence day is not
  one. Statistics take roughly a fifth longer to compute as a result — that is
  the price of the first twenty years of a life appearing in them.
- **The loading window no longer shows a counter that stands still.** Opening
  *Statistics* used to show “0 / 2” for the whole wait and then jump to done.
  Counting the individual requests instead did not fix it either — one of them
  takes longer than the others together, so it simply stood at “3 / 4”. The
  loading views now say what they are working on in a sentence and leave the
  numbers to the runs that genuinely have a known amount of work. And the open
  statistics panel is no longer fetched twice while the view is opening.
- **The weather now comes from one named source instead of whichever one the
  service felt like.** Until now the request left the choice to Open-Meteo — and
  it chose by the age of the day: recent days came from one model, your
  childhood from another. Measured for 27 June 2026 in Hamburg, where a weather
  station recorded 39.1 °C: the old request returned **31.3 °C**, the source now
  used returns 37.6 °C. So a “hottest day of your life” was comparing two
  different models across the decades. It is ERA5 from now on, for every day
  from 1940 to today, worldwide, over land and sea — the only source that covers
  a whole life without gaps, which matters more here than being right to the
  last degree. **Every weather value also says what it is now**: a modelled
  value over a roughly 25 km grid, not a station reading — good enough to
  compare days and years, not to quote as a thermometer. Two side effects worth
  knowing: the last few days have no weather until the archive catches up, and
  under *My data → Weather* there is a new **discard and fetch again** button —
  values fetched before this version came from the old, mixed choice, and the
  normal run only fills gaps and cannot replace them.
- **Days you take back from your residence no longer keep its weather.** Enter a
  two-week trip as single days — or shorten a residence period — and those days
  stop belonging to the residence. Their weather, fetched at home, used to stay
  behind and keep counting: a day on a Greek island reported the temperature in
  your home town, and because the day rule takes the more cautious of two
  values, the stale one even won against the real weather of the trip once that
  arrived. Days that had dropped out of a shortened period were counted towards
  badges as well, although nothing placed you anywhere that day. Nothing is
  deleted, so the values come back by themselves if you remove the entry or
  extend the period again. The day counts in the statistics were never affected
  — those are recomputed from scratch every time you look.
- **A residence can be corrected after the fact.** Label, place and period — all
  three, from the same form you entered it with, including picking the place on
  the map again. Until now a typo in the label meant deleting the period and
  entering it anew. Moving a period is genuinely cheap, because the days it
  fills are never stored: change the row and everything recomputes on the next
  look. Two things it takes care of quietly: clearing the “until” date really
  does reopen the period to *today* rather than leaving the old end in place,
  and editing only the label leaves your place untouched — a point you picked on
  the map is not silently replaced by the town centre.
- **Every category chip now says how many entries it stands for.** Until now
  only the residence did, and it sits in the same row — a row where one
  switch carries a number and the rest do not reads as if something were broken
  in the rest. On the map the number is the one for the period you are looking
  at; in the timeline it is the one for everything you have recorded, because
  the timeline only ever holds a window and a number out of that window would
  be an arbitrary subset. It also follows what you have switched on: hide the
  automatically recorded entries and the chip drops to what is left. Switching a
  category off no longer blanks its number — that is precisely the number you
  reach for when deciding to switch it back on.
- **All of your residence days are reachable now, not just 300 of them.** The
  timeline used to show 300 derived days picked evenly across the entire period
  — so out of twenty years you saw roughly every twenty-fourth day, with no way
  to get at the rest, and underneath it the footer claimed you had reached the
  beginning of your story. The derived days now behave like everything else in
  the timeline: the most recent ones first, and “load older entries” keeps going
  back until the first day of the period is on screen. In the *Year* and
  *Decade* views there is no limit at all any more — and that also repairs a
  wrong number, because the “N derived” on each summary row was counting the
  sample rather than the days: a December with 31 derived days reported 26.
- **“Today” opens right away.** The greeting, the tiles and the first-entry form
  are there immediately; the “On this day” look-back fills itself in underneath
  and says so while it works, instead of holding the whole first view of the app
  behind a progress panel. The look-back itself also got much faster — measured
  at 20,000 entries with imported visits included, it went from 852 ms to 79 ms
  for exactly the same result. It was loading every multi-day entry in the
  database in full in order to throw almost all of them away again.
- **The mouse pointer changes over clickable points on the map.** Entries and
  photos are drawn on a single canvas — that is what made twenty thousand of
  them possible at all — but a canvas brings no cursor with it, so thousands of
  points gave no hint that they could be opened. Clicking and pointing now use
  the same hit test, so the pointer changes exactly where the click lands.
- **“Delete all my data” shows what it is doing.** It cleared tens of thousands
  of rows while the button just said “… running”. It now uses the same progress
  panel as everything else. It cannot be cancelled, on purpose: cancelling would
  only stop your browser waiting — the server would keep deleting, and you would
  be looking at data that no longer exists.
- **“Delete all my data” and “Delete all data” actually delete now.** Both
  returned a server error, and the log said the data was gone while it was still
  there — the deletion stopped halfway on a table nobody had listed, and
  everything before it was rolled back. Deleting a user account failed the same
  way. Three separate lists of what to delete have become one, so the next table
  added to the system cannot go missing from only some of them. Two things that
  were being left behind now go too: derived residence weather, and photos that
  belong to your account without hanging on any entry — those kept a row after
  their file had already been deleted.
- **Your residence periods are part of the backup.** They were missing from both
  the JSON export and the ZIP archive: the one table that exists purely because
  you typed it in, unrecoverable from anything else, absent from the very backup
  the delete dialog tells you to make first.
- **The vector basemap no longer floods the browser console.** A third-party
  style that asks for icons its own sprite sheet does not contain produced one
  error message per icon *per map tile*. It is now said once, and the settings
  page names which icons the style is missing — the map itself works, only that
  icon is absent from those spots.
- **The share entry in the app manifest declares its encoding**, which silences
  a browser warning when the app is installed.
- **The weather record lists show each day once.** “Coldest day” listed the
  same 11 January ten times over, once per photo taken that day — a ranking of
  entries under a heading that says *day*, and since every photo became an
  entry of its own, a busy day pushed every other day off the list. Each day now
  takes one line, represented by its most extreme place: the coldest spot for
  the coldest day, the hottest for the hottest. The record tiles above the lists
  are unchanged — they always showed the same extreme value.
- **The week and month view no longer freezes the browser** (reported as
  “everything crashes, no error in the log”). Travelled paths were sent up to a
  thousand at a time with every recorded point, and each was drawn as a
  separate element the browser had to reposition on every drag. With a vector
  background map underneath, that was enough to lock the page up.
- **The map stopped hiding paths without saying so.** Above a thousand paths in
  a period it silently kept only the newest ones — in a busy month, the first
  three weeks simply were not there, and the map looked complete. It now takes
  a sample spread evenly across the period and says on the map how many of how
  many it is showing, the same way the point and photo notices already did.
- **Opening the map no longer refetches everything when nothing has changed.**
  At twenty thousand entries that was six megabytes and two thirds of a second
  on every visit to the tab. It now recognises an unchanged corpus — including
  a renamed entry, which is the case a simple count would miss.
- **The timeline no longer throws away photo entries when the Google switch is
  off.** The two switches are separate now, and the browser-side filter had to
  learn that.
- **“Remove collection entries” no longer fails with a server error.** The
  clean-up for the old photo-day summary entries ran into a database error
  whenever an entry had weather attached to it — which, for those entries, is
  always. Everything hanging off such an entry is now removed with it, except
  the things that must survive: photos **you** uploaded are kept and attached
  to the day instead, travelled paths are unlinked rather than deleted, and
  sub-entries are unhooked, exactly as the delete dialog does it.
- **The map no longer freezes with a vector background and everything shown.**
  It used to build one drawing object per photo — twenty thousand of them for
  twenty thousand photos, each recomputed on every mouse move. It now draws all
  of them in a single pass. Nothing is left out, the popup with its preview
  picture stays.
- **A folded-up day of photos no longer says “12 visits”.** It says “12 photos”,
  and expanding it now shows exactly those twelve — before, it also pulled in
  that day's Google visits, so the expanded list could be longer than the
  number above it.
- **The weather is back on the map.** Marker popups and the stop list beside
  the map had shown no weather at all for a while — not because it was missing,
  but because the second request that fetches it was reading the answer in a
  shape the server had stopped sending. Nothing looked broken: a map without
  weather looks exactly like a map whose entries do not have any yet. A failed
  fetch is also no longer remembered as “this period has no weather”, so a
  brief network hiccup no longer costs you the weather for that period until
  you reload.
- **“Paths travelled” now shows when it cannot draw anything.** Above month
  view the paths are deliberately left out — a year of them is tens of
  thousands of lines and would lock the browser up — but the switch stayed lit
  as though it were working. It is now struck through with the reason, the same
  way the other map switches already were, and your choice survives the zoom
  change.
- **Grouped location visits by district now expand again.** When the timeline
  condenses imported visits by district, a card like “HafenCity · 3 visits” did
  nothing when you tried to open it — it was looking up the group by *city*
  (“Hamburg”), which never matches a district name, so it opened onto nothing.
  It now resolves the group at the level it was grouped by, so the individual
  visits appear.
- **A finer world map.** The country outlines were coarse. They have been
  replaced with a higher-resolution set — and, as a side effect, 29 countries
  that the app knew about but the old map could not draw now show up (they were
  grey even after you had been there). The finer map is only loaded when you open
  the World tab.
- **Search no longer reports itself as “unavailable”.** Search does two things:
  a plain text match over titles, descriptions, places and linked items, and an
  AI-based “similar meaning” match. When the AI part could not be reached, it
  took the whole search down and you saw “server search unavailable” — even
  though the text matches were already found. The AI-based part has been removed
  entirely (it also did not scale to large libraries); search is now a fast,
  dependable text search that is always available.
- **Achievements just above the top tier are ordered sensibly.** Among platinum
  achievements, one that has passed further marks now ranks above one that has
  merely reached platinum — previously the plain “top tier reached” one sorted
  first, which read as if it were the greater feat.
- **The raw database view is hidden on phones.** It is a wide table meant for
  horizontal scrolling — unusable on a small screen, and working directly on the
  raw tables is a desk job anyway. On narrow screens both the tab and its
  content are now hidden (it was already admin-only); everything else stays
  reachable on mobile.
- **The “check” buttons looked like they did nothing.** Their result was written
  to the end of the description column beside the button — on a wide screen, the
  other half of the display — and nothing at all happened while the check was
  running. The result now appears directly underneath the button that produced
  it, the button says it is working, and a short summary also arrives as a
  notification.
- **Running jobs could be pushed out of the Jobs tab by finished ones.** The list
  was sorted by start time and cut off after a dozen rows, so a long run sank
  below everything that had finished since — and eventually disappeared, taking
  its progress and its stop button with it. Running jobs are now listed first,
  in full, under their own heading; only the history is shortened.
- **A job showed up under its internal name (`photo_points`) instead of “Place
  photos on the map”.** It now has a proper name in both languages.
- **Photo dots on the map were easy to miss.** They were the same small size at
  every zoom level and disappeared between event pins and cluster bubbles. They
  are now larger, grow as you zoom in and have a clearer outline. Event pins
  deliberately still sit on top of them.
- **“What was the weather that day?” had four different answers.** Timeline,
  bundled card, statistics and achievements each worked it out their own way,
  so the same day could contribute one number to your sun-hours total and a
  different one to a badge. There is now a single rule, written down and shared
  by all four: per value the **lowest** reading of that day (on a travelling day
  the more cautious one), and a weather condition only where the whole day
  agrees. Achievements keep asking whether the day *reached* a threshold
  anywhere, so nothing you have already earned is taken away — but the sunshine
  balance and the warmest-trip average can shift slightly on days you spent
  travelling between two regions, and those are the days where the old numbers
  were picking a value at random.
- **Adding weather no longer asks the same question over and over.** Several
  entries at the same place on the same day used to cost one request to the
  weather service each — after a Timeline import that is dozens per day for a
  single answer. Identical requests are now answered once per run, which makes
  the “add weather” run noticeably faster and much gentler on the free service
  it depends on.
- **Photo points went missing on the map — two reasons, both silent.** Reported
  from use: 8120 located photos, Immich full of pictures from a trip to
  Mallorca, and not a single photo dot on that map in Life-Dash. First, the
  layer asked for the time window of the *entries* of the shown period instead
  of the period itself: a year ended on the day of its last imported visit, and
  a decade covered a single year. The photo layer answers “where did I take
  pictures in this period?”, and limiting it by the entries answers a different
  question — precisely the years this layer was built for have photos and no
  visits. Second, when a period held more points than one answer carried, the
  map used to keep the *oldest* ones; over a library spanning 2009 to today
  that quietly dropped everything after roughly 2016, so a trip in the middle
  of your life vanished while the map still looked full.
- **When a background run finishes, the page updates by itself.** Adding
  weather, resolving place names, linking Immich photos, recalculating
  proposals — all of that happened on the server, and nothing you had open took
  notice, so the change appeared only after a reload. Now a finished run says so
  wherever you are in the app, with its result, and rebuilds the view you are
  looking at. Runs you started and watched yourself are not announced twice.
- **A run you walk away from still updates its own row.** The jobs table only
  refreshed while you were looking at that exact tab; start something, switch to
  the timeline, and it stayed at “running” forever — including after it had
  long finished.

### Security

- **The example settings file no longer hands out a working sign-in key.**
  `.env.example` shipped `SESSION_SECRET=change-me`, and copying that file is
  the first step of the install instructions. The check that refuses to start
  with a publicly known key was looking for a *different* placeholder, so this
  one went through: a fresh instance signed its login cookies with a nine-
  character string printed in the public repository, and anyone who read it
  could sign in as anybody. The check no longer works from a list of bad
  values — it requires a real key of **at least 32 bytes**, which every
  placeholder fails by being short. If yours is too short the app now stops at
  startup and prints the one command that makes a proper one.
- **The login cookie is now marked HTTPS-only on every path into the app.**
  Signing in with e-mail and password already set it that way; signing in
  through an identity provider did not, so on a site served over HTTPS the
  session could still travel over an unencrypted connection. Both paths now go
  through one place, along with the short-lived cookie that carries the login
  handshake. Running locally over plain HTTP is unchanged.
- **A hand-written import file can no longer reach into another account.**
  Restoring a backup always filed everything under the account doing the
  restoring — but a row carries more than its owner, and a file written by hand
  could point one of those references at somebody else's entry, place or
  object: a measurement attached to their entry, or their place name showing up
  in your timeline. Every reference is now checked against what you actually
  own, and the import reports how many rows it turned away. Genuine backups
  bring everything they refer to and are unaffected, including the entries a
  multi-day trip splits into.
- **The Immich connection test now checks the address it is handed.** Saving an
  address had always rejected anything that was not `http://` or `https://`; the
  *test* button had not, although that is the path that actually calls the
  address. Where your Immich lives is still entirely your choice, including on
  your own network.
- **The container no longer runs as root.** It starts as root only long enough
  to hand your `data` and `media` folders to an unprivileged user, then drops
  to it before the application starts. Existing installations need nothing;
  your backup now has to be read as root, because the files belong to user
  10001. If your data sits on a network share where that handover cannot work,
  the log says so and names the one command to run.
- **The base image is pinned to an exact build**, not to a tag that quietly
  points somewhere new each week, and a weekly dependency check now opens pull
  requests instead of relying on someone remembering.
- **`FORWARDED_ALLOW_IPS` can be set** to name your reverse proxy instead of
  believing forwarded headers from anyone. The default is unchanged, because a
  wrong value here makes the app think it is running unencrypted — the reasons
  for and against are in `docs/DEPLOY.md`.
- **`SECURITY.md`** says how to report a vulnerability privately, and lists what
  is known and deliberate so nobody spends an evening on it.
- **You can sign out everywhere.** Settings → Sessions ends every running
  session of your account, on every device, including the one you are looking
  at. Until now a sign-in simply lasted up to 30 days and nothing could end it
  early — if a phone was lost, the only real option was to change the signing
  key and restart the server.
- **Changing your password now signs out every other device.** That is what
  people expect it to do, and it did not: the old sessions kept working for
  another month. Your current window stays signed in.
- **API tokens must say who they were issued for.** If you sign in via an
  identity provider and a second application shares it, a token meant for that
  other application was accepted here. It is now checked. If your provider
  issues tokens for a resource rather than for the client, set `OIDC_AUDIENCE`;
  the log says exactly what was expected when a token is refused.
- **The app refuses to start with a login that is not a login.** `AUTH_MODE=dev`
  means *no* sign-in at all — every request is treated as the account that owns
  all the data. If your instance looks like it is meant to be reachable (a
  `PUBLIC_BASE_URL` that is not this machine, or an OIDC provider already
  configured), Life-Dash now stops with a message naming the three ways out
  instead of coming up wide open. Set `DEV_AUTH_ALLOW_PUBLIC=true` if that is
  deliberate — a public demo instance is exactly that case — and every start
  will say so. The same now applies to `SESSION_SECRET`: with a real sign-in
  the app will not start while it still carries the example value from
  `.env.example`, which is public and signs your session cookies.
- **Security headers, including a content security policy.** The page may only
  load code from your own instance, may not be embedded in a foreign frame, may
  not send data anywhere else, and passes no referrer to outside links. Over
  HTTPS it also asks browsers to stay on HTTPS.
- **The administration's raw table view no longer hands out secrets** — nor
  accepts them. Password hashes and the stored Immich key are shown as `***`,
  and writing either through that view is refused with a pointer to the right
  place. Being unable to read a password hash while still being able to *set*
  one would have been the more useful half for an attacker.
- **Secrets can no longer end up in the log**, which matters because the log is
  displayed in the administration. API keys and tokens are masked wherever they
  appear — including the per-account Immich key, which the app cannot recognise
  by name and catches by shape.
- **Captured text has an upper limit** (20,000 characters, about ten dense
  pages). It protects the AI request behind it, which is billed per call.
- **The map libraries are served by your own instance instead of a public CDN.**
  Leaflet and its clustering plugin used to be fetched from `unpkg.com` on every
  start, with no integrity check — meaning the page that shows your whole life
  database executed code delivered by someone else, and told that someone else
  each time you opened the app. Both libraries now ship with Life-Dash. Nothing
  changes on screen; three things change behind it: no request leaves your
  network before the login screen, the app can be locked down with a strict
  content security policy, and **the offline map finally works** — without a
  network the map used to fail at the library, not at the map tiles, so it never
  drew anything at all.

## [0.39.0] – 2026-07-23

### Added
- **Every geotagged photo becomes its own point on the map.** Until now an album
  of 1200 pictures from London was a single entry and therefore a single dot,
  although each of those pictures knows for itself where it was taken. A new run
  under *My data → Immich → “Locate photos”* reads the position, the time and
  the place name Immich already knows, and stores one row per picture. It
  creates **no entries** and changes nothing you have written; one button
  discards the lot again. The result is a separate, switchable layer — “📷
  Photos” on the map and in the timeline, off by default, because twenty years
  of library are tens of thousands of markers and that is not what you open the
  map for. In the timeline the pictures arrive condensed per day and place (“34
  photos in Aarhus”) rather than as thousands of rows. The map's period picker
  now knows about photo days as well: the years before the smartphone have
  photos and no visits, and until now there was no way to steer to them.
- **The timeline lets you choose how coarsely a day is condensed.** Country,
  city, district or the exact point — one setting for imported visits and for
  photos alike. Condensing by city was a good default and a poor rule: “which
  countries was I in during 2019?” and “which parts of Berlin?” are both fair
  questions. The district comes from the address parts of your own places; where
  they are missing, entries stay separate and the timeline says how many places
  are affected and where to catch up, instead of quietly falling back to the
  city. The place-name run picks those places up on its own from now on — once
  each, at the very end of its queue.
- **Vector maps as a background map.** Immich and most modern map services no
  longer serve image tiles but a *style* that the browser draws itself: sharp at
  every zoom level, readable labels. Enter a style URL under *Administration →
  Map* and “🧭 Vector map” appears on every map. No provider is preset — the
  help text only says where to look up the one your own Immich uses. If the
  browser cannot do it (no WebGL), the map falls back to the default and the
  settings page says why, rather than showing a grey rectangle.

### Changed
- **Immich no longer proposes albums on its own.** An album became *one*
  proposal spanning several days with a single point on the map, and it became
  the twin of the trip you had entered yourself. The better way round: you
  create the trip, and the photos attach themselves to it. Albums are still
  available — there is a tick box next to the run, and the preview is still
  mandatory. Album proposals already sitting in the queue can be discarded in
  one go; confirmed entries and the photo days are left alone, and a discarded
  album never comes back.

### Fixed
- **The Google timeline import no longer creates two-day events.** Google
  reports the start and the end of a stay, and both were taken over as they
  came — so every night in your own bed became a two-day entry. At a home
  address that adds up: over two thousand of them were reported. New imports are
  cut at the day boundary, with the times kept to the second; a button under *My
  data → Imports* catches up with what is already there and says beforehand how
  many entries become how many rows. Only imported visits are affected — trips
  you entered by hand and Immich proposals stay multi-day, because there the
  span is a statement.
- Places whose address could not be resolved are now marked as *asked* rather
  than staying indistinguishable from *never asked* — without that, the
  place-name run would have come back to them on every single pass.

- **Six new weather records.** Strongest sun (UV index), strongest gust, hottest
  and coldest day by *feel* rather than by thermometer, and the longest and
  shortest day by daylight hours. All six are calculated from values that every
  weather lookup has been fetching since 0.22 — same request, no extra traffic;
  they simply had nowhere to go except a single entry's detail view. Entries
  enriched before 0.22 do not carry them, and the tiles say so instead of
  showing a zero. A polar night with no daylight at all counts as the shortest
  day, because that is a measurement; a day without rain still does not count as
  the wettest.

- **“My data” now reads as a first run, top to bottom.** The sections were in
  the order they had been built in; they are now in the order in which they feed
  each other, numbered, with a short guide at the top: pick your modules →
  import the Google timeline → resolve place names → Immich → split multi-day
  entries → add weather → back up. The same order, with the reasoning, is now in
  the README, so the question “where do I start?” has one answer in two places
  instead of none. The map's clustering threshold moved from *Place names* to
  *Map*, where the rest of the map settings are.
- **Adding weather is no longer an admin chore.** It used to sit in the *System*
  tab, which meant an ordinary account had no way to run it at all and its
  entries simply stayed without weather. It is now step 6 under *My data*, and
  the run stays inside the account that started it — pressing your own button no
  longer touches anybody else's entries. The nightly schedule now gives every
  account its own turn for those runs (weather, place names and both Immich
  runs); before, whoever ran first used up the slot for everyone. Recomputing
  proposals and rebuilding embeddings stay in *System*: those genuinely work
  across the whole instance.
- **Imported places no longer get called “Home” or “Work”.** Google describes
  *how* it recognised a stay — that is not the name of the place, and it ended
  up in the visit title, on the map and in the collection. The place is now
  named after its address, and the fact itself is kept where it belongs: the
  place's type. Existing entries such as “Home — Example Street 1” lose the
  prefix on the next place-name run, and that costs nothing — it is a cut, not
  a lookup.
- **The whole interface now switches language.** Roughly two hundred texts were
  built in the page itself and were therefore out of reach of the translation:
  the moderation queue, bulk confirmation, user management, the database view,
  the jobs table, achievements, the world checklist, import and export, months,
  seasons and the timeline cards. Numbers and dates follow the chosen language
  too — “1,703” and “1.703” are the same number in two languages, and reading
  the wrong one is worse than reading no translation. Switching the language
  now also redraws “Today” and the map, which stayed behind before.
- **Achievements and module figures are translated too.** Their names and
  descriptions live in the module files (“Sonnenstunden-Sammler”, “Sichtungen
  pro Jahr”) and reach the page through the API — text that came from a
  different direction and was therefore missed by every earlier translation
  pass. The module files stay German: they are the source, not the display, and
  English lives in exactly one place. The check reads those files, so a new
  module cannot quietly reopen the gap.
- Speech input dictates in the language the app is set to, instead of always
  German.

- **The map was invisible on phones.** A frame added for the map's own “points
  are hidden” notice collapsed to zero height in the mobile layout — the exact
  same failure the map had years ago, one level higher up. A check now watches
  the whole chain between the layout and the map, not just the one frame that
  caused it.
- **Photos of a day sat at the bottom of it.** A time group only shows its first
  entries and hides the rest behind “show N more” — so on busy days the photo
  strip disappeared behind that button, and busy days are exactly the days one
  takes photos. The strip now leads its day (and its week or month), above the
  diary entry and the entries.
- **The place-name format showed nothing selected.** Anyone who had never
  changed it saw four empty boxes, although the server was using all four
  building blocks — and ticking one to “switch it on” silently switched the
  other three off. The boxes now show what actually applies.
- **Named places counted as “too long” forever.** A place with a name of its own
  (“Café Central, …”) has one part more than the format allows, so every
  place-name run looked it up again, got the same answer back and left it in the
  open pile. Where the raw address parts are stored, the run now compares
  instead of counting.
- Places created from a device location or from an AI-analysed entry keep their
  raw address parts as well. Reformatting them no longer needs the network — the
  same thing imported places have been doing since 0.38 — and the fallback for a
  failed lookup is no longer the full administrative address chain including the
  postcode.

## [0.38.0] – 2026-07-22

### Added
- **Split every multi-day event into day entries at once.** Under Administration
  → My data → “Day entries”. The per-event button in the edit dialog stays; this
  one does the same for all of them, which matters once photo albums start
  arriving as multi-day entries. Take a look first — it says how many entries
  become how many days, and names what it leaves out and why: entries that are
  only proposals (splitting those would multiply the moderation queue), vaguely
  dated ones (days out of “summer 2002” would be invented), and anything longer
  than the span you set, 31 days by default — a year-long entry is 365 rows and
  stays a deliberate single decision. Existing days are kept and only gaps are
  filled, so pressing twice creates nothing twice. The per-day weather is added
  by the weather run afterwards.

### Fixed
- **The switch for imported location visits in “On this day” did nothing.** The
  tick could be set and was remembered, but the page asked the server using the
  wrong name for the setting — and an unknown setting is quietly ignored. The
  look-back now really does include imported visits when asked to.
- **The year picker for Immich proposals offered only years Life-Dash already
  knew.** When Immich cannot answer the question “which years are worth a run?”,
  the picker falls back to your own data — but it did not say so, and the years
  before the smartphone (the ones this feature exists for) are exactly the ones
  missing from that list. It now names the reason. The question itself also
  survives more Immich versions: the timeline endpoint changed which parameters
  it demands, so Life-Dash now tries the current form first and works its way
  back instead of giving up on the first rejection.
- **An album was proposed even when you had already recorded that trip.**
  “Mallorca_2005” from Immich landed next to your own “Urlaub auf Mallorca” of
  the same fortnight — the same trip twice. Albums are now compared against your
  own entries and skipped when one already covers the period; the preview names
  which album it left out and which entry covers it. A short album inside a
  long entry (a weekend during a year abroad) is still proposed — those are not
  the same thing. Nothing is remembered about the skip: delete the entry and the
  album is offered again.
- **Albums whose photos predate GPS had no place at all.** For a 2005 album
  there is nothing in the photos to read, while the place sits in the album's
  name. The name is now looked up, and only accepted if it turns out to be a
  real place — “Mallorca” yes, “Beste Bilder” no. Such a place is marked as
  coming from the name, in the preview and in the entry, because a guess and a
  measurement must not look alike. Places you already have are used before
  anything is looked up online.
- **An album spanning two regions was placed between them on the map.** Its
  point was the average of all its photos while its name came from the most
  frequent place — so the map showed a spot where nobody had been. The point now
  belongs to the name.
- **The setup instructions asked for too few Immich permissions.** They named
  three; proposing events from photos also needs `album.read` (albums) and
  `user.read` (telling your own photos from other people's). A key created by
  following them exactly could not run the feature, and Life-Dash reported that
  as “Immich rejects the API key” — sending you off to replace a key that was
  fine. The hint now names all five, an error names the **one** permission that
  is missing, and the connection test checks each of them separately instead of
  just the connection. A missing album permission no longer stops the run
  either: photo days still work, and the result says what it had to leave out.
- **When Immich refused, the preview showed “Bad gateway” instead of the
  reason.** Life-Dash reported a failure of the photo server as a server error
  of its own — and a reverse proxy replaces the body of such a response with its
  own error page, so the sentence explaining what was wrong (“Immich rejects the
  API key”, “Immich does not know that address”) never arrived. The preview now
  answers normally and puts the reason in the result, the way the year list
  already did. If your preview has been failing, this is the change that will
  finally tell you why.
- **The Immich preview could end in a gateway error instead of a result.** On a
  large library it re-downloaded every album of the chosen year on every run —
  including the ones already confirmed or rejected — and when accessed from
  outside, the reverse proxy in between gave up before the answer arrived: not
  a late result, but none at all. Albums that already have an entry are now
  skipped, and the preview keeps to a time budget, answering with what it has
  seen and saying how many albums it did not get to. Creating the proposals is
  a background job and still looks at all of them. The preview also logs when it
  starts, and the button counts the seconds, so a slow look-up no longer looks
  like a dead one.
- **The Immich preview button could do nothing at all.** The year picker was
  filled only from the server, and that call sat behind a chain of swallowed
  errors — so if anything went wrong beforehand, the picker stayed empty and
  the button refused with “please pick a year first” over a list with no years,
  without sending anything. The picker now fills itself with the last few years
  before any server is involved: the years from Immich are a recommendation, not
  a precondition. If that lookup fails it now says so instead of leaving a blank.
- **Photos from late in the evening were filed on the wrong day.** Immich
  reports two timestamps — one in UTC, one in the photographer's local time —
  and Life-Dash read the wrong one, then dropped the timezone. In central
  Europe that moved every photo taken after about 22:00 to the previous day,
  and the day is what a photo hangs on. Found while reviewing the connector
  against Immich's own API description, which says plainly which field is
  meant for grouping by local days.
- **A photo proposal no longer takes possession of its own photos.** The two
  halves of the Immich connector disagreed: the newer half creates unconfirmed
  proposals out of a day's pictures, the older half saw an ordinary entry and
  attached those very pictures to it — so rejecting a proposal had something to
  undo, which it was never supposed to have. Pictures now stay with the **day**
  until you confirm; they are visible right there either way. Existing links
  are released on the next photo run.
- **A day's twelve pictures are now spread across the day.** Immich answers
  newest first, so a holiday with 300 photos showed the last twelve — the
  evening, and nothing of the day.
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
