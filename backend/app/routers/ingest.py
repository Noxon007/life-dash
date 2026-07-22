"""Ingestion-Endpoints: Roh-Text rein -> Stufe-2-Vorschau raus."""
from __future__ import annotations

import time
from collections import OrderedDict

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

# --------------------------------------------------------------------------- #
# P5.1 — Doppelte aus der Offline-Warteschlange
# --------------------------------------------------------------------------- #
# Eine Erfassung, die offline gepuffert wurde, wird so lange erneut gesendet,
# bis der Server sie bestätigt hat — das ist die Zusage „nie etwas verlieren"
# (Kap. 4, Stufe 1). Der Preis: bricht die Verbindung NACH dem Speichern und
# VOR der Antwort ab, sendet der Client dieselbe Erfassung ein zweites Mal.
#
# Dagegen ein Gedächtnis über die mitgeschickte `client_id`. Bewusst im
# Arbeitsspeicher und nicht als Spalte:
#   * die Wiederholung passiert binnen Minuten, nicht Wochen — eine Tabelle
#     würde ein Vielfaches dieser Zeit aufbewahren und gepflegt werden wollen;
#   * ein Neustart genau in diesem Fenster kostet höchstens EIN doppeltes
#     Fragment, und ein doppelter Vorschlag ist sichtbar und verwerfbar,
#     während eine verlorene Erfassung endgültig ist. Die Richtung des Fehlers
#     ist also die richtige;
#   * und das Schema hält ab 0.35 still (Kap. 14.3).
# Ohne `client_id` greift nichts davon: zweimal derselbe Satz von Hand sind
# zwei Erfassungen, weil ein Mensch das so meinen kann.
_SEEN_TTL_S = 1800.0
_seen: "OrderedDict[tuple[str, str], tuple[float, str]]" = OrderedDict()
_SEEN_MAX = 500


def _seen_get(user_id: str, client_id: str) -> str | None:
    now = time.monotonic()
    while _seen and next(iter(_seen.values()))[0] < now - _SEEN_TTL_S:
        _seen.popitem(last=False)
    hit = _seen.get((user_id, client_id))
    return hit[1] if hit else None


def _seen_put(user_id: str, client_id: str, fragment_id: str) -> None:
    _seen[(user_id, client_id)] = (time.monotonic(), fragment_id)
    while len(_seen) > _SEEN_MAX:
        _seen.popitem(last=False)


@router.post("", response_model=IngestResult)
def ingest(
    payload: FragmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IngestResult:
    """Speichert den Roh-Text (Roh-Eingang) und erzeugt KI-Vorschläge (unbestätigt)."""
    if payload.client_id:
        known = _seen_get(user.id, payload.client_id)
        if known:
            existing = db.get(Fragment, known)
            if existing is not None and existing.user_id == user.id:
                return IngestResult(
                    fragment=FragmentRead.model_validate(existing),
                    events=[event_to_read(e) for e in existing.events],
                    duplicate=True,
                )

    fragment = Fragment(user_id=user.id, raw_text=payload.raw_text, source=payload.source,
                        capture_lat=payload.capture_lat, capture_lng=payload.capture_lng)
    db.add(fragment)
    db.flush()

    events = ingest_fragment(db, fragment)
    # P2.4: Wetter (Fakten-Anreicherung) direkt mitliefern statt Admin-Knopf;
    # Embeddings entstehen bereits beim Anlegen des Events.
    auto_enrich_events(db, events)
    db.commit()

    # Erst NACH dem Commit merken: was nicht gespeichert wurde, darf beim
    # nächsten Versuch nicht als „schon da" durchgewunken werden.
    if payload.client_id:
        _seen_put(user.id, payload.client_id, fragment.id)

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
