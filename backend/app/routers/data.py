"""Daten-Export & -Import (Datenkontrolle, siehe ARCHITECTURE Kap. 10).

Export: alle eigenen Daten (Stufe 1–3) als ein JSON-Dokument.
Import: dasselbe Format zurückspielen — idempotent (vorhandene IDs werden
übersprungen), alles landet beim angemeldeten Nutzer. Funktioniert damit
als Backup/Restore und für Umzüge zwischen Instanzen.
"""
from __future__ import annotations

import logging
import zipfile
from datetime import date as date_type, datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from dateutil import parser as dateparser
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import Date, DateTime, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import Base, get_db
from app.joblog import Progress
from app.services import archive
from app.services import media as media_svc
from app.wipe import is_delete_word, wipe_user_rows
from app.models import (
    BaselineLocation,
    DayMetric,
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
    """ORM-Zeile -> JSON-fähiges Dict (Zeitpunkte und Tage als ISO-Strings)."""
    out: dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        # Reihenfolge ist Pflicht: `datetime` IST ein `date`. Andersherum
        # geprüft verlöre jeder Zeitstempel seine Uhrzeit.
        if isinstance(val, datetime):
            val = val.isoformat()
        elif isinstance(val, date_type):
            val = val.isoformat()
        elif hasattr(val, "value"):  # Enum
            val = val.value
        out[col.name] = val
    return out


def _dict_to_kwargs(model, data: dict) -> dict:
    """JSON-Dict -> Spalten-Werte (ISO-Strings zurück zu Zeitpunkten/Tagen)."""
    kwargs: dict[str, Any] = {}
    for col in model.__table__.columns:
        if col.name not in data:
            continue
        val = data[col.name]
        if val is not None and isinstance(col.type, DateTime):
            val = dateparser.parse(str(val))
        elif val is not None and isinstance(col.type, Date):
            # Ein reiner Tag muss auch als `date` ankommen und nicht als
            # `datetime` mit 00:00 — sonst steht in `baseline_locations`
            # etwas, das die Wohnort-Rechnung anders vergleicht als das,
            # was sie selbst schreibt.
            val = dateparser.parse(str(val)).date()
        kwargs[col.name] = val
    return kwargs


# --------------------------------------------------------------------------- #
# Anmerkung 200 — ein Verweis zeigt auf EIGENES, oder er kommt nicht an
# --------------------------------------------------------------------------- #
# Der Import schreibt `user_id` auf den anmeldenden Nutzer um und war damit
# scheinbar sicher. Nur trägt eine Zeile mehr Verweise als ihren Besitzer:
# `metrics` und `event_entity_links` haben gar kein `user_id` und behielten die
# `event_id` aus der Datei, `media_refs` bekam einen neuen Besitzer und zeigte
# weiter auf ein fremdes Ereignis, `baseline_locations` auf einen fremden Ort.
# Eine von Hand geschriebene Datei konnte so an FREMDE Ereignisse anhängen —
# und über `location_id` wäre der Name eines fremden Ortes im eigenen
# Zeitstrahl gelandet.
#
# **Die Prüfung ist deshalb allgemein und nicht auf die beiden gemeldeten
# Tabellen gemünzt** (die wiederkehrende Falle: eine Regel, die nach ihrem
# ersten Anwendungsfall benannt ist, wird beim zweiten nicht gesucht). Gefragt
# wird das Schema: JEDER Fremdschlüssel auf eine nutzergebundene Tabelle muss
# auf eine Zeile dieses Nutzers zeigen. Eine neue Tabelle mit einem neuen
# Verweis ist damit von sich aus mitgeprüft.
#
# Ein echtes Backup verletzt das nie — es bringt alle Zeilen mit, auf die es
# sich beruft. Wer die Bedingung verletzt, hat die Datei geschrieben.
def _user_scoped_refs(model) -> list[tuple[str, str]]:
    """(Spalte, Zieltabelle) je Fremdschlüssel auf eine nutzergebundene Tabelle.

    `user_id` selbst steht nicht darunter: `users` trägt keine `user_id`, und
    die Spalte wird ohnehin überschrieben."""
    refs: list[tuple[str, str]] = []
    for col in model.__table__.columns:
        for fk in col.foreign_keys:
            if "user_id" in fk.column.table.columns:
                refs.append((col.name, fk.column.table.name))
    return refs


class _OwnRows:
    """Welche Zeilen darf diese Datei ansprechen? Je Tabelle einmal beantwortet.

    Zwei Herkünfte, und die zweite ist der Grund, warum das eine Klasse ist und
    keine Abfrage:

    * **Was schon in der Datenbank steht** und mir gehört (Re-Import, Umzug auf
      eine Instanz, die Teile davon schon hat).
    * **Was diese Datei selbst mitbringt.** Ein Tages-Kind verweist auf sein
      Eltern-Ereignis, und beide stehen in derselben Datei — in der Reihenfolge,
      in der die Datenbank sie ausgelesen hat, also nicht verlässlich Eltern
      zuerst. Zählte nur der Stand VOR dem Lauf, verlöre ein völlig gültiges
      Backup seine Kinder. **Eine Prüfung, die Angriffe abwehrt und dabei den
      Normalfall beschädigt, wird beim ersten Fehlalarm wieder ausgebaut** —
      der Wächter dazu (`test_own_export_still_restores_completely`) hat genau
      diesen Fall beim ersten Lauf gefunden.

    Die zweite Herkunft zählt **nur für Kennungen, die es noch nicht gibt**.
    Sonst wäre sie das Schlupfloch, das die ganze Prüfung aufhebt: eine Datei,
    die die Kennung eines FREMDEN Ereignisses in ihrem `events`-Block nennt,
    bekäme sie als „versprochen" gutgeschrieben — importiert würde die Zeile
    nie (sie existiert ja), aber jeder Verweis darauf ginge durch.
    """

    def __init__(self, db: Session, user_id: str, payload: dict,
                 promised_from: list[tuple[str, type]]) -> None:
        self._db, self._user_id = db, user_id
        self._cache: dict[str, set[str]] = {}
        for key, model in promised_from:
            ids = {r["id"] for r in payload.get(key, []) if r.get("id")}
            if ids:
                table = model.__table__.name
                self._promise(table, ids)

    def _ids(self, table: str) -> set[str]:
        if table not in self._cache:
            t = Base.metadata.tables[table]
            self._cache[table] = set(self._db.execute(
                select(t.c.id).where(t.c.user_id == self._user_id)).scalars())
        return self._cache[table]

    def _promise(self, table: str, ids: set[str]) -> None:
        """Nimmt die Kennungen auf, die dieser Lauf ANLEGEN wird — also alle,
        die es noch nicht gibt. Was es schon gibt, entscheidet die Datenbank."""
        t = Base.metadata.tables[table]
        known = set(self._db.execute(select(t.c.id).where(t.c.id.in_(ids))).scalars())
        self._ids(table).update(ids - known)

    def owns(self, table: str, value) -> bool:
        return value in self._ids(table)

    def revoke(self, model, row_id) -> None:
        """Nimmt ein Versprechen zurück, wenn die Zeile doch nicht ankommt.

        Sonst zeigte ein Kind auf ein Eltern-Ereignis, das der Lauf gerade
        verworfen hat — ein Verweis ins Leere, auf PostgreSQL das Ende des
        ganzen Imports."""
        self._ids(model.__table__.name).discard(row_id)


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
    # F20: Die Wohnort-Zeiträume sind Lebensdatenbank — eine Zeile, von Hand
    # eingetragen, aus nichts wiederherstellbar. Bis hierher fehlten sie im
    # Export: eine Sicherung, die vollständig AUSSIEHT und die einzige
    # handgepflegte Tabelle auslässt. `exclude_source` gilt für sie nicht, sie
    # haben keine Quelle — sie sind selbst die Quelle.
    baselines = _loaded("Wohnorte", db.query(BaselineLocation)
                        .filter(BaselineLocation.user_id == user.id).all())
    # **Anmerkung 199 — die zweite Hälfte des Wetters.** `metrics` (Wetter am
    # Ereignis) stand hier seit jeher, `day_metrics` (dasselbe Wetter am
    # Wohnort-Tag) nie. Beide sind Schicht 4 und beide wiederbeschaffbar — aber
    # eine Sicherung, die die eine Hälfte mitnimmt und die andere auslässt,
    # trifft keine Entscheidung, sie hat eine übersehen. Die Zeile hängt am
    # KONTO und an keinem Ereignis; `exclude_source` gilt für sie nicht, weil
    # ihre Quelle immer die Anreicherung ist.
    day_metrics = _loaded("Tageswerte", db.query(DayMetric)
                          .filter(DayMetric.user_id == user.id).all())
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
    # Anmerkung 139: Die Fotopunkte hatten hier bis 0.39 einen eigenen Block —
    # sie hingen an keinem Ereignis und wären sonst still aus dem Backup
    # gefallen. Seit sie EREIGNISSE sind, deckt `events` sie ab. Ein zweiter
    # Block wäre dieselbe Zeile zweimal im Export.
    _loaded("Verknüpfungen", links)
    # F15/Anmerkung 57: Ab hier ist der JSON-Export KEIN vollständiges Backup
    # mehr. Bilddateien passen nicht hinein; ihre Metadaten schon. Wer das
    # nicht weiß, verliert seine Fotos im Vertrauen auf eine Datei, die
    # vollständig aussieht — deshalb steht es im Export selbst, nicht nur in
    # der Doku. Das schließt A29 (ZIP-Export mit Dateien) später sauber ab.
    uploads = sum(1 for m in media if m.provider == "local")
    total = sum(len(x) for x in (fragments, locations, entities, events,
                                 links, media, metrics, tracks, baselines,
                                 day_metrics))
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
        # Neuer Schlüssel, aber KEINE neue Export-Version: der Import liest
        # jeden Block mit `payload.get(key, [])`, ein älterer Export bringt
        # den Schlüssel eben nicht mit. Eine Versionsnummer hochzuzählen
        # hieße „ab hier inkompatibel", und das ist es nicht.
        "baseline_locations": [_row_to_dict(x) for x in baselines],
        # Ebenfalls ein neuer Schlüssel ohne neue Export-Version, aus demselben
        # Grund wie darüber: der Import liest jeden Block mit `get(key, [])`.
        "day_metrics": [_row_to_dict(x) for x in day_metrics],
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

    WELCHE Tabellen und in welcher Reihenfolge, steht in `app.wipe` — dieselbe
    Liste, die der Admin-Weg liest.
    """
    if not is_delete_word(confirm):
        raise HTTPException(
            400, "Zum Bestätigen bitte LÖSCHEN eingeben — das lässt sich nicht rückgängig machen.")

    events = db.query(Event).filter(Event.user_id == user.id).count()
    doomed = media_svc.list_uploads_for_user(db, user.id)

    log.warning("Eigene Daten löschen: beginne (%d Events, %d Bilddateien, user=%s)",
                events, len(doomed), user.email or user.id)
    deleted = wipe_user_rows(db, user.id, log)
    db.commit()
    files = media_svc.purge_files(doomed)

    log.warning("Eigene Daten gelöscht: %d Zeilen, %d Bilddateien (user=%s)",
                sum(deleted.values()), files, user.email or user.id)
    return {"deleted": deleted, "total": sum(deleted.values()), "media_files": files}


def _day_metric_keys(db: Session, user_id: str) -> set[tuple[str, str]]:
    """(Tag, Kennzahl) der schon vorhandenen Tageswerte — als ISO-Text.

    Als Text und nicht als `date`, weil die Gegenseite aus dem JSON kommt und
    dort ein Tag „1998-07-04" heißt. Beide Seiten auf dieselbe Form zu bringen
    ist die halbe Arbeit an einem Vergleich; sie hier zu machen heißt, dass der
    Aufrufer sie nicht ein zweites Mal anders macht.
    """
    return {(d.isoformat() if hasattr(d, "isoformat") else str(d)[:10], k)
            for d, k in db.query(DayMetric.day, DayMetric.key)
            .filter(DayMetric.user_id == user_id).all()}


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
        # Nach `locations`: die Zeile zeigt per Fremdschlüssel auf einen Ort.
        ("baseline_locations", BaselineLocation, True),
        # Anmerkung 199: hängt nur am Konto, kann also überall stehen.
        ("day_metrics", DayMetric, True),
    ]
    imported: dict[str, int] = {}
    skipped = 0
    skipped_foreign = 0
    # Anmerkung 200: Nur die nutzergebundenen Blöcke versprechen etwas — ihre
    # Zeilen werden per `has_user` auf den anmeldenden Nutzer umgeschrieben und
    # gehören ihm damit per Konstruktion. `metrics` und `event_entity_links`
    # haben keinen Besitzer und können deshalb auch keinen zusagen.
    own = _OwnRows(db, user.id, payload,
                   [(key, model) for key, model, has_user in plan if has_user])
    # Der Import prüft jede Zeile einzeln gegen die Datenbank (Idempotenz) —
    # bei einem vollen Backup sind das zehntausende Abfragen. Ohne Zwischenstand
    # ist der Unterschied zwischen „arbeitet" und „hängt" nicht zu sehen.
    rows_total = sum(len(payload.get(key, [])) for key, _, _ in plan)
    progress = Progress(log, "Daten-Import", unit="Zeilen")
    progress.start(rows_total, note=f"user={user.email or user.id}")
    seen = 0
    for key, model, has_user in plan:
        count = 0
        # **Die Kennung allein genügt nicht, wo eine FACHLICHE Eindeutigkeit
        # zugesagt ist** (Anmerkung 199). `day_metrics` ist die einzige
        # exportierte Tabelle mit einer solchen Zusage (`ux_day_metrics_key`
        # über Konto, Tag, Kennzahl) — und sie greift hier besonders leicht:
        # das Tageswetter entsteht bei JEDEM Anreicherungslauf neu, ein Konto
        # trägt dieselbe Aussage also längst unter einer anderen Kennung. Ohne
        # diesen Griff bräche der GANZE Import an einer Zeile ab, die nichts
        # Neues sagt — und zwar erst beim Commit, also nachdem jede andere
        # Tabelle schon als „importiert" gezählt war.
        taken = _day_metric_keys(db, user.id) if key == "day_metrics" else None
        refs = _user_scoped_refs(model)          # Anmerkung 200
        for row in payload.get(key, []):
            seen += 1
            progress.beat(seen, rows_total - seen, note=key)
            if not row.get("id") or db.get(model, row["id"]) is not None:
                skipped += 1
                continue
            if taken is not None:
                natural = (str(row.get("day") or "")[:10], row.get("key"))
                if natural in taken:
                    skipped += 1
                    continue
                taken.add(natural)
            kwargs = _dict_to_kwargs(model, row)
            if has_user:
                kwargs["user_id"] = user.id
            # Anmerkung 200: kein Verweis auf fremde Zeilen. Verworfen wird die
            # ganze Zeile und nicht nur der Verweis — ein Messwert ohne sein
            # Ereignis ist keine gerettete Hälfte, sondern eine Zeile ohne
            # Aussage, und ein Ereignis ohne den fremden Ort hätte den Import
            # stillschweigend zu einer Teil-Wiederherstellung gemacht.
            foreign = [c for c, table in refs
                       if kwargs.get(c) is not None and not own.owns(table, kwargs[c])]
            if foreign:
                skipped_foreign += 1
                if has_user:
                    own.revoke(model, row["id"])
                log.warning("Import: %s %s übersprungen — %s zeigt auf fremde Daten",
                            key, row["id"], ", ".join(sorted(foreign)))
                continue
            db.add(model(**kwargs))
            count += 1
        db.flush()
        imported[key] = count
        if payload.get(key):
            log.info("Import: %s — %d neu, %d schon vorhanden",
                     key, count, len(payload[key]) - count)
    db.commit()
    progress.finish(f"{sum(imported.values())} neu, {skipped} übersprungen"
                    + (f", {skipped_foreign} mit fremdem Verweis" if skipped_foreign else ""))
    if skipped_foreign:
        log.warning("Import: %d Zeilen verwiesen auf fremde Daten und wurden "
                    "verworfen (user=%s)", skipped_foreign, user.email or user.id)
    # `skipped_foreign` steht auch dann in der Antwort, wenn es 0 ist: eine
    # Zahl, die nur bei Ärger auftaucht, prüft niemand — und die Oberfläche
    # könnte den Fall nicht anzeigen, ohne das Feld vorher zu kennen.
    return {"imported": imported, "skipped_existing": skipped,
            "skipped_foreign": skipped_foreign,
            "total": sum(imported.values())}
