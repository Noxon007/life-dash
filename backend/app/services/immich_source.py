"""P2.1 Stufe 2 — Immich als EREIGNIS-Quelle, nicht nur als Bilderlieferant.

Stufe 1 (0.25.0) hängt Fotos an Ereignisse, die es schon gibt. Diese Stufe
dreht die Richtung um: aus den Fotos selbst entstehen Ereignisse — georef-
erenzierte eigene Fotos eines Tages an einem Ort werden zu einem Ereignis
(„34 Fotos in Detmold").

**Anmerkung 138: direkt bestätigt, wie ein Google-Besuch — nicht mehr als
Vorschlag in der Moderation.** Bis 0.39 lief das über einen Umweg
(„Vorschlag" → Moderation → Bestätigen), begründet mit Anmerkung 30 („nichts
bestätigt sich automatisch"). Der Umweg widersprach sich mit dem eigenen
Vorbild: ein Google-Besuch — dieselbe Sorte Beleg, dieselbe Automatik beim
Import — wird seit jeher SOFORT bestätigt (`tracks.py`, `confirmed_by=
"import"`). Zwei Konnektoren mit derselben Beleglage, zwei verschiedene
Antworten auf „wird das Ereignis?" — das war Anmerkung 106 in genau dem Code,
der sie an anderer Stelle zitiert. Jetzt gilt für beide dieselbe Regel:
ein Fotocluster ist so viel Beleg wie ein GPS-Stopp, also wird er genauso
behandelt. Die Sicherheitsmarge bleibt woanders erhalten — `MIN_CLUSTER_
PHOTOS` hält Einzelbilder draußen, die Vorschau (`/api/immich/preview`) zeigt
vor jedem Lauf, was er anlegen würde, und `Event.external_id` verhindert eine
Wiederauferstehung nach dem Löschen (siehe `create_confirmed_visits`).

**Alben sind komplett raus** (waren P2.1 Stufe 3, Anmerkung 116). Ein Album
war ohnehin schon standardmäßig aus und ein mehrdeutigerer Fall als ein
Tagescluster — eine Reise ist eine größere Behauptung als „hier waren an
diesem Tag Fotos". Statt sie auch zu automatisieren, wurde der ganze Zweig
gestrichen: **Reisen legt der Mensch an, die Fotos hängen sich daran**
(Stufe 1 tut das bereits über „An Einträge hängen").

Die teure Hälfte ist nicht das Clustern, sondern jeder Fall, in dem Life-Dash
den Tag schon kennt (Anmerkung 107). Die Antworten stehen weiter unten bei
`_proposed_slots`/`_owned_slots` und `create_confirmed_visits`.

**Identität ist der PLATZ, nicht der Inhalt.** `external_id` trägt
`immich:day:<datum>:<ort>` — niemals einen Hash über die Asset-IDs. Ein
nachgeladenes Foto machte aus demselben Tag sonst ein zweites Ereignis.
Dieselbe Überlegung wie bei A39s Gruppenvertreter: stabil schlägt clever.

**Kein Schema.** Der Grabstein gegen eine Wiederauferstehung nach dem Löschen
existiert bereits: jedes Ereignis entsteht aus einem `Fragment`, Fragmente
werden nie automatisch gelöscht, und `_TEXT_SOURCES` hält `immich` aus der
KI-Neuberechnung heraus. Gefragt wird deshalb nach den FRAGMENTEN — „habe ich
diesen Platz je angelegt?" —, nicht nach den Ereignissen, denn ein manuell
gelöschtes Ereignis nimmt nur die Ereigniszeile mit.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models import (ConfirmState, DatePrecision, Event, Fragment,
                        FragmentStatus, Location, MediaRef, Source)
from app.services import immich as api
from app.services.immich_link import PROVIDER

log = logging.getLogger("lifedash.immich")

SLOT_PREFIX = "immich:"
# `Event.external_id` ist String(64). „immich:day:" + Datum + ":" sind 22
# Zeichen, für den Ort bleiben 42. Abgeschnitten wird DETERMINISTISCH — ein
# Platz, der sich beim zweiten Lauf anders abkürzt, wäre kein Platz mehr.
_EXTERNAL_ID_MAX = 64
# Ab wie vielen Fotos ein Tag/Ort ein Ereignis wird. Zwei Bilder sind ein
# Schnappschuss, kein Ereignis — die Zahl hält jetzt die Lebensdatenbank
# sauber, nicht mehr nur eine Warteschlange lesbar (Anmerkung 138: seit dem
# Wegfall der Moderation ist sie die einzige verbliebene Bremse).
MIN_CLUSTER_PHOTOS = 4
# Spannt ein Cluster nur wenige Stunden, ist der Zeitpunkt eine Aussage;
# über den Tag verteilt ist es der Tag (Kap. 3.1: Genauigkeit nie
# überzeichnen).
EXACT_MAX_HOURS = 4


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit]


def slot_day(day: date, place: str) -> str:
    head = f"{SLOT_PREFIX}day:{day.isoformat()}:"
    return head + _short(place, _EXTERNAL_ID_MAX - len(head))


@dataclass
class Proposal:
    """Ein Tagescluster, bevor er existiert — die Vorschau zeigt genau das."""

    slot: str
    title: str
    start: datetime
    end: datetime
    precision: DatePrecision
    place: str | None = None
    country: str | None = None
    photos: int = 0
    lat: float | None = None
    lng: float | None = None

    def as_dict(self) -> dict:
        return {
            "slot": self.slot, "title": self.title,
            "start": self.start.isoformat(), "end": self.end.isoformat(),
            "precision": self.precision.value, "place": self.place,
            "photos": self.photos,
        }


# --------------------------------------------------------------------------- #
# Schon bekannte Plätze (Anmerkung 107)
# --------------------------------------------------------------------------- #
def _proposed_slots(db: Session, user_id: str) -> set[str]:
    """Jeder Platz, der je angelegt wurde — **auch die gelöschten**.

    Der wichtigste Fall: ein gelöschtes Ereignis darf nicht wiederkommen. Das
    Löschen nimmt nur die Ereigniszeile mit, das Fragment (der Grabstein)
    bleibt — genau deshalb wird hier das Fragment gefragt, nicht das Ereignis.

    Das ist das vierte Auftreten derselben Falle: F12 `weather_rev`, A39s
    Leerstring, A42s „kein Artikel", jetzt hier. Wer eine Quelle wiederholt
    befragt, muss auch das ERGEBNISLOSE Ergebnis aufschreiben.
    """
    rows = (db.query(Fragment.raw_text)
            .filter(Fragment.user_id == user_id, Fragment.source == Source.immich)
            .all())
    slots: set[str] = set()
    for (raw,) in rows:
        try:
            slots.add(json.loads(raw)["slot"])
        except (ValueError, KeyError, TypeError):
            continue
    return slots


def _owned_slots(db: Session, user_id: str) -> set[str]:
    """Plätze, zu denen es ein Ereignis GIBT.

    Einmal angelegt und dann umbenannt oder umdatiert, bleibt das Ereignis
    über `external_id` erkennbar und ab da unantastbar — ein zweiter Lauf legt
    denselben Platz nicht doppelt an.
    """
    rows = (db.query(Event.external_id)
            .filter(Event.user_id == user_id,
                    Event.external_id.like(f"{SLOT_PREFIX}%")).all())
    return {r[0] for r in rows if r[0]}


def _days_with_owning_events(db: Session, user_id: str,
                             start: datetime, end: datetime) -> set[date]:
    """Tage, an denen ein Ereignis bereits Immich-Fotos BESITZT — Fall (1).

    Nicht „Tage mit Ereignissen": Es geht nicht um Besuche, sondern darum,
    dass die Fotos schon ein Zuhause haben. Ein selbst erfasstes „Konzert"
    mit angehängten Bildern braucht kein zweites Ereignis „12 Fotos in Köln";
    ein Tag, an dem nur ein Google-Besuch steht, sehr wohl (Fall 7).
    """
    rows = (db.query(Event.date_start)
            .join(MediaRef, MediaRef.event_id == Event.id)
            .filter(Event.user_id == user_id,
                    Event.date_start.isnot(None),
                    Event.date_start >= start, Event.date_start <= end,
                    MediaRef.provider == PROVIDER).all())
    return {r[0].date() for r in rows if r[0]}


# --------------------------------------------------------------------------- #
# Erkennen
# --------------------------------------------------------------------------- #
def cluster_assets(assets: list[dict], my_id: str | None) -> list[Proposal]:
    """Eigene, georeferenzierte, im Zeitstrahl sichtbare Fotos → (Tag, Ort).

    Drei Filter, und jeder ersetzt ein Stück der Unterdrückungsregel, die der
    Autor in Anmerkung 107 gekippt hat:

    * **nur mit Koordinaten** — ein weitergeleitetes WhatsApp-Bild, ein
      Bildschirmfoto, ein Download trägt kein EXIF-GPS und kann deshalb
      keinen Ort erfinden. Es bleibt, was es heute ist: Anreicherung am Tag.
    * **nur eigene** (`ownerId`) — die eigentliche Gefahr waren nie
      Screenshots, sondern **geteilte Alben**: fremde Urlaubsfotos haben sehr
      wohl GPS und erfänden stillschweigend einen Tag.
    * **nur im Zeitstrahl** — was im Archiv oder im gesperrten Ordner liegt,
      hat der Nutzer bewusst herausgenommen.

    Gruppiert wird nach Immichs eigenem Ortsnamen, nicht nach einem
    Koordinatenraster: eine Rasterzelle kann mitten durch eine Stadt laufen
    und denselben Tag zweimal anlegen.
    """
    buckets: dict[tuple[date, str], list[dict]] = defaultdict(list)
    for asset in assets:
        if not api.is_own(asset, my_id) or not api.is_in_timeline(asset):
            continue
        if api.asset_geo(asset) is None:
            continue
        when = api.asset_time(asset)
        place = api.asset_place(asset)
        if when is None or not place:
            continue
        buckets[(when.date(), place)].append(asset)

    out: list[Proposal] = []
    for (day, place), group in sorted(buckets.items()):
        if len(group) < MIN_CLUSTER_PHOTOS:
            continue
        times = sorted(t for t in (api.asset_time(a) for a in group) if t)
        geos = [g for g in (api.asset_geo(a) for a in group) if g]
        span_h = (times[-1] - times[0]).total_seconds() / 3600.0
        exact = span_h <= EXACT_MAX_HOURS
        out.append(Proposal(
            slot=slot_day(day, place),
            title=f"{len(group)} Fotos in {place}"[:255],
            start=times[0] if exact else datetime(day.year, day.month, day.day),
            end=times[-1] if exact else datetime(day.year, day.month, day.day,
                                                 23, 59, 59),
            precision=DatePrecision.exact if exact else DatePrecision.day,
            place=place, country=api.asset_country(group[0]),
            photos=len(group),
            lat=round(sum(g[0] for g in geos) / len(geos), 6) if geos else None,
            lng=round(sum(g[1] for g in geos) / len(geos), 6) if geos else None,
        ))
    return out


# --------------------------------------------------------------------------- #
# Vorschau (P2.5-Muster) und Anlegen
# --------------------------------------------------------------------------- #
def scan_year(db: Session, user, year: int, url: str, key: str,
              heartbeat=None, budget_s: float | None = None,
              report: dict | None = None) -> list[Proposal]:
    """Was dieses Jahr an Tagesclustern ergäbe — **ohne irgendetwas anzulegen**.

    Genau dieselbe Funktion füttert die Vorschau und den Lauf. Zwei getrennte
    Wege wären zwei Regeln, und die widersprechen sich still (Anmerkung 106).

    `budget_s` deckelt die Zeit, `report` nimmt auf, was dabei gemessen wurde.
    Beides braucht nur die **Vorschau** (Anmerkung 113): sie hängt an einer
    einzelnen HTTP-Anfrage, und dazwischen steht bei einer Fernnutzung ein
    umgekehrter Vertreter mit einer festen Geduld — gemeldet als **502 Bad
    Gateway**. Der Job braucht das nicht: er läuft im Hintergrund, hat einen
    Herzschlag und niemanden, der auf eine Antwort wartet.
    """
    began = time.monotonic()

    def _note(**kw) -> None:
        if report is not None:
            report.update(kw)

    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31, 23, 59, 59)

    # Das eigene Wissen steht am ANFANG, nicht am Ende (Anmerkung 113): zwei
    # billige Abfragen entscheiden, welche Cluster überhaupt zählen, bevor die
    # teure Foto-Abfrage läuft.
    known = _proposed_slots(db, user.id) | _owned_slots(db, user.id)
    housed = _days_with_owning_events(db, user.id, start, end)

    my_id = api.own_user_id(url, key)
    if not my_id:
        log.warning("Immich nennt keine eigene Nutzerkennung — Fotocluster "
                    "werden übersprungen (fremde Fotos wären nicht erkennbar)")

    assets = api.search_assets_paged(url, key, start, end, heartbeat=heartbeat)
    clusters = cluster_assets(assets, my_id)
    log.info("Immich %d: %d Fotos gelesen, %d Tagescluster", year,
             len(assets), len(clusters))
    _note(seconds=round(time.monotonic() - began, 1))

    # Fall (1): Fotos, die schon ein Zuhause haben, brauchen kein Ereignis.
    clusters = [c for c in clusters if c.start.date() not in housed]

    # Fälle (2)/(3)/(4): schon angelegt oder gelöscht — der Platz ist vergeben.
    return [p for p in clusters if p.slot not in known]


def create_confirmed_visits(db: Session, user, proposals: list[Proposal]) -> int:
    """Legt Ereignisse an — direkt bestätigt, wie ein Google-Besuch (Anm. 138).

    Je ein `Fragment` (Grabstein) + ein sofort `confirmed`-es Ereignis. Der
    Grabstein bleibt auch nach einer manuellen Löschung stehen: ohne ihn
    fände `scan_year` denselben Platz beim nächsten Lauf wieder frei und legte
    ihn erneut an — eine Wiederauferstehung, die eine bewusste Löschung
    rückgängig macht.

    Fall (6): Die Fotos werden hier **nicht** umgehängt. Das Ereignis ZEIGT
    die Bilder seines Fensters (sie hängen weiter am Tag, F18/Anmerkung 106).
    """
    created = 0
    for prop in proposals:
        fragment = Fragment(
            user_id=user.id,
            raw_text=json.dumps({
                "type": "immich_source", "slot": prop.slot,
                "title": prop.title, "photos": prop.photos,
                "place": prop.place,
                "range": [prop.start.isoformat(), prop.end.isoformat()],
            }, ensure_ascii=False),
            source=Source.immich,
            status=FragmentStatus.processed,
        )
        db.add(fragment)
        db.flush()
        now = datetime.now(timezone.utc)
        db.add(Event(
            user_id=user.id,
            title=prop.title,
            description=_describe(prop),
            date_start=prop.start, date_end=prop.end,
            date_precision=prop.precision,
            category="event",
            # Foto-GPS ist ein Beleg, kein Geständnis — dieselbe mittelhohe
            # Zuversicht wie bei einem Google-Besuch (`tracks.py`).
            confidence=0.6,
            confirmed=ConfirmState.confirmed,
            confirmed_at=now,
            confirmed_by="import",
            source=Source.immich,
            location=_location_for(db, user, prop),
            origin_fragment=fragment,
            external_id=prop.slot,
        ))
        created += 1
    return created


def _describe(prop: Proposal) -> str:
    bits = [f"{prop.photos} Fotos aus Immich"]
    if prop.place:
        bits.append(f"in {prop.place}")
    return " ".join(bits)


def _location_for(db: Session, user, prop: Proposal) -> Location | None:
    """Ort des Ereignisses — vorhandene Orte wiederverwenden, sonst anlegen.

    `external_ref` bekommt einen eigenen Namensraum (`immich:place:…`), damit
    ein zweiter Lauf denselben Ort findet, statt Detmold ein zweites Mal
    anzulegen — dieselbe Idempotenz wie beim Timeline-Import.
    """
    if not prop.place or prop.lat is None or prop.lng is None:
        return None
    # Anmerkung 105 hielt fest, dass der richtige Schlüssel `(Stadt, Land)`
    # ist, und ließ ihn für die vorhandenen Städte bewusst liegen. Hier wird
    # der Schlüssel NEU vergeben — dann gleich richtig, sonst landet
    # Springfield/Massachusetts auf den Koordinaten von Springfield/Illinois.
    ref = _short(f"{SLOT_PREFIX}place:{prop.place}|{prop.country or '?'}", 255)
    existing = (db.query(Location)
                .filter(Location.user_id == user.id, Location.external_ref == ref)
                .first())
    if existing:
        return existing
    loc = Location(user_id=user.id, name=prop.place[:255], lat=prop.lat,
                   lng=prop.lng, type="poi",
                   city=prop.place[:128], external_ref=ref)
    db.add(loc)
    db.flush()
    return loc


def years_with_photos(db: Session, user_id: str) -> list[int]:
    """Jahre, die einen Lauf lohnen — für die Auswahl in der Oberfläche.

    Bewusst aus den EIGENEN Daten (Ereignisse und Medien), nicht aus Immich:
    die Frage „welche Jahre gibt es?" wäre dort ein Vollscan der Bibliothek,
    nur um eine Auswahlliste zu füllen.
    """
    from sqlalchemy import func

    years: set[int] = set()
    for (y,) in (db.query(func.extract("year", Event.date_start))
                 .filter(Event.user_id == user_id, Event.date_start.isnot(None))
                 .distinct().all()):
        if y:
            years.add(int(y))
    for (y,) in (db.query(func.extract("year", MediaRef.captured_at))
                 .filter(MediaRef.user_id == user_id,
                         MediaRef.captured_at.isnot(None)).distinct().all()):
        if y:
            years.add(int(y))
    today = date.today().year
    years.add(today)
    return sorted(years, reverse=True)
