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


def _match_ids(db: Session, user_id: str, q: str):
    """Subquery der Treffer-IDs (Titel/Beschreibung/Ort/Entity), eindeutig.

    DISTINCT NUR auf `Event.id` — nicht auf der ganzen Zeile. `Event` trägt
    JSON-Spalten (`embedding` u. a.), und PostgreSQL hat für den Typ `json`
    keinen Gleichheitsoperator: `SELECT DISTINCT event.*` bricht dort mit
    „could not identify an equality operator for type json". Auf SQLite (JSON =
    Text) fällt das nicht auf — genau die A37-Dialekt-Fehlerklasse. `test_search`
    kompiliert das für PostgreSQL und stellt sicher, dass keine JSON-Spalte unter
    DISTINCT gerät.
    """
    like = f"%{q}%"
    return (
        db.query(Event.id)
        .outerjoin(Location, Event.location_id == Location.id)
        .outerjoin(EventEntityLink, EventEntityLink.event_id == Event.id)
        .outerjoin(Entity, EventEntityLink.entity_id == Entity.id)
        .filter(Event.user_id == user_id)
        .filter(
            Event.title.ilike(like)
            | Event.description.ilike(like)
            | Location.name.ilike(like)
            | Entity.name.ilike(like)
        )
        .distinct()
        .subquery()
    )


@router.get("", response_model=list[EventRead])
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EventRead]:
    """Volltextsuche über die eigenen Events."""
    # Erst die Treffer-IDs eindeutig machen (siehe `_match_ids`), dann die vollen
    # Zeilen dazu holen und sortieren. Das äußere Query hat KEIN DISTINCT, darf
    # also gefahrlos die JSON-Spalten mitführen und nach Datum sortieren
    # (ORDER BY unter DISTINCT verlangte die Spalte in der Auswahl — PostgreSQL).
    match = _match_ids(db, user.id, q)
    hits = (
        db.query(Event)
        .join(match, Event.id == match.c.id)
        .order_by(Event.date_start.desc())
        .limit(limit)
        .all()
    )
    return [event_to_read(e) for e in hits]
