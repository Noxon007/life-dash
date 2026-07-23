"""P2.1 Stufe 2 — Immich als EREIGNIS-Quelle, nicht nur als Bilderlieferant.

Stufe 1 (0.25.0) hängt Fotos an Ereignisse, die es schon gibt. Diese Stufe
dreht die Richtung um: aus den Fotos selbst entstehen **Vorschläge**. Zwei
Zweige, beide `unconfirmed`, keiner je automatisch bestätigt (Anmerkung 30):

* **Fotocluster** — georeferenzierte eigene Fotos eines Tages an einem Ort
  werden zu einem Vorschlag („34 Fotos am 12. Juli in Detmold").
* **Alben** — Name, Zeitraum und Orte eines Albums werden zu einem
  `trip`-Vorschlag („Dänemark 2024").

Die teure Hälfte ist nicht das Clustern, sondern jeder Fall, in dem Life-Dash
den Tag schon kennt (Anmerkung 107). Die Antworten stehen weiter unten bei
`_existing_slots` und `create_proposals`.

**Identität ist der PLATZ, nicht der Inhalt.** `external_id` trägt
`immich:day:<datum>:<ort>` bzw. `immich:album:<id>` — niemals einen Hash über
die Asset-IDs. Ein nachgeladenes Foto machte aus demselben Tag sonst einen
zweiten Vorschlag. Dieselbe Überlegung wie bei A39s Gruppenvertreter: stabil
schlägt clever.

**Kein Schema.** Der Grabstein für abgelehnte Vorschläge existiert bereits:
jedes Ereignis entsteht aus einem `Fragment`, Fragmente werden nie automatisch
gelöscht, `FragmentStatus.discarded` gibt es, und `_TEXT_SOURCES` hält
`immich` aus der KI-Neuberechnung heraus. Gefragt wird deshalb nach den
FRAGMENTEN — „habe ich diesen Platz je vorgeschlagen?" —, nicht nach den
Ereignissen, denn `discard_event` löscht die Ereigniszeile.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

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
# Ab wie vielen Fotos ein Tag/Ort ein Vorschlag wird. Zwei Bilder sind ein
# Schnappschuss, kein Ereignis; die Zahl darf klein sein, weil nichts
# automatisch bestätigt wird — sie hält nur die Warteschlange lesbar.
MIN_CLUSTER_PHOTOS = 4
# Spannt ein Cluster nur wenige Stunden, ist der Zeitpunkt eine Aussage;
# über den Tag verteilt ist es der Tag (Kap. 3.1: Genauigkeit nie
# überzeichnen).
EXACT_MAX_HOURS = 4
# Ein Album wird ohne Zeitfenster abgefragt (siehe `scan_year`); Immich
# verlangt aber laut Spezifikation Zeitstempel MIT Zone, also zwei weite
# Grenzen statt gar keiner.
_WIDE_START = datetime(1900, 1, 1)
_WIDE_END = datetime(2100, 12, 31, 23, 59, 59)


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit]


def slot_day(day: date, place: str) -> str:
    head = f"{SLOT_PREFIX}day:{day.isoformat()}:"
    return head + _short(place, _EXTERNAL_ID_MAX - len(head))


def slot_album(album_id: str) -> str:
    head = f"{SLOT_PREFIX}album:"
    return head + _short(album_id, _EXTERNAL_ID_MAX - len(head))


@dataclass
class Proposal:
    """Ein Vorschlag, bevor er existiert — die Vorschau zeigt genau das."""

    slot: str
    kind: str                     # "day" | "album"
    title: str
    start: datetime
    end: datetime
    precision: DatePrecision
    place: str | None = None
    country: str | None = None
    photos: int = 0
    shared: bool = False          # aus einem GETEILTEN Album (Fall 7c)
    lat: float | None = None
    lng: float | None = None

    def as_dict(self) -> dict:
        return {
            "slot": self.slot, "kind": self.kind, "title": self.title,
            "start": self.start.isoformat(), "end": self.end.isoformat(),
            "precision": self.precision.value, "place": self.place,
            "photos": self.photos, "shared": self.shared,
        }


# --------------------------------------------------------------------------- #
# Die sieben Fälle „es gibt schon einen Eintrag" (Anmerkung 107)
# --------------------------------------------------------------------------- #
def _proposed_slots(db: Session, user_id: str) -> set[str]:
    """Jeder Platz, der je vorgeschlagen wurde — **auch die abgelehnten**.

    Fall (2), der wichtigste: Ein abgelehnter Vorschlag darf nicht
    wiederkommen. `discard_event` löscht das Ereignis, das Fragment aber
    nicht — und genau deshalb ist das Fragment der Grabstein. Gefragt wird
    also hier und nicht bei den Ereignissen.

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
    """Plätze, zu denen es ein Ereignis GIBT — bestätigt oder nicht.

    Fälle (3) und (4): einmal bestätigt und dann umbenannt oder umdatiert,
    bleibt das Ereignis über `external_id` erkennbar und ab da unantastbar;
    ein gewachsenes Album belegt denselben Platz und bekommt keinen zweiten
    Vorschlag.
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
    mit angehängten Bildern braucht keinen Vorschlag „12 Fotos in Köln";
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
    und denselben Tag zweimal vorschlagen.
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
            slot=slot_day(day, place), kind="day",
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


def album_proposal(album: dict, assets: list[dict], *, shared: bool) -> Proposal | None:
    """Ein Album → ein `trip`-Vorschlag.

    Geteilte Alben sind hier ausdrücklich willkommen (Fall 7c): Ein Album ist
    ein von Menschen benannter, begrenzter Behälter — der Behälter selbst ist
    der Beleg, und bestätigt wird ohnehin von Hand. Dass es ein geteiltes ist,
    steht auf der Karte; wer je eine Reise geteilt bekommt, auf der er nicht
    war, entscheidet dann informiert statt still.

    Der Zeitraum kommt aus den Fotos und nicht aus `startDate`/`endDate` des
    Albums: die beiden Felder sind laut Spezifikation **optional**, und ein
    Vorschlag ohne Datum wäre keiner.
    """
    times = sorted(t for t in (api.asset_time(a) for a in assets) if t)
    if not times:
        return None
    places: dict[str, int] = defaultdict(int)
    geos = []
    for asset in assets:
        place = api.asset_place(asset)
        if place:
            places[place] += 1
        geo = api.asset_geo(asset)
        if geo:
            geos.append(geo)
    top = max(places.items(), key=lambda kv: kv[1])[0] if places else None
    # Ein Album ist eine Spanne von TAGEN, kein Zeitpunkt — also Tagesgrenzen,
    # auch wenn alle Bilder aus einer Stunde stammen. Uhrzeiten stehen zu
    # lassen und daneben `day` zu behaupten, wäre eine Genauigkeit, die die
    # Angabe selbst dementiert (aufgefallen im Smoke-Lauf).
    first, last = times[0], times[-1]
    return Proposal(
        slot=slot_album(album["id"]), kind="album",
        title=(album.get("albumName") or "Album")[:255],
        start=datetime(first.year, first.month, first.day),
        end=datetime(last.year, last.month, last.day, 23, 59, 59),
        precision=DatePrecision.day,
        place=top, country=next((api.asset_country(a) for a in assets
                                 if api.asset_country(a)), None),
        photos=len(assets), shared=shared,
        lat=round(sum(g[0] for g in geos) / len(geos), 6) if geos else None,
        lng=round(sum(g[1] for g in geos) / len(geos), 6) if geos else None,
    )


def _drop_clusters_inside_albums(clusters: list[Proposal],
                                 albums: list[Proposal]) -> list[Proposal]:
    """Fall (5): Liegt ein Cluster in der Spanne eines Albums, gewinnt das Album.

    Es ist der größere Zusammenhang — „Dänemark 2024" sagt mehr über den
    17. Juli als „23 Fotos in Aarhus", und beides nebeneinander wäre derselbe
    Tag zweimal in der Warteschlange.
    """
    if not albums:
        return clusters
    spans = [(a.start, a.end) for a in albums]
    return [c for c in clusters
            if not any(lo <= c.start <= hi or lo <= c.end <= hi for lo, hi in spans)]


# --------------------------------------------------------------------------- #
# Vorschau (P2.5-Muster) und Anlegen
# --------------------------------------------------------------------------- #
def scan_year(db: Session, user, year: int, url: str, key: str,
              heartbeat=None, budget_s: float | None = None,
              report: dict | None = None) -> list[Proposal]:
    """Was dieses Jahr an Vorschlägen ergäbe — **ohne irgendetwas anzulegen**.

    Genau dieselbe Funktion füttert die Vorschau und den Lauf. Zwei getrennte
    Wege wären zwei Regeln, und die widersprechen sich still (Anmerkung 106).

    `budget_s` deckelt die Zeit, `report` nimmt auf, was dabei liegen blieb.
    Beides braucht nur die **Vorschau** (Anmerkung 113): sie hängt an einer
    einzelnen HTTP-Anfrage, und dazwischen steht bei einer Fernnutzung ein
    umgekehrter Vertreter mit einer festen Geduld — gemeldet als **502 Bad
    Gateway**. Ein Lauf über eine gewachsene Bibliothek fragt Immich einmal je
    Album; das kann diese Geduld überschreiten, und dann ist das Ergebnis
    nicht etwa spät, sondern **weg**.

    Der Job braucht das nicht: er läuft im Hintergrund, hat einen Herzschlag
    und niemanden, der auf eine Antwort wartet — er bekommt deshalb kein
    Budget und sieht weiterhin alles an. Eine halbe Vorschau ist brauchbar
    (man sieht, was für ein Jahr zu erwarten ist), ein halber Lauf wäre es
    nicht.
    """
    began = time.monotonic()

    def _spent() -> bool:
        return budget_s is not None and (time.monotonic() - began) > budget_s

    def _note(**kw) -> None:
        if report is not None:
            report.update(kw)

    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31, 23, 59, 59)

    # Das eigene Wissen steht am ANFANG, nicht am Ende (Anmerkung 113). Es
    # kostet drei billige Abfragen und entscheidet, welche teuren Netzabfragen
    # überhaupt nötig sind. Vorher wurde erst alles geholt und dann gefiltert:
    # jedes Album, das dieses Jahr berührt, wurde bei JEDEM Lauf vollständig
    # heruntergeladen — auch die längst bestätigten und die abgelehnten — nur
    # um am Ende weggeworfen zu werden. Bei einer gewachsenen Bibliothek ist
    # das der Löwenanteil der Laufzeit, und beim zweiten Lauf ist er komplett
    # umsonst.
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

    album_props: list[Proposal] = []
    skipped = 0
    looked_at = 0
    open_albums = 0
    for owned in (True, False):
        try:
            found = api.albums(url, key, owned=owned)
        except api.ImmichError as exc:
            # Fehlt dem Schlüssel `album.read`, sind die Fototage trotzdem zu
            # haben — ein fehlendes Häkchen darf nicht die ganze Funktion
            # umbringen. Verschwiegen wird es aber nicht: sonst fehlten die
            # Alben, und niemand wüsste warum (Anmerkung 113).
            if exc.status != 403:
                raise
            log.warning("Immich: Alben übersprungen — %s", exc)
            _note(albums_denied=str(exc))
            break
        for album in found:
            if not _album_touches_year(album, year):
                continue
            if _spent():
                # Abgebrochen, nicht abgeschnitten: die Vorschau SAGT, wie
                # viele Alben sie nicht mehr angesehen hat. Eine Zahl, die
                # aussieht wie „alles", ist hier der teurere Fehler
                # (Anmerkung 110: was eine Ansicht nicht zeigen kann, muss sie
                # sagen — und zwar dort, wo hingeschaut wird).
                open_albums += 1
                continue
            if slot_album(album["id"]) in known:
                # Fälle (2)/(3)/(4): schon vorgeschlagen, schon bestätigt oder
                # abgelehnt. Der Platz ist vergeben — die Fotos dazu braucht
                # niemand mehr.
                skipped += 1
                continue
            # **Nicht** auf das Jahr eingegrenzt: Ein Album ist ein begrenzter
            # Behälter mit einer eigenen Spanne. Fragte man nur nach den Fotos
            # dieses Jahres, bekäme eine Silvesterreise (28.12.–3.1.) einen
            # Vorschlag über die halbe Reise — und weil der Platz derselbe ist,
            # würde der Lauf im anderen Jahr ihn stillschweigend überspringen
            # statt ihn zu vervollständigen. Das Jahr entscheidet, OB das Album
            # angeboten wird, nicht was drin ist.
            items = api.search_assets_paged(url, key, _WIDE_START, _WIDE_END,
                                            album_id=album["id"],
                                            heartbeat=heartbeat)
            looked_at += 1
            if not items:
                continue
            prop = album_proposal(album, items, shared=not owned)
            if prop:
                album_props.append(prop)
    log.info("Immich %d: %d Alben vorgeschlagen, %d schon vergeben, "
             "%d nicht mehr angesehen (%.1fs)", year, len(album_props),
             skipped, open_albums, time.monotonic() - began)
    _note(partial=bool(open_albums), albums_open=open_albums,
          albums_checked=looked_at, seconds=round(time.monotonic() - began, 1))

    clusters = _drop_clusters_inside_albums(clusters, album_props)

    # Fall (1): Fotos, die schon ein Zuhause haben, brauchen keinen Vorschlag.
    clusters = [c for c in clusters if c.start.date() not in housed]

    # Fälle (2), (3), (4) für die Tage — die Alben sind oben schon durch.
    return [p for p in (album_props + clusters) if p.slot not in known]


def _album_touches_year(album: dict, year: int) -> bool:
    """Grober Vorfilter über die (optionalen) Album-Daten.

    Fehlen sie, wird das Album NICHT ausgeschlossen — ein fehlendes Datum ist
    keine Auskunft über das Jahr, und lieber eine Abfrage zu viel als ein
    Album, das nie vorgeschlagen wird.
    """
    lo, hi = album.get("startDate"), album.get("endDate")
    if not lo and not hi:
        return True
    for value in (lo, hi):
        if not value:
            continue
        try:
            if datetime.fromisoformat(str(value).replace("Z", "+00:00")).year == year:
                return True
        except ValueError:
            return True
    # Beide Daten da und beide in anderen Jahren — kann das Jahr trotzdem
    # überspannen (Silvesterreise), deshalb der Bereichsvergleich.
    try:
        a = datetime.fromisoformat(str(lo).replace("Z", "+00:00")).year
        b = datetime.fromisoformat(str(hi).replace("Z", "+00:00")).year
        return a <= year <= b
    except (ValueError, TypeError):
        return True


def create_proposals(db: Session, user, proposals: list[Proposal]) -> int:
    """Legt Vorschläge an: je einer ein `Fragment` (Grabstein) + ein Ereignis.

    Alles `unconfirmed` — nichts wird je automatisch bestätigt (Anmerkung 30).
    Das Fragment trägt den Platz im Klartext; es ist die Antwort auf „habe ich
    das schon einmal vorgeschlagen?", auch nachdem das Ereignis abgelehnt und
    damit gelöscht wurde.

    Fall (6): Die Fotos werden hier **nicht** umgehängt. Ein Vorschlag ZEIGT
    die Bilder seines Fensters (sie hängen weiter am Tag, F18/Anmerkung 106),
    besitzt sie aber erst, wenn ein Mensch bestätigt. Eine Ablehnung hat
    deshalb nichts rückgängig zu machen — und hochgeladene Dateien wandern
    ohnehin nie (Anmerkung 57).
    """
    created = 0
    for prop in proposals:
        fragment = Fragment(
            user_id=user.id,
            raw_text=json.dumps({
                "type": "immich_source", "slot": prop.slot, "kind": prop.kind,
                "title": prop.title, "photos": prop.photos,
                "place": prop.place, "shared": prop.shared,
                "range": [prop.start.isoformat(), prop.end.isoformat()],
            }, ensure_ascii=False),
            source=Source.immich,
            status=FragmentStatus.processed,
        )
        db.add(fragment)
        db.flush()
        db.add(Event(
            user_id=user.id,
            title=prop.title,
            description=_describe(prop),
            date_start=prop.start, date_end=prop.end,
            date_precision=prop.precision,
            category="trip" if prop.kind == "album" else "event",
            # Ein Vorschlag ist ein Vorschlag: die Zuversicht ist mittelhoch,
            # weil Foto-GPS ein Beleg ist — aber nie 1.0, denn was der Tag
            # BEDEUTETE, weiß nur der Mensch.
            confidence=0.6,
            confirmed=ConfirmState.unconfirmed,
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
    if prop.shared:
        # Steht bewusst IM Text und nicht nur in einem Feld: wer den Vorschlag
        # sieht, muss wissen, dass die Bilder von jemand anderem stammen.
        bits.append("— aus einem geteilten Album")
    return " ".join(bits)


def _location_for(db: Session, user, prop: Proposal) -> Location | None:
    """Ort des Vorschlags — vorhandene Orte wiederverwenden, sonst anlegen.

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
                   lng=prop.lng, type="poi", city=prop.place[:128],
                   external_ref=ref)
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
