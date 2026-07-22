"""A29 — vollständiges Backup: ZIP aus JSON-Daten **und** Bilddateien.

Seit F15 (0.24.0) ist der JSON-Export kein komplettes Backup mehr: Binärdaten
passen nicht hinein. Ein Backup, das die unersetzliche Hälfte still weglässt,
ist ein Betriebsmangel — deshalb steht A29 in Gruppe A und nicht bei den
Features.

Aufbau des Archivs:

    export.json          — dasselbe Dokument wie der reine JSON-Export
    media/<dateiname>     — je hochgeladenem Bild das Original

Zwei Eigenschaften, die den Unterschied zwischen „Backup" und „Datei, die wie
ein Backup aussieht" ausmachen:

* **Gestreamt.** Weder Export noch Import halten das Archiv im Speicher oder
  legen es zwischenzeitlich komplett auf die Platte. Ein Leben an Fotos sind
  Gigabytes, nicht Megabytes.
* **Rückspielbar.** Die Importseite wird mitgebaut; ein Archiv, das man nicht
  zurückspielen kann, ist kein Backup.
"""
from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path

from app.joblog import Progress

log = logging.getLogger("lifedash.archive")

JSON_NAME = "export.json"
MEDIA_PREFIX = "media/"
# Vorschaubilder wandern NICHT ins Archiv: sie sind aus dem Original jederzeit
# neu erzeugbar (Ableitung) und würden das Backup ohne Gewinn aufblähen.
# Der Import legt sie beim Zurückspielen neu an.
CHUNK = 1024 * 1024
# Fortschritt im Log: A34 zählte Dateien (alle 250 eine Zeile), jetzt zählt
# `app.joblog.Progress` die Zeit — bei ungleich großen Dateien ist nur die Uhr
# ein verlässliches Lebenszeichen.


class ArchiveError(ValueError):
    """Archiv unbrauchbar — Meldung geht an den Nutzer."""


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
class _ChunkSink:
    """Sammelt, was zipfile schreibt, und gibt es häppchenweise weiter.

    zipfile will ein dateiähnliches Objekt. Statt einer echten Datei bekommt es
    dieses hier: alles Geschriebene wird sofort an den HTTP-Strom
    weitergereicht und wieder verworfen. `seekable() -> False` sagt zipfile,
    dass es nicht zurückspringen darf — es benutzt dann Data-Descriptors, was
    genau für diesen Fall vorgesehen ist.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self._pos = 0

    def write(self, data: bytes) -> int:
        self._buf += data
        self._pos += len(data)
        return len(data)

    def flush(self) -> None:  # von zipfile erwartet
        pass

    def tell(self) -> int:
        return self._pos

    def seekable(self) -> bool:
        return False

    def drain(self) -> bytes:
        out = bytes(self._buf)
        self._buf.clear()
        return out


def stream(payload: dict, files: list[tuple[str, Path]]):
    """Erzeugt das Archiv Stück für Stück.

    `files` ist eine Liste (Name im Archiv, Pfad auf der Platte). Fehlende
    Dateien werden übersprungen und gezählt statt den Export abzubrechen —
    ein unvollständiges Backup ist immer noch besser als gar keines, und die
    Ursache steht danach im Log.
    """
    sink = _ChunkSink()
    missing = done = 0
    total = len(files)
    # A34: Ein Archiv über zehntausend Fotos läuft minutenlang. Ohne Spur im
    # Log ist ein langsamer Export von einem hängenden nicht zu unterscheiden.
    progress = Progress(log, "Archiv-Export", unit="Bilddateien")
    progress.start(total)
    # Die JSON-Daten komprimieren sich gut; JPEG/PNG sind bereits komprimiert
    # und würden nur CPU kosten -> je Eintrag passend gewählt.
    with zipfile.ZipFile(sink, "w", allowZip64=True) as zf:
        zf.writestr(zipfile.ZipInfo(JSON_NAME),
                    json.dumps(payload, ensure_ascii=False, indent=1),
                    compress_type=zipfile.ZIP_DEFLATED)
        yield sink.drain()

        for name, path in files:
            done += 1
            progress.beat(done, total - done)
            if not path.is_file():
                missing += 1
                continue
            info = zipfile.ZipInfo(MEDIA_PREFIX + name)
            with zf.open(info, "w", force_zip64=True) as target, path.open("rb") as src:
                while chunk := src.read(CHUNK):
                    target.write(chunk)
                    if data := sink.drain():
                        yield data
            if data := sink.drain():
                yield data
    yield sink.drain()      # Zentralverzeichnis am Schluss
    progress.finish(f"{total - missing}/{total} Bilddateien geschrieben" +
                    (f", {missing} fehlten auf der Platte" if missing else ""))


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #
def safe_member(name: str) -> str | None:
    """Prüft einen Archiv-Eintrag und gibt den reinen Dateinamen zurück.

    Archive sind fremde Daten: ein Eintrag namens `../../etc/cron.d/böse`
    würde beim Entpacken außerhalb des Zielverzeichnisses landen („Zip Slip").
    Erlaubt ist deshalb ausschließlich `media/<dateiname>` ohne jede
    Pfadkomponente — alles andere wird verworfen, nicht repariert.
    """
    if not name.startswith(MEDIA_PREFIX):
        return None
    rest = name[len(MEDIA_PREFIX):]
    if not rest or rest != Path(rest).name or rest.startswith("."):
        return None
    if "\\" in rest or ".." in rest:
        return None
    return rest


def read_payload(zf: zipfile.ZipFile) -> dict:
    """Holt export.json aus dem Archiv."""
    try:
        raw = zf.read(JSON_NAME)
    except KeyError:
        raise ArchiveError(
            f"Im Archiv fehlt {JSON_NAME} — ist das ein Life-Dash-Backup?") from None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"{JSON_NAME} ist beschädigt") from exc
    if not isinstance(data, dict):
        raise ArchiveError(f"{JSON_NAME} hat ein unerwartetes Format")
    return data


def extract_media(zf: zipfile.ZipFile, target_dir: Path, *,
                  max_bytes: int, verify) -> tuple[int, int]:
    """Entpackt die Bilder ins Zielverzeichnis.

    Gibt (wiederhergestellt, übersprungen) zurück. Übersprungen wird, was
    schon da ist — so ist ein zweiter Import folgenlos —, und was die Prüfung
    nicht besteht.

    `verify(bytes)` bekommt jede Datei zu sehen, bevor sie geschrieben wird.
    Ein Archiv ist genauso fremd wie ein Upload: es darf nichts hineinkommen,
    was nicht als Bild erkannt wird.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    restored = skipped = seen = 0
    members = [i for i in zf.infolist() if not i.is_dir()]
    progress = Progress(log, "Archiv-Import", unit="Einträge")
    progress.start(len(members))
    for info in members:
        seen += 1
        progress.beat(seen, len(members) - seen, note=f"{restored} wiederhergestellt")
        name = safe_member(info.filename)
        if name is None:
            if info.filename != JSON_NAME:
                log.warning("Archiv: Eintrag %r verworfen", info.filename)
                skipped += 1
            continue
        if info.file_size > max_bytes:
            log.warning("Archiv: %s ist zu groß (%d Bytes)", name, info.file_size)
            skipped += 1
            continue
        dest = target_dir / name
        if dest.exists():
            skipped += 1
            continue
        data = zf.read(info)
        if not verify(data):
            log.warning("Archiv: %s ist kein gültiges Bild", name)
            skipped += 1
            continue
        dest.write_bytes(data)
        restored += 1
    progress.finish(f"{restored} wiederhergestellt, {skipped} übersprungen")
    return restored, skipped
