# Changelog

Alle nennenswerten Änderungen an Life-Dash. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/) (`MAJOR.MINOR.PATCH`).

Solange die Version bei `0.x` steht, gilt die App als in Entwicklung: neue
Features erhöhen `MINOR`, Fehlerbehebungen `PATCH`; Breaking Changes können in
jedem `MINOR` vorkommen.

## [Unreleased]

## [0.7.0] – 2026-07-16

### Hinzugefügt
- **A9 — Logging & Beobachtbarkeit:** Zentrale Logging-Konfiguration
  (`lifedash.*`-Logger, einheitliches Format mit Zeitstempel), steuerbar über
  `LOG_LEVEL` (.env / Compose). Geloggt werden jetzt u. a. App-Start (Version,
  Auth-/KI-/DB-Modus), Export/Import mit Zeilenzahlen, Admin-Aktionen
  (Neuberechnung, Wetter-/Embedding-Batches, Rohansicht-Änderungen,
  Daten-Wipe), Geocoding-/Open-Meteo-Fehler und die Ortsnamen-Auflösung.
  Docker Compose bekommt Log-Rotation (`max-size: 10m`, `max-file: 5`).
- **A10 — Ortsnamen konsequent auf Deutsch/Latein:** Nominatim wird mit
  Sprach-Fallback `de,en` angefragt; liefert OSM keinen deutschen Namen,
  kommt die englische/lateinische Umschrift statt Lokalschrift (z. B.
  Griechisch). Zusätzlich bevorzugt `namedetails` den besten lateinischen
  Namen. Neue Admin-Aktion **„Fremdschrift-Namen eindeutschen"** löst
  bestehende Orte mit nicht-lateinischer Schrift erneut auf
  (`resolve-names?scope=nonlatin`); Besuchs-Events werden mit umbenannt,
  manuell umbenannte Einträge bleiben unangetastet.
- **A13 — Uhrzeiten anzeigen & bearbeiten:** Events mit `date_precision =
  exact` zeigen jetzt Datum **und Uhrzeit** („12.07.2026, 14:30–16:05") —
  damit werden importierte Timeline-Besuche als Tagesablauf lesbar. Der
  Bearbeiten-Dialog bekommt optionale Uhrzeit-Felder und die Präzision
  „Tag + Uhrzeit"; eine eingegebene Uhrzeit hebt die Präzision automatisch
  auf `exact`. Uhrzeiten bleiben lokale Wanduhrzeit („wie erlebt", keine
  UTC-Umrechnung).
- **A5 (Karten-Teil) — Marker-Clustering statt 300er-Deckel:** Die Karte
  zeigt jetzt **alle** Punkte eines Zeitraums. Bis 300 Stopps bleibt die
  nummerierte Tagesroute; darüber werden die Marker gebündelt
  (Leaflet.markercluster) statt abgeschnitten. Die Stopp-Liste bleibt als
  DOM-Schutz gedeckelt und sagt das dazu.
- **A8 — Export-Rückmeldung:** Der Daten-Export meldet Erfolg per Toast
  (Anzahl Events/Fragmente/Objekte/Orte/Routen/Metriken, Dateigröße,
  Dateiname) bzw. Fehler als Fehler-Toast; der Button ist während des
  Exports deaktiviert.

### Behoben
- **Stiller Präzisions-Downgrade beim Bearbeiten:** Der Bearbeiten-Dialog
  stufte `exact`-Events beim Speichern unbemerkt auf `day` herab (die
  Uhrzeit ging verloren). Jetzt bleibt `exact` erhalten und ist wählbar.

## [0.6.0] – 2026-07-16

### Hinzugefügt
- **A1 — Saubere UI-Dialoge statt Browser-Popups:** Alle nativen
  `alert()`/`confirm()`/`prompt()`-Dialoge (~20 Stellen: Export, Import,
  Batch-Läufe, Löschen …) ersetzt durch **Toasts** im App-Stil (Erfolg /
  Warnung / Fehler, Klick schließt) und ein **Bestätigungs-Modal** — inkl.
  Tipp-Bestätigung („LÖSCHEN") beim Daten-Wipe. Auf Mobil erscheinen Toasts
  über der Bottom-Navigation.
- **A2 — Fortschrittsbalken bei großen Importen:** Google-Timeline-Import
  und JSON-Restore laufen bei großen Dateien in Etappen mit echtem
  Fortschritt („12.000 / 48.500 Segmente") statt unbestimmtem Spinner —
  gefahrlos, weil beide Importe idempotent sind. Beim Etappen-Import wird
  das automatische Reverse-Geocoding übersprungen (neuer Query-Param
  `auto_resolve=false`); Chunk-Grenzen halten zusammengehörige
  Geräte-Export-Segmente (Route + Aktivität) beieinander.
- **A3 — Versionsnummer im UI:** Die Sidebar zeigt unten links die laufende
  Version (z. B. „Life-Dash v0.6.0"). Eine Quelle der Wahrheit:
  `backend/app/version.py` speist UI, `/health` und die OpenAPI-Doku
  (dort stand bis jetzt fälschlich 0.2.0).

## [0.5.0] – 2026-07-16

### Hinzugefügt
- **P2.5 — Bulk-Bestätigen:** Die Moderations-Queue kann viele korrekte
  KI-Vorschläge auf einmal übernehmen — Filter nach Kategorie, Quelle,
  Mindest-Confidence und Zeitraum, immer zweistufig: erst **Vorschau** der
  betroffenen Events, dann Bestätigen. Neue Endpoints
  `POST /api/moderation/bulk-confirm/preview` und `…/bulk-confirm`.
- **P2.6 — Invarianten-Test „Bestätigtes ist unantastbar":** Automatische
  Tests (`backend/tests/`, pytest) fahren alle Recompute-/Enrichment-/
  Import-Pfade gegen die Invariante aus KONZEPT Kap. 3.1: Neuberechnung
  verschont bestätigte Fragmente samt Geschwister-Events, Wetter ist additiv
  und idempotent, Bulk-Bestätigen kippt nur den Status, Re-Import erzeugt
  keine Duplikate und fasst Bestätigtes nicht an, die Ortsnamen-Auflösung
  respektiert manuell umbenannte Titel, Embedding-Neuberechnung ändert nur
  das Embedding.
- **P2.7 — Bestätigungs-Provenienz:** Jedes Event speichert jetzt, **wann**
  und **wodurch** es bestätigt wurde (`confirmed_at`, `confirmed_by`:
  manuell / Sammel-Bestätigung / Import) — sichtbar im Bearbeiten-Dialog.
  Bestandsdaten werden migriert (Import-Besuche → „Import", Rest → „manuell",
  Zeitpunkt = letzte Änderung); erneutes Bestätigen/Bearbeiten überschreibt
  die ursprüngliche Provenienz nicht.
- **P2.4 — Auto-Enrichment nach der Eingabe:** Neue Events (KI-Analyse und
  manuelle Eingabe) bekommen ihr Wetter sofort beim Anlegen statt erst über
  den Admin-Knopf (best effort — schlägt der Abruf fehl, trägt der Admin-Lauf
  später nach); Embeddings entstehen weiterhin direkt beim Anlegen. Korrigiert
  der Nutzer Zeit oder Ort eines Events, wird dessen Wetter passend zu den
  neuen Fakten neu geholt (nutzergestartete Korrektur — keine
  Maschinen-Änderung an Bestätigtem).
- **P2.2 — Google-Timeline-Import:** Upload des Timeline-Exports (Geräte-Export
  `semanticSegments` und altes Takeout-Format `timelineObjects`) unter
  Admin → „Meine Daten". Besuche werden zu bestätigten Events
  (source `google_timeline`), Bewegungen zu `Track`-Zeilen (Stufe 3, Punkte
  unvereinfacht). Re-Import ist idempotent (Segment-Hash als `external_id`).
  Neue Endpoints: `POST /api/import/timeline`, `GET /api/tracks?start=&end=`.
- **Routen als Karten-Layer:** Timeline-Routen erscheinen auf der Karte als
  farbige Linien nach Aktivität (zu Fuß/Rad/Auto/Transit), zuschaltbar über
  den Chip „🛰️ Timeline-Routen", gefiltert auf den angezeigten Zeitraum.
- **Vier-Schichten-Modell präzisiert** (KONZEPT Kap. 3.1): Eingang →
  Vorschlagsraum → **Lebensdatenbank (fix)** → Ableitungen. Harte Invariante:
  Maschinen ändern Bestätigtes nie, nur additiv ergänzen. Konsequenz:
  **Wetter ist Fakten-Anreicherung** — der Knopf „Stufe 3 neu berechnen"
  (der Wetter verwarf und neu holte) ist entfernt; Wetter wird nur noch
  ergänzt, wo es fehlt. Embeddings bleiben als Ableitung neu berechenbar.
- **Stopp-Knopf & Anfragen-Ticker für alle Admin-Läufe:** Stufe-2-Neuberechnung,
  Stufe 3, Wetter, Embeddings und Ortsnamen laufen jetzt in Etappen — der
  Aktions-Knopf zeigt live die verbrauchten Anfragen („⏹ Stoppen — 120
  KI-Anfragen · noch ~340") und stoppt auf Klick nach dem laufenden Batch.
  Fortschritt bleibt erhalten, derselbe Knopf setzt fort. Die Stufe-2-Neuberechnung
  fasst Import-Fragmente (Timeline) nicht mehr an — KI-Extraktion über
  Import-Zusammenfassungen hätte Unsinn erzeugt.
- **Ortsnamen für importierte Besuche:** Der Geräte-Export enthält keine
  Ortsnamen — neuer Button „📍 Ortsnamen auflösen" (Admin → Meine Daten) holt
  Adressen per Reverse-Geocoding (Nominatim, 1 Anfrage/s, etappenweise
  fortsetzbar) und benennt Orte samt Besuchs-Events um; manuell geänderte
  Titel bleiben geschützt. Kleine Folge-Importe (≤ 30 neue Orte) lösen Namen
  direkt beim Import auf.
- **P2.3 — Unscharfe-Zeiten-Review:** Admin-Bereich listet alle Events mit
  grober Zeitangabe (Jahreszeit/Jahr/Jahrzehnt/ohne Datum); Klick öffnet die
  Schnellbearbeitung.
- **Statistik ist klickbar** (wie im Kompendium): Kacheln führen zu
  Kompendium/Timeline (kategorie-gefiltert)/Karte/Moderation, der heißeste/
  kälteste Tag öffnet das Event, Chart-Balken (Kategorien, Tiere) springen zu
  Timeline-Filter bzw. Kompendium-Detailseite.

### Geändert
- **PostgreSQL ist jetzt der Compose-Standard** (kein `--profile postgres`
  mehr): `docker compose up -d` startet App + DB, `POSTGRES_PASSWORD` in
  `.env` genügt. Version: **`postgres:18-alpine`** (Support bis Nov. 2030,
  Async-I/O). Achtung Image-Eigenheit ab 18: Der Daten-Mount zeigt auf
  `/var/lib/postgresql` (nicht mehr `…/data`) — Upgrade von einer
  bestehenden 16er-DB via JSON-Export (docs/DEPLOY.md Kap. 6).
- **Daten liegen als Ordner neben der Compose-Datei** (Bind-Mounts statt
  Docker-Volumes): `./db` = PostgreSQL-Datenverzeichnis, `./data` =
  App-Daten (SQLite beim Minimal-Setup). Backup = Ordner sichern oder
  `pg_dump`; bestehende Volume-Installationen ziehen per JSON-Export um. **Migration von SQLite:** JSON-Export ziehen, `DATABASE_URL`
  aus `.env` entfernen, `up -d`, Export importieren (docs/DEPLOY.md Kap. 6).
  SQLite bleibt via `DATABASE_URL`-Override + `up -d --no-deps app` möglich.
- **Performance für importierte Massendaten** (>10k Timeline-Events):
  - `/api/events` lädt Verknüpfungen jetzt eager (Sammel-Queries statt
    N+1-Lazy-Loading): 11,7k Events in 0,7 s statt 4,4 s.
  - Timeline, Karte, Statistik und Unscharfe-Zeiten teilen sich **einen**
    Events-Abruf (vorher 4 × mehrere MB).
  - Timeline rendert pro Zeitgruppe zunächst 25 Karten („▼ weitere anzeigen"),
    statt 10k+ DOM-Knoten auf einmal.
  - Importierte Google-Besuche sind im Zeitstrahl standardmäßig ausgeblendet
    (Toggle „🛰️ Besuche") — auf der Karte bleiben sie immer sichtbar.
  - Karte deckelt Marker/Stopp-Liste bei 300 pro Zeitraum; Timeline-Routen
    werden nur bis Monats-Zoom gezeichnet; `/api/tracks` hat ein Server-Limit
    (Default 1000, max. 5000).
- Datenexport/-import und „Alle Daten löschen" erfassen jetzt auch Tracks;
  Schema-Migration ergänzt `events.external_id` in Bestands-DBs automatisch.

## [0.4.0] – 2026-07-15

### Hinzugefügt
- **Verknüpfte Objekte im Bearbeiten-Dialog editierbar** (z. B. „Seeadler" →
  „Adler" korrigieren, Objekte ergänzen/entfernen). `PATCH /api/moderation/{id}`
  akzeptiert dazu ein `entities`-Feld, das die Verknüpfungen vollständig
  ersetzt; verwaiste Entities werden aufgeräumt, die Änderung ist als Override
  vor KI-Neuberechnungen geschützt.

## [0.3.2] – 2026-07-15

### Behoben
- **Karte wurde auf Mobilgeräten nicht angezeigt.** Leaflet vermisst sich jetzt
  mehrfach neu (`invalidateSize` nach Einblenden) und reagiert auf
  Drehen/Resize — Mobil meldete direkt nach dem Einblenden oft Höhe 0.
- **Eingabe-Symbol in der Mobil-Navigation** hatte einen blauen runden
  FAB-Hintergrund; entfernt, das Icon sieht jetzt aus wie die übrigen Tabs.

### Hinzugefügt
- **Sichtbarer Lade-Overlay während der KI-Analyse** (Spinner + Text). Auf Mobil
  war die einzige Rückmeldung bisher der Button-Text, der oft außerhalb des
  Sichtfelds lag.

## [0.3.1] – 2026-07-15

### Behoben
- **OIDC-Login scheiterte hinter dem Reverse Proxy mit HTTP 403.** Die
  Server-zu-Server-Aufrufe an Pocket ID (Discovery, JWKS, Token-Tausch) senden
  jetzt einen expliziten `User-Agent`; der Default `Python-urllib/…` wurde von
  Bot-Filtern (Traefik/Pangolin, CrowdSec) geblockt.

## [0.3.0] – 2026-07-15

### Geändert
- **Versionierung auf SemVer umgestellt** (`vMAJOR.MINOR.PATCH`) + dieses
  CHANGELOG eingeführt. Der Release-Workflow erzeugt aus einem Git-Tag `vX.Y.Z`
  automatisch die Image-Tags `X.Y.Z`, `X.Y` und `latest`.
- KI-Stack aufgeräumt: **Gemini API als Standardweg**, Defaults auf
  `gemini-3.5-flash` / `gemini-embedding-2` gesetzt.
- **Ollama-Service aus dem Compose-Stack entfernt** (lokales Ollama bleibt als
  Alternative dokumentiert, ist aber nicht Teil des ausgelieferten Stacks).

## [0.2.0] – 2026-07-15

### Behoben
- **Multi-Arch-Image** (`linux/amd64` + `linux/arm64`); v0.1 war amd64-only und
  auf dem Raspberry Pi 5 (ARM64) nicht lauffähig.

## [0.1.0] – 2026-07-15

### Hinzugefügt
- Erstveröffentlichung (P0 + P1): FastAPI-Backend, responsive PWA-Frontend,
  OIDC-Multi-User (Pocket ID), Homelab-Deployment via Docker Compose und
  GHCR-Release-Workflow.

<!-- Die Tags v0.1/v0.2 (zweistellig) stammen aus der Zeit vor der
     SemVer-Umstellung; ab v0.3.0 gilt durchgehend MAJOR.MINOR.PATCH. -->
