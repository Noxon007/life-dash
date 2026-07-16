"""Stufe-3-Enrichment: reichert verortete Events mit Wetter an (Metric).

Läuft on-demand über das Admin-Panel und ist jederzeit neu berechenbar,
ohne Stufe 2 zu verändern.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Event, Metric, Source
from app.services.weather import fetch_weather


def _weather_candidates(db: Session) -> list[Event]:
    """Verortete, datierte, nicht-zukünftige Events ohne Wetter-Metrik."""
    today = datetime.now(timezone.utc).date()
    out: list[Event] = []
    for event in db.query(Event).all():
        loc = event.location
        if not loc or loc.lat is None or event.date_start is None:
            continue
        if event.date_start.date() > today:
            continue  # Zukunft hat noch kein Wetter
        if any(m.source == Source.weather for m in event.metrics):
            continue
        out.append(event)
    return out


def enrich_weather(db: Session, limit: int | None = None) -> tuple[int, int]:
    """Hängt Temperatur + Bedingung an Events ohne Wetter (Batch fürs Admin-UI).

    Gibt (angereichert, verbleibend) zurück. Wetter ist Fakten-Anreicherung
    (KONZEPT Kap. 3.1): einmal geholt = dauerhaft; es wird nur ergänzt,
    nie verworfen und neu berechnet.
    """
    candidates = _weather_candidates(db)
    batch = candidates if limit is None else candidates[:limit]
    enriched = 0
    for event in batch:
        w = fetch_weather(event.location.lat, event.location.lng, event.date_start)
        if not w:
            continue
        if w.get("temp_c") is not None:
            db.add(Metric(event_id=event.id, key="temperature_c",
                          value=w["temp_c"], unit="°C", source=Source.weather))
        if w.get("condition"):
            db.add(Metric(event_id=event.id, key="weather",
                          value_text=w["condition"], source=Source.weather))
        enriched += 1
    db.commit()
    return enriched, len(candidates) - enriched
