# CLAUDE.md — Arbeitsanleitung für dieses Repo

## Was ist das
Life-Dash: self-hosted „Lebensdatenbank" (FastAPI + SQLAlchemy/SQLite; Vanilla-JS-PWA
komplett in `frontend/index.html`, wird vom Backend unter `/` ausgeliefert). AGPL-3.0.
**Führendes Dokument: `docs/KONZEPT.md`** — Roadmap in Kap. 14.2 (Paket-Nummern A*/F*/P*),
Entscheidungen/Anmerkungen in Kap. 15. Erst dort gezielt nachlesen statt Code raten.

## Kommandos (Windows!)
- Python: `C:\Users\phili\miniforge3\envs\py313\python.exe` — **kein `python` im PATH**
- Tests: `cd backend` → `<python> -m pytest tests -q` (laufen offline: Mock-KI, Geocoding aus)
- Smoke-Server mit Scratch-DB (echte DB nie anfassen):
  `$env:DATABASE_URL="sqlite:///./_smoke.db"; $env:AUTH_MODE="dev"; $env:AI_PROVIDER="mock"`
  dann `<python> -m uvicorn app.main:app --port 8123` aus `backend/`
- JS-Check: Inline-Scripts aus index.html per node `new Function(...)` syntaxprüfen

## Architektur-Kurzfassung
- Vier Schichten: Fragment (Roh-Eingang, nie automatisch löschen) → unconfirmed (Vorschlag)
  → confirmed (**Lebensdatenbank — Maschinen ändern Bestätigtes nie, Anreicherung wie
  Wetter nur ADDITIV**) → Ableitungen (Embeddings/Ansichten, jederzeit neu berechenbar)
- `backend/app/`: `models.py` (Event mit parent_event_id/F7, note=Markdown/F1),
  `migrate.py` (ALTER-TABLE-Migrationen: `_MISSING_COLUMNS`), `routers/` (events,
  moderation, tracks=Timeline-Import+Ortsnamen, jobs=Background-Worker mit Lock pro Typ,
  admin, data=Export/Import, auth=OIDC, world=F5, achievements=F6), `services/`
  (ingestion, enrichment=Wetter, geocode=Nominatim/LocationIQ mit 429-Backoff,
  weather=Open-Meteo, achievements=F6-Metriken), `data/countries.py` (Länder-Stammdaten:
  Name→ISO→Kontinent; passt zu `frontend/world-countries.geojson`)
- `frontend/index.html`: EIN File (CSS+HTML+JS, ~3600 Zeilen) — **gezielt per Grep und
  Read mit offset/limit lesen, nie komplett**
- Module deklarativ: `backend/modules/*.yaml` (Kategorien, Labels, Farben, Kompendium)

## Arbeitsregeln (vom User festgelegt)
- **NIE pushen oder taggen** — Commits ja; Push/Tag macht der User selbst
- **Zwei Gleise (Anmerkung 86):** Push auf `main` → Image `:main` (Testen, ohne
  Version). SemVer-Tag → `:X.Y.Z`/`:latest` (Veröffentlichung). Eine neue
  Version also nur, wenn ein NUTZER einen Unterschied merkt — mehrere Pakete
  dürfen sich eine teilen. Nicht mehr je Arbeitspaket eine Nummer vergeben.
- Jede Version: `backend/app/version.py` + `CHANGELOG.md` (verständliche Produktsprache,
  **keine Paketkürzel** wie „A25") + KONZEPT-Tabelle abhaken (✅ + „fertig vX.Y.Z")
- Commit-Stil: deutsch, `feat(bereich): X.Y.Z — Beschreibung` (Historie ansehen)
- Doku derzeit deutsch; Paket F10 stellt sie später einmalig auf Englisch um
- Neue Event-Kategorie? Drei Stellen: KI-Prompt/Module-YAML, Frontend (catLabels/Farben/
  KNOWN_CATS/FILTER_CATS_BASE + CSS), ggf. Selects im HTML
- Allgemeingültigkeit (A27): nichts Homelab-Spezifisches hart verdrahten (Provider-Namen
  etc. aus Config); `.env.example` ist die Setup-Referenz

## Stand
Umgesetzt bis **v0.39.0** (2026-07-23). **Gruppe A ist komplett** (A1–A48),
Gruppe B bis **F19**; **P5.1, F1 und P2.1 (alle drei Stufen) sind fertig**. Offen
ist damit nur noch: **0.40 (offen, sammelt auf `main`)**, **Demo-Modus (0.41)**
und **R1** (1.0, drei Etappen auf `main`).

**Arbeitsweise ab 0.40 (vom User festgelegt, 2026-07-23): alles auf `main`,
kein Versionssprung, bis der User den Demo-Modus ansagt.** Was sich bis dahin
angesammelt hat, wird 0.40.0 — voraussichtlich überwiegend Fixes. `version.py`
bleibt so lange auf **0.39.0**, neue CHANGELOG-Punkte gehen unter
`[Unreleased]`; die Anzeige sagt dann `0.39.0-dev`, und genau dafür gibt es die
Kennung (Anm. 86). **Nicht bei jedem Paket die Version hochziehen** — das war
zweimal die Ursache für den Anm.-91-Defekt: ein Bump als Startschuss statt als
Schlussstrich.
**Tageswetter vereinheitlicht (Anmerkung 119, auf `main` ohne Versionssprung).**
Aus der Frage „ein Tag hat zwei Orte — wo steht dann das Wetter?" fielen VIER
Antworten auf eine Frage: Zeitstrahl = Wetter des A39-Vertreters `min(id)`
(UUIDs, also ein zufälliger von fünf Besuchen), Client-Sammelkarte = gar keins
(sie ruft `eventChips` nicht auf), Erfolge = `min` je Tag, Statistik-Bilanz =
**erstes Ereignis des Tages**. Anm. 106 in Reinform. Jetzt EINE Regel in
`services/weather_day.py` (Schicht 4): Zahlen = Minimum des Tages (der
VORSICHTIGE Wert), Texte nur bei Einigkeit des Tages, dazu `regions` = Zahl der
berührten 0,1°-Zellen NEBEN dem Wert (A40: was nicht alles zeigen kann, muss es
sagen). Endpunkt `/api/days/weather`, Tageskopf im Tages-Zoom.
**Zwei Fragen bleiben bewusst verschieden beantwortet:** OB ein Tag zählt
(Erfolgs-Schwelle) fragt weiter „irgendein Eintrag erreicht es" — sonst würden
verdiente Abzeichen aberkannt (`test_f19_badges.py` seit 0.35) —, WAS er
beisteuert, ist immer der vorsichtige Wert. Als Vorfilter geschrieben macht die
Schwelle beides zugleich (11 h + 3 h mit `min: 10` ergibt 11, nicht 3): deshalb
`having`. Dazu ein Prozess-Cache in `fetch_weather` je (Tag, Koordinate auf 2
Stellen ≈ 1,1 km) — bewusst NICHT gröber (0,1° läge AUF der Auflösung der
Quelle) und **Fehlschläge werden nicht gemerkt** (Gegenrichtung zur
Endlos-Abruf-Falle: ein Prozess-Cache, keine dauerhafte Marke).
**Feedback-Runde: die App tat es und sagte es nicht (Anmerkung 120, auf `main`
ohne Versionssprung).** Sieben gemeldete Punkte, sechs davon derselbe Defekt.
**(a)** „Nachsehen" schrieb sein Ergebnis ans ENDE der Beschreibungsspalte
daneben — auf einem breiten Bildschirm die andere Hälfte, hinter zehn Zeilen
Erklärung; jetzt volle Zeile UNTER dem Knopf (`.action-row.has-result`), dazu
Ladezustand und Toast. **A40 andersherum: eine Ansicht, die etwas zeigen KANN,
muss es dorthin stellen, wo hingeschaut wird.** **(b)** Jeder Job-Start sprang
in den Jobs-Reiter, und das WAR die Rückmeldung — bei zwanzig Jahren
zwanzigmal weg vom Knopf. Jetzt ein Live-Streifen oben in „Meine Daten"
(`#data-jobs`, `startServerJob(..., stay=true)`); **der zuletzt beendete Lauf
bleibt mit seinem Ergebnis stehen**, sonst ist der Satz, für den es den Lauf
gibt, der einzige, den niemand sieht. **(c)** Laufende Jobs rutschten unter
die abgeschlossenen und fielen aus den zwölf Zeilen: **Abgeschlossenes ist
eine Chronik, Laufendes ein Zustand — nur die Chronik wird beschnitten**
(`list_jobs` liefert Aktive vollständig und zuerst). **(d)** `photo_points`
stand als nackter Schlüssel da; das Backend kannte sein Label längst — **ein
Fallback, der wie eine Anzeige aussieht, versteckt die Lücke**, Wächter
`check-job-labels.js` vergleicht `JOB_TYPES` gegen deutsche Tabelle UND
englischen Katalog, in beide Richtungen. **(e) „Alle Jahre" für beide
Immich-Läufe:** die Jahresaufteilung (Anm. 107) war für eine ANFRAGE richtig
(25-s-Budget der Vorschau, abgeleitet aus der Geduld umgekehrter Vertreter),
nie für einen Hintergrund-Job. Die Vorschau geht die Jahre EINZELN durch —
eine Sammelanfrage antwortete mit einem Ausschnitt, und ein Ausschnitt hebt
den Riegel nicht auf („ein Zwanzigstel sehen, alles anlegen") —, und der Lauf
bekommt `imsPreviewedYears`, die Jahre der VORSCHAU, nicht die der Auswahl
(Anm. 106: zwei Angaben über dieselbe Sache laufen auseinander). **(f)**
Fotopunkte wachsen mit dem Zoom, kräftigerer Rand; die REIHENFOLGE bleibt
(Fotos unter den Pins — was oben liegt, sagt, was zählt). **(g) Die siebte
Frage brauchte eine Antwort, keine Änderung:** ein aufgelöster Ortsname
verschiebt die Koordinate NICHT — `reverse_geocode` liefert keine, und im
ganzen Backend gibt es genau eine Zuweisung an `Location.lat` (in einem
ungespeicherten Vorschlag). **Nebenbefund:** das Leaflet-Doppel gab für jede
Eigenschaft sich selbst zurück, also auch für `getZoom()` → jeder Vergleich
`z >= 14` stürzte ab. In 20 Wächter-Dateien dieselbe Kopie. Neu:
`test_multi_year_jobs.py`, `check-job-labels.js`.
**Zwei Selbstfunde:** `round(x, 1)` gibt es auf PostgreSQL nur für `numeric`,
nicht für `double precision` (`sqlutil.weather_cell`, geprüft in
`test_a37_postgres_dialect.py`); und die erste Spannen-Grenze des Endpunkts
(4000 Tage) hätte in einem dünnen Bestand jede Seite von 1994 bis heute
getroffen und das Tageswetter still weggelassen — die Antwort ist ohnehin durch
die 300 Ereignisse der Seite begrenzt. **Eine Grenze aus dem falschen Grund
wird zur stillen Auslassung.** Wächter `tools/check-day-weather.js` +
`tests/test_weather_day.py`, beide gegen fünf injizierte Defekte gefahren
(Anm. 108) — eine Zusicherung war dabei zuerst aus dem falschen Grund grün.

Hinter 1.0 bleiben
nur noch neue Import-Konnektoren (P2.8 OwnTracks, P2.9 Automatisierung,
P2.10 Trakt, P2.11 Dawarich/GPX, P4.1 Health, P4.2 PSN) plus **P5.2**
(Whisper — einzige Ausnahme, schwere neue Laufzeit-Abhängigkeit).

**Releaseplan bis 1.0 steht in KONZEPT Kap. 14.3.** Fertig: 0.21 A28+F14 ·
0.22 F13 · 0.23 F11+F12 · 0.24 F15 (Fotos) · 0.25 P2.1 (Immich, Stufe 1) ·
0.26 A29 (ZIP-Backup) · 0.27 Fixes (A31/A32/A30) · 0.28 F16+A33+A34 ·
0.29 A35 (lokale Konten) · 0.30 P3.1 · 0.31 A36+F17 (schlanke Liste, Alter) ·
0.32 A37 (serverseitiges Zeitfenster) · 0.33 A38+A40 (Mobil-Layout,
Kartenschalter) + dev-Kennung · 0.34 A39+F18+A41 (Städte, Tages-Fotos) · 0.35 F19+A42 (Sammlung) ·
0.36 P5.1+F1-Rest (Erfassen) · 0.37 P2.1 Stufe 2 (Immich als Quelle) ·
0.38 Feedback-Runde (Anm. 110) · 0.39 A45–A48 + P2.1 Stufe 3 (Anm. 116).
Offen: **0.40 (was sich ansammelt)** · **0.41 Demo-Modus** ·
**1.0 = Veröffentlichung**. Kein Termindruck (Anmerkung 58).
Dort nachsehen statt Reihenfolge raten.

**Was hinter 1.0 wartet, entscheidet die ART (Anmerkung 101, 2026-07-22):**
neue Import-Konnektoren warten, alles andere nicht — vorher galt „nicht
dringend", was P5.1, F1-Rest und P2.1 Stufe 2 grundlos nach hinten schob.
Begründung: 1.0 ist per Ausschluss definiert als „vollständiges Werkzeug zum
Erfassen und Erkunden von Hand", und ein Konnektor erweitert die *Zufuhr*,
nicht das Konzept. Ein Paket, das Erfassen oder Erkunden verbessert, ist
deshalb gar kein 1.x-Kandidat. Preis: drei Releases mehr vor dem Demo-Modus,
bewusst in Kauf genommen; Rückzugsreihenfolge steht in 14.3.

**Achtung Tags (Anmerkung 91):** `v0.32.0` wurde gesetzt, als A38 noch
fehlte — deshalb ist A38 zu 0.33.0 geworden und der Rest um eins gerutscht.
Ein Tag ist das einzige Unveränderliche hier: **zuletzt setzen, nicht als
Startschuss für das letzte Paket.** Zum Testen reicht Push auf `main`.
**Zweites Auftreten, beim Nachtaggen am 2026-07-23 gefunden:** der Bump auf
0.38.0 (`567c275`) lag **elf Commits vor** dem Ende dessen, was das CHANGELOG
unter 0.38.0 beschreibt (Anm. 111–113 kamen danach). Nicht der Tag war früh,
sondern der Bump — `v0.38.0` gehört deshalb auf `d753d0d`, den ersten Commit,
bei dem die Sektion vollständig und `[Unreleased]` leer ist. **Der Prüfsatz
für jeden Tag lautet: an diesem Commit muss `[Unreleased]` LEER sein.** Ab 0.40
erübrigt sich die Frage, weil der Bump erst beim Release gesetzt wird.

**Nur noch drei Versionen bis 1.0 (Anmerkung 89).** Härtung,
Projektoberfläche und Freeze-Pass sind KEINE eigenen Versionen mehr,
sondern drei Etappen von 1.0.0 — sie laufen auf `main` (`:main`-Image)
und bekommen einen einzigen Tag. Grund: bis zur Veröffentlichung gibt es
genau einen Betreiber (den User), und der merkt ein gepinntes Base-Image
nicht. Der Plan war älter als Anmerkung 86 und wurde nachgezogen.
**Regel für künftige Einschübe:** eine eigene Version nur bei
Schema-Folge UND beobachteter Beschwerde — sonst reicht `main`.

**A38 fertig (v0.33.0, Anmerkung 82).** Untere Leiste trägt vier Ziele +
„Mehr"-Sheet (statt neun à 40 px); das Sheet wird aus der Sidebar GEKLONT,
also nie zweitpflegen. Bearbeiten-Dialog = die Detailansicht (Klick auf
Karte öffnet ihn) und jetzt Bottom Sheet mit `dvh` + klebender Knopfleiste.
**Zwei Regeln, die `tools/check-a38-mobile.js` erzwingt:** kein Inline
`min-width` (Inline schlägt Stylesheet → Media Query kommt nicht dran) und
kein `max-height` in `vh` (rechnet ohne Adressleiste). Beide Defekte saßen
an mehr Stellen, als die Audit-Liste kannte.

**A40 fertig (v0.33.0, Anmerkung 92).** Kartenschalter: „Zurückgelegte Wege"
(gemessen) vs. „Reihenfolge verbinden" (gezeichnet) — hießen vorher beide
„Route"; „Punkte zusammenfassen" ist EIN Schalter für Bündeln (ab Monat, je
Ort) und Clustern (Tag/Woche, nach Nähe), Schwelle jetzt in den Einstellungen.
**Design-Regel daraus (gilt allgemein):** Ein Bedienelement, das gerade nichts
bewirken kann, muss das ZEIGEN — `.filter-chip.inert` (durchgestrichen +
Begründung im Titel), bewusst anders als `.off` (vom Nutzer ausgeschaltet).
Der wiederkehrende Defekt in diesem Projekt ist nicht Kaputtheit, sondern
**Stille** (siehe auch A37-Kacheln, Anm. 79 Immich-Verknüpfung).

**A39+F18 fertig (v0.34.0).** `Location.city` als echtes Feld (Rückfüllung im
A28-Lauf; **Leerstring = „nachgesehen, keine Stadt", NULL = „nie nachgesehen"** —
ohne die Unterscheidung fragt der Lauf stadtlose Orte ewig neu ab, vgl. F12
`weather_rev`). Zeitstrahl verdichtet importierte Besuche je (Tag, Stadt);
**verdichtet wird VOR dem Blättern**, sonst zerschneidet die Seitengrenze eine
Gruppe und beide Hälften zeigen zu kleine Zahlen. Sammelkarte ist kein
Ereignis → Klick klappt auf statt zu bearbeiten. `MediaRef.event_id` nullable:
Fotos hängen wahlweise am Tag (`captured_at`). **Erste Migration, die eine
Spalte ÄNDERT** — SQLite braucht Tabellen-Neubau (`_relax_not_null` in
migrate.py), und beim Kopieren muss jede NOT-NULL-Spalte einen Ersatzwert
bekommen: Bestandszeilen haben dort NULL, weil die Spalte per ADD COLUMN kam.
**Wer Medien sucht, sucht sie über `user_id`, nicht über Events** — sonst
fehlen Tages-Fotos beim Löschen, Aufräumen und im Export.

**A42+F19 fertig (v0.35.0, Anmerkungen 102–104).** **A42:** Städte haben jetzt
eine Seite wie jeder andere Sammlungstyp — `/api/cities/detail` (Orte,
Ereignis-VORSCHAU mit Gesamtzahl, A37) und `/api/cities/describe` mit
`city_info` als Cache. Städte bleiben bewusst **keine `Entity`** (Anm. 95),
deshalb eigene Endpunkte statt `openEntityDetail`. Drei Regeln daraus:
**(a)** Das Land geht in die Wikidata-Suche, sonst ist „Frankfurt" eine
Begriffsklärung; **(b)** ein Fehlversuch wird GESPEICHERT (Zeile ohne
`description` = „nachgesehen, kein Artikel", Neuversuch nach 30 Tagen) — dieselbe
Endlos-Abruf-Falle wie F12 `weather_rev` und A39-Leerstring, jetzt zum dritten
Mal; **(c)** `city_info` hat bewusst KEINE `user_id` (Wikipedia gehört
niemandem), der Zugriffsschutz sitzt an den eigenen Orten.
`services/wikipedia.py` ist nicht mehr fest deutsch, `Entity.attributes` trägt
`desc_lang`. **F19:** Über Platin zählt eine erzeugte Marke weiter (1 · 2,5 · 5
je Zehnerpotenz) — **aber nur bei unbegrenzten Metriken**: es gibt sieben
Kontinente, „nächste Marke: 10" wäre ein Rechenfehler mit Anspruch (Anm. 104).
**Der eigentliche Grund für vorverdiente Abzeichen war ein Zählfehler, keine
Schwelle** (Anm. 103): die Wettermetriken zählten Einträge, wo überall „Tage"
stand — A31/Anm. 64 hatte in dieser Datei überlebt. Frage bei jeder
Invarianten-Reparatur: *wo gilt derselbe Satz noch?*

**Immich-Durchsicht (Anmerkung 111, in 0.38.0) — zwei Nähte, zwei Defekte,
404 Tests haben keinen bemerkt.** **(a)** `asset_time` las `fileCreatedAt`
(laut Spec **UTC**) und schnitt die Zone ab statt sie anzuwenden → ein Foto vom
13.5. 01:30 Berlin landete auf dem **12.** Nicht eine Stunde daneben, ein TAG —
und am Tag hängen der F18-Behälter und der Platz eines Vorschlags. Immich
liefert `localDateTime` genau dafür („timezone-agnostic … grouping by local
days"). **Regel: bietet eine API zwei Zeitstempel, beantwortet einer eine
andere Frage — und „Zone abschneiden" ist nie „in Ortszeit umrechnen".**
**(b)** Stufe 1 kannte nur `google_timeline` als maschinelle Quelle und hängte
den Fotovorschlägen aus Stufe 2 deren eigene Bilder an — gegen Anm. 107 Fall 6.
**Das ist Anmerkung 106 in genau dem Code, der sie zitiert:** dieselbe Regel
stand zweimal wörtlich da, und die zweite maschinelle Quelle brachte sie zum
Auseinanderlaufen. Jetzt EINE Liste `MACHINE_SOURCES`, die `candidates()` und
`day_candidates()` beide lesen. **Gewohnheit daraus: bekommt ein Paket eine
zweite Stufe, die ältere Hälfte mit den Regeln der neueren lesen** — beide
Befunde saßen dort, wo die Annahme des einen Teils auf die des anderen trifft,
und genau dort greift kein Test von selbst.

**0.39.0 fertig (Anmerkung 116) — A45–A48 + P2.1 Stufe 3.** Drei Beobachtungen
aus der Nutzung, und jede war eine Frage ans MODELL, nicht an die Anzeige.
**A45 (Fotopunkte):** Der geplante Weg — Spalten an `MediaRef` — hätte nicht
getragen, denn `MediaRef` ist auf **zwölf Bilder je Tag** gedeckelt
(`immich_link.MAX_PER_EVENT`), und das ist richtig: es beantwortet „welche
Bilder stehen neben diesem Eintrag?". Die Karte hätte zwölf Punkte je Tag
gezeigt und ausgesehen, als ginge sie. **Zwei Fragen mit zwei Deckelungen
teilen sich keine Tabelle** — in einer Zeile wären es zwei Bedeutungen in
derselben Spalte (Anm. 106 in seiner teuersten Form). Deshalb `photo_points`,
Schicht 4, verwerfbar. **Ein Foto wird trotzdem kein Ereignis** (Anm. 87): die
Punkte sind eine ausblendbare EBENE, im Zeitstrahl je (Tag, Ort) verdichtet.
**A46 (Besuchstage):** eine Zeile Ursache, viel Folge — `date_end` roh aus dem
Google-Besuch übernommen, also war jede Nacht im eigenen Bett ein zweitägiges
Ereignis. Mehrtägig entsteht ab jetzt nur noch von Hand. Der Aufräum-Lauf für
den Bestand fasst BESTÄTIGTES an; daraus folgt jede seiner Grenzen (nur auf
Knopfdruck, nie im Nachtplan, nur `google_timeline`, Vorschau nennt die Zeilen
DANACH). Teuer war die Idempotenz: Bestandszeilen tragen den nackten Hash, und
wer nur die neuen Teil-Schlüssel kennt, legt beim Re-Import alles ein zweites
Mal DANEBEN an. **A47 (Granularität):** Land → Stadt → Ortsteil → Punkt,
serverseitig verdichtet (A39/A37: verdichtet wird VOR dem Blättern). Ortsteil
aus `Location.address` über eine Fallback-Kette — Nominatim nennt die Ebene je
nach Land `suburb`, `city_district`, `neighbourhood` oder `quarter`.
**A48 (Vektorkarte):** Immichs Stil ist `"type": "vector"` (Spezifikation 8) und
gar kein API-Endpunkt, sondern eine Admin-Einstellung — Leaflet kann ihn nicht
zeichnen, es braucht MapLibre plus Brücke. **P2.1 Stufe 3:** Alben nur noch auf
Nachfrage; ein Album war EIN mehrtägiger Vorschlag mit einem Kartenpunkt und der
Zwilling der handerfassten Reise.

**Drei Fallen, die 0.39 ein weiteres Mal gestellt hat:**
**(a) Die Endlos-Abruf-Falle, siebte und achte Auflage** (nach F12
`weather_rev`, A39-Leerstring, A42 „kein Artikel", P2.1-Grabstein, Anm. 114
`_name_defect`): die durchsuchten Foto-Jahre müssen gemerkt werden, und
`Location.address` braucht eine Marke im FEHLSCHLAG. Die zweite ist die
schwierigere, weil die Marke an den **frühen Ausstiegen** sitzt — den Pfaden,
die man nicht als schreibend denkt. **Und sie hat zugeschlagen:** nachdem der
Adress-Nachzug am Ortsnamen-Lauf hing, lief die Testsuite endlos. Sichtbar
gemacht hat es ein Test-Doppel, das das alte Verhalten treu nachbaute — **ein
Doppel, das ein Feld auslässt, ist keine Vereinfachung, sondern eine andere
Funktion.** **(b) JSON-Spalten speichern Python-`None` als JSON-`null`, nicht
als SQL-NULL.** `address IS NULL` traf die Zeilen nicht; ohne
`JSON(none_as_null=True)` hätte der Rückfüll-Lauf sie für immer übersehen und
der Index behauptet, es sei nichts offen. **(c) `= Query(False)` als Default
kommt beim Direktaufruf als Query-OBJEKT an und ist damit wahr** — der
Alben-Schalter stand überall auf AN, wo niemand ihn gesetzt hatte. Die Falle
stand seit A37 in `events.py` aufgeschrieben (`Annotated` statt Query-Default)
und ist hier zum zweiten Mal aufgetreten.

**Wächter gegen den kaputten Stand — und zwei, die im ersten Anlauf wertlos
waren.** Anm. 108 verlangt, jede Prüfung einmal gegen den Defekt zu fahren, den
sie festnageln soll. Dabei fiel auf: eine prüfte auf die Ziffer `4`, die auch im
Datum `2026-07-04` steckt; eine andere injizierte den Defekt in den DEUTSCHEN
Quelltext, während die Seite unter jsdom **englisch** startet — der Defekt
erreichte die Zusicherung nie. Neu: `check-a46-visit-split.js`,
`check-photo-layer.js`, `check-tl-granularity.js`, `check-vector-basemap.js`.
Dazu ein HTTP-Doppel für Immich (`tools/immich_double.py` +
`tools/smoke_a45.py`, Anm. 109): 1200 Assets in den echten DTOs prüfen
Blättern, Besitzfilter, den Mitternachts-Fall aus Anm. 111 und die
Ortsteil-Ableitung in einem Lauf — nichts davon erreichen Unit-Tests, weil sie
den Client komplett ersetzen. **Aus dem Repo-Wurzelverzeichnis starten:**
`<python> tools/immich_double.py &` und `<python> tools/smoke_a45.py`.

**Feedback-Runde nach 0.38.0 (Anmerkung 114) — sechs Punkte, drei davon ein
zweites Mal derselbe Defekt.** Liegt auf `main`, **ohne Versionssprung**
(Anm. 89: eigene Version nur bei Schema-Folge UND Beschwerde — hier gibt es
kein neues Feld). **(a)** Karte auf dem Handy unsichtbar: Anmerkung 34 eine
Ebene höher — der Rahmen für den Kartenhinweis (Anm. 110) trug `flex: 1`,
und in Spaltenrichtung heißt das `flex-basis: 0` in der HÖHE. **Ein Wächter,
der nur seinen Auslöser kennt, ist einer für die Vergangenheit** —
`check-a38-mobile.js` prüft jetzt die ganze Kette zwischen `.map-layout` und
`#map`. **(b)** Fotoleisten standen am ENDE ihrer Gruppe, also hinter
„x weitere anzeigen" — an genau den Tagen, an denen fotografiert wurde. Der
Kommentar darüber sagte „oben"; der Code hängte an. **(c)** „Zuhause"/
„Arbeit" sind keine Ortsnamen (A19 hatte das für „Gesuchte Adresse" schon
entschieden): der `semanticType` geht jetzt in `Location.type` — **und ein
Typ, der an einem Anzeigetext hängt, verschwindet mit ihm**. **(d)**
Endlos-Abruf-Falle, fünfte Auflage: `_name_defect` zählte Kommas, aber
`short_name` stellt den POI-Eigennamen VORAN — jeder benannte Ort galt ewig
als „zu lang". Mit `Location.address` ist es eine Rechnung statt einer
Schätzung. **(e)** Die Bausteine-Auswahl zeigte vier leere Kästchen und
meinte alle vier (`sanitize_parts`): **eine Voreinstellung muss an beiden
Enden dieselbe sein**. **(f)** ~200 im JS gebaute Texte waren nie
übersetzbar; `t()` fällt still auf Deutsch zurück, deshalb drei Jahre
unbemerkt. **Siebte Quelle, direkt danach gemeldet: die Modul-Dateien** —
Abzeichen und Modul-Kennzahlen (`backend/modules/*.yaml`) kommen über die API
in die Oberfläche, sind also Text aus einer anderen Richtung; jeder frühere
Durchgang über `index.html` musste sie verfehlen. Übersetzt wird trotzdem im
Katalog (Präfix `mod.`), **das YAML bleibt deutsch: es ist die Quelle, nicht
die Anzeige.** Neu: `tools/check-i18n-coverage.js` (jeder Schlüssel im Katalog,
kein verwaister Eintrag, kein deutscher Text IM Katalog — und er **liest die
Modul-YAMLs**, denn wer eine Modul-Datei schreibt, denkt nicht an den
englischen Katalog) und `check-place-format.js`. Zahlen/Daten folgen jetzt `LOC()` statt hart
`'de-DE'`. Dazu die sechs F12-Wetterrekorde (UV, Böe, gefühlt, Tageslicht) —
die Werte kommen seit 0.22 mit; **eine Null ist beim Regen kein Rekord, beim
Tageslicht schon** (Polarnacht = kürzester Tag, vgl. Anm. 104).

**Einstieg-Reihenfolge (Anmerkung 115, nach 0.38.0, auf `main` ohne
Versionssprung).** README hat jetzt einen Guide „Getting started — a sensible
order", und „Meine Daten" steht in derselben, nummerierten Reihenfolge:
**Module → Google-Timeline → Ortsnamen → Immich (verbinden → vorschlagen →
bestätigen → Fotos) → Tages-Einträge → Wetter → Backup.** Zwei Gründe, die
keine Vorlieben sind: **Ortsnamen früh**, weil das der einzige von außen
gedrosselte Lauf ist (Nominatim) und weil bis dahin alles „Ort (53.49, 10.00)"
heißt; **Wetter zuletzt**, weil es jede Zeile genau einmal fragt (F12-Marker) —
ein Lauf, der einmal fragt, gehört ans Ende, nicht an den Anfang. Die Abschnitte
standen vorher in ihrer Bauzeitpunkt-Reihenfolge (Backup oben, Module unten):
**das ist ein Änderungsprotokoll, keine Anleitung.**
**„Wetter ergänzen" ist aus dem System-Reiter nach „Meine Daten" gewandert** —
der Reiter ist `admin-only`, der Endpunkt war es NIE: eine reine
Oberflächensperre über einer instanzweiten Aktion. Jetzt filtert
`enrich_weather(user_id=…)` auf das startende Konto; `recompute`/`embeddings`
bleiben in System (die rechnen wirklich über alles). **Die Sperre bleibt
global**: sie schützt nicht die Daten, sondern das Kontingent bei
Open-Meteo/Nominatim/Immich, und das hängt an der Instanz.
**Der stille Befund dabei: der Nachtplan fragte „lief das heute schon?" ohne
„bei wem?"** — ab dem zweiten Konto nimmt der erste Nutzer allen anderen den
Termin, Nacht für Nacht, ohne Fehlermeldung. Galt schon für `resolve_names`,
`immich`, `immich_source`. Jetzt EINE Liste `USER_SCOPED_TYPES` (dieselbe Form
wie `MACHINE_SOURCES`, Anm. 111). Tests: `backend/tests/test_job_scope.py`,
gegengeprüft am kaputten Stand (3 von 8 fallen dort um).

**Feedback-Runde 0.38.0 (Anmerkung 110) — zwei teure Befunde, beide Stille.**
**(a)** Der Bild-Endpunkt hielt seine DB-Verbindung, während er bei Immich auf
das Foto wartete (15 s Zeitlimit). Hinter HTTP/2 feuert der Browser dutzende
Bildabrufe parallel → Pool leer → **jede** Anfrage scheitert, auch die des
Zeitstrahls, der deshalb „endlos lädt". **Regel: ein Proxy-Endpunkt ist kein
Datenbank-Endpunkt** — Verbindung VOR dem Netzaufruf zurückgeben, danach nur
noch Werte anfassen (jeder ORM-Zugriff nach `close()` holt sie sich wieder).
**(b)** Die Karte zeichnete ohne Bündelung `all.slice(0, 300)` — die ersten
300 CHRONOLOGISCH — und schwieg darüber; der Hinweis stand nur in der Liste
daneben. **A40 einen Schritt weiter: auch eine ANSICHT, die nicht alles zeigen
kann, muss das sagen — und zwar dort, wo hingeschaut wird.**
Dazu: `Location.address` bewahrt jetzt die Roh-Bausteine (Umformatieren ohne
Netz statt 1,2 s je Ort), eigene Kachel für unscharfe Daten, Schalter für
importierte Besuche in „An diesem Tag" (der Parameter existierte seit F16, die
Oberfläche hat ihn nie gesetzt — **ein Standard, den man nicht ändern kann, ist
keiner**), Fotoleisten folgen der Zoomstufe (Woche gebündelt, ab Monat 12 von N
und die Beschriftung sagt es). Wächter: `check-map-nothing-hidden.js`,
`check-photo-strips.js`.
**Zwei Entscheidungen festgehalten:** Französisch-Guayana bleibt Frankreich/
Europa (politisch korrekt, Preis bewusst); und die Wikipedia-Frage —
**ein ausgehender Abruf muss einer GESPEICHERTEN eigenen Tatsache dienen**
(Anm. 100), deshalb Stadtbeschreibung ja, Geburtstag „des Tages" nein.

**P2.1 Stufe 2 fertig (v0.37.0, Anmerkung 109).** Immich schlägt jetzt
Ereignisse vor: Fototage (Tag + Ort) und Alben, beide `unconfirmed`, jahresweise
mit **Pflicht-Vorschau**. `services/immich_source.py`, Endpunkte
`/api/immich/years|preview`, Job `immich_source`. **Kein Schema.**
**Identität ist der PLATZ** (`immich:day:<datum>:<ort>`, `immich:album:<id>`),
nie ein Hash über die Assets — sonst wird ein nachgeladenes Foto zum zweiten
Vorschlag. **Grabstein = das Fragment**: `discard_event` löscht das Ereignis,
das Fragment bleibt und trägt den Platz → ein abgelehnter Vorschlag kommt nie
wieder (vierte Auflage der Endlos-Abruf-Falle nach F12/A39/A42).
**Die OpenAPI-Spezifikation lesen, nicht die Attrappe fragen** — zehn Minuten,
drei Entscheidungen gekippt: Alben filtert der Server (`?isOwned=`), **Assets
NICHT** (`MetadataSearchDto` hat kein Besitzfeld → auf der Antwort über
`ownerId` + `/users/me`); `exifInfo` liefert **city/state/country** (kein
Nominatim, und stabiler als ein Koordinatenraster, dessen Zellenrand mitten
durch eine Stadt läuft); `visibility` hält Archiviertes und **Gesperrtes**
draußen. Zweites Mal, dass die Spezifikation eine Annahme dieses Konnektors
umbringt (Stufe 1: `takenAfter` braucht eine Zeitzone).
**Der Smoke-Lauf gegen ein HTTP-Doppel fand, was Unit-Tests nicht konnten:**
die Jahresauswahl kam aus dem EIGENEN Bestand und bot damit ausgerechnet die
Jahre nicht an, für die es das Paket gibt (vor dem Smartphone gibt es keine
Besuche) → jetzt `/timeline/buckets` mit Fotozahl je Jahr.
Wächter: `tools/check-p21-preview.js` (Vorschau-Pflicht, Jahreswechsel
entwertet sie).
**Selbstkontrolle 0.37.0 — fünf Befunde, vier davon an derselben Grenze:** dort,
wo die Test-Attrappe aufhört und der echte Client anfängt. Silvester-Album aufs
Laufjahr beschnitten (das Jahr entscheidet OB, nicht WAS); Scan ohne Herzschlag
→ Job nach 180 s als verwaist eingesammelt, nachdem er alles getan hat; dann
riss das weite Album-Fenster `_stamp` auf (`astimezone()` wirft unter Windows
`OSError` vor 1970 — **das fand nur der Smoke-Lauf**, Unit-Tests ersetzen
`search_assets_paged` komplett); zwei Springfields wären ein Ort geworden
(Anm. 105: Schlüssel ist `(Stadt, Land)` — neu vergeben heißt gleich richtig);
20.000-Grenze schnitt still. **Regel: bei jedem Konnektor zusätzlich ein
HTTP-Doppel fahren, das sich an die echten DTOs hält** — zwanzig Zeilen, drei
Befunde, einer davon für Unit-Tests prinzipiell unerreichbar.

**P5.1+F1 fertig (v0.36.0, Anmerkung 108).** Das Loch beim Offline-Erfassen war
nicht die fehlende Warteschlange, sondern die **Eingangstür**: `init()` hatte
EINEN Zweig für zwei Fehler — „nicht angemeldet" und „Anfrage kam nie an" —,
also stand man ohne Netz vor einer Anmeldemaske, die ohne Netz nicht bedienbar
ist. Unterscheidungsmerkmal ist jetzt `err.status` (vorhanden = der Server hat
GEANTWORTET), und dieselbe Unterscheidung braucht die Warteschlange dreimal:
**puffern** nur ohne Status (ein gepuffertes 422 wird ewig wiederholt),
**abbrechen** bei Netzverlust, **nicht abstempeln** bei 401 (nach dem Anmelden
geht derselbe Eintrag durch — die einzige unumkehrbare Fehlentscheidung in
einem Mechanismus, dessen Zweck Umkehrbarkeit ist). Wiederholen heißt
Doppelte in Kauf nehmen: die `client_id` liegt bewusst im Arbeitsspeicher
(`_seen` in `routers/ingest.py`), **kein Schema** — ein doppelter Vorschlag ist
sichtbar und verwerfbar, eine verlorene Erfassung endgültig. Ohne `client_id`
wird NICHT entdoppelt (zwei gleiche Sätze von Hand sind zwei Erfassungen).
**Eine Warteschlange ist so viel wert wie das, was sie zeigt** — Text, Zähler,
Grund; die manuelle Eingabe bekommt gar keine (sie schreibt Bestätigtes) und
wird stattdessen nach der A40-Regel `inert` gestellt.
**F1 war eine Grenzfrage, keine Textfrage:** der Vorschlag steht NEBEN dem
Tagebuchfeld, „Übernehmen" hängt an (überschreibt nie), der Endpunkt ist ein
GET und speichert nichts — so gilt die Zusage aus 0.15.0 unverändert.
Unbestätigte fließen nicht ein, werden aber GEZÄHLT und genannt; der
Tagebuch-Eintrag ist aus seinem eigenen Material ausgeschlossen, sonst frisst
sich der Text selbst. **Nur `exact`/`day` fließen in einen Tagestext** —
„Sommer 2002" steht mit `date_start=2002-06-01` da und stünde sonst im
Vorschlag für den 1. Juni (dieselbe Regel wie F14 `_ON_THIS_DAY_PRECISIONS`).
Wächter: `tools/check-p51-outbox.js` (stellt `onLine`, Netzfehler und vollen
Speicher HER) und `tools/check-f1-journal-ai.js`.

**Selbstkontrolle 0.36.0 — vier Befunde, drei davon dieselbe Frage.** „Wo gilt
derselbe Satz noch?" (Anm. 103) fand: unscharfe Daten im Tagestext (F14-Regel),
die falsche Begründung, wenn die KI nichts liefert (nicht „nichts erfasst"),
und `_seen` ohne Schloss (KeyError → 500 → die Warteschlange stempelt die
Erfassung als abgelehnt ab). Der vierte kam vom Lesen eines Kommentars GEGEN
seinen Code: `await flushOutbox()` wartete nicht. **Und zwei der Tests dazu
waren im ersten Anlauf wertlos** — der Thread-Test bestand auch ohne Schloss
(das Fenster ist Bytecodes breit, „acht Threads im Kreis" trifft es nie), der
Sprach-Test prüfte die Rückrichtung (jsdom meldet `en-US`, die App startet
englisch). **Neue Regel: jede Prüfung, die einen Fehler festnageln soll, einmal
gegen den kaputten Stand laufen lassen** — `git show HEAD:datei > /tmp/alt` und
den Wächter darauf ansetzen.

**Immich hängt Tages-Fotos an den TAG (Anmerkung 106, in 0.35.0).** Vorher ging
ein Foto an den ersten Besuch, dessen ±6-h-Fenster es traf — bei `exact`-Präzision
der importierten Besuche und 25 km Ortstoleranz entschied faktisch die
Reihenfolge einer Abfrage **ohne ORDER BY**. Und die A39-Sammelkarte zeigt
`min(id)` (UUIDs!), also einen ANDEREN zufälligen Besuch: gemessen vier Fotos
verknüpft, null sichtbar. Jetzt: `targets()` liefert erst Ereignisse (engeres
Fenster, selbst erfasst = Aussage über den Tag), dann Tage aus importierten
Besuchen → `MediaRef` ohne `event_id` (F18-Behälter). **Der Tag filtert bewusst
NICHT nach Ort** — ein Zeit-Behälter mit Ortsfilter wäre in sich widersprüchlich.
Bestandsverknüpfungen an Besuchen werden zu Lauf-Beginn gelöst, sonst gälten sie
über `seen` als vergeben. **Regel:** „wohin gehört das?" hatte drei Antworten in
zwei Dateien (`candidates`, Job-Schleife, `link_batch`) — eine davon hatte die
Entduplizierung verloren. Eine Regel an mehreren Orten widerspricht sich, und
zwar still.

**Wächter prüfen Zustände, die es geben muss.** `check-a41-cities.js` prüfte ein
Jahr lang, dass der Städte-Reiter im Markup steht — im Betrieb ersetzt
`applyModules()` die Leiste Sekundenbruchteile nach dem Start, der Reiter war
also nie zu sehen und die Prüfung trotzdem grün. Wer eine UI-Eigenschaft
absichert, muss den Zustand HERSTELLEN (`w.eval('MODULES = …; applyModules()')`),
nicht den Auslieferungszustand lesen. `npm run check` in `tools/` fährt jetzt
alle Wächter, auch die vier, die man vorher von Hand starten musste.

**Verworfen: ein automatisches Tages-Objekt je Tag** (Anmerkung 87) — das hieße
`parent_event_id` auf Bestätigtem setzen und Tausende leere Container, die jede
Aggregation wieder ausfiltern müsste. Der Container ist das Datum, kein Objekt.
Allgemein: erst prüfen, ob die Zeitachse den Container schon liefert, bevor
eine Zeile entsteht, die für immer gepflegt, gezählt und ausgefiltert wird.

**A36 fertig (v0.31.0):** `/api/events?slim=1` lässt die Roh-Metriken weg
(67 % der Nutzlast) und ersetzt sie durch ein kompaktes `weather`-Objekt;
Zeitstrahl/Heute/Karte nutzen slim, nur die Statistik holt die volle Liste
(fetchEventsFull) beim Öffnen. −60 % (19→8 MB bei 12k). weatherSummary liest
aus e.weather ODER e.metrics — geprüft von tools/check-weather-line.js.

**F17 fertig (v0.31.0):** Alter je Ereignis als Chip auf der Karte, Ableitung
aus dem Meilenstein „Geburt" (Anmerkung 72), „~" bei vager Datierung. BIRTH_DATE
wird in renderTimelineList aus tl.events ermittelt.

**A37 fertig (v0.32.0, Anmerkung 81/85):** Der Zeitstrahl lädt Seiten
(`/api/events?limit&offset`, `TL_PAGE=300`, Nachladen beim Scrollen in
`.content`). **Grundregel ab jetzt: Wer eine Zahl über den GESAMTEN Bestand
braucht, holt sie vom Server** — `/api/events/index` (Gesamt, Unbestätigte,
Jahre, Spanne, Geburts-Meilenstein für F17) und `/api/stats/overview`
(alle Statistik-Kacheln und -Diagramme, `services/stats_overview.py`).
Ein Client-Reduce über `tl.events` zählt nur noch das geladene Fenster.
`tools/check-a37-window.js` prüft genau das (Verkehr + Kacheln). Karte:
eigener Endpunkt `/api/events/map` (ohne Wetter; das kommt je Zeitraum nach —
gemessen 799 vs. 356 Byte je Punkt). Einzelabruf `GET /api/events/{id}` für
Ereignisse außerhalb des Fensters. Gemessen bei 12k über HTTP: Start
12,7 MB/1,49 s → 0,31 MB/0,08 s, Statistik 26 MB/5,5 s → 2 kB/0,39 s.
**Offen bleibt A38 (Mobil-Layout)** im selben Release, Audit-Liste in
Anmerkung 82.

**Kein Ticket-System (Anmerkung 83):** Beobachtungen aus der Nutzung werden als
nummerierte Anmerkung in KONZEPT Kap. 15 festgehalten, Pakete in 14.2/14.3 —
nicht in Linear, Jira o. ä. Eine Wahrheit, und zwar die, die beim Arbeiten
gelesen wird.

**Medien-Invariante (Anmerkung 57, ab F15 bindend):** `provider='local'` sind
hochgeladene Dateien = **Lebensdatenbank**, dürfen von Neuberechnungen NIE
angefasst werden; `provider='immich'` sind Verweise = Ableitung, jederzeit
verwerfbar. Im Code erzwingen, nicht nur dokumentieren. JSON-Export enthält nur
Medien-Metadaten — `MEDIA_DIR` separat sichern.

Marktposition und Abgrenzung stehen seit 2026-07-20 in **KONZEPT Kap. 1.1**;
Anmerkungen 51–56 halten die Entscheidungen dazu fest (Karten, KI-Urheberschaft,
Marktanalyse, Werbung, Wachstum, Medienimporte). **Beitragsmodell: vorerst
keine Fremd-PRs** — bewusst kein CLA/DCO, damit die Lizenzfrage offen bleibt.

**Doku ist ab 0.20.0 englisch** (README, backend/README, DEPLOY, KONZEPT,
CHANGELOG). Diskussion/Input dürfen deutsch bleiben — übersetzt wird beim
Schreiben. Diese Datei (CLAUDE.md) bleibt bewusst deutsch.

## Frontend-Übersetzung (F10)
Deutsch steht im Quelltext und ist die Wahrheit; `I18N_EN` in `index.html`
enthält NUR Englisch. Fehlt ein Schlüssel, erscheint Deutsch — nie ein leeres
Label. Drei Wege: `data-i18n` (HTML-Inhalt), `data-i18n-title`/`data-i18n-ph`
(Attribute), `t('key', 'Deutscher Text')` (JS). Neue UI-Texte immer so anlegen.
**Achtung TDZ:** `LANG`/`I18N_EN` stehen bewusst VOR dem Theme-Block, weil
`applyTheme()` schon beim Laden `t()` ruft. Prüfen mit jsdom statt nur Syntax:
ein Syntaxcheck übersieht genau diese Fehlerklasse.
