"""Stufe-3-Enrichment: reichert verortete Events mit Wetter an (Metric).

Läuft on-demand über das Admin-Panel und ist jederzeit neu berechenbar,
ohne Stufe 2 zu verändern.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Event, Metric, Source
from app.services.weather import fetch_weather


def enrich_weather(db: Session, force: bool = False) -> int:
    """Hängt Temperatur + Bedingung an verortete, datierte Events.

    force=False: nur Events ohne Wetter. force=True: alle neu berechnen.
    """
    today = datetime.now(timezone.utc).date()
    enriched = 0
    for event in db.query(Event).all():
        loc = event.location
        if not loc or loc.lat is None or event.date_start is None:
            continue
        if event.date_start.date() > today:
            continue  # Zukunft hat noch kein Wetter

        has_weather = any(m.source == Source.weather for m in event.metrics)
        if has_weather and not force:
            continue
        # Re-Enrichment: alte Wetter-Metriken entfernen
        for m in list(event.metrics):
            if m.source == Source.weather:
                db.delete(m)
        db.flush()

        w = fetch_weather(loc.lat, loc.lng, event.date_start)
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
    return enriched
