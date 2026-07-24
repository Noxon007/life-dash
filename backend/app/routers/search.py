"""Suche: serverseitige Volltextsuche, nutzergebunden.

Durchsucht Titel, Beschreibung, Ortsname und verknüpfte Entity-Namen.

Bewusst KEINE semantische (Embedding-)Suche mehr (Entscheidung 2026-07-24,
Feedback-Runde): die kostete einen KI-Dienst, lud zum Suchen ALLE Events mit
Embedding in den App-Prozess und rechnete Cosine in reinem Python — bei 20k
Einträgen der einzige nicht skalierende Pfad. Schlug der Embed-Dienst fehl, riss
der Aufruf die ganze Antwort mit (500), obwohl die Volltexttreffer längst
feststanden — das war das gemeldete „Server-Suche nicht erreichbar". Volltext
allein ist schnell, ohne Abhängigkeit und deckt den genutzten Fall ab. Kehrt die
semantische Suche je zurück, gehört sie als Schicht-4-Ableitung mit Vektorindex
(pgvector) in die DB, nicht in den Prozess (KONZEPT Kap. 15).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Entity, Event, EventEntityLink, Location, User
from app.routers._serialize import event_to_read
from app.schemas import EventRead

router = APIRouter(prefix="/api/search", tags=["Suche"])


@router.get("", response_model=list[EventRead])
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EventRead]:
    """Volltextsuche über die eigenen Events."""
    like = f"%{q}%"

    # Volltext: Titel/Beschreibung ODER Ortsname ODER Entity-Name
    hits = (
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
        .order_by(Event.date_start.desc())
        .limit(limit)
        .all()
    )
    return [event_to_read(e) for e in hits]
