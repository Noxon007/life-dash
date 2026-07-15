"""Hilfsfunktionen zum Serialisieren von ORM-Objekten in Schemas."""
from __future__ import annotations

from app.models import Event
from app.schemas import EntityRead, EventRead, LocationRead, MetricRead


def event_to_read(event: Event) -> EventRead:
    """Baut ein EventRead inkl. verknüpfter Entities und Metriken."""
    entities = [
        EntityRead.model_validate(link.entity) for link in event.entity_links
    ]
    metrics = [MetricRead.model_validate(m) for m in event.metrics]
    location = LocationRead.model_validate(event.location) if event.location else None

    return EventRead(
        id=event.id,
        title=event.title,
        description=event.description,
        date_start=event.date_start,
        date_end=event.date_end,
        date_precision=event.date_precision,
        category=event.category,
        note=event.note,
        confidence=event.confidence,
        confirmed=event.confirmed,
        source=event.source,
        location=location,
        origin_fragment_id=event.origin_fragment_id,
        entities=entities,
        metrics=metrics,
    )
