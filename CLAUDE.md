# CLAUDE.md — Arbeitsanleitung für dieses Repo

## Was ist das
Life-Dash: self-hosted „Lebensdatenbank" (FastAPI + SQLAlchemy/SQLite bzw.
PostgreSQL; Vanilla-JS-PWA komplett in `frontend/index.html`, wird vom Backend
unter `/` ausgeliefert). AGPL-3.0.

**Vier Dokumente, vier Fragen — erst dort gezielt nachlesen statt Code raten:**

| Frage | Datei |
|---|---|
| Was ist das System, was tut es, welche Regeln hält es? | `docs/internal/ARCHITECTURE.md` |
| Was ist noch offen? | `docs/internal/ROADMAP.md` |
| Warum ist es so gebaut, und wann kam es? | `docs/internal/DECISIONS.md` — nummerierte Anmerkungen; **Anhang A** = was in welcher Version gebaut wurde, **Anhang B** = die geschlossenen KONZEPT-Kapitel |
| Was merkt ein NUTZER zwischen zwei Versionen? | `CHANGELOG.md` |

`docs/DEPLOY.md` + `.env.example` sind der Betrieb. `docs/` bleibt sonst frei
für die spätere MkDocs-Seite (R2) — Arbeitsdokumente gehören nach
`docs/internal/`.

## Kommandos (Windows!)
- Python: `C:\Users\phili\miniforge3\envs\py313\python.exe` — **kein `python` im PATH**
- Tests: `cd backend` → `<python> -m pytest tests -q` (laufen offline: Mock-KI,
  Geocoding aus) — 864 Tests, ~40 s, SQLite im Arbeitsspeicher
- **Tests gegen echtes PostgreSQL** (das, worauf betrieben wird): `pwsh
  tools/pg-test.ps1` — **kein Docker**, legt mit den installierten Binärdateien
  einen eigenen Cluster in `backend/_pgtest/` auf Port **55432** an und stoppt
  ihn danach (`-Keep` lässt ihn stehen, `-Stop` räumt auf). ~45 s. Zwei Riegel
  davor, weil die Suite das Schema löscht: die URL darf nicht die betriebene
  sein, und der DB-Name muss `test` enthalten. Der Cluster läuft mit
  `lc_messages=C` — ein deutsch installiertes PostgreSQL meldet in cp1252, und
  `psycopg2` dekodiert das als UTF-8, sodass **jeder echte Befund als
  `UnicodeDecodeError` ankäme**. Das Skript wartet auf die BEDINGUNG (antwortet
  der Server?) statt auf `pg_ctl` — das beendet sich auf Windows nicht
  verlässlich, und der gestartete Server erbt die Ausgabekanäle: hängt stdout an
  einer Pipe, bleibt der Lauf nach erfolgreichem Start stumm stehen.
- Wächter: `cd tools` → `npm run check` (41 jsdom-Dateien)
- **Smoke gegen ein HTTP-Doppel** (Immich): `<python> tools/immich_double.py &`
  dann `<python> tools/smoke_a45.py` — findet, was Unit-Tests prinzipiell nicht
  können (Blättern, Zeitzonen, echte DTOs). Immer aus dem Wurzelverzeichnis.
- **API-Kosten messen** statt raten: `<python> tools/_measure_api.py` legt
  20.000 Ereignisse an und misst die Endpunkte; `DEMO=1` misst stattdessen den
  ausgelieferten Demo-Bestand. **`DB=pfad/zur.db` misst eine BESTEHENDE
  Datenbank** (Anmerkung 220) — die ersten beiden Formen bauen sich ihren
  Messgegenstand selbst und messen die Herstellung mit; genau daran hat der
  Lauf 1.412 ms gemeldet, wo es 15 Sekunden waren.
- **Live-Lauf gegen einen laufenden Server**: `node tools/live-check.js
  http://127.0.0.1:8123` — der einzige Lauf mit echtem Frontend gegen echte
  Antworten (alle anderen Wächter benutzen Attrappen). Seit Anmerkung 220 ein
  eigener CI-Job **mit Demo-Bestand**, weil eine leere Datenbank die
  Größenordnung nicht zeigt; `LIVE_BUDGET_MS` deckelt die Statistik-Endpunkte.
- **Zeitstrahl messen**: `node tools/measure-timeline.js [Seiten]
  [Wohnort-Jahre]` — Aufbauzeit und Knotenzahl je nachgeladener Seite, für
  alle drei Zoomstufen; mit dem zweiten Wert zusätzlich die abgeleiteten Tage.
  Der Kopf der Datei trägt die zuletzt gemessenen Zahlen; der nächste Umbau
  wird daran gemessen und nicht an einem Gefühl (Anmerkung 179/182).
- **CI** (`.github/workflows/tests.yml`): bei jedem Push/PR pytest auf SQLite
  *und* PostgreSQL plus die Wächter. Bewusst ohne Pfadfilter und ohne
  `cancel-in-progress`: ein übersprungener Test sieht aus wie ein bestandener.
- Smoke-Server mit Scratch-DB (echte DB nie anfassen):
  `$env:DATABASE_URL="sqlite:///./_smoke.db"; $env:AUTH_MODE="dev"; $env:AI_PROVIDER="mock"`
  dann `<python> -m uvicorn app.main:app --port 8123` aus `backend/`

## Architektur-Kurzfassung
- **Vier Schichten:** Fragment (Roh-Eingang, nie automatisch löschen) →
  unconfirmed (Vorschlag) → confirmed (**Lebensdatenbank — Maschinen ändern
  Bestätigtes nie, Anreicherung wie Wetter nur ADDITIV**) → Ableitungen
  (Ansichten, Statistik, Wohnort-Tage; jederzeit neu berechenbar)
- **Vierte Sorte Aussage:** `BaselineLocation` = stehende Tatsache mit
  Gültigkeitszeitraum (eine Zeile, Lebensdatenbank), die Tage daraus =
  Schicht 4, nirgends gespeichert (`services/baseline.py`). **Die beiden
  Tagesmengen sind disjunkt** — der Wohnort füllt nur Lücken. Wer eine Zahl
  über TAGE bildet, muss ihn mitzählen; wer eine über EINTRÄGE bildet, darf es
  nicht. **Der Verräter ist die Überschrift** (Anmerkung 194): „Regentage",
  „Sonnenstunden", „kältester Tag" sind Zahlen über Tage — wer die Tagesliste
  aus der EREIGNIS-Tabelle aufzählt, liegt schon falsch, und zwar lautlos: es
  fehlen nur Jahre. **Achtung, ein Eintrag belegt nur seinen ANFANGSTAG** — ein
  ungeteilter Mehrtäger lässt den Wohnort die übrigen Tage füllen; die Antwort
  darauf ist der Lauf „Mehrtägiges aufteilen" (Anmerkung 183).
- **Der Code sagt `baseline`, alles andere sagt „Wohnort"/„residence"**
  (Anmerkung 183): Tabelle, Modell, Endpunkte und `services/baseline.py`
  behalten den alten Namen, Oberfläche und Doku nicht. Wer nach EINEM Wort
  greppt, findet die andere Hälfte nicht.
- **Löschen hat EINE Liste:** `app/wipe.py` (`WIPE_ORDER` = Reihenfolge und
  Besitz-Bezug, `WIPE_KEEPS` = was mit Begründung stehen bleibt, `DELETE_WORDS`
  = das Losungswort). Drei Aufrufer lesen sie: „meine Daten", „alle Daten",
  „Nutzer löschen". Neue Tabelle mit Nutzerdaten → hier eintragen, sonst wird
  `test_wipe_completeness.py` rot. **Und gleich danach in `routers/data.py`**
  (Export-Block UND `plan` im Import): was gelöscht werden kann, muss vorher zu
  sichern sein — `day_metrics` stand in der Löschliste und fehlte im Backup
  (Anmerkung 199). `test_anm199_review.py` prüft beide Seiten gegen
  `Base.metadata`.
- **Wo ein Lauf erscheint, sind ZWEI Fragen** (ARCHITECTURE Kap. 4.6): *wer
  taktet?* (Server → Jobs-Reiter, überlebt das Schließen der Seite; Browser →
  `runForeground()`-Overlay) und *ist er registriert?* (`startJob` = Sperre je
  Typ, unabhängig von der ersten Frage). Registrierte Vordergrund-Läufe stehen
  an beiden Stellen — Backup- und Timeline-Import sind genau das.
- `backend/app/`: `models.py` · `migrate.py` (handgeschriebene ALTER-TABLE-
  Schritte: `_MISSING_COLUMNS`, `_DROPPED_TABLES`) · `wipe.py` · `routers/` (events,
  moderation, tracks = Timeline-Import + Ortsnamen, jobs = Hintergrund-Worker
  mit Lock pro Typ, admin, data = Export/Import, auth, baselines, world,
  achievements) · `services/` (ingestion, enrichment = Wetter, geocode =
  Nominatim/LocationIQ mit 429-Backoff, translit = Umschrift Griechisch/
  Kyrillisch für Ortsnamen, weather = Open-Meteo, baseline, gaps,
  weather_day, stats_* inkl. `stats_tracks` = Kilometer aus dem
  Timeline-Import, eigener Reiter wegen der Herkunft) · `data/countries.py` (passt zu
  `frontend/world-countries.geojson`)
- `frontend/index.html`: EIN File (CSS+HTML+JS, ~13.000 Zeilen) — **gezielt per
  Grep und Read mit offset/limit lesen, nie komplett**
- Module deklarativ: `backend/modules/*.yaml`
- **Nicht im Einsatz, obwohl das alte Konzept sie nannte:** PostGIS, pgvector,
  Alembic, Redis, semantische Suche. Nicht vergessen — bewusst gelassen.

## Arbeitsregeln (vom User festgelegt)
- **Committen ja, und zwar immer — NIE pushen oder taggen.** Fertige Arbeit
  gehört ohne Nachfrage in einen Commit (2026-08-04 ausdrücklich bestätigt:
  „ruhig immer committen, nur nicht pushen"). Push und Tag macht der User
  selbst; Push-Befehle nur nennen, nie ausführen.
- **Zwei Gleise:** Push auf `main` → Image `:main` (Testen, ohne Version).
  SemVer-Tag → `:X.Y.Z`/`:latest` (Veröffentlichung). Eine neue Version also
  nur, wenn ein NUTZER einen Unterschied merkt — mehrere Pakete dürfen sich
  eine teilen. **Nicht je Arbeitspaket eine Nummer vergeben**; das war zweimal
  die Ursache für einen Tag am falschen Commit (ein Bump als Startschuss statt
  als Schlussstrich).
- **Ab 0.40: alles auf `main`, kein Versionssprung**, bis der User den
  Demo-Modus ansagt. `version.py` bleibt auf 0.39.0, neue CHANGELOG-Punkte
  unter `[Unreleased]`, die Anzeige sagt `0.39.0-dev`.
- Jede Version: `backend/app/version.py` + `CHANGELOG.md` (verständliche
  Produktsprache, **keine Paketkürzel** wie „A25") + Paket abhaken in
  `DECISIONS.md` Anhang A (✅ + „fertig vX.Y.Z"); ein fertiges Paket wird aus
  `ROADMAP.md` ENTFERNT — dort steht nur Offenes.
- **Prüfsatz vor jedem Tag:** an diesem Commit muss `[Unreleased]` LEER sein.
- Commit-Stil: deutsch, `feat(bereich): X.Y.Z — Beschreibung` (Historie ansehen)
- Kein Ticket-System: Beobachtungen werden nummerierte Anmerkung in
  `DECISIONS.md`, Pakete stehen in `ROADMAP.md`
- Neue Event-Kategorie? Drei Stellen: KI-Prompt/Module-YAML, Frontend
  (catLabels/Farben/KNOWN_CATS/FILTER_CATS_BASE + CSS), ggf. Selects im HTML
- Allgemeingültigkeit: nichts Homelab-Spezifisches hart verdrahten
  (Provider-Namen etc. aus Config); `.env.example` ist die Setup-Referenz
- Doku englisch (README, DEPLOY, ARCHITECTURE, ROADMAP, DECISIONS, CHANGELOG).
  **Diese Datei bleibt deutsch.**

## Wiederkehrende Fallen
Der wiederkehrende Defekt in diesem Projekt ist nicht Kaputtheit, sondern
**Stille**. Diese Liste ist die eine Sorte Historie, die beim Arbeiten etwas
ändert — alles andere steht mit Begründung in `DECISIONS.md`.

**Zufuhr & Marken**
- **Endlos-Abruf-Falle** (neun Auflagen): ein FEHLVERSUCH muss eine Marke
  hinterlassen, sonst fragt der Lauf ewig neu. Drei Zustände unterscheidbar
  halten — **NULL = nie nachgesehen · leer = nachgesehen, nichts bekommen ·
  gefüllt**. Die Marke sitzt an den FRÜHEN AUSSTIEGEN, also den Pfaden, die man
  nicht als schreibend denkt. Gegenrichtung nicht vergessen: bei
  ABGESCHALTETEM Dienst darf keine Marke gesetzt werden.
- **Eine Zahl wird zur Aussage über die ZUFUHR**, ohne dass jemand den Code
  anfasst — „Tage" gegen „Einträge". **Wo Überschrift und Rechnung sich über
  die Einheit uneinig sind, ist die Überschrift meist die ältere und die wahre.**
- **JSON-Spalten speichern Python-`None` als JSON-`null`**, nicht als SQL-NULL
  → `JSON(none_as_null=True)`, sonst findet `IS NULL` die Zeile nie.

**Regeln, die sich verdoppeln**
- **Eine Voraussetzung, die beim SCHREIBEN galt, gilt beim LESEN nicht mehr.**
  Der Lauf legte die Zeile nur an, weil die Bedingung damals stimmte — und die
  lesende Stelle berief sich darauf, dass sie stimmt. Dazwischen liegt jede
  Änderung des Nutzers (Anmerkung 185: ein Wohnort-Tag, der nachträglich einen
  Eintrag bekommt, brachte sein Wetter mit). Bedingungen über ABLEITUNGEN
  gehören in die Abfrage, nicht in die Geschichte der Zeile.
- **Eine Regel an zwei Orten läuft auseinander, und zwar still.** Bekommt ein
  Paket eine zweite Stufe oder eine zweite Quelle: die ältere Hälfte mit den
  Regeln der neueren lesen. EINE Liste, von beiden gelesen (`MACHINE_SOURCES`,
  `USER_SCOPED_TYPES`, `TRACK_ZOOMS`).
- **Ein Name entscheidet, wer die Regel findet.** Eine Regel, die nach ihrem
  ersten Anwendungsfall heißt statt nach ihrer Aufgabe, wird beim zweiten nicht
  gesucht.
- **Zwei Fragen mit zwei Deckelungen teilen sich keine Tabelle.**
- Bei jeder Invarianten-Reparatur fragen: **wo gilt derselbe Satz noch?**
- **Wo das SCHEMA die Frage beantworten kann, ist eine handgeschriebene Liste
  die dritte Kopie** (Anmerkung 219). „Was hängt an einem Ereignis?" stand
  dreimal da — zweimal vollständig, einmal nicht, und die unvollständige
  meldete beim Löschen „keine Folgeänderungen". Die Zerlegung, die hält:
  **WELCHE Spalten es gibt, fragt `Base.metadata`** (`_dependents`,
  `_user_scoped_refs`), **WAS mit ihnen geschieht, steht von Hand da** — das
  kann das Schema nicht wissen. Dann ist eine neue Tabelle von selbst mitgeprüft.
- **Eine Reihenfolge, auf die es ankommt, gehört IN die Funktion, nicht an ihre
  Aufrufstelle** (Anmerkung 219: `create_all` stand neben `ensure_schema` statt
  darin — auf einer bestehenden Datenbank folgenlos, auf einer frischen fiel
  jeder Schritt aus, der eine Tabelle voraussetzt).

- **Eine fremde Schnittstelle ohne ausdrückliche Angabe ENTSCHEIDET selbst** —
  und ändert die Entscheidung nach Kriterien, die nicht in unserem Code stehen
  (Anmerkung 186: Open-Meteo wählte das Wettermodell nach dem ALTER des Tages,
  sechs Kelvin Unterschied). Jede Vorgabe, die man weglassen kann, wird
  irgendwann von der Gegenseite anders beantwortet als beim Bauen.

**Deckeln, Anzeigen, Schweigen**
- **Deckeln heißt nicht abschneiden.** `slice(0, N)` nimmt die ersten N
  chronologisch — in einem vollen Monat fehlt alles ab der Mitte. Gleichmäßig
  verteilen (`sqlutil.even_spread`, `mpEvenSpread`). Dreimal aufgetreten.
- **Eine Ansicht, die nicht alles zeigen kann, muss das SAGEN** — dort, wo
  hingeschaut wird, und **zuerst das, was man ansieht**, nicht das Versteckte.
- **Ein Bedienelement, das gerade nichts bewirken kann, muss das ZEIGEN**
  (`.inert` = außer Kraft, ≠ `.off` = vom Nutzer ausgeschaltet).
- **Ein `catch`, das zwei verschiedene Fehler auf dieselbe Stille abbildet,
  trägt den Defekt statt ihn zu melden.**
- **Ein Extremwert über eine gedeckelte Größe beschreibt den Deckel, nicht den
  Tag** (Anmerkung 216). Vier Kacheln auf einmal: Sonnenschein ≤ Tageslänge,
  Regenstunden ≤ 24, Tageslänge = Kalender, Fotos je Tag = unser eigenes
  Zwölfer-Limit. **Die Probe ist die Rangliste, nicht die Kachel** — ein
  einzelner Rekord liest sich immer plausibel, zehn identische Werte
  untereinander nicht. Vor jeder neuen Rekord-Kachel fragen: kann diese Zahl
  zwei Tage unterscheiden?
- **Ein Fortschrittsbalken ist eine Zusage über die verbleibende ZEIT.** Wo die
  Gesamtmenge nicht die Arbeit ist (vier Anfragen, von denen eine länger dauert
  als die drei anderen zusammen), ist der Satz die ehrlichere Auskunft:
  `op.note()` sagt, WORAUF gewartet wird, `op.step()` nur dort, wo gezählt und
  nicht geschätzt wird. Zweimal repariert (Anmerkung 193, dann 216) — die erste
  Runde hat den Stillstand nur feiner aufgelöst.

**Last & Datenbank**
- **Nie ein Zeichenobjekt je Element.** Der Canvas-Renderer ist die halbe
  Antwort; die andere ist, kein Objekt je Punkt zu erzeugen.
- **Ein Proxy-Endpunkt ist kein Datenbank-Endpunkt** — Verbindung VOR dem
  Netzaufruf zurückgeben.
- **Wer eine Zahl über den GESAMTEN Bestand braucht, holt sie vom Server.**
- **`query().delete()` verliert die ORM-Kaskade** — sichtbar nur dort, wo
  Fremdschlüssel erzwungen werden (PostgreSQL), still auf SQLite.
- **SQLite erzwingt keine Fremdschlüssel — eine vergessene Kindtabelle ist
  deshalb in JEDEM Test grün.** Sie fällt erst auf PostgreSQL um, und dann
  NACHDEM die Zeilen davor schon „gelöscht" ins Log geschrieben haben: ein
  Protokoll, das einen Erfolg meldet, den es nicht gab, ist teurer als keins.
  Deshalb ist die Löschreihenfolge in `app/wipe.py` eine Liste, und der Test
  prüft gegen `Base.metadata` statt gegen Beispiele — eine Tabelle, nach der
  niemand fragt, kann kein Test vermissen.
- **Ein `OR` zwischen zwei `IN`-Unterabfragen verbietet PostgreSQL den
  Semi-Join** (Anmerkung 214). Es bleiben zwei `SubPlan`, und ob so einer
  EINMAL gehasht oder je Zeile der äußeren Tabelle neu durchlaufen wird,
  entscheidet allein die Schätzung gegen `work_mem` (Vorgabe 4 MB). **Das ist
  eine Klippe, keine Kurve:** dieselbe Abfrage kostet 97 ms oder läuft nie
  fertig, je nachdem, auf welcher Seite der Kante der Bestand steht. Zwei
  getrennte Abfragen haben kein `OR` — die Vereinigung macht das `dict`. Auf
  SQLite ist nichts davon zu sehen (Ephemeral-Index), und die Testsuite auf
  PostgreSQL auch nicht: ihr Bestand ist zu klein. **Wer einen Plan prüft,
  prüft ihn mit dem ECHTEN Wertesatz** — mit vier statt dreizehn Schlüsseln
  schätzt der Planer anders und antwortet auf eine andere Frage.
- **Eine korrelierte Unterabfrage wird je Zeile der äußeren Tabelle neu
  ausgewertet — und WELCHEN Index sie dabei nimmt, entscheidest nicht du**
  (Anmerkung 220). SQLite bricht ohne `ANALYZE` den Gleichstand zugunsten des
  ZULETZT angelegten Index, und `Table.indexes` ist eine `set`: dieselbe
  Migration auf denselben Daten legt sie in verschiedener Reihenfolge an.
  Gemessen an drei Demo-Beständen: 1,33 s / 14,6 s / 15,0 s für dieselbe
  Abfrage. **In einer Ein-Personen-Instanz ist `user_id` die UNSELEKTIVSTE
  Spalte** — greift der Planer danach, läuft die innere Suche jedes Mal ganz
  durch. Die Antwort ist nicht, den Index zu erzwingen, sondern die Korrelation
  wegzunehmen: ein Semi-Join (`IN` über eine Unterabfrage ohne Außenbezug) wird
  EINMAL ausgewertet. Im Plan steht der Unterschied wörtlich da — `LIST
  SUBQUERY` gegen `CORRELATED SCALAR SUBQUERY`, und das ist die einzige
  Eigenschaft, auf die ein Wächter sich verlassen darf (eine Zeitmessung ist
  auf jedem dritten Bau grün).
- **Hängt etwas auf dem Server, ist `pg_stat_activity` die erste Frage**, nicht
  die zweite: `SELECT now()-query_start, query FROM pg_stat_activity WHERE
  state='active'` nennt die Anweisung im vollen Wortlaut, während sie läuft.
  Eine Runde davon schlägt jede Stunde Plan-Raten.
- **Dialektklasse SQLite ↔ PostgreSQL:** `round()` nur für `numeric`,
  `DISTINCT` nicht über JSON-Spalten, `concat` erst ab SQLite 3.44, `extract`
  liefert auf PG Fließkomma. Dafür ist `pwsh tools/pg-test.ps1` da.
- **`with TestClient(app)` fährt den LIFESPAN** — öffnet die KONFIGURIERTE
  Datenbank und startet den Ticker. Auf SQLite unsichtbar, auf PostgreSQL hängt
  die Suite. Client ohne `with` bauen.
- **`= Query(False)` als Default** kommt beim Direktaufruf als Query-OBJEKT an
  und ist damit wahr → `Annotated` benutzen.

**Was mit der Maus tadellos ist** (Anmerkung 217/218)
- **Ein Bedienelement, das nur auf `click` hört, ist ohne Maus NICHT VORHANDEN
  — und das sieht man beim Benutzen nie.** Ein `<div>` mit Klick-Horcher hat
  kein `tabindex` (Tab springt vorbei), keine Rolle (der Screenreader liest
  Text) und kein Enter. Wer die Bauform nicht ändern kann, schreibt aus, was
  ein `<button>` MITBRINGT — an der EINEN Stelle, an der gebunden wird.
  `cloneNode` bringt Attribute mit und Horcher nicht: ein `tabindex` ohne
  Handler ist die schlimmere Hälfte, ein Fokusrahmen, der nichts tut.
- **Eine unbekannte CSS-Variable fällt nicht auf einen Standardwert, sie lässt
  die Eigenschaft ERBEN.** `var(--tippfehler)` ist kein Fehler und keine
  Warnung — nur ein Entwurf, der still nicht gilt.
- **Ein Attribut kann aussehen wie eine Bindung und keine sein.** `data-i18n-…`
  wirkt nur, wenn `applyLang` es liest; ein Knopf, dessen Beschriftung ein
  Zeichen ist („‹", „⛶"), trägt seinen ganzen Namen im `aria-label`.
- **Der CSP-Skript-Hash wird EINMAL beim Start gerechnet**
  (`SecurityHeaders.__init__`, Anmerkung 208). Wer `index.html` unter einem
  laufenden Smoke-Server ändert, bekommt eine Kopfzeile, die auf die alte Datei
  zeigt — der Browser verwirft dann das GANZE Skript, und die Seite lädt und tut
  nichts. **Nach jeder Frontend-Änderung neu starten**, und im Zweifel messen:
  `curl -D- -o /dev/null http://…/` gegen den Hash der Datei.
- **Escape, Klick daneben, Tab-Falle und Fokus-Rückweg sind EINE Regel für ALLE
  Dialoge** (`OVERLAYS`, Anmerkung 218) — sonst hängt es vom geöffneten Dialog
  ab, welche Geste hilft. Jeder Eintrag nennt seine Schließfunktion, nicht
  `remove('show')`: Dialoge räumen auf, und ein zweiter Ausgang, der das
  überspringt, lässt Zustand stehen. `close: null` heißt „mit Grund kein
  Ausweg", nicht „vergessen" — für die Fokus-Regeln zählt der Eintrag trotzdem.
  **`openOverlay`/`closeOverlay` sind der EINZIGE Weg**, an dem `.show` an einem
  Overlay wandert; wer es selbst schreibt, bekommt Falle und Rückweg lautlos
  nicht (der Wächter sucht danach).
- **Ein Dialog, aus dem Tab hinausführt, ist mit der Tastatur keiner** — die
  Verdunklung ist Farbe, der Tab-Ring läuft dahinter weiter, und man drückt
  Knöpfe, die man nicht sieht. Was in einer Ansicht offen ist, entscheidet die
  BAUFORM (`.modal-overlay, .sheet-overlay, .lightbox, .loading-overlay`) und
  keine zweite Namensliste; so fällt der siebte Dialog auf, sobald er die
  Klasse benutzt.
- **`offsetParent` ist der naheliegende Sichtbarkeitstest und hier unbrauchbar**
  — unter jsdom immer `null`, ein Wächter darauf prüft nichts. Der Weg über die
  BERECHNETE Anzeige (`getComputedStyle`) gilt in beiden, auch für z-Ebenen.
- **Eine Vorsichtsmaßnahme, die kein Test von ihrem Fehlen unterscheiden kann,
  ist keine.** In 218 war das eine gemerkte Fokus-Spur gegen den Fall „Dialog
  setzt den Fokus beim Öffnen selbst weiter" — den es nicht gibt, weil in einem
  `display:none`-Teilbaum nichts den Fokus halten kann. Der Lauf gegen den
  kaputten Stand ist nicht nur die Probe auf den Wächter, sondern auch die auf
  den Code: bleibt er grün, ist eine Hälfte davon zu viel.
- **Was am Schreibtisch unsichtbar ist:** Scroll-Verkettung
  (`overscroll-behavior`), die SEITLICHEN Safe-Area-Ränder (die beißen nur
  QUER), `prefers-reduced-motion` über ALLE Animationen, und `resize` auf dem
  Handy als Dauerfeuer (Adressleiste beim Scrollen → `reSize` bündelt).

**Prüfungen, die nichts prüfen** (die teuerste Klasse)
- **Jede Prüfung einmal gegen den KAPUTTEN Stand fahren.** Sonst ist sie grün,
  weil es die Funktion GIBT — nicht, weil der Aufrufer sie BENUTZT.
- **Zwei Funktionen, jede für sich geprüft, und der Defekt liegt DAZWISCHEN**
  (Anmerkung 219). Widerruf und Neuausstellung waren einzeln bewiesen; den
  Rundlauf „widerrufen → sofort neu ausstellen → gilt es?" prüfte niemand, und
  genau der war kaputt. Wo zwei Hälften eine Zusage tragen, ist die Prüfung der
  ÜBERGANG, nicht die Summe der Hälften.
- **Ein Auflösungsproblem mit einer verschobenen GRENZE zu beantworten trifft
  die falsche Hälfte** (Anmerkung 219). Ganze Sekunden konnten „kurz davor"
  und „kurz danach" nicht unterscheiden; die Sekunde Vorlauf traf deshalb auch
  das gerade neu ausgestellte Cookie. Erst die Auflösung erhöhen, dann die
  Grenze setzen. **Und `iat` nie in die Zukunft** — PyJWT weist so ein Token ab,
  aus „gilt nicht" würde „unlesbar".
- **Ein `const` auf oberster Skriptebene ist KEINE Fenster-Eigenschaft**
  (anders als eine `function`-Deklaration): `w.OVERLAYS` und `w.LANG` sind
  stumm `undefined`, und die Prüfung wird eine über nichts. Aus dem Quelltext
  lesen oder `w.eval()` — die App nicht für ihren Test global machen.
- **Unter jsdom startet die Seite ENGLISCH**; `applyI18n` ersetzt das deutsche
  Markup. Wer nutzersichtbaren Text prüft, prüft **Anzeige, deutschen
  Quelltext UND englischen Katalog**.
- **Ein Wächter muss den Zustand HERSTELLEN**, nicht den Auslieferungszustand
  lesen (`applyModules()` ersetzt die Leiste Sekundenbruchteile nach dem Start).
- **Ein Doppel, das ein Feld auslässt, ist keine Vereinfachung, sondern eine
  andere Funktion.** Auffang-Proxys, die für jede Eigenschaft sich selbst
  zurückgeben, machen aus `getZoom()` oder `getLayers().length` etwas, das gar
  keine Zahl ist.
- **Ein Wächter, der nur seinen Auslöser kennt, ist einer für die
  Vergangenheit** — die ganze Kette prüfen, und in BEIDE Richtungen (ein
  undokumentierter und ein erfundener Schlüssel sind beides Defekte).
- **Bei jedem Konnektor zusätzlich ein HTTP-Doppel** mit den echten DTOs:
  Blättern, Zeitzonen und Besitzfilter erreichen Unit-Tests prinzipiell nicht.
- **Prüfen, ob eine Zusicherung eine Eigenschaft oder ein Attribut liest** —
  Code setzt oft die EIGENSCHAFT, das Markup trägt das ATTRIBUT.

## Stand
**Auf `main`, `version.py` = 0.39.0, alles seither unter `[Unreleased]`.**
Gruppe A (A1–A48) und Gruppe B bis F21 sind gebaut, ebenso P2.1 (alle drei
Stufen), P3.1, P5.1 und F1. Offen bis 1.0 sind nur noch **R1** (Härtung,
Projektoberfläche) und **R2** (Doku-Seite) — Einzelheiten in `ROADMAP.md`.

**Der Demo-Bestand steht (R1a, Anmerkung 203).** `app/demo/` baut hinter
`SEED_DEMO=true` (nur dev-Modus, nur wenn das Konto leer ist) ein erfundenes
Leben von 32 Jahren: ~8.500 Ereignisse, 29 Reisen, 5 Wohnorte, ~4.100 Wege,
~460 erzeugte Bilder, Wetter für jeden Tag, in ~12 s und **ohne Netz**. Fünf
Regeln, die beim Ändern zählen:
- **Gebaut, nicht durch die Pipeline gejagt** — sonst hinge der Bestand am
  KI-Anbieter und jeder Screenshot wäre ein Einzelstück.
- **Das Wetter ist erfunden** (`demo/weather.py`, Hash über Ort+Tag, nur die
  Tageslänge echt gerechnet) und trägt **den Revisionsmarker**. Ohne ihn
  startet der Wetter-Knopf elftausend Open-Meteo-Abrufe. Die Grenze „zu jung
  für das Archiv" wird bei `enrichment._too_recent` GEFRAGT, nie abgeschrieben.
- **`life.BLANK`** = 75 Tage ohne Wohnort und ohne Eintrag, damit der
  Lückenbericht etwas zu sagen hat. EINE Definition, drei Leser.
- **Nichts ist später als gestern** datiert, und der Bestand ist nicht überall
  Platin (5 von 18) — beides bewusst, siehe Anmerkung 203.
- **Die Bilder werden erzeugt** (`demo/photos.py`, Farbverlauf + Ort/Datum +
  „Demo-Bild") und gehen über `media.store`, denselben Weg wie ein Upload.
  Beide Sorten kommen vor: am Ereignis und am TAG (F18). **Die Foto-Ebene der
  Karte bleibt leer** — die besteht aus `immich`-Ereignissen und lebt von
  fremden Vorschaubildern; ohne Immich wären das tausende tote Verweise.

**Offen aus den Rückmeldungen vom 2026-08-04** (Anmerkungen 168–182 sind
erledigt, die zweite Rückmeldung mit elf Punkten vollständig, aus der dritten
die Punkte 1 und 2):

- Der **LCP-Wert der Vektorkarte** ist mit der Vektorkarte selbst erledigt:
  **A48 ist zurückgezogen** (Anmerkung 206, Ansage des Users „macht zu viel
  Ärger"). Weg sind MapLibre, die Leaflet-Brücke, der Einstellungsblock, zwölf
  Katalogschlüssel und `check-vector-basemap.js`. Nicht behoben, sondern
  entfernt — die Frage wird nicht wieder aufgemacht.
- **Zeitstrahl im Tages-Zoom**: jede nachgeladene Seite baut die GANZE Liste neu
  — gemessen 26 ms bei 300 Karten, 172 ms bei 1.800, also mit jeder Seite mehr
  (`node tools/measure-timeline.js`). Anmerkung 179 hat den gemeldeten Fall
  (Jahr/Jahrzehnt) über den Index gelöst; dieser hier ist bewusst stehen
  geblieben, weil der Umbau (Gruppen einzeln ersetzen statt `innerHTML`) an den
  index-basierten Registern `VISIT_GROUPS`/`TL_STRIP_MEDIA` hängt.
- **Aus „Grundort" ist „Wohnort" geworden** (Anmerkung 183) — erledigt, hier
  nur noch, damit die Frage nicht ein zweites Mal aufgemacht wird: Die REGEL
  bleibt, wie sie war (jeder Eintrag an einem Tag lässt den Wohnort schweigen).
  Der Vorschlag, ihn bei EINZELNEN Ereignissen anderswo weiterzählen zu lassen
  und nur bei MEHRTÄGIGEN Abwesenheiten schweigen zu lassen, wurde ausgeschrieben
  und vom User verworfen — „konsequenter und einfacher, mit der Ungenauigkeit
  kann ich leben". Die Ungenauigkeit ist eine Asymmetrie: zwei Einträge in zwei
  Städten geben BEIDEN einen Tag, ein einzelner Eintrag anderswo kostet den
  Wohnort seinen.
- **Das Zeichen ist gewählt** (Anmerkung 180): Biene als Hauptzeichen, Wabe als
  Beizeichen. Erledigt, hier nur noch als Hinweis, dass die Frage keine offene
  mehr ist.

**Rückmeldung 2026-08-05, zweiter Satz (Anmerkungen 195–198) ist erledigt** —
Statistik-Layout, Fotos am Tag, Wohnort-Umkreis, EIN Name je Land. Der letzte
Rest daraus, der **deutsch verdrahtete Welt-Reiter**, ist mit **Anmerkung 202**
geschlossen.

**Serverseitig benannte Ansichten (Anmerkung 202).** Welt-Reiter und
Ranglisten heißen, wie der SERVER sie nennt — Länder- und Kontinentnamen sind
Stammdaten (`data/countries.py`, `name_de`/`name_en`/`CONTINENTS_EN`) und
können nicht in `I18N_EN`. Zwei Regeln dazu, beide teuer erkauft:
- **Die Anfrage NENNT die Sprache** (`?lang=`), sie liest sie nicht aus dem
  Konto. Der Sprachknopf zeichnet neu und schickt die Sprache erst DANACH ins
  Konto — ein `lang_for(user)` auf der Leseseite antwortet mit der alten.
  `geocode.display_lang(requested, user)` hält die Regel an EINER Stelle:
  Wunsch, sonst Konto. Läufe ohne Aufrufer (Ortsnamen) bleiben bei `lang_for`.
- **Die Sprache gehört in jede Merkzelle**, die eine solche Antwort behält
  (`statsTopsFor`). Ein Sprachwechsel ändert den Bestandsstempel nicht.

**Runde 2026-08-09, zweiter Satz (Anmerkungen 206-213) — R1(d) und R1(e) sind
gebaut, R1(f) ist gestrichen.** Ansage des Users: Vektorkarte raus, getesteter
Upgrade-Pfad raus, Haertung und Projektoberflaeche bauen, alle Anmerkungen
schliessen, die kein Feature nach 1.0 sind.

- **206** Vektorkarte (A48) zurueckgezogen — mit ihr MapLibre, Anmerkung 171
  und die offene LCP-Frage. Nicht behoben, sondern entfernt.
- **207** Leaflet + markercluster liegen in `frontend/vendor/`. Kein CDN mehr,
  und **die Offline-Karte war vorher keine**: der Worker durfte ein fremdes
  Skript nicht cachen. Waechter `check-no-cdn.js` haelt `index.html` und
  `sw.js` zusammen — wer eine Datei aus `SHELL` vergisst, wird rot.
- **208** Haertung: `AUTH_MODE=dev` und das Standard-Secret brechen den START
  ab (`app/startup_checks.py`, Ausnahme `DEV_AUTH_ALLOW_PUBLIC`).
  Sicherheits-Kopfzeilen und CSP in `app/security.py` — **script-src mit
  HASHES**, gerechnet aus der ausgelieferten Datei, mit der
  Zeilenenden-Normalisierung des HTML-Parsers. Ohne die waere die Seite auf
  Windows (CRLF) tot und im Container (LF) heil. Log-Schwaerzung an den
  HANDLERN, nicht am Logger: Python wendet die Filter der Vorfahren bei der
  Weitergabe nicht an. Rohansicht schwaerzt UND verweigert Geheimnisse.
- **209** Sitzungen widerrufbar ueber EINEN Zeitstempel je Nutzer
  (`users.sessions_valid_from`), Sperrtabelle gedeckelt, Bearer-Audience
  geprueft (`OIDC_AUDIENCE`).
- **210** Container gibt seine Rechte ab (`docker-entrypoint.sh`, uid 10001),
  Basis-Image am Digest, Dependabot, `SECURITY.md`. **Nicht gebaut** — hier
  laeuft kein Docker; der erste `docker compose build` ist die Probe.
- **211** `CONTRIBUTING.md` (keine Pull Requests), Issue-Vorlagen, „was dieses
  Projekt bewusst nicht tut".
- **212** Ein Serverlauf, der fertig wird, aktualisiert die offene Ansicht.
  EIN Waechter statt der reiter-gebundenen Jobs-Tabelle; eigene
  Vordergrund-Laeufe melden sich nicht doppelt.
- **213** Wetter-Ereignisseite gemessen: 1710 -> 1611 ms. **Der Umbau der
  zwoelf Ranglisten nach SQL bleibt offen** — vier Regeln auf einmal in die
  Abfrage, und eine falsche Rangliste ist schlimmer als eine langsame.
- **215** Rueckmeldung zum Immich-Block: „Erweitert: zurueckehmen" war schlecht
  formatiert, und „Foto-Ereignisse verwerfen" meldete nichts. Zwei Dinge, drei
  Saetze zum Weiterarbeiten:
  - **`flex: 0 0 100%` heisst in einer SPALTE Hoehe, nicht Breite.** Der
    `details.adv`-Block sass in `.action-key` (215 px, `flex-direction:column`)
    und wurde deshalb nicht breit. Dazu `<span class="hint">` ohne
    `display:block` — `.hint` ist ein Kasten mit Rahmen, und eine Inline-Box mit
    Rahmen zerreisst der Browser an jedem Zeilenumbruch. Beide `details.adv` auf
    derselben Seite sitzen in `.action-desc`; dieser jetzt auch.
  - **Der Rueckweg ist stapelweise** (`/api/photos/reset?limit=`, Deckel 5.000)
    und laeuft ueber `runBatchedAdmin` mit Job-Typ `photo_reset`: Browser
    taktet, Server registriert — dieselbe Kombination wie der Backup-Import.
    `remaining` wird nach JEDEM Stapel frisch gezaehlt, nie fortgeschrieben (der
    Bestand hat mehr als einen Schreiber). `im-reset` bleibt EINE Anweisung und
    bekommt nur das Overlay ohne Balken.
  - **`#pp-result` gab es seit Anmerkung 206 nicht mehr**, `ppLoadIndex()`
    schrieb also ins Nichts. Die Zahl steht jetzt unter dem Verwerfen-Knopf, und
    die Rueckfrage holt sie beim Klick frisch statt aus `mp.photoTotal`.
- **214** Die Einschraenkung aus 213 hat den Statistik-Reiter auf dem
  betriebenen PostgreSQL zum Stillstand gebracht (100 % CPU, 524 vom Proxy).
  Ursache war das `OR` zwischen zwei `IN`-Unterabfragen — siehe die neue Falle
  unter „Last & Datenbank". Jetzt zwei Abfragen mit `EXISTS`, gleiche Menge,
  geschaetzte Kosten 255.050.589 -> 21.309.

**Damit sind die zehn offenen Punkte aus Anmerkung 200 geschlossen.** Offen
bleiben aus R1 nur noch **b** (Screenshots/GIF, braucht den User), **c**
(versionierte ghcr-Images) und **g** (Spendenlink) sowie **R2**.

**Runde 2026-08-09, dritter Satz (Anmerkung 216) — der Statistik-Reiter und die
Ladeansichten.** Neun Punkte, vier davon derselbe Defekt in vier Verkleidungen.
Vier Sätze zum Weiterarbeiten:
- **Ein Wert, der nach oben gedeckelt ist, ist kein Rekord.** Gestrichen sind
  „Sonnigster Tag" (Sonnenschein ≤ Tageslänge), „Längster Regen" (≤ 24 h),
  „Längster/Kürzester Tag" (= Kalender) und „Tage mit den meisten Fotos"
  (= unser eigener Zwölfer-Deckel der Tagesleiste). **Sichtbar wurde es erst
  durch die Rangliste unter der Kachel** — eine Kachel zeigt einen Wert, eine
  Rangliste zeigt, ob er zwei Tage unterscheiden kann. Wer eine neue Kachel
  baut: dieselbe Frage stellen. `rain_h`/`daylight_h` sind damit auch aus
  `_WX_KEYS` raus (ein Schlüssel dort kostet eine Zeile je Ereignis UND je
  Wohnort-Tag), `sunshine_h` bleibt für die Jahressumme.
- **„Umzüge" ist „Wohnorte".** Die Kachel zählte Meilenstein-TITEL
  (`umzug|umgezogen|eingezogen`) und stand auf 0, während fünf Wohnorte
  eingetragen waren — die Falle „eine Zahl wird zur Aussage über die ZUFUHR".
  Seit F20 gibt es die Tatsache als Zeile; `_MOVE_RE`/`_MOVE_WORDS` sind weg,
  die Geburt ist die letzte Textregel, die eine Zahl trägt.
- **`op.all` gibt es nicht mehr.** Ein Zähler über ANFRAGEN misst nicht die
  Wartezeit, sieht aber aus wie ein Versprechen über sie („3 / 4" stand fest,
  weil eine der vier Anfragen länger dauert als die anderen drei zusammen).
  Ansichts-Lader sagen nur noch `op.note()`; `op.step()` bleibt dort, wo die
  Gesamtmenge WIRKLICH die Arbeit ist (Backup-Import, Timeline-Import,
  Foto-Rückweg). `check-foreground.js` prüft beide Richtungen — Satz da UND
  kein `step()`.
- **Der Immich-Lauf zählt je Phase.** `job.unit`/`job.done` wechseln beim
  Phasenwechsel gemeinsam; **nur wenn es offene Monate GIBT**, sonst bliebe
  „0 Monate geprüft" als Schlusszeile stehen — und das abschließende
  `_progress(total)` hätte `done` auf null zurückgezogen (`_tick` schreibt
  Differenzen fort).

**Backend-Durchsicht 2026-08-11 (Anmerkung 219): vier Reparaturen, eine
Messung offen.** Repariert: der Passwortwechsel warf den Nutzer aus der eigenen
App (Widerruf gegen Neuausstellung, jetzt `auth.session_cookie_for` als EINE
Stelle und `iat` mit Nachkommastellen), die Rohansicht fragt beim Löschen das
Schema statt einer handgeschriebenen Kette (`admin.ON_DELETE` mit
cascade/detach/**refuse** — ein Wohnort verschwindet nicht als Nebenwirkung),
`create_all` ist in `ensure_schema` gewandert, und der Nachtplan überlebt ein
kaputtes Konto. Dazu: EIN User-Agent in `version.py`, `/health` nennt
`auth_mode` und `database` nicht mehr.
**Offen und gemessen: `enrichment._weather_candidates` lädt vor JEDEM
25er-Batch alle verorteten Ereignisse samt Metriken** — 396 ms bei 2.000,
1.321 ms bei 5.000, 2.979 ms bei 10.000 fertigen Ereignissen, also quadratisch
über einen Rückstandslauf. Die Antwort steht zwölf Zeilen tiefer schon da:
`_day_weather_candidates` fragt die `weather_rev`-Marke in SQL; die
Ereignis-Hälfte kann dasselbe als `NOT EXISTS`. Bewusst eigene Runde — es
ändert, welche Zeilen ein Lauf aufgreift.

**Vollständige Durchsicht vor dem Release 2026-08-12 — 30 Befunde, in vier
Teile geschnitten. Teil 1 ist gebaut (Anmerkung 220), Teil 2–4 sind offen.**
Der Bericht liegt als Artefakt vor; die Aufteilung:
- **Teil 1 ✅ Statistik-Reiter und die Prüfung, die ihn nicht gefangen hat.**
  29 s → 2,3 s, Antwort Byte für Byte identisch. Dazu `DB=`-Modus im
  Messwerkzeug und `live-check.js` als CI-Job. Einzelheiten: Anmerkung 220.
- **Teil 2 (offen) Korrektheit in Ableitungen und an den Eingängen.** Sieben
  Befunde, alle „eine Regel an zwei Orten" oder eine fehlende Prüfung am Rand:
  `admin._coerce_value` kennt `Date` nicht (PATCH auf `baseline_locations.
  date_start` → 500 auf SQLite, still durchgewinkt auf PostgreSQL) · die
  wärmste Reise verliert 23 % ihrer Tage, weil `by_day` VOR dem
  Kategorie-Filter verdichtet · der Import antwortet auf kaputte Nutzlast mit
  einem 500er · die Rangliste „Jahre" sortiert nach einer Kalenderkonstante
  (sechsmal 366) · `_short_place` schneidet „Ort (54.358, 10.123)" hinter der
  ersten Zahl ab · `date_end` vor `date_start` und ein Wohnort ab 2099 werden
  angenommen.
- **Teil 3 (offen) Der Demo-Bestand als Schaufenster.** Kein einziges
  mehrtägiges Ereignis (also keine „Längste Reise", kein F7, nichts für
  „Mehrtägiges aufteilen") · 3.633 von 3.675 Orten sind Koordinaten-Platzhalter
  und alle als `name_manual` markiert, weshalb „Ortsnamen auflösen" 0 offen
  meldet · der Windrekord aus 32 Jahren steht bei 36 km/h.
- **Teil 4 (offen) Betrieb, Start, Doku.** Das Dockerfile setzt `MEDIA_DIR`
  nicht (nur die Compose) · `psycopg2-binary` ist die einzige ungepinnte
  Abhängigkeit · `pytest` steht in den Produktions-Requirements · `chown -R
  /data` läuft bei jedem Start über die ganze Fotobibliothek · `sqlite://`
  stürzt beim Import ab · SQLite läuft ohne `PRAGMA foreign_keys` · zwei
  Alt-Aufräumläufe scannen bei jedem Start die vollen Tabellen · **der
  `[Unreleased]`-Block hat 172 Punkte und doppelte Überschriften und muss vor
  dem Tag verdichtet werden.**

**Code-Durchsicht 2026-08-07 (Anmerkung 201): fünf Reparaturen und vier
Aufräumungen drin, drei Punkte bewusst offen — sie brauchen erst eine
MESSUNG.** Repariert: `on_this_day` lädt mit `user_id`-Filter, „heute" kommt im
Browser aus der lokalen Uhr statt aus UTC (`todayLocal()` — das Tagebuch öffnete
nach Mitternacht den Vortag), toter Zweig in `_run_weather`, die Login-Sperre
lässt nach ihrer Zeit wieder los (Zähler verfiel nie), `_visit_group_info`
rundet bis auf die Mikrosekunde ab. Aufgeräumt: EIN `evenSpread` im Browser
statt `spreadPick` + `mpEvenSpread` (die dritte Fassung war `sqlutil.even_spread`
und die Fotoleisten wichen als einzige ab), `immich._km` heißt `rough_km` und
ist öffentlich, `district_index` prüft beide Koordinaten, die Asymmetrie
`/stop` (Starter ODER Admin) gegen `/finish` (nur Starter) steht jetzt im
Docstring. **Die drei Messfragen daraus sind mit Anmerkung 204 beantwortet.**

**Code-Durchsicht 2026-08-06 (Anmerkung 199) ist erledigt** — Backup trägt
`day_metrics`, wärmste Reise heißt wie die Reise, Stichentscheid im Überblick,
`skipped_invalid` und `discard_weather`. Die Messfrage daraus
(`_place_ranking` ohne `LIMIT`) ist mit Anmerkung 204 geschlossen.

**Gemessen 2026-08-09 (Anmerkung 204) — vier Fragen erledigt, eine repariert,
eine neue gefunden.** `DEMO=1 <python> tools/_measure_api.py` misst gegen den
ausgelieferten Demo-Bestand; die Zahlen stehen im Kopf der Datei. **Nicht mehr
aufmachen:** `_place_ranking` 27 ms bei 3.673 Orten / 199 ms bei 28.673,
`_farthest_from_home` 33/181 ms — deckeln würde die Antwort ändern, für 200 ms.
`_day_weather_candidates` 42 ms je Durchlauf, gegen Stunden Open-Meteo im
selben Lauf. Sicherung und Rücklauf über 288.428 Zeilen laufen durch, auch mit
einer `IN`-Liste von 126.361 — **das hängt aber an `psycopg2`** (bindet
clientseitig); mit `psycopg3`/`asyncpg` wäre es ein harter Fehler.
- **Repariert:** der Export las `metrics` und `event_entity_links` über ALLE
  Konten (ein zweites Konto kostete ein Drittel der Exportzeit). Besitz steht
  jetzt im Join.
- **Neu gefunden und halb repariert:** die Statistik verbrachte 94 % ihrer
  Zeit im Wetter. `weather_day.year_totals` zählt die Bilanz jetzt in SQL
  (2.326 → 1.710 ms). **Zwei Stufen sind Pflicht** — erst je (Tag, Schlüssel)
  das Minimum (`_per_day_key`, dieselbe Funktion, die `day_values` liest),
  dann die Summe: direkt über die Rohzeilen zählt ein importierter Tag mit
  dreißig Besuchen dreißigmal. **Offen bleibt die Ereignis-Seite**
  (`weather_values` + `_extreme_tops`, ~1,1 s) — die entscheidet, welche Zeile
  in zwölf Ranglisten gewinnt, und gehört in eine eigene Runde.
- **`day_values` ist die teure Auskunft** (eine Zeile je Tag UND Schlüssel).
  Für Zahlen, die man nur summiert oder zählt, ist sie die falsche.

**Rückmeldung 2026-08-09 (Anmerkung 205): die Tagesliste kam aus der falschen
Tabelle.** „Fotos verknüpfen" baute die Liste der Tage aus der EREIGNIS-Tabelle
— ein Tag, den nur der Wohnort deckt, hatte dort keine Zeile und blieb lautlos
ohne Bilder (der Verräter war wieder die Überschrift). Die Entscheidung des
Users ist die weiteste: **jeder Tag, an dem Immich Fotos hat, bekommt seine
Leiste** — ohne Rückfrage an den eigenen Bestand. Vier Sätze zum Weiterarbeiten:
- **Der Lauf hat ZWEI Phasen** (`_run_immich`): erst die Ereignisse
  (`targets` = nur noch Ereignisse), dann die Monate. `seen` wandert durch
  beide — ein Ereignis greift zuerst, der Tag sammelt auf.
- **Gefragt wird MONATSWEISE, nie je Tag.** `link_day`/`day_candidates` sind
  weg; `timeline_buckets` sagt in EINEM Aufruf, welche Monate etwas hergeben
  (mit `with_coordinates=False` — die Leiste braucht kein GPS, `photo_years`
  schon).
- **Die Marke ist die FOTOZAHL je Monat**, nicht ein Häkchen
  (`open_months`/`mark_month`, `user.settings["immich_days"]`). Nur so sind
  „nachgesehen, nichts da" und „nie nachgesehen" unterscheidbar, und ein
  nachträglicher Upload macht den Monat von selbst wieder auf. `reset()` wirft
  sie mit weg — sonst legt der Knopf den Lauf still, der die Leisten neu baut.
- **`fill_day_strips` folgt derselben Regel** (jeder Tag mit Fotos) und filtert
  seitdem nach Besitz: seine Eingabe ist die ROHE Jahresliste.

**Rückmeldung 2026-08-09, zweiter Satz (Anmerkung 206): EIN Immich-Lauf, und
der Zeitstrahl sieht Tage ohne Eintrag.**
- **`photo_points` gibt es als Job-Typ nicht mehr** — `_run_immich` macht
  beides: Phase 1 die eigenen Ereignisse, Phase 2 die Bibliothek monatsweise
  (`photo_points.scan_month`: ein Griff, daraus Ereignisse UND Tagesleisten).
  Der Name bleibt in `JOB_TYPES`, damit die Job-Historie lesbar bleibt.
- **Die Tagesregel steht nur noch in `photo_points.fill_day_strips`.**
  `immich_link.link_month` ist weg; der Aufrufer holt den Monat und reicht die
  Assets durch, `taken`/`seen` gehören ihm.
- **Vorschau und Jahresauswahl sind weg** (`/api/immich/preview`, `/years`,
  `scan_year`, `preview_summary`, `scanned_years`, `photo_years`). Entscheidung
  des Users: „im doing schaue ich mir keine 8.000 Vorschläge an." An ihrer
  Stelle steht der Rückweg; `check-p21-preview.js` → `check-immich-run.js`
  bewacht jetzt genau den. **Der Lauf bleibt im Nachtplan** — eine Maschine
  legt damit unbeaufsichtigt Bestätigtes an, ausdrücklich so gewollt.
- **Ein Ereignis je FOTO bleibt.** Der Vorschlag „je Tag+Ort" wurde geprüft und
  verworfen: `compressVisits` bündelt maschinelle Einträge eines Tages schon
  nach TITEL, der Zeitstrahl zeigt also längst eine Zeile je Tag+Ort. Echte
  Daten daraus zu machen hätte die Foto-Ebene der Karte gekostet (ein Punkt je
  Foto, Popup über `immich:photo:<asset>`). Frage ist geschlossen.
- **Im Browser dieselbe Falle wie 205:** die Tagesmenge kam aus `g.items`.
  `tlPhotoDayRows()` schiebt Marker VOR dem Gruppieren ein (wie F20 beim
  Wohnort) und entfernt sie nach dem Einsetzen der Leiste wieder.

**Doku-Umbau 2026-08-04.** `KONZEPT.md` ist aufgelöst: was das System IST steht
in `ARCHITECTURE.md`, was OFFEN ist in `ROADMAP.md`, die geschlossenen Kapitel
(MVP-Definition, Release-Risiken, beantwortete Fragen) wörtlich in
`DECISIONS.md` Anhang B. **Vor der Veröffentlichung werden die 49 alten Tags,
Releases und ghcr-Images gelöscht** (Entscheidung des Users, 2026-08-04) — der
Bestand ist ohne getesteten Upgrade-Pfad ohnehin nicht installierbar, und der
Nachweis waren nie die Tags, sondern `DECISIONS.md`. Der CHANGELOG wird beim
1.0-Schnitt archiviert (`docs/CHANGELOG-0.x.md`), nicht gelöscht.

## Frontend-Übersetzung (F10)
Deutsch steht im Quelltext und ist die Wahrheit; `I18N_EN` in `index.html`
enthält NUR Englisch. Fehlt ein Schlüssel, erscheint Deutsch — nie ein leeres
Label. Drei Wege: `data-i18n` (HTML-Inhalt), `data-i18n-title`/`data-i18n-ph`
(Attribute), `t('key', 'Deutscher Text')` (JS). Neue UI-Texte immer so anlegen.
Auch **Modul-YAMLs** kommen über die API in die Oberfläche und brauchen einen
Katalog-Eintrag (Präfix `mod.`) — das YAML selbst bleibt deutsch, es ist die
Quelle, nicht die Anzeige. Zahlen und Daten folgen `LOC()`, nie hart `'de-DE'`.
**Achtung TDZ:** `LANG`/`I18N_EN` stehen bewusst VOR dem Theme-Block, weil
`applyTheme()` schon beim Laden `t()` ruft. Prüfen mit jsdom statt nur Syntax:
ein Syntaxcheck übersieht genau diese Fehlerklasse.
