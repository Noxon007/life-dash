"""F15 — hochgeladene Bilder: speichern, prüfen, Vorschau, EXIF.

Anders als jede andere Anreicherung liegen hier **Originaldaten**, die es
nirgendwo sonst gibt (KONZEPT Anmerkung 57): eine hochgeladene Datei gehört
zur Lebensdatenbank und wird von Maschinen nie angefasst.

Sicherheitsleitplanken, weil dies der erste Pfad ist, über den fremde Bytes
auf die Platte kommen:
  * Der Dateityp wird **durch Öffnen mit Pillow** bestimmt, nie aus Dateiname
    oder mitgeschicktem Content-Type — beides kann der Client frei behaupten.
  * Nur eine kleine Erlaubnisliste an Formaten. SVG ist bewusst NICHT dabei:
    es kann Skript enthalten und würde beim Ausliefern im Browser ausgeführt.
  * Der Dateiname auf der Platte wird selbst erzeugt (UUID + Endung aus dem
    erkannten Format); der eingereichte Name landet nie im Pfad.
  * Die Größe wird beim Lesen begrenzt, nicht erst danach.
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

log = logging.getLogger("lifedash.media")

# Erkanntes Pillow-Format -> (Endung, ausgelieferter Content-Type)
ALLOWED: dict[str, tuple[str, str]] = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
    "GIF": (".gif", "image/gif"),
}
THUMB_SUFFIX = ".thumb.jpg"


class MediaError(ValueError):
    """Eingereichte Datei ist unbrauchbar — Meldung geht an den Nutzer."""


def media_root() -> Path:
    root = Path(settings.media_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _user_dir(user_id: str) -> Path:
    """Ein Unterverzeichnis je Nutzer — hält das Löschen eines Kontos einfach
    und verhindert, dass ein Verzeichnis mit zehntausenden Dateien entsteht."""
    d = media_root() / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def path_for(user_id: str, filename: str) -> Path:
    """Absoluter Pfad einer gespeicherten Datei.

    Der Name stammt immer aus der Datenbank und damit aus unserer eigenen
    Erzeugung — trotzdem wird er hier gegen Pfad-Ausbrüche geprüft, weil diese
    Funktion auch dem Ausliefern dient und eine manipulierte DB-Zeile (oder
    ein künftiger Aufrufer) sonst beliebige Dateien lesbar machen würde.
    """
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise MediaError("Unzulässiger Dateiname")
    base = _user_dir(user_id).resolve()
    target = (base / filename).resolve()
    if not target.is_relative_to(base):
        raise MediaError("Unzulässiger Dateiname")
    return target


def _exif_datetime(img: Image.Image) -> datetime | None:
    """Aufnahmezeitpunkt aus den EXIF-Daten (36867 = DateTimeOriginal)."""
    try:
        exif = img.getexif()
    except Exception:  # noqa: BLE001 — kaputtes EXIF darf nie den Upload kippen
        return None
    for tag in (36867, 36868, 306):     # Original, Digitalisiert, Änderung
        raw = exif.get(tag)
        if not raw:
            continue
        try:
            return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _exif_gps(img: Image.Image) -> tuple[float, float] | None:
    """Aufnahmeort aus den EXIF-GPS-Daten als (lat, lng) in Dezimalgrad."""
    try:
        gps = img.getexif().get_ifd(0x8825)
    except Exception:  # noqa: BLE001
        return None
    if not gps:
        return None

    def _deg(value) -> float | None:
        try:
            d, m, s = (float(x) for x in value)
            return d + m / 60 + s / 3600
        except (TypeError, ValueError):
            return None

    lat, lng = _deg(gps.get(2)), _deg(gps.get(4))
    if lat is None or lng is None:
        return None
    if str(gps.get(1, "N")).upper().startswith("S"):
        lat = -lat
    if str(gps.get(3, "E")).upper().startswith("W"):
        lng = -lng
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return None
    return round(lat, 6), round(lng, 6)


def read_upload(stream, *, max_bytes: int | None = None) -> bytes:
    """Liest höchstens `max_bytes` + 1 Byte — so wird eine zu große Datei
    erkannt, ohne sie je vollständig in den Speicher zu holen."""
    limit = int(max_bytes or settings.media_max_mb * 1024 * 1024)
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise MediaError(f"Datei ist größer als {settings.media_max_mb} MB")
    if not data:
        raise MediaError("Leere Datei")
    return data


def store(user_id: str, data: bytes) -> dict:
    """Prüft, speichert und vermisst ein Bild.

    Gibt die Angaben für den MediaRef-Datensatz zurück, dazu die aus EXIF
    gelesenen Vorschläge (`captured_at`, `gps`) — Vorschläge deshalb, weil
    bestätigte Daten nie automatisch überschrieben werden (Kap. 3.1).
    """
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            if fmt not in ALLOWED:
                raise MediaError(
                    f"Format {fmt or 'unbekannt'} wird nicht unterstützt "
                    f"({', '.join(sorted(ALLOWED))})")
            probe.verify()          # erkennt abgeschnittene/kaputte Dateien
    except UnidentifiedImageError:
        raise MediaError("Die Datei ist kein Bild") from None
    except MediaError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise MediaError("Die Datei ist kein lesbares Bild") from exc

    suffix, mime = ALLOWED[fmt]
    filename = f"{uuid.uuid4().hex}{suffix}"
    target = path_for(user_id, filename)

    # verify() macht das Bild unbrauchbar -> für Maße, EXIF und Vorschau neu öffnen
    with Image.open(io.BytesIO(data)) as img:
        width, height = img.size
        captured = _exif_datetime(img)
        gps = _exif_gps(img)
        thumb = ImageOps.exif_transpose(img)   # gedrehte Handyfotos aufrichten
        thumb = thumb.convert("RGB")
        thumb.thumbnail((settings.media_thumb_px, settings.media_thumb_px))

    target.write_bytes(data)
    try:
        thumb.save(path_for(user_id, filename + THUMB_SUFFIX), "JPEG", quality=82)
    except OSError as exc:
        target.unlink(missing_ok=True)         # keine Datei ohne Vorschau zurücklassen
        raise MediaError("Vorschaubild konnte nicht erzeugt werden") from exc

    log.info("Bild gespeichert: %s (%s, %dx%d, %d Bytes)",
             filename, mime, width, height, len(data))
    return {"filename": filename, "mime": mime, "bytes": len(data),
            "width": width, "height": height,
            "captured_at": captured, "gps": gps}


def purge_for_events(db, event_ids) -> int:
    """Löscht die Dateien aller hochgeladenen Bilder dieser Events.

    Muss VOR dem Löschen der Datensätze laufen — danach ist nicht mehr
    bekannt, welche Dateien gemeint waren. Ohne diesen Schritt bliebe bei
    jedem Event-Löschen eine verwaiste Datei auf der Platte liegen.
    """
    from app.models import MediaRef

    ids = list(event_ids)
    if not ids:
        return 0
    refs = (db.query(MediaRef)
            .filter(MediaRef.event_id.in_(ids), MediaRef.provider == "local")
            .all())
    for ref in refs:
        delete(ref.user_id or "", ref.external_id)
    return len(refs)


def purge_all(db) -> int:
    """Löscht die Dateien ALLER hochgeladenen Bilder (für „alle Daten
    löschen"). Räumt anschließend leere Nutzerverzeichnisse ab."""
    from app.models import MediaRef

    refs = db.query(MediaRef).filter(MediaRef.provider == "local").all()
    for ref in refs:
        delete(ref.user_id or "", ref.external_id)
    for child in media_root().iterdir():
        if child.is_dir() and not any(child.iterdir()):
            child.rmdir()
    return len(refs)


def delete(user_id: str, filename: str) -> None:
    """Entfernt Datei und Vorschau. Fehlende Dateien sind kein Fehler — die
    Datenbank bleibt sonst mit einer Zeile zurück, die sich nicht löschen lässt."""
    for name in (filename, filename + THUMB_SUFFIX):
        try:
            path_for(user_id, name).unlink(missing_ok=True)
        except (MediaError, OSError) as exc:
            log.warning("Datei %s ließ sich nicht löschen: %s", name, exc)
