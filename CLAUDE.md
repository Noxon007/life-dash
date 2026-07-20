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
- Jede Version: `backend/app/version.py` + `CHANGELOG.md` (verständliche Produktsprache,
  **keine Paketkürzel** wie „A25") + KONZEPT-Tabelle abhaken (✅ + „fertig vX.Y.Z")
- Commit-Stil: deutsch, `feat(bereich): X.Y.Z — Beschreibung` (Historie ansehen)
- Doku derzeit deutsch; Paket F10 stellt sie später einmalig auf Englisch um
- Neue Event-Kategorie? Drei Stellen: KI-Prompt/Module-YAML, Frontend (catLabels/Farben/
  KNOWN_CATS/FILTER_CATS_BASE + CSS), ggf. Selects im HTML
- Allgemeingültigkeit (A27): nichts Homelab-Spezifisches hart verdrahten (Provider-Namen
  etc. aus Config); `.env.example` ist die Setup-Referenz

## Stand
Umgesetzt bis **v0.20.0** (2026-07-20). **F10 komplett** (App zweisprachig +
Doku auf Englisch). Offen und klein: **A28** (ein Ortsnamen-Lauf statt
Scope-Auswahl), **F11** (mehr aus vorhandenen Wetterdaten — reine Ableitung,
kein API-Aufruf), **F12** (zusätzliche Wetterfelder via Re-Enrichment),
**F13** (wählbare Hintergrundkarten + eigene Tile-URL), **F14** („An diesem
Tag"), **P3.1** (deklarative Statistik-Widgets), F8-Rest („Druck mit Fotos",
wartet auf P2.1). Groß: **R1** (Veröffentlichungsreife — Demo-Modus,
Screenshots, Härtung, getesteter Upgrade-Pfad; Gate vor jeder Werbung),
Import-Quellen (P2.1 Immich, P2.8 OwnTracks, P2.9 Automatisierung,
P2.10 Trakt/Medienkonsum, P2.11 Dawarich/Reitti/GPX, P4.1 Health, P4.2 PSN)
und P5.1/P5.2 (Offline-Capture, Whisper).

**Releaseplan bis 1.0 steht in KONZEPT Kap. 14.3.** Fertig: 0.21 A28+F14 ·
0.22 F13 · 0.23 F11+F12 · 0.24 F15 (Fotos) · 0.25 P2.1 (Immich, Stufe 1) ·
0.26 A29 (ZIP-Backup). Offen: **0.27 Fixes (A31/A32/A30)** · 0.28 F16+A33+A34 ·
0.29 A35 (lokale Konten, fertig) ·
**0.30 P3.1** · 0.31 Demo-Modus · 0.32 Härtung · 0.33 Projektoberfläche ·
0.34 Freeze · **1.0 = Veröffentlichung**. Import-Konnektoren erst danach.
Kein Termindruck (Anmerkung 58). Dort nachsehen statt Reihenfolge raten.

**F17 (Altersanzeige, offen, Anmerkung 72):** Geburtsdatum ist ein
Meilenstein-Ereignis „Geburt" (kein Profilfeld — eine Wahrheit); Alter je
Ereignis = Ableitung, dezent auf der Karte. Startformular dazu hängt an A35
(0.29, Anmerkung 73). F17 selbst noch nicht terminiert.

**Offener Messwert (Anmerkung 61):** `/api/events` liefert ALLES auf einmal —
2,0 kB je Ereignis, bei 20.000 Ereignissen 38 MB, davon 74 % Metriken/Medien/
Objekte. F12 hat das etwa verdoppelt. 0.27 bringt nur die Ladeanzeige (A30);
die Ursache behebt A36, bewusst vertagt.

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
