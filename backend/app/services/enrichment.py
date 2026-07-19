"""Stufe-3-Enrichment: reichert verortete Events mit Wetter an (Metric).

Läuft on-demand über das Admin-Panel und ist jederzeit neu berechenbar,
ohne Stufe 2 zu verändern.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Event, Metric, Source
from app.services.weather import fetch_weather


def _needs_weather(event: Event) -> bool:
    """Verortet, datiert, nicht in der Zukunft und noch ohne Wetter-Metrik?"""
    today = datetime.now(timezone.utc).date()
    loc = event.location
    if not loc or loc.lat is None or event.date_start is None:
        return False
    if event.date_start.date() > today:
        return False  # Zukunft hat noch kein Wetter
    return not any(m.source == Source.weather for m in event.metrics)


def _weather_candidates(db: Session) -> list[Event]:
    """Verortete, datierte, nicht-zukünftige Events ohne Wetter-Metrik."""
    return [e for e in db.query(Event).all() if _needs_weather(e)]


def _add_weather(db: Session, event: Event) -> bool:
    """Holt Wetter für EIN Event und hängt es als Metriken an (ohne Commit).
    F3: Mittel + Min/Max getrennt, Bedingung aus Stundendaten, Niederschlag."""
    w = fetch_weather(event.location.lat, event.location.lng, event.date_start)
    if not w:
        return False
    for key in ("temp_c", "temp_min_c", "temp_max_c"):
        if w.get(key) is not None:
            db.add(Metric(event_id=event.id,
                          key="temperature_c" if key == "temp_c" else key,
                          value=w[key], unit="°C", source=Source.weather))
    if w.get("precip_mm") is not None:
        db.add(Metric(event_id=event.id, key="precipitation_mm",
                      value=w["precip_mm"], unit="mm", source=Source.weather))
    if w.get("condition"):
        db.add(Metric(event_id=event.id, key="weather",
                      value_text=w["condition"], source=Source.weather))
    return True


def auto_enrich_events(db: Session, events: list[Event]) -> int:
    """Auto-Enrichment direkt nach Ingest/Eingabe (P2.4): Wetter für die
    gerade erzeugten Events ergänzen, statt auf den Admin-Knopf zu warten.

    Best effort — Fehler (z. B. Open-Meteo nicht erreichbar) dürfen die
    Erfassung nie scheitern lassen; fehlendes Wetter trägt später der
    Admin-Lauf nach. Commit macht der Aufrufer."""
    enriched = 0
    for event in events:
        try:
            if _needs_weather(event) and _add_weather(db, event):
                enriched += 1
        except Exception:  # noqa: BLE001 — Anreicherung ist nie kritisch
            continue
    return enriched


def enrich_weather(db: Session, limit: int | None = None) -> tuple[int, int]:
    """Hängt Temperatur + Bedingung an Events ohne Wetter (Batch fürs Admin-UI).

    Gibt (angereichert, verbleibend) zurück. Wetter ist Fakten-Anreicherung
    (KONZEPT Kap. 3.1): einmal geholt = dauerhaft; es wird nur ergänzt,
    nie verworfen und neu berechnet.
    """
    candidates = _weather_candidates(db)
    batch = candidates if limit is None else candidates[:limit]
    # Pro Event committen: der Unique-Index (A11, ux_metrics_weather) weist
    # Dubletten aus parallelen Läufen ab — dann verliert nur DIESES Event
    # (bereits angereichert), nicht der ganze Batch.
    enriched = 0
    for event in batch:
        try:
            if _add_weather(db, event):
                db.commit()
                enriched += 1
        except IntegrityError:
            db.rollback()  # parallele Instanz war schneller — kein Schaden
    return enriched, len(candidates) - enriched
