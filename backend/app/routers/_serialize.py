"""Hilfsfunktionen zum Serialisieren von ORM-Objekten in Schemas."""
from __future__ import annotations

from app.models import Event, Source
from app.schemas import (EntityRead, EventGroup, EventRead, LocationRead,
                         MediaRead, MetricRead)


def _weather_compact(event: Event) -> dict | None:
    """A36: Die 16 Wetter-Metriken eines Ereignisses als EIN flaches Objekt.

    In der schlanken Liste ersetzt das die Metrik-Zeilen — sie sind 67 % der
    Nutzlast (bei 12.000 Ereignissen der Unterschied zwischen 24 und 7 MB), und
    der Zeitstrahl braucht davon nur die Werte, nicht Herkunft/Einheit/ID je
    Zeile. `weather_rev` (interner Marker) fällt weg."""
    flat: dict = {}
    for m in event.metrics:
        if m.source != Source.weather or m.key == "weather_rev":
            continue
        flat[m.key] = m.value_text if m.value_text is not None else m.value
    return flat or None


def event_to_read(event: Event, *, slim: bool = False,
                  weather: dict | None = None,
                  child_count: int | None = None,
                  group: dict | None = None) -> EventRead:
    """Baut ein EventRead inkl. verknüpfter Entities und Metriken.

    slim (A36): Die Metrik-Zeilen entfallen; stattdessen trägt `weather` die
    Wetterwerte kompakt. Alles andere (Entities, Medien, Ort) bleibt, damit die
    Karten unverändert rendern.

    `weather` (A36-Performance): das kompakte Wetter, vom Aufrufer vorberechnet.
    Der Zeitstrahl-Endpunkt lädt die Metriken GAR NICHT (das Laden von 16 Zeilen
    je Ereignis als ORM-Objekte war der eigentliche Flaschenhals — bei 12.000
    Ereignissen 3 s), sondern holt das Wetter in EINER schlanken Abfrage und
    reicht es hier durch. Wird nichts übergeben, fällt slim auf die geladenen
    Metriken zurück (Einzelaufruf/Test)."""
    entities = [
        EntityRead.model_validate(link.entity) for link in event.entity_links
    ]
    metrics = [] if slim else [MetricRead.model_validate(m) for m in event.metrics]
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
        # vorberechnetes Wetter bevorzugen; sonst (Einzelaufruf) aus den
        # geladenen Metriken bauen
        weather=(weather if weather is not None else _weather_compact(event)) if slim else None,
        # A37/F7: vom Aufrufer je Seite gezählt (None = nicht ermittelt)
        child_count=child_count,
        # A39: Diese Karte vertritt mehrere Besuche desselben Tages in
        # derselben Stadt (None = vertritt nur sich selbst)
        group=EventGroup(**group) if group else None,
    )
