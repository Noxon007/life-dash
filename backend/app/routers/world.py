"""F5 — Welt-Reiter: besuchte Länder, Kontinente-Checkliste.

Reine Schicht-4-Ableitung: Es wird nichts gespeichert, alles kommt live aus den
`country`-Entities (KI-Erkennung) und deren Event-Verknüpfungen (Import über F4).
Der ISO-Code stammt aus den Stammdaten (`app/data/countries.py`) und ist derselbe
Schlüssel, den `frontend/world-countries.geojson` je Fläche trägt.
"""
from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.data import countries as ref
from app.database import get_db
from app.models import ConfirmState, Entity, Event, EventEntityLink, Metric, Source, User
from app.schemas import ContinentProgress, VisitedCountry, WorldRead
from app.services import baseline

router = APIRouter(prefix="/api", tags=["Welt"])


@router.get("/world", response_model=WorldRead)
def world(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorldRead:
    """Besuchte Länder je Kontinent — Grundlage für Karte und Checklisten.

    Gezählt werden nur Länder aus der **Lebensdatenbank**: die country-Entity
    muss bestätigt sein oder an mindestens einem bestätigten Event hängen.
    Vorschläge färben die Weltkarte also nicht ein.
    """
    rows = (
        db.query(Entity, Event)
        .outerjoin(EventEntityLink, EventEntityLink.entity_id == Entity.id)
        .outerjoin(Event, Event.id == EventEntityLink.event_id)
        .filter(Entity.user_id == user.id, Entity.type == "country")
        .all()
    )

    # ISO -> aggregierter Stand; mehrere Entities können auf dasselbe Land
    # zeigen ("USA" und "Vereinigte Staaten") und werden hier zusammengeführt.
    agg: dict[str, dict] = {}
    unmatched: set[str] = set()

    for entity, event in rows:
        country = ref.resolve(entity.name)
        if country is None:
            unmatched.add(entity.name)
            continue
        confirmed_event = event is not None and event.confirmed == ConfirmState.confirmed
        if not confirmed_event and entity.confirmed != ConfirmState.confirmed:
            continue
        slot = agg.setdefault(
            country.iso,
            {"country": country, "event_count": 0, "first": None, "last": None,
             "event_ids": set(), "days": set()},
        )
        if confirmed_event:
            slot["event_count"] += 1
            slot["event_ids"].add(event.id)
            when = event.date_start
            if when is not None:
                # Anmerkung 143: TAGE sind die führende Zahl, Einträge stehen
                # daneben. Seit die Massenimporte da sind, sagt „312 Ereignisse
                # in Frankreich" nichts mehr über Frankreich, sondern über die
                # Zufuhr — dreißig Google-Besuche an einem Tag sind ein Tag.
                # Beide Zahlen bleiben: die Ereigniszahl ist keine Falschaussage,
                # sie beantwortet nur eine andere Frage.
                slot["days"].add(when.date())
                if slot["first"] is None or when < slot["first"]:
                    slot["first"] = when
                if slot["last"] is None or when > slot["last"]:
                    slot["last"] = when

    # F20: Der Grundort färbt die Karte mit. Ein Land, in dem jemand sechs
    # Jahre Kindheit verbracht hat, ist besucht — und zwar auch dann, wenn aus
    # dieser Zeit kein einziger Eintrag existiert; das ist der Fall, für den es
    # das Paket gibt (Anmerkung 144, Entscheidung 2: abgeleitete Tage zählen
    # voll). Das Land kommt aus `Location.country` und nicht aus einer
    # `country`-Entity: eine Entity anzulegen hieße, aus einer Ableitung eine
    # Zeile in der Lebensdatenbank zu machen — genau das, was F20 vermeidet.
    #
    # `event_count` bleibt unberührt. Ein abgeleiteter Tag ist kein Eintrag,
    # und beide Zahlen stehen nebeneinander (Anmerkung 143).
    #
    # EIN Kalenderdurchlauf für alle Länder: je Grundort einen zu fahren wäre
    # je Zeitraum eine eigene Abfrage nach den erfassten Tagen, für dieselbe
    # Antwort.
    iso_cache: dict[str, str | None] = {}
    for day, row in baseline.inferred_days(db, user.id).items():
        name = (row.location.country if row.location else None) or ""
        if not name:
            continue
        if name not in iso_cache:
            found = ref.resolve(name)
            iso_cache[name] = found.iso if found else None
            if found is None:
                unmatched.add(name)
        iso = iso_cache[name]
        if iso is None:
            continue
        slot = agg.setdefault(
            iso, {"country": ref.BY_ISO[iso], "event_count": 0, "first": None,
                  "last": None, "event_ids": set(), "days": set()})
        # Die Tage landen in DERSELBEN Menge wie die Ereignistage. Ein `set`
        # und keine Summe: läge zufällig doch ein Ereignistag darin, zählte er
        # sonst zweimal. Dass das nicht vorkommen kann (der Grundort füllt nur
        # Lücken), ist eine Eigenschaft der Ableitung — sich darauf zu
        # VERLASSEN, wo eine Menge es ohnehin erledigt, wäre die vermeidbare
        # Hälfte der Annahme.
        slot["days"].add(day)
        when = datetime.combine(day, time.min)
        if slot["first"] is None or when < slot["first"]:
            slot["first"] = when
        if slot["last"] is None or when > slot["last"]:
            slot["last"] = when

    # F11: Durchschnittstemperatur je Land — aus bereits gespeicherten
    # Wetterdaten, ohne einen einzigen API-Aufruf. Bewusst in EINER Abfrage
    # über alle Events des Nutzers statt mit einer IN-Liste von Event-IDs:
    # bei zehntausenden importierten Events sprengt die sonst das
    # SQL-Variablenlimit.
    temp_by_event: dict[str, float] = dict(
        db.query(Metric.event_id, Metric.value)
        .join(Event, Event.id == Metric.event_id)
        .filter(Event.user_id == user.id,
                Metric.source == Source.weather,
                Metric.key == "temperature_c",
                Metric.value.isnot(None))
        .all()
    )

    def to_read(slot: dict) -> VisitedCountry:
        country: ref.Country = slot["country"]
        temps = [t for eid in slot["event_ids"] if (t := temp_by_event.get(eid)) is not None]
        return VisitedCountry(
            iso=country.iso,
            name=country.name_de,
            continent=country.continent,
            event_count=slot["event_count"],
            day_count=len(slot["days"]),
            first_visit=slot["first"],
            last_visit=slot["last"],
            avg_temp_c=round(sum(temps) / len(temps), 1) if temps else None,
        )

    visited = {iso: to_read(slot) for iso, slot in agg.items()}
    per_continent = ref.by_continent()

    continents: list[ContinentProgress] = []
    for code, label in ref.CONTINENTS.items():
        here = [visited[c.iso] for c in per_continent[code] if c.iso in visited]
        here.sort(key=lambda c: c.name)
        continents.append(ContinentProgress(
            code=code,
            label=label,
            total=len(per_continent[code]),
            visited=len(here),
            countries=here,
            missing=[c.name_de for c in per_continent[code] if c.iso not in visited],
        ))

    # „Zuletzt neu besucht": nach dem ERSTEN Besuch sortiert — ein Land, das man
    # 2003 zum ersten Mal betreten hat, ist keine Neuentdeckung von gestern.
    recent = sorted(
        (c for c in visited.values() if c.first_visit is not None),
        key=lambda c: c.first_visit,
        reverse=True,
    )[:8]

    return WorldRead(
        countries_total=len(ref.BY_ISO),
        countries_visited=len(visited),
        continents_total=len(ref.CONTINENTS),
        continents_visited=sum(1 for c in continents if c.visited > 0),
        continents=continents,
        recent=recent,
        unmatched=sorted(unmatched),
    )
