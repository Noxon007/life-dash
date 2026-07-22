"""F15/F18 — Bilder von Hand anhängen: an ein Ereignis oder an einen Tag.

Anders als der Immich-Konnektor (P2.1) braucht das hier keinen fremden Dienst:
die Datei liegt im Medienverzeichnis, der Datensatz zeigt darauf. Beides
gehört zur **Lebensdatenbank**, nicht zu den Ableitungen (Anmerkung 57).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import (APIRouter, Body, Depends, File, HTTPException, Query,
                     Response, UploadFile)
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, MediaRef, User
from app.schemas import MediaRead, MediaUploadResult
from app.services import immich as immich_api
from app.services import media as media_svc
from app.services.immich_link import PROVIDER as IMMICH

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


# F18 (Anmerkung 87): Bilder eines TAGES — die, die an keinem Ereignis hängen.
# Der Tag ist kein Objekt, sondern der Kalendertag von `captured_at`; die
# Zeitachse trägt die Zuordnung, wie überall sonst in diesem Modell.
@router.get("/days/{day}/media", response_model=list[MediaRead])
def list_day_media(day: date, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> list[MediaRead]:
    """Bilder, die an diesem Kalendertag hängen (ohne Ereignis)."""
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)
    refs = (db.query(MediaRef)
            .filter(MediaRef.user_id == user.id,
                    MediaRef.event_id.is_(None),
                    MediaRef.captured_at >= start, MediaRef.captured_at < end)
            .order_by(MediaRef.sort_order, MediaRef.created_at).all())
    return [_to_read(m) for m in refs]


@router.get("/days/media", response_model=dict[str, list[MediaRead]])
def list_day_media_range(
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, list[MediaRead]]:
    """Tages-Bilder eines Zeitraums, nach Tag gebündelt (`{"2026-07-05": [...]}`).

    Der Zeitstrahl lädt seit A37 Seiten; eine Abfrage je sichtbarem Tag wären
    dutzende Anfragen beim Scrollen. Eine je Seite reicht — dieselbe Regel wie
    beim Wetter und bei den Kinder-Zählungen.
    """
    start = datetime(date_from.year, date_from.month, date_from.day)
    end = datetime(date_to.year, date_to.month, date_to.day) + timedelta(days=1)
    refs = (db.query(MediaRef)
            .filter(MediaRef.user_id == user.id,
                    MediaRef.event_id.is_(None),
                    MediaRef.captured_at >= start, MediaRef.captured_at < end)
            .order_by(MediaRef.captured_at, MediaRef.sort_order).all())
    out: dict[str, list[MediaRead]] = {}
    for ref in refs:
        out.setdefault(ref.captured_at.date().isoformat(), []).append(_to_read(ref))
    return out


@router.post("/days/{day}/media", response_model=MediaUploadResult,
             status_code=201)
def upload_day_media(
    day: date,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MediaUploadResult:
    """Lädt ein Bild hoch und hängt es an einen TAG statt an ein Ereignis.

    Der Aufnahmezeitpunkt aus den EXIF-Daten wird übernommen, sofern er auf
    diesen Tag fällt — sonst gilt der gewählte Tag. Ohne Ereignis ist
    `captured_at` der einzige Anker, es darf hier also nicht leer bleiben;
    das ist der einzige Unterschied zum Upload an ein Ereignis, wo ein Bild
    ohne Aufnahmezeit weiterhin erlaubt ist (es hängt ja am Ereignis).
    """
    try:
        data = media_svc.read_upload(file.file)
        info = media_svc.store(user.id, data)
    except media_svc.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    taken = info["captured_at"]
    if not taken or taken.date() != day:
        taken = datetime(day.year, day.month, day.day, 12, 0)
    highest = (db.query(func.max(MediaRef.sort_order))
               .filter(MediaRef.user_id == user.id, MediaRef.event_id.is_(None))
               .scalar())
    ref = MediaRef(
        user_id=user.id, event_id=None, provider="local",
        external_id=info["filename"], mime=info["mime"], bytes=info["bytes"],
        width=info["width"], height=info["height"],
        captured_at=taken, sort_order=(highest or 0) + 1,
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
    # P2.1: Immich-Verweise kommen aus dem fremden Dienst — durchgereicht,
    # nie zwischengespeichert (Kap. 9: Verweise, keine Kopien). Der
    # API-Schlüssel bleibt dabei serverseitig und erreicht den Browser nie.
    if ref.provider == IMMICH:
        cfg = immich_api.config_for(user)
        if cfg is None:
            raise HTTPException(status_code=404, detail="Immich nicht eingerichtet")
        try:
            data = immich_api.thumbnail(*cfg, ref.external_id)
        except immich_api.ImmichError as exc:
            # 502: der Fehler liegt beim fremden Dienst, nicht bei uns
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return Response(content=data, media_type="image/jpeg", headers=_SAFE_HEADERS)

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


@router.post("/media/immich/reset")
def reset_immich(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    """Verwirft alle Immich-Verknüpfungen — der nächste Lauf baut sie neu auf.

    Erlaubt, weil Verweise eine **Ableitung** sind (Anmerkung 57): die Bilder
    liegen in Immich und bleiben dort. Selbst hochgeladene Dateien
    (`provider=local`) sind davon ausdrücklich NICHT betroffen — die gehören
    zur Lebensdatenbank und wären unwiederbringlich.
    """
    from app.services.immich_link import reset

    return {"removed": reset(db, user.id)}


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
