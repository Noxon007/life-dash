"""F6 — Achievements: Erfolge in vier Stufen, deklarativ aus den Modul-YAMLs.

Schicht-4-Ableitung (Kap. 3.1): nichts wird gespeichert, alles bei jeder Abfrage
aus der Lebensdatenbank neu gerechnet. Gezählt wird ausschließlich **Bestätigtes**
— Vorschläge sollen keine Erfolge auslösen.

Ein Achievement im Modul-YAML sieht so aus:

    achievements:
      - id: animal_collector
        label: "Tier-Sammler"
        emoji: "🦁"
        description: "Verschiedene Tierarten gesehen"
        metric: entity_count          # entity_count | event_count | continent_count
        tiers: { bronze: 5, silber: 25, gold: 100, platin: 500 }

Neue Metrik = eine Funktion in `_METRICS`; neuer Erfolg = drei Zeilen YAML.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data import countries as ref
from app.models import ConfirmState, Entity, Event, EventEntityLink
from app.modules.registry import Module, registry
from app.schemas import AchievementRead, AchievementsRead
from app.services.ingestion import tracked_modules

# Reihenfolge = Wertigkeit; der Index ist zugleich die Punktzahl (Bronze 1 … Platin 4)
TIERS: tuple[str, ...] = ("bronze", "silber", "gold", "platin")


def _entity_count(db: Session, user_id: str, module: Module, spec: dict) -> int:
    """Verschiedene bestätigte Objekte des Modul-Typs (Arten, Länder, Filme …)."""
    return (
        db.query(func.count(func.distinct(func.lower(Entity.name))))
        .filter(Entity.user_id == user_id, Entity.type == module.key)
        .filter(Entity.confirmed == ConfirmState.confirmed)
        .scalar()
    ) or 0


def _event_count(db: Session, user_id: str, module: Module, spec: dict) -> int:
    """Bestätigte Events in den Kategorien des Moduls (oder aus `categories`)."""
    categories = spec.get("categories") or module.event_categories
    if not categories:
        return 0
    return (
        db.query(func.count(Event.id))
        .filter(Event.user_id == user_id,
                Event.confirmed == ConfirmState.confirmed,
                Event.category.in_(categories))
        .scalar()
    ) or 0


def _visited_countries(db: Session, user_id: str) -> set[ref.Country]:
    """Bestätigte Länder, über die Stammdaten aufgelöst — dieselbe Zählweise
    wie der Welt-Reiter (F5). Wichtig, weil mehrere Entity-Namen dasselbe Land
    meinen können („USA" und „Vereinigte Staaten") und unbekannte Namen
    („Absurdistan") gar kein Land sind: Ohne das Auflösen zählte der Erfolg
    mehr Länder, als die Weltkarte einfärbt.
    """
    names = (
        db.query(Entity.name)
        .outerjoin(EventEntityLink, EventEntityLink.entity_id == Entity.id)
        .outerjoin(Event, Event.id == EventEntityLink.event_id)
        .filter(Entity.user_id == user_id, Entity.type == "country")
        .filter((Entity.confirmed == ConfirmState.confirmed)
                | (Event.confirmed == ConfirmState.confirmed))
        .distinct()
        .all()
    )
    return {c for (name,) in names if (c := ref.resolve(name)) is not None}


def _country_count(db: Session, user_id: str, module: Module, spec: dict) -> int:
    """Verschiedene besuchte Länder (nach ISO-Code, nicht nach Schreibweise)."""
    return len(_visited_countries(db, user_id))


def _continent_count(db: Session, user_id: str, module: Module, spec: dict) -> int:
    """Kontinente, auf denen mindestens ein bestätigtes Land liegt."""
    return len({c.continent for c in _visited_countries(db, user_id)})


_METRICS = {
    "entity_count": _entity_count,
    "event_count": _event_count,
    "country_count": _country_count,
    "continent_count": _continent_count,
}


def _evaluate(spec: dict, module: Module, value: int) -> AchievementRead:
    """Ordnet einen Metrik-Wert der erreichten Stufe zu und rechnet den
    Fortschritt bis zur nächsten aus."""
    thresholds = {t: int(spec["tiers"][t]) for t in TIERS if t in (spec.get("tiers") or {})}

    reached_index = 0
    for index, tier in enumerate(TIERS, start=1):
        if tier in thresholds and value >= thresholds[tier]:
            reached_index = index

    remaining = [t for t in TIERS if t in thresholds and thresholds[t] > value]
    next_tier = remaining[0] if remaining else None
    next_threshold = thresholds[next_tier] if next_tier else None

    if next_threshold is None:
        progress = 1.0
    else:
        # Fortschritt innerhalb der aktuellen Stufe, nicht ab null — sonst sieht
        # der Balken zwischen Gold und Platin fast immer voll aus.
        floor = thresholds[TIERS[reached_index - 1]] if reached_index else 0
        span = next_threshold - floor
        progress = (value - floor) / span if span > 0 else 0.0

    return AchievementRead(
        id=spec["id"],
        module=module.key,
        label=spec.get("label", spec["id"]),
        description=spec.get("description"),
        emoji=spec.get("emoji") or module.emoji,
        value=value,
        tier=TIERS[reached_index - 1] if reached_index else None,
        tier_index=reached_index,
        next_tier=next_tier,
        next_threshold=next_threshold,
        progress=max(0.0, min(1.0, progress)),
        thresholds=thresholds,
    )


def compute(db: Session, user_id: str) -> AchievementsRead:
    """Alle Erfolge des Nutzers — nur aus Modulen, die er auch trackt (A15)."""
    tracked = tracked_modules(db, user_id)
    out: list[AchievementRead] = []

    for module in registry.modules:
        if tracked is not None and module.key not in tracked:
            continue
        for spec in module.achievements:
            metric = _METRICS.get(spec.get("metric", ""))
            if metric is None or not spec.get("tiers"):
                continue
            out.append(_evaluate(spec, module, metric(db, user_id, module, spec)))

    # Fast Geschaffte zuerst: erreichte Stufe absteigend, dann Fortschritt.
    out.sort(key=lambda a: (-a.tier_index, -a.progress, a.label))

    return AchievementsRead(
        earned=sum(1 for a in out if a.tier_index > 0),
        total=len(out),
        points=sum(a.tier_index for a in out),
        achievements=out,
    )
