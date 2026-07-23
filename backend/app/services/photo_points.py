"""A45 — wo fotografiert wurde. Ein Punkt je verortetem Foto.

Gemeldet aus dem Betrieb: Immich hinterließ einen Sammeleintrag „London, 1200
Bilder", und auf der Karte war das **ein** Punkt. Die 1200 Bilder wissen
einzeln, wo sie entstanden sind — Life-Dash hat es nur nie aufgeschrieben.

**Warum eine eigene Tabelle.** `MediaRef` ist auf zwölf Bilder je Tag gedeckelt
(`immich_link.MAX_PER_EVENT`), und das ist richtig: es beantwortet „welche
Bilder stehen neben diesem Eintrag?", und eine Fotoleiste mit 1200 Vorschauen
ist keine. Hier lautet die Frage „wo wurde fotografiert?", und da ist jede
Auslassung ein Loch in der Karte. Zwei Fragen, zwei Deckelungen — zusammen in
einer Tabelle wären es zwei Bedeutungen in derselben Zeile (Anmerkung 106).

**Schicht 4.** Alles hier steht auch in Immich; verwerfen und neu berechnen ist
jederzeit erlaubt. Die Medien-Invariante (Anmerkung 57) bleibt unberührt, weil
hier grundsätzlich keine hochgeladenen Dateien landen.

**Der Ort kommt aus `exifInfo`, nicht aus Nominatim** (Anmerkung 109): Immich
hat schon rückwärts geokodiert, das kostet keinen fremden Abruf und ist
stabiler als ein Koordinatenraster, dessen Zellenrand mitten durch eine Stadt
läuft.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import PhotoPoint
from app.services import immich as api
from app.services.immich_link import PROVIDER

log = logging.getLogger("lifedash.immich")

# Wie viele Punkte höchstens in EINE Antwort gehen. Nicht die Bibliothek ist
# die Grenze, sondern der Browser: 50.000 Marker sind kein Kartenbild mehr,
# sondern eine blaue Fläche. Überschritten wird das nie stillschweigend —
# `points_for` sagt, dass es mehr gibt, und der Aufrufer verdichtet
# (Anmerkung 110: was eine Ansicht nicht zeigen kann, muss sie sagen).
MAX_POINTS = 5000


# A47 — Ortsteil eines Fotos.
#
# `exifInfo` hat kein Feld dafür: Immichs Rückwärts-Geokodierung liefert
# city/state/country und sonst nichts. Geraten wird trotzdem nicht — gefragt
# wird der EIGENE Ortsbestand, der seine Roh-Bausteine seit Anmerkung 110
# aufbewahrt. Ein Foto, das 200 m von einem bekannten Ort entstand, liegt im
# selben Ortsteil; eines mitten in der Wildnis bekommt keinen und landet in
# einer eigenen, benannten Gruppe.
#
# Und es kostet keinen Abruf: Anmerkung 100 verlangt, dass ein ausgehender
# Abruf einer gespeicherten eigenen Tatsache dient — hier geht gar keiner raus.
DISTRICT_RADIUS_KM = 0.6


def district_index(db: Session, user_id: str) -> list[tuple[float, float, str]]:
    """(lat, lng, Ortsteil) aller eigenen Orte, die einen kennen.

    Einmal je Lauf geladen, nicht je Foto: bei 20.000 Bildern wären das sonst
    20.000 Abfragen für eine Frage, deren Antwort sich nicht ändert.
    """
    from app.models import Location
    from app.sqlutil import DISTRICT_KEYS

    out: list[tuple[float, float, str]] = []
    rows = (db.query(Location)
            .filter(Location.user_id == user_id,
                    Location.lat.isnot(None), Location.address.isnot(None))
            .all())
    for loc in rows:
        address = loc.address or {}
        for key in DISTRICT_KEYS:
            value = (address.get(key) or "").strip()
            if value:
                out.append((loc.lat, loc.lng, value))
                break
    return out


def _district(geo: tuple[float, float],
              index: list[tuple[float, float, str]]) -> str | None:
    """Der Ortsteil des nächstgelegenen eigenen Ortes — oder None."""
    if not index:
        return None
    best, best_km = None, DISTRICT_RADIUS_KM
    for lat, lng, name in index:
        km = api._km(geo, (lat, lng))
        if km < best_km:
            best, best_km = name, km
    return best


# Warum ein Foto KEINEN Punkt bekommen hat — in der Reihenfolge, in der
# geprüft wird. Gezählt wird der ERSTE Grund, damit die Zahlen sich zur
# gelesenen Menge addieren statt sie zu überzeichnen: ein fremdes Foto ohne
# Koordinaten ist ein Ausschluss, nicht zwei.
DROP_REASONS = {
    "foreign": "{n} von jemand anderem",
    "hidden": "{n} nicht im Immich-Zeitstrahl (archiviert, versteckt oder gesperrt)",
    "no_geo": "{n} ohne Koordinaten",
    "no_time": "{n} ohne verwertbare Aufnahmezeit",
    "no_id": "{n} ohne Kennung",
}


def drop_reasons(report: dict) -> list[str]:
    """Die Ausschlussgründe als lesbare Teilsätze, der größte zuerst.

    **Die Summe allein ist keine Auskunft.** „2016 Fotos gelesen, 17 neu
    verortet" lässt genau die Frage offen, die man beim Lesen stellt: Warum die
    anderen 1999? Ob die Bibliothek schlicht kein GPS trägt oder ob der
    API-Schlüssel auf ein fremdes Konto zeigt, sind zwei völlig verschiedene
    Lagen — und sie sahen bis hier identisch aus. Das ist der wiederkehrende
    Defekt dieses Projekts: nicht Kaputtheit, sondern Stille (Anmerkung 110).
    """
    dropped = report.get("dropped") or {}
    out = [(n, DROP_REASONS[key].format(n=n))
           for key, n in dropped.items() if n and key in DROP_REASONS]
    out.sort(key=lambda pair: -pair[0])
    return [text for _n, text in out]


def upsert_assets(db: Session, user_id: str, assets: list[dict],
                  my_id: str | None, report: dict | None = None) -> tuple[int, int]:
    """Trägt die verorteten eigenen Fotos ein. Gibt (neu, aktualisiert) zurück.

    Dieselben drei Filter wie `immich_source.cluster_assets` — und aus denselben
    Gründen (Anmerkung 107): nur mit Koordinaten (ein Bildschirmfoto kann
    keinen Ort erfinden), nur eigene (fremde Urlaubsfotos aus geteilten Alben
    haben sehr wohl GPS), nur im Zeitstrahl (Archiviertes und Gesperrtes hat
    der Nutzer bewusst herausgenommen).

    Idempotent über `asset_id`: ein zweiter Lauf findet dasselbe Foto wieder.
    Aktualisiert wird trotzdem — in Immich lässt sich ein Ort nachtragen, und
    dann ist der alte Punkt schlicht falsch.

    `report` nimmt auf, was dabei liegen blieb — dieselbe Bauform wie bei
    `immich_source.scan_year`. Die drei Filter sind hier bewusst EINZELN
    geprüft statt in einem `or`: verodert lässt sich nicht mehr sagen, welcher
    von ihnen zugeschlagen hat, und genau das ist die Frage.
    """
    districts = district_index(db, user_id)
    dropped = dict.fromkeys(DROP_REASONS, 0)
    wanted: dict[str, dict] = {}
    for asset in assets:
        if not api.is_own(asset, my_id):
            dropped["foreign"] += 1
            continue
        if not api.is_in_timeline(asset):
            dropped["hidden"] += 1
            continue
        geo = api.asset_geo(asset)
        if geo is None:
            dropped["no_geo"] += 1
            continue
        when = api.asset_time(asset)
        if when is None:
            dropped["no_time"] += 1
            continue
        asset_id = asset.get("id")
        if not asset_id:
            dropped["no_id"] += 1
            continue
        exif = asset.get("exifInfo") or {}
        wanted[asset_id] = {
            "taken_at": when, "lat": geo[0], "lng": geo[1],
            "district": _district(geo, districts),
            "city": (exif.get("city") or "").strip() or None,
            "state": (exif.get("state") or "").strip() or None,
            "country": api.asset_country(asset),
        }
    if report is not None:
        report["dropped"] = dropped
        report["kept"] = len(wanted)
        report["unchanged"] = 0
    if not wanted:
        return 0, 0

    # EINE Abfrage für alle vorhandenen statt einer je Foto: bei einem
    # Jahreslauf über 20.000 Bilder ist das der Unterschied zwischen Sekunden
    # und Minuten.
    existing = {p.asset_id: p for p in db.query(PhotoPoint).filter(
        PhotoPoint.user_id == user_id, PhotoPoint.provider == PROVIDER,
        PhotoPoint.asset_id.in_(list(wanted)))}

    added = changed = 0
    for asset_id, values in wanted.items():
        point = existing.get(asset_id)
        if point is None:
            db.add(PhotoPoint(user_id=user_id, provider=PROVIDER,
                              asset_id=asset_id, **values))
            added += 1
            continue
        if any(getattr(point, field) != value for field, value in values.items()):
            for field, value in values.items():
                setattr(point, field, value)
            changed += 1
    if report is not None:
        # **„Unverändert" ist die Zahl, die dem Lauf gefehlt hat.** Ohne sie
        # liest sich der zweite Lauf über dasselbe Jahr wie ein gescheiterter
        # erster: „2016 gelesen, 17 neu" — und die 800 Punkte, die längst da
        # sind, kommen im Satz nicht vor.
        report["unchanged"] = len(wanted) - added - changed
    return added, changed


def scan_year(db: Session, user, year: int, url: str, key: str,
              heartbeat=None, report: dict | None = None) -> tuple[int, int, int]:
    """Ein Jahr Immich → Fotopunkte. Gibt (gesehen, neu, aktualisiert) zurück.

    Jahresweise wie `immich_source.scan_year`, und aus demselben Grund: eine
    zwanzig Jahre alte Bibliothek in einem Zug ist kein Lauf, sondern ein
    Zeitlimit.

    `report` nimmt die Aufschlüsselung auf (siehe `upsert_assets`). Der
    Rückgabewert bleibt das Tripel: die Aufschlüsselung ist eine Auskunft über
    den Lauf, kein Ergebnis von ihm.
    """
    # Immer aufgeschlüsselt, auch wenn niemand danach fragt: das Protokoll
    # braucht die Zahlen genauso wie die Oberfläche, und zwei Wege zu einer
    # Auskunft laufen still auseinander (Anmerkung 106).
    report = report if report is not None else {}
    my_id = api.own_user_id(url, key)
    report["own_user_id"] = my_id
    if not my_id:
        # Ohne eigene Kennung ließe sich ein fremdes Foto nicht erkennen —
        # und ein geteiltes Album schriebe Punkte in die eigene Karte, an
        # denen man nie war. Lieber nichts (dieselbe Strenge wie `is_own`).
        log.warning("Immich nennt keine eigene Nutzerkennung — Fotopunkte "
                    "werden übersprungen")
        return 0, 0, 0
    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31, 23, 59, 59)
    assets = api.search_assets_paged(url, key, start, end, heartbeat=heartbeat)
    added, changed = upsert_assets(db, user.id, assets, my_id, report=report)
    report["seen"] = len(assets)
    log.info("Fotopunkte %d: %d Fotos gelesen, %d neu, %d aktualisiert, "
             "%d unverändert — ohne Punkt: %s", year, len(assets), added, changed,
             report.get("unchanged", 0),
             "; ".join(drop_reasons(report)) or "keins")
    return len(assets), added, changed


def scanned_years(user) -> set[int]:
    """Jahre, die schon einmal durchsucht wurden.

    **Der Unterschied zwischen „keine Fotos" und „nie nachgesehen"** — die
    Falle, die dieses Projekt inzwischen zum sechsten Mal stellt (F12
    `weather_rev`, A39-Leerstring, A42 „kein Artikel", P2.1-Grabstein,
    Anmerkung 114 `_name_defect`). Ohne diese Liste zeigte die Karte für 2004
    dasselbe wie für ein Jahr ohne Kamera: nichts, wortlos.

    Kein Schema: die Liste ist eine Notiz über einen Lauf, kein Datum über das
    Leben — sie gehört in die Einstellungen, nicht in die Lebensdatenbank.
    """
    raw = ((user.settings or {}).get("photo_points") or {}).get("years") or []
    return {int(y) for y in raw if str(y).isdigit() or isinstance(y, int)}


def mark_scanned(db: Session, user, year: int) -> None:
    """Merkt sich, dass dieses Jahr durchsucht wurde.

    `user.settings` ist eine JSON-Spalte: neu ZUWEISEN, nicht an Ort und
    Stelle ändern — SQLAlchemy bemerkt eine Mutation im Dict sonst nicht und
    schreibt nichts.
    """
    settings = dict(user.settings or {})
    block = dict(settings.get("photo_points") or {})
    block["years"] = sorted(scanned_years(user) | {int(year)})
    settings["photo_points"] = block
    user.settings = settings


def reset(db: Session, user_id: str) -> int:
    """Verwirft alle Fotopunkte dieses Kontos — Ableitung, jederzeit erlaubt."""
    count = (db.query(PhotoPoint)
             .filter(PhotoPoint.user_id == user_id).delete(synchronize_session=False))
    return count


def points_for(db: Session, user_id: str, start: datetime | None = None,
               end: datetime | None = None,
               limit: int | None = None) -> tuple[list[PhotoPoint], int]:
    """Punkte eines Zeitraums und die WAHRE Gesamtzahl.

    Beides zurückzugeben ist der Punkt: eine Liste, die stillschweigend bei
    5.000 aufhört, sieht auf der Karte aus wie die ganze Wahrheit
    (Anmerkung 110). Der Aufrufer muss den Unterschied nennen können.

    `limit=None` liest `MAX_POINTS` zur AUFRUFZEIT. Als Default-Argument wäre
    der Wert beim Import festgezurrt — die Konstante ließe sich dann weder in
    einem Test noch zur Laufzeit ändern, und beim Schreiben des Tests fiel
    genau das auf.

    **Und deckeln heißt hier NICHT abschneiden.** `ORDER BY taken_at LIMIT
    5000` liefert die 5.000 ÄLTESTEN — über eine Bibliothek von 2009 bis heute
    also die Jahre bis etwa 2016, und alles danach fehlt auf der Karte. Ein
    Reisejahr in der Mitte verschwindet damit vollständig, während die Karte
    voll aussieht. Gegriffen wird deshalb gleichmäßig über den Zeitraum: die
    Form der Antwort bleibt erhalten, jede Gegend kommt vor, und die genaue
    Zahl steht ohnehin in `total`.

    Das ist dieselbe Regel, die vierzig Zeilen weiter für die Vorschaubilder
    einer Gruppe schon gilt (`GROUP_THUMBS`, Anmerkung 111: „gleichmäßig über
    die Gruppe greifen statt vorne abschneiden"). Sie stand zweimal da und ist
    genau an der zweiten Stelle nicht angewandt worden — der Anmerkung-106-Fall
    in seiner leisesten Form.
    """
    if limit is None:
        limit = MAX_POINTS
    query = db.query(PhotoPoint).filter(PhotoPoint.user_id == user_id)
    if start is not None:
        query = query.filter(PhotoPoint.taken_at >= start)
    if end is not None:
        query = query.filter(PhotoPoint.taken_at <= end)
    total = query.count()
    if total <= limit:
        return query.order_by(PhotoPoint.taken_at).all(), total

    # Jede `step`-te Zeile in zeitlicher Reihenfolge. Die Nummerierung macht
    # die Datenbank (Fensterfunktion) — 8.000 Kennungen in ein `IN (…)` zu
    # legen wäre die Sorte Abfrage, die je nach SQLite-Übersetzung an einer
    # Parametergrenze zerbricht.
    step = -(-total // limit)          # aufgerundet: nie mehr als `limit`
    numbered = (query.with_entities(
        PhotoPoint.id.label("pid"),
        func.row_number().over(order_by=PhotoPoint.taken_at).label("rn"))
        .subquery())
    rows = (db.query(PhotoPoint)
            .join(numbered, numbered.c.pid == PhotoPoint.id)
            .filter((numbered.c.rn - 1) % step == 0)
            .order_by(PhotoPoint.taken_at)
            .limit(limit).all())
    return rows, total


def day_index(db: Session, user_id: str) -> dict[date, int]:
    """Wie viele Fotopunkte auf welchem Kalendertag liegen.

    Der Zeitstrahl braucht das, BEVOR er eine Seite baut: eine Zahl, die erst
    beim Aufklappen entsteht, ist keine, mit der man sich entscheidet.
    """
    from app.sqlutil import day_parts

    y, m, d = day_parts(PhotoPoint.taken_at)
    rows = (db.query(y, m, d, func.count(PhotoPoint.id))
            .filter(PhotoPoint.user_id == user_id)
            .group_by(y, m, d).all())
    return {date(int(a), int(b), int(c)): int(n) for a, b, c, n in rows}
