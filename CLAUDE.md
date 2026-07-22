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
Umgesetzt bis **v0.35.0** (2026-07-22). **Gruppe A ist komplett** (A1–A42),
Gruppe B bis **F19**. Offen ist damit nur noch: **P5.1** (Offline-Erfassung),
**F1-Rest** (KI-Tageszusammenfassung), **P2.1 Stufe 2** (Immich als
Ereignisquelle), dann **Demo-Modus** und **R1** (Veröffentlichungsreife).
Hinter 1.0 bleiben
nur noch neue Import-Konnektoren (P2.8 OwnTracks, P2.9 Automatisierung,
P2.10 Trakt, P2.11 Dawarich/GPX, P4.1 Health, P4.2 PSN) plus **P5.2**
(Whisper — einzige Ausnahme, schwere neue Laufzeit-Abhängigkeit).

**Releaseplan bis 1.0 steht in KONZEPT Kap. 14.3.** Fertig: 0.21 A28+F14 ·
0.22 F13 · 0.23 F11+F12 · 0.24 F15 (Fotos) · 0.25 P2.1 (Immich, Stufe 1) ·
0.26 A29 (ZIP-Backup) · 0.27 Fixes (A31/A32/A30) · 0.28 F16+A33+A34 ·
0.29 A35 (lokale Konten) · 0.30 P3.1 · 0.31 A36+F17 (schlanke Liste, Alter) ·
0.32 A37 (serverseitiges Zeitfenster) · 0.33 A38+A40 (Mobil-Layout,
Kartenschalter) + dev-Kennung · 0.34 A39+F18+A41 (Städte, Tages-Fotos) · 0.35 F19+A42 (Sammlung).
Offen: **0.36 P5.1+F1-Rest (Erfassen)** ·
**0.37 P2.1 Stufe 2 (Immich als Quelle)** · **0.38 Demo-Modus** ·
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
