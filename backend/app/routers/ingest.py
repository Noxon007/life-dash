"""Ingestion-Endpoints: Roh-Text rein -> Stufe-2-Vorschau raus."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Fragment, User
from app.routers._serialize import event_to_read
from app.schemas import FragmentCreate, FragmentRead, IngestResult
from app.services.enrichment import auto_enrich_events
from app.services.ingestion import ingest_fragment

router = APIRouter(prefix="/api/ingest", tags=["Ingestion"])


@router.post("", response_model=IngestResult)
def ingest(
    payload: FragmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IngestResult:
    """Speichert den Roh-Text (Roh-Eingang) und erzeugt KI-Vorschläge (unbestätigt)."""
    fragment = Fragment(user_id=user.id, raw_text=payload.raw_text, source=payload.source,
                        capture_lat=payload.capture_lat, capture_lng=payload.capture_lng)
    db.add(fragment)
    db.flush()

    events = ingest_fragment(db, fragment)
    # P2.4: Wetter (Fakten-Anreicherung) direkt mitliefern statt Admin-Knopf;
    # Embeddings entstehen bereits beim Anlegen des Events.
    auto_enrich_events(db, events)
    db.commit()

    return IngestResult(
        fragment=FragmentRead.model_validate(fragment),
        events=[event_to_read(e) for e in events],
    )


@router.get("/reverse-location")
def reverse_location(
    lat: float,
    lng: float,
    user: User = Depends(get_current_user),
) -> dict:
    """F2: Gerätestandort -> Adressvorschlag fürs Eingabeformular
    (Reverse-Geocoding im gewählten Anzeige-Format)."""
    from fastapi import HTTPException

    from app.services import geocode as geocode_svc

    hit = geocode_svc.reverse_geocode(lat, lng, geocode_svc.lang_for(user))
    if not hit:
        raise HTTPException(404, "Keine Adresse zu diesem Standort gefunden")
    return {"name": geocode_svc.short_name(hit, geocode_svc.parts_for(user))}
