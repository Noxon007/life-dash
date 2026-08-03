"""Anmerkung 139 — ein verortetes Foto ist EIN bestätigtes Ereignis.

**Was sich gegenüber A45/Anmerkung 138 geändert hat, und warum.**

Bis 0.39 gab es hierfür *zwei* Mechanismen nebeneinander: eine verwerfbare
Kartenebene (`PhotoPoint`, ein Punkt je Foto) und einen Lauf, der aus
Fototagen Ereignisse machte (`immich_source`, ein Ereignis je Tag+Ort ab vier
Fotos). Beide zeichneten dieselben Fotos auf dieselbe Karte, mit zwei
verschiedenen Deckelungen und zwei verschiedenen Antworten auf „was ist das
hier eigentlich?". Genau die Doppelung, die Anmerkung 106 in diesem Projekt
immer wieder findet — hier war sie ausnahmsweise mit Absicht gebaut worden.

Jetzt gibt es **einen** Weg: jedes eigene, verortete, im Immich-Zeitstrahl
sichtbare Foto wird ein Ereignis, sofort bestätigt, wie ein Google-Besuch
(`confirmed_by="import"`, Anmerkung 138). Keine Mindestzahl mehr — ein
einzelnes Foto ist genauso viel Beleg dafür, dort gewesen zu sein, wie vier.

**Wo die Koordinate liegt, und warum nicht auf dem Ereignis.**

Ein Ereignis hat keine eigenen Koordinaten; es hat einen `Location`. Die
naheliegende Abkürzung wäre gewesen, `Event.lat`/`Event.lng` einzuführen —
zwei Spalten im Kern des Modells für einen einzelnen Konnektor. Nicht nötig:
`PhotoPoint` war der Sache nach ohnehin ein Ort plus ein Zeitstempel plus eine
Asset-Kennung, und alle drei haben im Ereignis-Modell längst ihren Platz (der
Ort im `Location`, die Zeit im `date_start`, die Kennung in der `external_id`).
Das ist das eigentliche „Auflösen in die Ereignis-Pipeline": nicht die Tabelle
woanders hinschieben, sondern feststellen, dass es sie nicht braucht.

**Der Ort wird über die KOORDINATE entdoppelt, nicht über den Stadtnamen.**
Ein Ort je Stadt hieße, 1200 Bilder aus London wären wieder EIN Kartenpunkt —
also genau der gemeldete Defekt, der A45 ausgelöst hat. Ein Ort je Foto hieße
20.000 Ortszeilen. Der Schlüssel ist deshalb die auf fünf Nachkommastellen
(≈ 1 m) gerundete Koordinate: Serienaufnahmen vom selben GPS-Fix fallen
zusammen, alles, was wirklich woanders war, bleibt getrennt.

**Diese Orte fragen NIEMALS bei Nominatim nach.** Immich hat sie bereits
rückwärts geokodiert (`exifInfo` liefert city/state/country, Anmerkung 109),
und 20.000 gedrosselte Abrufe wären knapp sieben Stunden Lauf für eine Auskunft,
die schon vorliegt. Sie tragen deshalb `type="photo"` und eine gesetzte
`address` — die Marke, an der `resolve_names` sie erkennt und stehen lässt
(Anmerkung 139 in Verbindung mit der Endlos-Abruf-Falle: ein Ort ohne Marke
wird ewig neu gefragt).

**Schicht.** Was hier entsteht, ist Lebensdatenbank — anders als bei A45, wo
die Punkte Schicht 4 waren. Deshalb legt `reset()` nicht mehr einfach eine
Tabelle leer, sondern löscht ausdrücklich nur, was dieser Lauf angelegt hat
(`external_id LIKE 'immich:photo:%'`), samt Grabsteinen.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (ConfirmState, DatePrecision, Event, EventEntityLink,
                        Fragment, FragmentStatus, Location, MediaRef, Metric,
                        Source, Track)
from app.services import immich as api
from app.services.immich_link import PROVIDER

log = logging.getLogger("lifedash.immich")

# `Event.external_id` ist String(64). „immich:photo:" sind 13 Zeichen, eine
# Immich-Asset-UUID 36 — es bleibt Luft. Der Platz ist die ASSET-KENNUNG und
# nicht Tag+Ort: ein Foto, das in Immich nachträglich einen Ort bekommt, ist
# dasselbe Foto und darf nicht als zweites Ereignis wiederkommen.
SLOT_PREFIX = "immich:photo:"
# Der alte Platz aus Anmerkung 138 (ein Ereignis je Tag+Ort). Steht hier, weil
# der Aufräum-Lauf ihn braucht — und weil er sonst niemandem mehr begegnet und
# beim nächsten Lesen wie ein Tippfehler aussieht.
DAY_SLOT_PREFIX = "immich:day:"
# Namensraum der Orte, die dieser Lauf anlegt.
PLACE_PREFIX = "immich:pt:"
# Auf wie viele Nachkommastellen die Koordinate für den Ortsschlüssel gerundet
# wird. Fünf sind ≈ 1,1 m — feiner als jedes Telefon-GPS, also fallen nur
# Aufnahmen vom IDENTISCHEN Fix zusammen. Gröber wäre bequemer und falsch:
# bei 0,001° (≈ 110 m) verschmölzen zwei Seiten eines Marktplatzes.
PLACE_ROUND = 5


def slot_photo(asset_id: str) -> str:
    return f"{SLOT_PREFIX}{asset_id}"[:64]


def asset_of(external_id: str | None) -> str | None:
    """Die Asset-Kennung aus dem Platz zurücklesen — für das Vorschaubild.

    Die Karte braucht zu jedem Fotopunkt sein Bild. Sie holt es NICHT über
    `MediaRef`: dessen Deckelung von zwölf je Tag beantwortet eine andere Frage
    („welche Bilder stehen neben diesem Eintrag?"), und zwei Fragen mit zwei
    Deckelungen teilen sich keine Tabelle (Anmerkung 116/A45). Die Kennung
    steht ohnehin schon im Platz; sie ein zweites Mal zu speichern hieße, zwei
    Angaben über dieselbe Sache zu führen (Anmerkung 106).
    """
    if external_id and external_id.startswith(SLOT_PREFIX):
        return external_id[len(SLOT_PREFIX):] or None
    return None


@dataclass
class PhotoProposal:
    """Ein Foto, bevor es ein Ereignis ist — die Vorschau zeigt genau das."""

    slot: str
    asset_id: str
    taken_at: datetime
    lat: float
    lng: float
    place: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    district: str | None = None

    @property
    def title(self) -> str:
        """Was im Zeitstrahl steht — **Text, nie ein Bild** (Anmerkung 139).

        Die Karte ist der Ort für das BILD, der Zeitstrahl der für die
        TATSACHE. Verdichtet werden gleichartige Fotos desselben Tages am
        selben Ort zu „12× Foto in Detmold" (A39-Bündelung, kein neuer Code).
        """
        wo = self.district or self.city or self.state or self.country
        return (f"Foto in {wo}" if wo else "Foto")[:255]

    def as_dict(self) -> dict:
        return {"slot": self.slot, "title": self.title,
                "at": self.taken_at.isoformat(), "place": self.place,
                "lat": self.lat, "lng": self.lng}


# --------------------------------------------------------------------------- #
# Ortsteil aus dem eigenen Bestand (A47) — ohne einen einzigen Abruf
# --------------------------------------------------------------------------- #
DISTRICT_RADIUS_KM = 0.6


def district_index(db: Session, user_id: str) -> list[tuple[float, float, str]]:
    """(lat, lng, Ortsteil) aller eigenen Orte, die einen kennen.

    Einmal je Lauf geladen, nicht je Foto: bei 20.000 Bildern wären das sonst
    20.000 Abfragen für eine Frage, deren Antwort sich nicht ändert.

    **Die eigenen Foto-Orte bleiben draußen.** Sie tragen ihren Ortsteil selbst
    aus genau dieser Quelle; sie wieder hineinzulassen hieße, die Ableitung als
    ihre eigene Grundlage zu benutzen — beim zweiten Lauf breitete sich ein
    einmal geratener Ortsteil über die halbe Stadt aus.
    """
    from app.sqlutil import DISTRICT_KEYS

    out: list[tuple[float, float, str]] = []
    rows = (db.query(Location)
            .filter(Location.user_id == user_id,
                    Location.lat.isnot(None), Location.address.isnot(None),
                    (Location.type.is_(None)) | (Location.type != "photo"))
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
    if not index:
        return None
    best, best_km = None, DISTRICT_RADIUS_KM
    for lat, lng, name in index:
        km = api._km(geo, (lat, lng))
        if km < best_km:
            best, best_km = name, km
    return best


# --------------------------------------------------------------------------- #
# Warum ein Foto kein Ereignis wurde
# --------------------------------------------------------------------------- #
# In der Reihenfolge, in der geprüft wird. Gezählt wird der ERSTE Grund, damit
# die Zahlen sich zur gelesenen Menge addieren statt sie zu überzeichnen: ein
# fremdes Foto ohne Koordinaten ist ein Ausschluss, nicht zwei.
DROP_REASONS = {
    "foreign": "{n} von jemand anderem",
    "hidden": "{n} nicht im Immich-Zeitstrahl (archiviert, versteckt oder gesperrt)",
    "no_geo": "{n} ohne Koordinaten",
    "no_time": "{n} ohne verwertbare Aufnahmezeit",
    "no_id": "{n} ohne Kennung",
    "known": "{n} schon angelegt oder bewusst gelöscht",
}


def drop_reasons(report: dict) -> list[str]:
    """Die Ausschlussgründe als lesbare Teilsätze, der größte zuerst.

    **Die Summe allein ist keine Auskunft.** „2016 Fotos gelesen, 17 neu"
    lässt genau die Frage offen, die man beim Lesen stellt: Warum die anderen
    1999? Ob die Bibliothek schlicht kein GPS trägt oder ob der API-Schlüssel
    auf ein fremdes Konto zeigt, sind zwei völlig verschiedene Lagen — und sie
    sahen bis Anmerkung 120 identisch aus.
    """
    dropped = report.get("dropped") or {}
    out = [(n, DROP_REASONS[key].format(n=n))
           for key, n in dropped.items() if n and key in DROP_REASONS]
    out.sort(key=lambda pair: -pair[0])
    return [text for _n, text in out]


# --------------------------------------------------------------------------- #
# Schon bekannte Plätze — die Endlos-Abruf-Falle, neunte Auflage
# --------------------------------------------------------------------------- #
def known_slots(db: Session, user_id: str) -> set[str]:
    """Jeder Platz, der je angelegt wurde — **auch die gelöschten**.

    Der wichtigste Fall ist der zweite: ein von Hand gelöschtes Foto-Ereignis
    darf nicht beim nächsten Lauf wiederkommen. Das Löschen nimmt nur die
    Ereigniszeile mit, das Fragment (der Grabstein) bleibt — genau deshalb wird
    hier das Fragment gefragt UND das Ereignis, nicht nur eines von beidem.

    Das ist inzwischen das neunte Auftreten derselben Falle in diesem Projekt
    (F12 `weather_rev`, A39-Leerstring, A42 „kein Artikel", P2.1-Grabstein,
    Anmerkung 114 `_name_defect`, A45-Jahresliste, `Location.address`).
    """
    slots: set[str] = set()
    for (raw,) in (db.query(Fragment.raw_text)
                   .filter(Fragment.user_id == user_id,
                           Fragment.source == Source.immich).all()):
        try:
            slot = json.loads(raw).get("slot")
        except (ValueError, TypeError, AttributeError):
            continue
        if slot:
            slots.add(slot)
    for (ext,) in (db.query(Event.external_id)
                   .filter(Event.user_id == user_id,
                           Event.external_id.like(f"{SLOT_PREFIX}%")).all()):
        if ext:
            slots.add(ext)
    return slots


# --------------------------------------------------------------------------- #
# Erkennen
# --------------------------------------------------------------------------- #
def photo_proposals(assets: list[dict], my_id: str | None,
                    districts: list[tuple[float, float, str]] | None = None,
                    known: set[str] | None = None,
                    report: dict | None = None) -> list[PhotoProposal]:
    """Aus Immich-Assets die Fotos, die ein Ereignis werden.

    Drei Filter, und jeder ersetzt ein Stück der Unterdrückungsregel, die der
    Autor in Anmerkung 107 gekippt hat:

    * **nur mit Koordinaten** — ein weitergeleitetes Bild, ein Bildschirmfoto,
      ein Download trägt kein EXIF-GPS und kann deshalb keinen Ort erfinden.
    * **nur eigene** (`ownerId`) — die eigentliche Gefahr waren nie
      Screenshots, sondern **geteilte Alben**: fremde Urlaubsfotos haben sehr
      wohl GPS und erfänden stillschweigend einen Tag.
    * **nur im Zeitstrahl** — was im Archiv oder im gesperrten Ordner liegt,
      hat der Nutzer bewusst herausgenommen.

    Die drei sind bewusst EINZELN geprüft statt in einem `or`: verodert ließe
    sich nicht mehr sagen, welcher zugeschlagen hat, und genau das ist die
    Frage, die beim Lesen des Protokolls gestellt wird.
    """
    districts = districts or []
    known = known or set()
    dropped = dict.fromkeys(DROP_REASONS, 0)
    out: list[PhotoProposal] = []
    seen: set[str] = set()
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
        slot = slot_photo(asset_id)
        # `seen` fängt den Fall ab, dass Immich dasselbe Asset über eine
        # Seitengrenze zweimal liefert — sonst legte ein Lauf es zweimal an
        # und der Grabstein käme zu spät.
        if slot in known or slot in seen:
            dropped["known"] += 1
            continue
        seen.add(slot)
        exif = asset.get("exifInfo") or {}
        city = (exif.get("city") or "").strip() or None
        state = (exif.get("state") or "").strip() or None
        out.append(PhotoProposal(
            slot=slot, asset_id=asset_id, taken_at=when,
            lat=geo[0], lng=geo[1],
            place=api.asset_place(asset) or city or state,
            city=city, state=state, country=api.asset_country(asset),
            district=_district(geo, districts),
        ))
    if report is not None:
        report["dropped"] = dropped
        report["kept"] = len(out)
    out.sort(key=lambda p: p.taken_at)
    return out


def scan_year(db: Session, user, year: int, url: str, key: str,
              heartbeat=None, budget_s: float | None = None,
              report: dict | None = None) -> list[PhotoProposal]:
    """Was dieses Jahr an Foto-Ereignissen ergäbe — **ohne etwas anzulegen**.

    Genau dieselbe Funktion füttert die Vorschau und den Lauf. Zwei getrennte
    Wege wären zwei Regeln, und die widersprechen sich still (Anmerkung 106).

    Jahresweise, und der Grund ist derselbe wie bei P2.1: eine zwanzig Jahre
    alte Bibliothek in einem Zug ist kein Lauf, sondern ein Zeitlimit.
    """
    report = report if report is not None else {}
    my_id = api.own_user_id(url, key)
    report["own_user_id"] = my_id
    if not my_id:
        # Ohne eigene Kennung ließe sich ein fremdes Foto nicht erkennen — und
        # ein geteiltes Album schriebe Ereignisse in die Lebensdatenbank, an
        # denen man nie war. Lieber nichts (dieselbe Strenge wie `is_own`).
        log.warning("Immich nennt keine eigene Nutzerkennung — Foto-Ereignisse "
                    "werden übersprungen")
        report["seen"] = 0
        return []
    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31, 23, 59, 59)
    assets = api.search_assets_paged(url, key, start, end, heartbeat=heartbeat,
                                     budget_s=budget_s, report=report)
    props = photo_proposals(assets, my_id, district_index(db, user.id),
                            known_slots(db, user.id), report)
    report["seen"] = len(assets)
    log.info("Foto-Ereignisse %d: %d Fotos gelesen, %d neu — ohne Ereignis: %s",
             year, len(assets), len(props),
             "; ".join(drop_reasons(report)) or "keins")
    return props


# --------------------------------------------------------------------------- #
# Anlegen
# --------------------------------------------------------------------------- #
def create_photo_events(db: Session, user, props: list[PhotoProposal]) -> int:
    """Legt je Foto ein sofort bestätigtes Ereignis an (Anmerkung 138/139).

    Je ein `Fragment` (Grabstein) + ein `confirmed`-es Ereignis. Der Grabstein
    bleibt auch nach einer manuellen Löschung stehen: ohne ihn fände der
    nächste Lauf denselben Platz wieder frei und legte ihn erneut an — eine
    Wiederauferstehung, die eine bewusste Löschung rückgängig macht.

    **Die Fotos werden NICHT umgehängt.** Ein Foto-Ereignis bekommt keinen
    `MediaRef`: die Karte holt das Bild über die Asset-Kennung in der
    `external_id` (`asset_of`), und der Zeitstrahl soll bei diesen Ereignissen
    ausdrücklich KEIN Bild zeigen. Die Tagesleisten aus Stufe 1 (F18) bleiben
    davon unberührt — das ist der zweite, unveränderte Job aus Anmerkung 139.
    """
    places = _place_cache(db, user.id)
    created = 0
    now = datetime.now(timezone.utc)
    for prop in props:
        fragment = Fragment(
            user_id=user.id,
            raw_text=json.dumps({
                "type": "photo_point", "slot": prop.slot,
                "asset_id": prop.asset_id, "place": prop.place,
                "at": prop.taken_at.isoformat(),
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
            date_start=prop.taken_at, date_end=prop.taken_at,
            # Ein Foto trägt seinen Zeitstempel — genauer wird es nicht.
            date_precision=DatePrecision.exact,
            category="event",
            # Foto-GPS ist ein Beleg, kein Geständnis — dieselbe mittelhohe
            # Zuversicht wie bei einem Google-Besuch (`tracks.py`).
            confidence=0.6,
            confirmed=ConfirmState.confirmed,
            confirmed_at=now,
            confirmed_by="import",
            source=Source.immich,
            location=_location_for(db, user, prop, places),
            origin_fragment=fragment,
            external_id=prop.slot,
        ))
        created += 1
    return created


def _describe(prop: PhotoProposal) -> str:
    bits = ["Foto aus Immich"]
    if prop.place:
        bits.append(f"in {prop.place}")
    bits.append(f"({prop.taken_at.strftime('%H:%M')})")
    return " ".join(bits)


def _place_key(lat: float, lng: float) -> str:
    return f"{PLACE_PREFIX}{round(lat, PLACE_ROUND)},{round(lng, PLACE_ROUND)}"[:255]


def _place_cache(db: Session, user_id: str) -> dict[str, Location]:
    """Alle Foto-Orte dieses Kontos, einmal geladen.

    Einer je Foto abzufragen wäre bei einem Jahreslauf über 20.000 Bilder der
    Unterschied zwischen Sekunden und Minuten — dieselbe Überlegung wie beim
    `district_index`, nur für die Schreibrichtung.
    """
    rows = (db.query(Location)
            .filter(Location.user_id == user_id,
                    Location.external_ref.like(f"{PLACE_PREFIX}%")).all())
    return {loc.external_ref: loc for loc in rows if loc.external_ref}


def _location_for(db: Session, user, prop: PhotoProposal,
                  cache: dict[str, Location]) -> Location:
    """Der Ort eines Fotos — je Koordinate einer, nicht je Stadt und nicht je Foto.

    Je Stadt wäre der gemeldete Defekt aus A45 („London, 1200 Bilder" = EIN
    Punkt). Je Foto wären 20.000 Ortszeilen für Aufnahmen, die zu Dritteln vom
    identischen GPS-Fix stammen. Der Schlüssel ist deshalb die gerundete
    Koordinate.

    `address` wird ausdrücklich GESETZT, auch wenn wenig drinsteht: sie ist die
    Marke „hier ist nichts mehr nachzuschlagen". Bliebe sie NULL, nähme der
    A47-Rückfülllauf diese Zeilen für unaufgelöste Orte und schickte 20.000
    gedrosselte Nominatim-Abrufe hinterher — die Endlos-Abruf-Falle in ihrer
    teuersten Ausprägung, weil sie hier nicht nur wiederholt, sondern auch
    fremde Kontingente verbrennt.
    """
    ref = _place_key(prop.lat, prop.lng)
    existing = cache.get(ref)
    if existing is not None:
        return existing
    name = prop.district or prop.city or prop.state or prop.country
    loc = Location(
        user_id=user.id,
        name=(name or "Foto-Ort")[:255],
        # Die Marke, an der jeder erkennt, woher diese Zeile kommt — und an der
        # `resolve_names` sie in Ruhe lässt.
        type="photo",
        lat=prop.lat, lng=prop.lng,
        city=(prop.city or None) and prop.city[:128],
        country=(prop.country or None) and prop.country[:64],
        address={k: v for k, v in (("city", prop.city), ("state", prop.state),
                                   ("country", prop.country),
                                   ("suburb", prop.district)) if v} or {"source": "immich"},
        external_ref=ref,
    )
    db.add(loc)
    db.flush()
    cache[ref] = loc
    return loc


# --------------------------------------------------------------------------- #
# Merkliste der durchsuchten Jahre
# --------------------------------------------------------------------------- #
def scanned_years(user) -> set[int]:
    """Jahre, die schon einmal durchsucht wurden.

    **Der Unterschied zwischen „keine Fotos" und „nie nachgesehen".** Ohne
    diese Liste zeigte die Oberfläche für 2004 dasselbe wie für ein Jahr ohne
    Kamera: nichts, wortlos.

    Kein Schema: die Liste ist eine Notiz über einen LAUF, kein Datum über das
    Leben — sie gehört in die Einstellungen, nicht in die Lebensdatenbank.
    """
    raw = ((user.settings or {}).get("photo_points") or {}).get("years") or []
    return {int(y) for y in raw if isinstance(y, int) or str(y).isdigit()}


def mark_scanned(db: Session, user, year: int) -> None:
    """Merkt sich, dass dieses Jahr durchsucht wurde.

    `user.settings` ist eine JSON-Spalte: neu ZUWEISEN, nicht an Ort und Stelle
    ändern — SQLAlchemy bemerkt eine Mutation im Dict sonst nicht und schreibt
    nichts.
    """
    settings = dict(user.settings or {})
    block = dict(settings.get("photo_points") or {})
    block["years"] = sorted(scanned_years(user) | {int(year)})
    settings["photo_points"] = block
    user.settings = settings


# --------------------------------------------------------------------------- #
# Zurücknehmen
# --------------------------------------------------------------------------- #
def _slot_events(db: Session, user_id: str, prefix: str):
    return (db.query(Event)
            .filter(Event.user_id == user_id,
                    Event.external_id.like(f"{prefix}%")))


def count_photo_events(db: Session, user_id: str) -> int:
    return (db.query(func.count(Event.id))
            .filter(Event.user_id == user_id,
                    Event.external_id.like(f"{SLOT_PREFIX}%")).scalar() or 0)


def remove_slots(db: Session, user_id: str, prefix: str,
                 drop_fragments: bool = True) -> int:
    """Löscht alles, was ein Lauf unter diesem Platz-Präfix angelegt hat.

    **Auch die Grabsteine**, und zwar mit Absicht: Dies ist „noch einmal von
    vorn", nicht „das will ich nicht mehr sehen". Blieben die Fragmente stehen,
    fände der nächste Lauf jeden Platz vergeben und legte nichts an — der
    Zurücksetzen-Knopf hätte dann alles gelöscht und die Wiederherstellung
    unmöglich gemacht. Ein einzeln gelöschtes Ereignis behält seinen Grabstein
    dagegen sehr wohl; das ist der andere Fall und der Sinn der Sache.

    Die Foto-Orte gehen mit, aber nur die eigenen (`immich:pt:`) und nur die,
    an denen nichts mehr hängt.

    **Alles, was am Ereignis hängt, muss hier von Hand mit** (Anmerkung 150),
    und das ist die Falle: `db.delete(event)` räumt Metriken, Verknüpfungen und
    Bilder über die ORM-Kaskade ab (`cascade="all, delete-orphan"` in
    `models.py`), ein Massenlöschen (`query(...).delete()`) fragt das Objekt nie
    und geht an ihr vorbei. Auf SQLite blieben Waisen zurück, auf PostgreSQL — dem, worauf
    betrieben wird — ist es eine Fremdschlüsselverletzung, also ein 500 statt
    einer Aufräumung. Getroffen hat es die Tagescluster aus Anmerkung 138: sie
    sind bestätigt und verortet, der Wetter-Lauf hat ihnen also Metriken
    angehängt, und die Testdoppel bauten sie nackt nach.
    """
    events = _slot_events(db, user_id, prefix).all()
    if not events:
        return 0
    frag_ids = {e.origin_fragment_id for e in events if e.origin_fragment_id}
    loc_ids = {e.location_id for e in events if e.location_id}
    ids = [e.id for e in events]
    # Alles Anhängende zuerst — ein Fremdschlüssel auf ein gelöschtes Ereignis
    # ist auf PostgreSQL ein Fehler und auf SQLite eine Waise.
    #
    # HOCHGELADENE Bilder werden dabei abgehängt, nicht gelöscht (Anmerkung 57:
    # `provider="local"` ist Lebensdatenbank, keine Ableitung). Sie hängen
    # danach am TAG (F18) — dafür braucht ein loses Bild `captured_at`, sonst
    # wäre das Abhängen ein stilles Wegwerfen.
    dates = {e.id: e.date_start for e in events}
    for ref in (db.query(MediaRef)
                .filter(MediaRef.event_id.in_(ids),
                        MediaRef.provider == "local").all()):
        ref.captured_at = ref.captured_at or dates.get(ref.event_id)
        ref.event_id = None
    db.flush()      # sonst löscht das Massenlöschen unten sie doch noch mit
    (db.query(MediaRef).filter(MediaRef.event_id.in_(ids))
     .delete(synchronize_session=False))
    (db.query(Metric).filter(Metric.event_id.in_(ids))
     .delete(synchronize_session=False))
    (db.query(EventEntityLink).filter(EventEntityLink.event_id.in_(ids))
     .delete(synchronize_session=False))
    # Der Weg ist eine eigene Aufzeichnung (Stufe 3) und keine Ableitung dieses
    # Ereignisses: er wird abgehängt, nicht gelöscht.
    (db.query(Track).filter(Track.event_id.in_(ids))
     .update({Track.event_id: None}, synchronize_session=False))
    # F7: Kinder werden abgehängt statt mitgelöscht — dieselbe Entscheidung wie
    # im Lösch-Dialog (`with_children=False`), und ohne sie zeigt der
    # Fremdschlüssel `parent_event_id` auf eine gelöschte Zeile.
    (db.query(Event).filter(Event.parent_event_id.in_(ids),
                            Event.id.notin_(ids))
     .update({Event.parent_event_id: None}, synchronize_session=False))
    (db.query(Event).filter(Event.id.in_(ids)).delete(synchronize_session=False))
    if drop_fragments and frag_ids:
        (db.query(Fragment).filter(Fragment.id.in_(frag_ids))
         .delete(synchronize_session=False))
    db.flush()
    if loc_ids:
        used = {r[0] for r in db.query(Event.location_id)
                .filter(Event.location_id.in_(loc_ids)).distinct()}
        orphan = [i for i in loc_ids if i not in used]
        if orphan:
            (db.query(Location)
             .filter(Location.id.in_(orphan),
                     Location.external_ref.like(f"{PLACE_PREFIX}%"))
             .delete(synchronize_session=False))
    return len(ids)


def reset(db: Session, user_id: str) -> int:
    """Verwirft alle Foto-Ereignisse dieses Kontos."""
    return remove_slots(db, user_id, SLOT_PREFIX)


def count_day_clusters(db: Session, user_id: str) -> int:
    """Wie viele Tagescluster aus Anmerkung 138 noch stehen — für die Vorschau."""
    return (db.query(func.count(Event.id))
            .filter(Event.user_id == user_id,
                    Event.external_id.like(f"{DAY_SLOT_PREFIX}%")).scalar() or 0)


def day_cluster_sample(db: Session, user_id: str, limit: int = 12) -> list[dict]:
    """Ein paar der betroffenen Zeilen, NAMENTLICH.

    „214 Ereignisse werden gelöscht" ist eine Zahl; „12. Juli 2018 — 34 Fotos
    in Detmold, …" ist eine Entscheidungsgrundlage. Dieselbe Zusage wie bei
    A46 und der F7-Serie: eine Vorschau, die nur zählt, ist keine.
    """
    rows = (_slot_events(db, user_id, DAY_SLOT_PREFIX)
            .order_by(Event.date_start.desc()).limit(limit).all())
    return [{"id": e.id, "title": e.title,
             "date": e.date_start.isoformat() if e.date_start else None}
            for e in rows]


def remove_day_clusters(db: Session, user_id: str) -> int:
    """Räumt die Tagescluster aus Anmerkung 138 weg.

    **Nur auf Knopfdruck, nie im Nachtplan** — dieselbe Strenge wie beim
    A46-Aufräum-Lauf, und aus demselben Grund: das hier fasst BESTÄTIGTES an.
    Die Grabsteine gehen mit, denn sonst blockierten sie nichts (die neuen
    Plätze heißen anders) und blieben als Datenmüll stehen.
    """
    return remove_slots(db, user_id, DAY_SLOT_PREFIX)


# --------------------------------------------------------------------------- #
# Jahresauswahl
# --------------------------------------------------------------------------- #
def years_with_photos(db: Session, user_id: str) -> list[int]:
    """Jahre, die einen Lauf lohnen — der Notnagel für die Auswahl.

    Bewusst aus den EIGENEN Daten (Ereignisse und Medien), nicht aus Immich:
    die Frage „welche Jahre gibt es?" wäre dort ein Vollscan der Bibliothek,
    nur um eine Auswahlliste zu füllen. Der reguläre Weg fragt Immichs
    `/timeline/buckets` (siehe `routers/immich.py`); diese Liste greift nur,
    wenn der Server das nicht kann — und sagt dann auch, dass sie es ist
    (Anmerkung 113).
    """
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
    years.add(date.today().year)
    return sorted(years, reverse=True)


def preview_summary(props: list[PhotoProposal], sample: int = 12) -> dict:
    """Die Vorschau eines Jahres — verdichtet, nicht als Liste von 20.000.

    Eine Vorschau muss NENNEN, was sie anlegt (A46, F7-Serie). Bei zwanzigtausend
    Fotos ist die vollständige Liste aber selbst keine Entscheidungsgrundlage
    mehr, sondern nur noch eine große Antwort. Genannt werden deshalb die ORTE
    mit ihren Zahlen — das ist die Ebene, auf der man „ja, das war so" oder
    „nein, das sind fremde Bilder" sagen kann — plus ein paar Beispiele.
    """
    by_place: dict[str, int] = defaultdict(int)
    days: set[date] = set()
    for p in props:
        by_place[p.place or "ohne Ortsangabe"] += 1
        days.add(p.taken_at.date())
    places = sorted(by_place.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "total": len(props),
        "days": len(days),
        "places": [{"place": name, "photos": n} for name, n in places[:40]],
        "places_total": len(places),
        "sample": [p.as_dict() for p in props[:sample]],
    }
