# Changelog

Alle nennenswerten Änderungen an Life-Dash. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/) (`MAJOR.MINOR.PATCH`).

Solange die Version bei `0.x` steht, gilt die App als in Entwicklung: neue
Features erhöhen `MINOR`, Fehlerbehebungen `PATCH`; Breaking Changes können in
jedem `MINOR` vorkommen.

## [Unreleased]

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
