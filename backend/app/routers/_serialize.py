"""Hilfsfunktionen zum Serialisieren von ORM-Objekten in Schemas."""
from __future__ import annotations

from app.models import Event
from app.schemas import (EntityRead, EventRead, LocationRead, MediaRead,
                         MetricRead)


def event_to_read(event: Event) -> EventRead:
    """Baut ein EventRead inkl. verknüpfter Entities und Metriken."""
    entities = [
        EntityRead.model_validate(link.entity) for link in event.entity_links
    ]
    metrics = [MetricRead.model_validate(m) for m in event.metrics]
    # F15: Bilder in fester Reihenfolge — die Galerie soll nicht bei jedem
    # Laden anders aussehen.
    media = [
        MediaRead(
            id=m.id, event_id=m.event_id, provider=m.provider, mime=m.mime,
            bytes=m.bytes, width=m.width, height=m.height, caption=m.caption,
            sort_order=m.sort_order or 0, captured_at=m.captured_at,
            url=f"/api/media/{m.id}/file", thumb_url=f"/api/media/{m.id}/thumb",
        )
        for m in sorted(event.media, key=lambda x: (x.sort_order or 0, x.id))
    ]
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
        confirmed_at=event.confirmed_at,
        confirmed_by=event.confirmed_by,
        source=event.source,
        location=location,
        origin_fragment_id=event.origin_fragment_id,
        parent_event_id=event.parent_event_id,
        entities=entities,
        metrics=metrics,
        media=media,
    )
