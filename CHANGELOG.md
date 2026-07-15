# Changelog

Alle nennenswerten Änderungen an Life-Dash. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/) (`MAJOR.MINOR.PATCH`).

Solange die Version bei `0.x` steht, gilt die App als in Entwicklung: neue
Features erhöhen `MINOR`, Fehlerbehebungen `PATCH`; Breaking Changes können in
jedem `MINOR` vorkommen.

## [Unreleased]

### Hinzugefügt
- **P2.2 — Google-Timeline-Import:** Upload des Timeline-Exports (Geräte-Export
  `semanticSegments` und altes Takeout-Format `timelineObjects`) unter
  Admin → „Meine Daten". Besuche werden zu bestätigten Events
  (source `google_timeline`), Bewegungen zu `Track`-Zeilen (Stufe 3, Punkte
  unvereinfacht). Re-Import ist idempotent (Segment-Hash als `external_id`).
  Neue Endpoints: `POST /api/import/timeline`, `GET /api/tracks?start=&end=`.
- **Routen als Karten-Layer:** Timeline-Routen erscheinen auf der Karte als
  farbige Linien nach Aktivität (zu Fuß/Rad/Auto/Transit), zuschaltbar über
  den Chip „🛰️ Timeline-Routen", gefiltert auf den angezeigten Zeitraum.
- **P2.3 — Unscharfe-Zeiten-Review:** Admin-Bereich listet alle Events mit
  grober Zeitangabe (Jahreszeit/Jahr/Jahrzehnt/ohne Datum); Klick öffnet die
  Schnellbearbeitung.
- **Statistik ist klickbar** (wie im Kompendium): Kacheln führen zu
  Kompendium/Timeline (kategorie-gefiltert)/Karte/Moderation, der heißeste/
  kälteste Tag öffnet das Event, Chart-Balken (Kategorien, Tiere) springen zu
  Timeline-Filter bzw. Kompendium-Detailseite.
- **Verknüpfte Objekte im Bearbeiten-Dialog editierbar** (z. B. „Seeadler" →
  „Adler" korrigieren, Objekte ergänzen/entfernen). `PATCH /api/moderation/{id}`
  akzeptiert dazu ein `entities`-Feld, das die Verknüpfungen vollständig
  ersetzt; verwaiste Entities werden aufgeräumt, die Änderung ist als Override
  vor KI-Neuberechnungen geschützt.

### Geändert
- **PostgreSQL ist jetzt der Compose-Standard** (kein `--profile postgres`
  mehr): `docker compose up -d` startet App + DB, `POSTGRES_PASSWORD` in
  `.env` genügt. **Migration von SQLite:** JSON-Export ziehen, `DATABASE_URL`
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
