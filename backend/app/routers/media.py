"""F15 — Bilder von Hand an Events hängen.

Anders als der Immich-Konnektor (P2.1) braucht das hier keinen fremden Dienst:
die Datei liegt im Medienverzeichnis, der Datensatz zeigt darauf. Beides
gehört zur **Lebensdatenbank**, nicht zu den Ableitungen (Anmerkung 57).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import (APIRouter, Body, Depends, File, HTTPException, Response,
                     UploadFile)
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, MediaRef, User
from app.schemas import MediaRead, MediaUploadResult
from app.services import media as media_svc

log = logging.getLogger("lifedash.media")
router = APIRouter(prefix="/api", tags=["Medien"])

# Uploads sind fremde Bytes. Selbst wenn nur geprüfte Bildformate hier
# landen: der Browser darf den Typ nicht selbst raten dürfen, sonst wird aus
# einer als Bild getarnten Datei doch noch ausführbarer Inhalt.
_SAFE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Disposition": "inline",
    "Cache-Control": "private, max-age=31536000, immutable",
}


def _own_event(db: Session, event_id: str, user: User) -> Event:
    event = db.get(Event, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="Event nicht gefunden")
    return event


def _own_media(db: Session, media_id: str, user: User) -> MediaRef:
    ref = db.get(MediaRef, media_id)
    # Doppelt abgesichert: eigener Datensatz ODER eigenes Event. Bestandszeilen
    # aus der Zeit vor Anmerkung 57 haben noch kein user_id.
    if ref is None:
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")
    owner = ref.user_id or (ref.event.user_id if ref.event else None)
    if owner != user.id:
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")
    return ref


def _to_read(ref: MediaRef) -> MediaRead:
    return MediaRead(
        id=ref.id, event_id=ref.event_id, provider=ref.provider,
        mime=ref.mime, bytes=ref.bytes, width=ref.width, height=ref.height,
        caption=ref.caption, sort_order=ref.sort_order or 0,
        captured_at=ref.captured_at,
        url=f"/api/media/{ref.id}/file", thumb_url=f"/api/media/{ref.id}/thumb",
    )


@router.get("/events/{event_id}/media", response_model=list[MediaRead])
def list_media(event_id: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> list[MediaRead]:
    """Bilder eines Events, in der gewählten Reihenfolge."""
    event = _own_event(db, event_id, user)
    refs = sorted(event.media, key=lambda m: (m.sort_order or 0, m.created_at or 0))
    return [_to_read(m) for m in refs]


@router.post("/events/{event_id}/media", response_model=MediaUploadResult,
             status_code=201)
def upload_media(
    event_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MediaUploadResult:
    """Lädt ein Bild hoch und hängt es an das Event.

    Bewusst SYNCHRON: Lesen, Prüfen, Skalieren und Schreiben blockieren alle.
    In einer `async def` würden sie die Ereignisschleife anhalten und damit
    jede andere Anfrage ausbremsen; als normale Funktion legt FastAPI den
    Aufruf in den Threadpool, wo blockierende Arbeit hingehört.

    Der Aufnahmezeitpunkt und die Koordinaten aus den EXIF-Daten werden
    **zurückgegeben, nicht angewendet**: über das Datum eines bestätigten
    Events entscheidet der Mensch (Kap. 3.1). Das Frontend bietet sie an.
    """
    event = _own_event(db, event_id, user)
    try:
        data = media_svc.read_upload(file.file)
        info = media_svc.store(user.id, data)
    except media_svc.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    highest = max((m.sort_order or 0 for m in event.media), default=-1)
    ref = MediaRef(
        user_id=user.id, event_id=event.id, provider="local",
        external_id=info["filename"], mime=info["mime"], bytes=info["bytes"],
        width=info["width"], height=info["height"],
        captured_at=info["captured_at"], sort_order=highest + 1,
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)

    gps = info["gps"]
    return MediaUploadResult(
        media=_to_read(ref),
        suggested_captured_at=info["captured_at"],
        suggested_lat=gps[0] if gps else None,
        suggested_lng=gps[1] if gps else None,
    )


def _send(ref: MediaRef, user: User, thumb: bool) -> Response:
    name = ref.external_id + (media_svc.THUMB_SUFFIX if thumb else "")
    try:
        path = media_svc.path_for(ref.user_id or user.id, name)
        data = path.read_bytes()
    except (media_svc.MediaError, OSError):
        raise HTTPException(status_code=404, detail="Datei nicht gefunden") from None
    return Response(content=data,
                    media_type="image/jpeg" if thumb else (ref.mime or "image/jpeg"),
                    headers=_SAFE_HEADERS)


@router.get("/media/{media_id}/file")
def get_file(media_id: str, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> Response:
    """Das Original — nur für den Besitzer."""
    return _send(_own_media(db, media_id, user), user, thumb=False)


@router.get("/media/{media_id}/thumb")
def get_thumb(media_id: str, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> Response:
    """Die Vorschau (serverseitig erzeugt, aufgerichtet)."""
    return _send(_own_media(db, media_id, user), user, thumb=True)


@router.patch("/media/{media_id}", response_model=MediaRead)
def update_media(
    media_id: str,
    # Annotated statt Body-als-Default: sonst steht beim direkten Aufruf
    # (Tests, interne Nutzung) das Body-Objekt selbst im Parameter und landet
    # als Wert in der Datenbank. Derselbe Fallstrick wie bei Query in 0.21.0.
    caption: Annotated[str | None, Body(embed=True)] = None,
    sort_order: Annotated[int | None, Body(embed=True)] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MediaRead:
    """Bildunterschrift oder Reihenfolge ändern."""
    ref = _own_media(db, media_id, user)
    if caption is not None:
        ref.caption = caption.strip() or None
    if sort_order is not None:
        ref.sort_order = sort_order
    db.commit()
    db.refresh(ref)
    return _to_read(ref)


@router.delete("/media/{media_id}")
def delete_media(media_id: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    """Löscht Bild und Datei — auf ausdrückliche Ansage des Nutzers.

    Das ist die EINZIGE Stelle, an der eine hochgeladene Datei verschwindet
    (plus dem Löschen des Events oder des Kontos). Keine Neuberechnung,
    kein Aufräum-Job fasst sie an.
    """
    ref = _own_media(db, media_id, user)
    filename, owner, was_upload = ref.external_id, ref.user_id or user.id, ref.is_upload
    db.delete(ref)
    db.commit()
    if was_upload:
        media_svc.delete(owner, filename)
    return {"deleted": media_id}
