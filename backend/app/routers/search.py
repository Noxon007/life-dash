"""Suche (Stufe 3): Volltext + semantisch (Embeddings), nutzergebunden.

Volltext durchsucht Titel, Beschreibung, Ortsname und verknüpfte
Entity-Namen. Semantik ergänzt Treffer über Cosine-Ähnlichkeit der
Event-Embeddings — nur aktiv, wenn der KI-Provider Embeddings liefert
(OPENAI_EMBED_MODEL gesetzt). Sonst reine Volltextsuche.
"""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai import get_provider
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Entity, Event, EventEntityLink, Location, User
from app.routers._serialize import event_to_read
from app.schemas import EventRead

router = APIRouter(prefix="/api/search", tags=["Suche"])


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@router.get("", response_model=list[EventRead])
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EventRead]:
    """Hybride Suche über die eigenen Events."""
    like = f"%{q}%"

    # --- Volltext: Titel/Beschreibung ODER Ortsname ODER Entity-Name ---
    text_hits = (
        db.query(Event)
        .outerjoin(Location, Event.location_id == Location.id)
        .outerjoin(EventEntityLink, EventEntityLink.event_id == Event.id)
        .outerjoin(Entity, EventEntityLink.entity_id == Entity.id)
        .filter(Event.user_id == user.id)
        .filter(
            Event.title.ilike(like)
            | Event.description.ilike(like)
            | Location.name.ilike(like)
            | Entity.name.ilike(like)
        )
        .distinct()
        .all()
    )
    results: dict[str, tuple[float, Event]] = {
        e.id: (2.0, e) for e in text_hits  # Volltext-Treffer immer zuerst
    }

    # --- Semantisch: Cosine über gespeicherte Embeddings ---
    query_vec = get_provider().embed(q, kind="query")
    if query_vec:
        candidates = (
            db.query(Event)
            .filter(Event.user_id == user.id, Event.embedding.isnot(None))
            .all()
        )
        for e in candidates:
            if e.id in results:
                continue  # Volltext-Treffer behalten ihren höheren Score
            sim = _cosine(query_vec, e.embedding or [])
            if sim >= settings.semantic_min_similarity:
                results[e.id] = (sim, e)

    ranked = sorted(results.values(), key=lambda t: t[0], reverse=True)[:limit]
    return [event_to_read(e) for _, e in ranked]
