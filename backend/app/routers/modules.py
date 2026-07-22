"""Modul- & Kompendium-Endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (CityInfo, Entity, Event, EventEntityLink, Location,
                        User)
from app.modules.registry import registry
from app.routers._serialize import EAGER, event_to_read
from app.schemas import (CityDetailRead, CityInfoRead, CityPlaceRead, CityRead,
                         EntityRead, EventRead, ModuleRead)
from app.services.geocode import lang_for

router = APIRouter(prefix="/api", tags=["Module & Kompendium"])


@router.get("/modules", response_model=list[ModuleRead])
def list_modules() -> list[ModuleRead]:
    """Alle registrierten Trackable-Module (aus YAML geladen)."""
    return [
        ModuleRead(
            key=m.key,
            label=m.label,
            icon=m.icon,
            color=m.color,
            emoji=m.emoji,
            compendium=m.compendium,
            category_labels=m.category_labels or {},
            event_categories=m.event_categories,
        )
        for m in registry.modules
    ]


@router.get("/compendium/{type}", response_model=list[EntityRead])
def compendium(
    type: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EntityRead]:
    """Eigene Entities eines Typs (z. B. 'animal', 'country') fürs Kompendium."""
    rows = (
        db.query(Entity, func.count(EventEntityLink.id))
        .outerjoin(EventEntityLink, EventEntityLink.entity_id == Entity.id)
        .filter(Entity.user_id == user.id, Entity.type == type)
        .group_by(Entity.id)
        .order_by(Entity.name)
        .all()
    )
    out = []
    for entity, count in rows:
        item = EntityRead.model_validate(entity)
        item.event_count = count
        out.append(item)
    return out


@router.get("/cities", response_model=list[CityRead])
def cities(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CityRead]:
    """A41: Die besuchten Städte als Kompendium-Tab.

    Städte sind KEINE `Entity` — sie stehen als `Location.city` (A39) und
    werden hier aggregiert statt gespiegelt. Eine zweite Wahrheit für dieselbe
    Tatsache wäre teurer als diese Abfrage: die Stadt kommt aus dem
    Ortsnamen-Lauf und ändert sich, wenn er sie korrigiert.

    Warum es Städte gibt und Orte nicht (Anmerkung 95): ein Kompendium
    beantwortet „welche habe ich?" und setzt damit eine Menge mit Horizont
    voraus. Ein Leben hat vielleicht 100–300 Städte; Orte sind ein
    Koordinaten-Index, der mit jedem Import um hunderte wächst — dafür ist die
    Karte da.

    Der Leerstring bedeutet „nachgesehen, keine Stadt" (A39) und ist keine
    Stadt — er fällt hier genauso weg wie NULL.
    """
    rows = (db.query(Location.city,
                     func.min(Location.country),
                     func.count(Event.id),
                     func.count(func.distinct(Location.id)),
                     func.min(Event.date_start),
                     func.max(Event.date_start))
            .join(Event, Event.location_id == Location.id)
            .filter(Location.user_id == user.id,
                    Event.user_id == user.id,
                    Location.city.isnot(None), Location.city != "")
            .group_by(Location.city)
            .order_by(Location.city)
            .all())
    return [CityRead(name=name, country=country, event_count=events,
                     place_count=places, first_visit=first, last_visit=last)
            for name, country, events, places, first, last in rows]


# --------------------------------------------------------------------------- #
# A42 — die Stadt als Sammlungs-EINTRAG, nicht nur als Kachel mit Sprungziel
#
# A41 gab den Städten einen Reiter; geklickt wurde daraus ein Zeitstrahl-Filter,
# also verließ man die Sammlung. Jeder andere Typ dort öffnet eine Seite. Was
# fehlte, ist beides hier: die Ereignisse der Stadt und ein Ort für ihre
# Beschreibung. Über eine Entity ging es nicht — Städte sind bewusst KEINE
# (Anmerkung 95): `Location.city` ist die eine Wahrheit, eine gespiegelte
# Entity-Zeile liefe beim nächsten Ortsnamen-Lauf auseinander.
#
# Die Stadt wird als Query-Parameter übergeben, nicht im Pfad: der Name kommt
# aus dem Geocoder, ist Freitext und darf jedes Zeichen enthalten — auch den
# Schrägstrich, der einen Pfad zerschnitte.
# --------------------------------------------------------------------------- #
CITY_EVENT_LIMIT = 100          # Vorschau; alles Weitere zeigt der Zeitstrahl
CITY_RETRY_AFTER = timedelta(days=30)


def _utcnow() -> datetime:
    """Naives UTC — bewusst ohne Zeitzone.

    Die Zeitspalten hier sind `DateTime` ohne Zeitzone; SQLite wie PostgreSQL
    geben deshalb naive Werte zurück. Ein zeitzonenbewusster `now()` ließe sich
    mit einem frisch gelesenen `fetched_at` nicht subtrahieren — das wäre ein
    TypeError erst beim zweiten Öffnen einer Stadt in einer neuen Sitzung, also
    genau dort, wo ihn keine schnelle Prüfung sieht.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _city_places(db: Session, user_id: str, name: str) -> list[Location]:
    """Die eigenen Orte dieser Stadt — zugleich der Zugriffsschutz: wer die
    Stadt nicht in den eigenen Orten hat, bekommt 404 statt einer Antwort
    darüber, ob jemand anders dort war."""
    return (db.query(Location)
            .filter(Location.user_id == user_id, Location.city == name)
            .order_by(Location.name)
            .all())


def _city_country(places: list[Location]) -> str | None:
    """Das Land einer Stadt — nach derselben Regel wie in der Liste.

    `/api/cities` nimmt `func.min(country)`; stünde hier „das erste Vorkommen",
    könnten Liste und Seite für dieselbe Stadt zwei verschiedene Länder nennen,
    und die Beschreibung würde unter einem anderen Schlüssel abgelegt als
    gesucht — der Cache liefe dann bei jedem Öffnen ins Leere.
    """
    known = sorted(p.country for p in places if p.country)
    return known[0] if known else None


@router.get("/cities/detail", response_model=CityDetailRead)
def city_detail(
    name: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CityDetailRead:
    """Eine Stadt als Sammlungs-Eintrag: Orte, Ereignis-Vorschau, Beschreibung.

    Bewusst nur die letzten `CITY_EVENT_LIMIT` Ereignisse mit Gesamtzahl daneben
    — eine Stadt kann nach einem Import tausende Besuche tragen, und A37 hat
    genau die Gewohnheit abgeschafft, „alles" zu schicken, weil es beim Autor
    noch passte. Der Zeitstrahl mit Stadtfilter (A41) zeigt den Rest.
    """
    places = _city_places(db, user.id, name)
    if not places:
        raise HTTPException(status_code=404, detail="Stadt nicht gefunden")

    place_ids = [p.id for p in places]
    base = (db.query(Event)
            .filter(Event.user_id == user.id, Event.location_id.in_(place_ids)))
    total = base.count()
    # Vorladen statt lazy je Ereignis: hundert Karten wären sonst dreihundert
    # Nachfragen (Metriken, Verknüpfungen, Bilder) — dasselbe N+1, das A36/A37
    # aus dem Zeitstrahl entfernt haben.
    events = (base.options(*EAGER).order_by(Event.date_start.desc().nullslast())
              .limit(CITY_EVENT_LIMIT).all())

    counts = dict(db.query(Event.location_id, func.count(Event.id))
                  .filter(Event.user_id == user.id,
                          Event.location_id.in_(place_ids))
                  .group_by(Event.location_id).all())
    # Spanne per Aggregat, nicht durch Laden aller Zeilen — Anmerkung 97 hat
    # genau diese Gewohnheit im Wetter-Lauf teuer gemacht.
    first, last = (db.query(func.min(Event.date_start), func.max(Event.date_start))
                   .filter(Event.user_id == user.id,
                           Event.location_id.in_(place_ids))
                   .one())

    country = _city_country(places)
    info = (db.query(CityInfo)
            .filter(CityInfo.name == name, CityInfo.country == (country or ""),
                    CityInfo.lang == lang_for(user))
            .first())

    return CityDetailRead(
        name=name,
        country=country,
        event_count=total,
        place_count=len(places),
        first_visit=first,
        last_visit=last,
        places=[CityPlaceRead(id=p.id, name=p.name, lat=p.lat, lng=p.lng,
                              event_count=counts.get(p.id, 0)) for p in places],
        events=[event_to_read(e) for e in events],
        events_shown=len(events),
        info=CityInfoRead.model_validate(info) if info else None,
    )


@router.post("/cities/describe", response_model=CityInfoRead | None)
def describe_city(
    name: str = Query(..., min_length=1),
    force: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CityInfoRead | None:
    """Beschreibung einer Stadt holen und im Cache ablegen (A42).

    Zwei Dinge, die der Entity-Weg nicht braucht und dieser hier schon:

    **(a) Das Land entscheidet mit.** „Frankfurt" gibt es mehrfach; ohne das
    Land beschriebe die Suche selbstbewusst die falsche Stadt.

    **(b) Ein Fehlschlag wird gespeichert.** Ein Ort ohne Wikipedia-Artikel ist
    normal, und ohne Merker fragte jeder Aufruf der Seite erneut — dieselbe
    Endlosschleife, die F12 (`weather_rev`) und A39 (Leerstring als Stadt)
    schon einmal beseitigen mussten. Nach `CITY_RETRY_AFTER` wird es erneut
    versucht: ein Artikel kann entstehen.
    """
    from app.services.wikipedia import fetch_city_summary

    places = _city_places(db, user.id, name)
    if not places:
        raise HTTPException(status_code=404, detail="Stadt nicht gefunden")

    lang = lang_for(user)
    country = _city_country(places) or ""
    row = (db.query(CityInfo)
           .filter(CityInfo.name == name, CityInfo.country == country,
                   CityInfo.lang == lang)
           .first())

    fresh = row is not None and (
        row.description or _utcnow() - row.fetched_at < CITY_RETRY_AFTER)
    if row is not None and fresh and not force:
        return CityInfoRead.model_validate(row)

    info = fetch_city_summary(name, country or None, lang) or {}
    if row is None:
        row = CityInfo(name=name, country=country, lang=lang)
        db.add(row)
    row.description = info.get("description")
    row.wiki_title = info.get("wiki_title")
    row.wiki_url = info.get("wiki_url")
    row.thumbnail = info.get("thumbnail")
    row.fetched_at = _utcnow()
    db.commit()
    db.refresh(row)
    return CityInfoRead.model_validate(row)


@router.post("/entities/{entity_id}/describe", response_model=EntityRead)
def describe_entity(
    entity_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EntityRead:
    """Holt eine Kurzbeschreibung aus Wikipedia und speichert sie in
    Entity.attributes (description, wiki_url, thumbnail). Lazy vom Kompendium
    aufgerufen, wenn noch keine Beschreibung vorhanden ist.

    0.35.0: Der Text kommt in der Sprache der Oberfläche (F10) — und trägt
    seitdem `desc_lang`. Ohne die Markierung bliebe der einmal geholte deutsche
    Absatz für immer stehen, auch wenn die App längst auf Englisch läuft: eine
    zwischengespeicherte Antwort auf eine Frage, die inzwischen anders lautet.
    """
    from app.services.wikipedia import fetch_summary

    entity = db.get(Entity, entity_id)
    if entity is None or entity.user_id != user.id:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")

    lang = lang_for(user)
    attrs = dict(entity.attributes or {})
    stale = attrs.get("desc_lang", "de") != lang
    if force or stale or not attrs.get("description"):
        info = fetch_summary(entity.name, entity.type, lang)
        # Nur speichern, wenn wirklich etwas gefunden wurde — bei Fehlschlag
        # (z. B. Wikipedia-Drosselung) wird beim nächsten Öffnen neu versucht.
        if info:
            attrs.update({k: v for k, v in info.items() if v})
            attrs["desc_lang"] = lang
            entity.attributes = attrs
            db.commit()
            db.refresh(entity)
    return EntityRead.model_validate(entity)


@router.get("/entities/{entity_id}/events", response_model=list[EventRead])
def entity_events(
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EventRead]:
    """Alle eigenen Events, die mit dieser Entity verknüpft sind —
    für die Kompendium-Detailansicht (z. B. alle Fuchs-Sichtungen)."""
    entity = db.get(Entity, entity_id)
    if entity is None or entity.user_id != user.id:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    events = (
        db.query(Event)
        .join(EventEntityLink, EventEntityLink.event_id == Event.id)
        .filter(EventEntityLink.entity_id == entity_id, Event.user_id == user.id)
        .order_by(Event.date_start.desc().nullslast())
        .all()
    )
    return [event_to_read(e) for e in events]
