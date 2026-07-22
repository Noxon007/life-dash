"""Daten-Export & -Import (Datenkontrolle, siehe Konzept Kap. 12).

Export: alle eigenen Daten (Stufe 1–3) als ein JSON-Dokument.
Import: dasselbe Format zurückspielen — idempotent (vorhandene IDs werden
übersprungen), alles landet beim angemeldeten Nutzer. Funktioniert damit
als Backup/Restore und für Umzüge zwischen Instanzen.
"""
from __future__ import annotations

import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from dateutil import parser as dateparser
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import DateTime
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.joblog import Progress
from app.services import archive
from app.services import media as media_svc
from app.models import (
    Entity,
    Event,
    EventEntityLink,
    Fragment,
    Location,
    MediaRef,
    Metric,
    Track,
    User,
)

log = logging.getLogger("lifedash.data")

router = APIRouter(prefix="/api/data", tags=["Export & Import"])

EXPORT_VERSION = 1


def _row_to_dict(obj) -> dict:
    """ORM-Zeile -> JSON-fähiges Dict (Datetimes als ISO-Strings)."""
    out: dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, "value"):  # Enum
            val = val.value
        out[col.name] = val
    return out


def _dict_to_kwargs(model, data: dict) -> dict:
    """JSON-Dict -> Spalten-Werte (ISO-Strings zurück zu Datetimes)."""
    kwargs: dict[str, Any] = {}
    for col in model.__table__.columns:
        if col.name not in data:
            continue
        val = data[col.name]
        if val is not None and isinstance(col.type, DateTime):
            val = dateparser.parse(str(val))
        kwargs[col.name] = val
    return kwargs


@router.get("/export")
def export_data(
    exclude_source: str = "",
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """Vollständiger Export der eigenen Daten als JSON.

    exclude_source (Auswahl-Export): Komma-Liste von Quellen, die NICHT
    exportiert werden — z. B. "google_timeline" lässt importierte Besuche,
    Routen und deren Roh-Belege weg (handliches Backup der handgepflegten
    Lebensdatenbank). Metriken/Verknüpfungen folgen ihren Events."""
    excluded = {s.strip() for s in exclude_source.split(",") if s.strip()}

    # A34/Anmerkung 92: Ein Export über 12 000 Ereignisse läuft eine Weile, und
    # bis 0.34.0 stand die einzige Zeile dazu ganz am Ende — wer währenddessen
    # ins Log sah, sah nichts. Jetzt meldet sich jeder Abschnitt einzeln; das
    # zeigt nebenbei, welcher Teil die Zeit kostet.
    log.info("Export beginnt (user=%s%s)", user.email or user.id,
             f", ohne {', '.join(sorted(excluded))}" if excluded else "")

    def _loaded(name: str, rows: list) -> list:
        log.info("Export: %s — %d Zeilen", name, len(rows))
        return rows

    def _kept(query, model):
        rows = query.filter(model.user_id == user.id).all()
        if not excluded:
            return rows
        return [r for r in rows if getattr(r.source, "value", r.source) not in excluded]

    fragments = _loaded("Fragmente", _kept(db.query(Fragment), Fragment))
    locations = _loaded("Orte", db.query(Location)
                        .filter(Location.user_id == user.id).all())
    entities = _loaded("Entitäten", db.query(Entity)
                       .filter(Entity.user_id == user.id).all())
    events = _loaded("Ereignisse", _kept(db.query(Event), Event))
    tracks = _loaded("Wege", _kept(db.query(Track), Track))
    event_ids = {e.id for e in events}
    links = [
        l for l in db.query(EventEntityLink).all() if l.event_id in event_ids
    ]
    # F18: Bilder gehören dem NUTZER, nicht zwingend einem Ereignis. Ein Filter
    # allein über `event_id` ließe alle Tages-Bilder aus dem Backup fallen —
    # lautlos, denn die Datei sähe vollständig aus. Bilder an Ereignissen, die
    # der Export bewusst weglässt (A21), bleiben weiterhin draußen.
    media = _loaded("Bilder", [m for m in db.query(MediaRef)
                               .filter(MediaRef.user_id == user.id).all()
                               if m.event_id is None or m.event_id in event_ids])
    metrics = _loaded("Messwerte", [m for m in db.query(Metric).all()
                                    if m.event_id in event_ids])
    _loaded("Verknüpfungen", links)
    # F15/Anmerkung 57: Ab hier ist der JSON-Export KEIN vollständiges Backup
    # mehr. Bilddateien passen nicht hinein; ihre Metadaten schon. Wer das
    # nicht weiß, verliert seine Fotos im Vertrauen auf eine Datei, die
    # vollständig aussieht — deshalb steht es im Export selbst, nicht nur in
    # der Doku. Das schließt A29 (ZIP-Export mit Dateien) später sauber ab.
    uploads = sum(1 for m in media if m.provider == "local")
    total = sum(len(x) for x in (fragments, locations, entities, events,
                                 links, media, metrics, tracks))
    log.info("Export fertig: %d Zeilen, davon %d Bilder als Verweis "
             "(Dateien liegen nicht im JSON)", total, uploads)
    return {
        "format": "lifedash-export",
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "media_files_included": False,
        "media_files_count": uploads,
        "media_note": (
            f"Dieser Export enthält die Angaben zu {uploads} hochgeladenen Bildern, "
            "aber NICHT die Bilddateien selbst. Das Medienverzeichnis "
            "(MEDIA_DIR) muss separat gesichert werden — siehe docs/DEPLOY.md."
        ) if uploads else None,
        "fragments": [_row_to_dict(x) for x in fragments],
        "locations": [_row_to_dict(x) for x in locations],
        "entities": [_row_to_dict(x) for x in entities],
        "events": [_row_to_dict(x) for x in events],
        "event_entity_links": [_row_to_dict(x) for x in links],
        "media_refs": [_row_to_dict(x) for x in media],
        "metrics": [_row_to_dict(x) for x in metrics],
        "tracks": [_row_to_dict(x) for x in tracks],
    }


@router.get("/export.zip")
def export_archive(
    exclude_source: str = "",
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> StreamingResponse:
    """A29: vollständiges Backup — dieselben Daten wie `/export`, PLUS die
    hochgeladenen Bilddateien.

    Der reine JSON-Export bleibt daneben bestehen: er ist klein, lesbar,
    diffbar und die richtige Wahl für alle, die ihr Medienverzeichnis
    anderweitig sichern.
    """
    payload = export_data(exclude_source=exclude_source, db=db, user=user)
    # Nur hochgeladene Dateien — Immich-Verweise zeigen auf ein fremdes
    # System, dessen Bilder nicht uns gehören und dort gesichert werden.
    uploads = [m for m in payload["media_refs"] if m.get("provider") == "local"]
    files: list[tuple[str, Path]] = []
    for row in uploads:
        try:
            files.append((row["external_id"],
                          media_svc.path_for(user.id, row["external_id"])))
        except media_svc.MediaError:
            continue
    payload["media_files_included"] = True
    payload["media_note"] = (
        f"Dieses Archiv enthält {len(files)} Bilddatei(en) unter media/. "
        "Zurückspielen über Verwaltung → Meine Daten → Import.")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info("Archiv-Export angefordert: %d Bilddateien (user=%s)", len(files),
             user.email or user.id)
    return StreamingResponse(
        archive.stream(payload, files),
        media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="life-dash-{stamp}.zip"'},
    )


@router.post("/import.zip")
def import_archive(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """A29: spielt ein Archiv zurück — Daten UND Bilddateien.

    Bewusst synchron (blockierendes Entpacken gehört in den Threadpool) und
    idempotent: vorhandene Zeilen und vorhandene Dateien werden übersprungen,
    ein zweiter Import ändert nichts. Genau das macht den Unterschied zwischen
    einem Archiv und einem Backup.
    """
    # Für ZipFile wird eine durchsuchbare Datei gebraucht; UploadFile liefert
    # genau das (SpooledTemporaryFile — im RAM nur, solange es klein ist).
    try:
        with zipfile.ZipFile(file.file) as zf:
            payload = archive.read_payload(zf)
            result = import_data(payload=payload, db=db, user=user)
            restored, skipped = archive.extract_media(
                zf, media_svc.media_root() / user.id,
                max_bytes=settings.media_max_mb * 1024 * 1024,
                verify=media_svc.is_image,
            )
    except zipfile.BadZipFile:
        raise HTTPException(400, "Die Datei ist kein lesbares ZIP-Archiv") from None
    except archive.ArchiveError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Vorschaubilder liegen nicht im Archiv (ableitbar) — hier neu erzeugen,
    # sonst zeigt der Zeitstrahl nach dem Zurückspielen kaputte Bilder.
    thumbs = sum(
        media_svc.ensure_thumbnail(user.id, m.external_id)
        for m in db.query(MediaRef).filter(MediaRef.user_id == user.id,
                                           MediaRef.provider == "local").all()
    )
    log.info("Archiv-Import: %d Bilddateien wiederhergestellt, %d übersprungen, "
             "%d Vorschauen erzeugt (user=%s)",
             restored, skipped, thumbs, user.email or user.id)
    return result | {"media_restored": restored, "media_skipped": skipped,
                     "thumbnails_created": thumbs}


@router.post("/wipe-mine")
def wipe_my_data(
    confirm: Annotated[str, Body(embed=True)] = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """A33: löscht ALLE eigenen Daten — das Gegenstück zum Export.

    Der Admin-Rundumschlag (`/api/admin/wipe-data`) leert die ganze Instanz und
    ist damit das falsche Werkzeug für „weg mit meinen Sachen". Hier geht nur,
    was diesem Konto gehört; das Konto selbst bleibt bestehen.

    Fragmente sind eingeschlossen: sie sind das Rohmaterial **dieses** Nutzers,
    kein geteiltes Beweisarchiv. Wer geht, lässt es nicht zurück.

    Reihenfolge wie in Anmerkung 59: erst die Dateinamen einsammeln, dann die
    Zeilen löschen, **dann** die Dateien. Andersherum hinterließe ein Fehler
    mittendrin den schlimmsten Zustand — Bilder weg, Daten noch da.
    """
    if confirm.strip().upper() != "LOESCHEN":
        raise HTTPException(
            400, "Zum Bestätigen bitte LOESCHEN eingeben — das lässt sich nicht rückgängig machen.")

    event_ids = [i for (i,) in db.query(Event.id).filter(Event.user_id == user.id).all()]
    doomed = media_svc.list_uploads_for_user(db, user.id)

    # A34: je Tabelle protokollieren — bei großen Beständen dauert das
    deleted: dict[str, int] = {}
    log.warning("Eigene Daten löschen: beginne (%d Events, %d Bilddateien, user=%s)",
                len(event_ids), len(doomed), user.email or user.id)
    if event_ids:
        for model, key in ((Metric, "metrics"), (MediaRef, "media_refs"),
                           (EventEntityLink, "event_entity_links")):
            deleted[key] = (db.query(model)
                            .filter(model.event_id.in_(event_ids))
                            .delete(synchronize_session=False))
            log.info("  %s: %d Zeilen gelöscht", key, deleted[key])
    for model, key in ((Track, "tracks"), (Event, "events"), (Entity, "entities"),
                       (Location, "locations"), (Fragment, "fragments")):
        deleted[key] = (db.query(model).filter(model.user_id == user.id)
                        .delete(synchronize_session=False))
        log.info("  %s: %d Zeilen gelöscht", key, deleted[key])
    db.commit()
    files = media_svc.purge_files(doomed)

    log.warning("Eigene Daten gelöscht: %d Zeilen, %d Bilddateien (user=%s)",
                sum(deleted.values()), files, user.email or user.id)
    return {"deleted": deleted, "total": sum(deleted.values()), "media_files": files}


@router.post("/import")
def import_data(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Spielt einen Life-Dash-Export zurück. Vorhandene IDs werden übersprungen
    (idempotent); alle importierten Zeilen gehören dem angemeldeten Nutzer."""
    if payload.get("format") != "lifedash-export":
        return {"error": "Kein Life-Dash-Export (format-Feld fehlt/falsch)"}

    # Reihenfolge beachtet Fremdschlüssel (Eltern zuerst)
    plan = [
        ("locations", Location, True),
        ("fragments", Fragment, True),
        ("entities", Entity, True),
        ("events", Event, True),
        ("event_entity_links", EventEntityLink, False),
        # media_refs führt seit 0.24.0 ein eigenes user_id (Anmerkung 57).
        # Es MUSS auf den importierenden Nutzer umgeschrieben werden — sonst
        # trägt die Zeile nach einer Wiederherstellung auf einer anderen
        # Instanz eine fremde Kennung, und die Bilder wären für niemanden
        # mehr erreichbar (weder Rechteprüfung noch Dateipfad passen).
        ("media_refs", MediaRef, True),
        ("metrics", Metric, False),
        ("tracks", Track, True),
    ]
    imported: dict[str, int] = {}
    skipped = 0
    # Der Import prüft jede Zeile einzeln gegen die Datenbank (Idempotenz) —
    # bei einem vollen Backup sind das zehntausende Abfragen. Ohne Zwischenstand
    # ist der Unterschied zwischen „arbeitet" und „hängt" nicht zu sehen.
    rows_total = sum(len(payload.get(key, [])) for key, _, _ in plan)
    progress = Progress(log, "Daten-Import", unit="Zeilen")
    progress.start(rows_total, note=f"user={user.email or user.id}")
    seen = 0
    for key, model, has_user in plan:
        count = 0
        for row in payload.get(key, []):
            seen += 1
            progress.beat(seen, rows_total - seen, note=key)
            if not row.get("id") or db.get(model, row["id"]) is not None:
                skipped += 1
                continue
            kwargs = _dict_to_kwargs(model, row)
            if has_user:
                kwargs["user_id"] = user.id
            db.add(model(**kwargs))
            count += 1
        db.flush()
        imported[key] = count
        if payload.get(key):
            log.info("Import: %s — %d neu, %d schon vorhanden",
                     key, count, len(payload[key]) - count)
    db.commit()
    progress.finish(f"{sum(imported.values())} neu, {skipped} übersprungen")
    return {"imported": imported, "skipped_existing": skipped,
            "total": sum(imported.values())}
