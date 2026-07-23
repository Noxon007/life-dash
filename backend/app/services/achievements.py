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

F19 (0.35.0): Die vier Stufen behalten ihre Namen — aber **Platin ist keine
Endstation mehr**. Oberhalb zählt der Erfolg gegen eine erzeugte nächste Marke
weiter (`_next_mark`), damit eine Zahl, die ein ganzes Leben umfasst, nicht
irgendwann stehenbleibt und nichts mehr sagt.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data import countries as ref
from app.models import ConfirmState, Entity, Event, EventEntityLink
from app.modules.registry import Module, registry
from app.schemas import AchievementRead, AchievementsRead
from app.services.ingestion import tracked_modules
from app.services.weather_day import day_value_query

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


def _weather_days(db: Session, user_id: str, spec: dict):
    """Basis für die F11-Wettermetriken — **ein Wert je Kalendertag**.

    Deklaration im YAML:

        metric: weather_event_count
        weather: { key: sunshine_h, min: 10 }

    F19/Anmerkung 103: Bis 0.34 zählte das hier **Einträge**. Wetter ist aber
    eine Eigenschaft des TAGES, und nach einem Timeline-Import trägt ein Tag
    dutzende Besuche mit demselben Wetter — „Tage mit mindestens 10
    Sonnenstunden" zählte also Besuche, und die gesammelten Sonnenstunden
    wurden mit der Zahl der Einträge je Tag multipliziert.

    Anmerkung 119: Die Regel steht jetzt in `services/weather_day.py`, weil
    dieselbe Frage auch die Statistik-Bilanz und der Zeitstrahl stellen — und
    jede hatte sich bis dahin ihre eigene Antwort gegeben. Was dabei auffiel:
    die Schwellen wurden hier VOR der Verdichtung geprüft, der günstigste
    Eintrag des Tages entschied also doch. Der Docstring versprach seit 0.35
    das Gegenteil.
    """
    cfg = spec.get("weather") or {}
    key = cfg.get("key")
    if not key:
        return None
    return day_value_query(db, user_id, key, confirmed_only=True,
                           min_value=cfg.get("min"), max_value=cfg.get("max"))


def _weather_event_count(db: Session, user_id: str, module: Module, spec: dict) -> int:
    """Wie viele bestätigte Tage erfüllen die Wetterbedingung?
    („Sonnenanbeter": Tage mit ≥ 10 Sonnenstunden.)"""
    q = _weather_days(db, user_id, spec)
    if q is None:
        return 0
    return db.query(func.count()).select_from(q.subquery()).scalar() or 0


def _weather_sum(db: Session, user_id: str, module: Module, spec: dict) -> int:
    """Summe einer Wetter-Metrik über alle bestätigten TAGE — z. B. gesammelte
    Sonnenstunden. Gerundet, weil Erfolge in ganzen Zahlen zählen."""
    q = _weather_days(db, user_id, spec)
    if q is None:
        return 0
    total = db.query(func.sum(q.subquery().c.value)).scalar()
    return int(round(total)) if total is not None else 0


_METRICS = {
    "entity_count": _entity_count,
    "event_count": _event_count,
    "country_count": _country_count,
    "continent_count": _continent_count,
    # F11 — Erfolge aus bereits gespeicherten Wetterdaten, ohne einen
    # einzigen zusätzlichen API-Aufruf
    "weather_event_count": _weather_event_count,
    "weather_sum": _weather_sum,
}


# F19: Marken oberhalb der letzten Stufe — 1 · 2,5 · 5 je Zehnerpotenz.
# Bewusst eine REGEL statt einer Liste: eine Liste hätte wieder ein Ende, und
# das Ende ist ja gerade das Problem (Anmerkung 99). Die Schrittweite ist so
# gewählt, dass die nächste Marke immer erreichbar aussieht (Faktor 2 bis 2,5)
# und trotzdem runde Zahlen liefert, die man sich merken kann.
_MARK_STEPS = (1.0, 2.5, 5.0)

# ... aber NUR für Metriken, die überhaupt weiterzählen können. Es gibt sieben
# Kontinente und knapp 200 Länder; „nächste Marke: 10 Kontinente" wäre kein
# Ansporn, sondern ein Rechenfehler mit Anspruch — und ausgerechnet für den,
# der die Sammlung vollständig hat. Die Grenze ist eine Eigenschaft der METRIK,
# nicht des einzelnen Erfolgs; ein YAML darf sie mit `open_ended` überstimmen,
# falls jemand eine gebundene Metrik anders meint.
_BOUNDED_METRICS = {"continent_count", "country_count"}


def _open_ended(spec: dict) -> bool:
    if "open_ended" in spec:
        return bool(spec["open_ended"])
    return spec.get("metric") not in _BOUNDED_METRICS


def _marks_from(start: int):
    """Aufsteigende Marken ab der Zehnerpotenz von `start` — endloser Strom."""
    exponent = max(0, len(str(max(1, start))) - 2)
    while True:
        for step in _MARK_STEPS:
            yield int(round(step * 10 ** exponent))
        exponent += 1


def _beyond(value: int, top: int) -> tuple[int, int, int]:
    """Nach der höchsten Stufe: (bereits passierte Marken, letzte, nächste).

    Der Boden ist die höchste Stufe selbst — wer Platin gerade eben erreicht
    hat, startet bei 0 % zur nächsten Marke und nicht bei „fast geschafft".
    """
    passed, floor = 0, top
    for mark in _marks_from(top):
        if mark <= top:
            continue
        if mark > value:
            return passed, floor, mark
        passed, floor = passed + 1, mark


def _evaluate(spec: dict, module: Module, value: int) -> AchievementRead:
    """Ordnet einen Metrik-Wert der erreichten Stufe zu und rechnet den
    Fortschritt bis zur nächsten aus — oder, oberhalb der letzten Stufe, bis
    zur nächsten erzeugten Marke (F19)."""
    thresholds = {t: int(spec["tiers"][t]) for t in TIERS if t in (spec.get("tiers") or {})}

    reached_index = 0
    for index, tier in enumerate(TIERS, start=1):
        if tier in thresholds and value >= thresholds[tier]:
            reached_index = index

    remaining = [t for t in TIERS if t in thresholds and thresholds[t] > value]
    next_tier = remaining[0] if remaining else None
    next_threshold = thresholds[next_tier] if next_tier else None
    beyond_top, marks_passed = False, 0

    if next_threshold is not None:
        # Fortschritt innerhalb der aktuellen Stufe, nicht ab null — sonst sieht
        # der Balken zwischen Gold und Platin fast immer voll aus.
        floor = thresholds[TIERS[reached_index - 1]] if reached_index else 0
    elif thresholds and _open_ended(spec):
        # F19: alle Stufen erreicht — ab hier zählt die Marke weiter. Ohne das
        # bliebe die Karte für den Rest des Lebens bei „höchste Stufe erreicht"
        # stehen, und die Zahl daneben sagte nichts mehr.
        beyond_top = True
        marks_passed, floor, next_threshold = _beyond(value, max(thresholds.values()))
    elif thresholds:
        # Begrenzte Metrik: hier IST Platin das Ende, und das ist keine
        # Schwäche der Leiter, sondern die Wahrheit über die Menge.
        return AchievementRead(
            id=spec["id"], module=module.key, label=spec.get("label", spec["id"]),
            description=spec.get("description"),
            emoji=spec.get("emoji") or module.emoji, value=value,
            tier=TIERS[reached_index - 1] if reached_index else None,
            tier_index=reached_index, progress=1.0, thresholds=thresholds)
    else:
        return AchievementRead(  # keine Stufen deklariert: nichts zu messen
            id=spec["id"], module=module.key, label=spec.get("label", spec["id"]),
            description=spec.get("description"),
            emoji=spec.get("emoji") or module.emoji, value=value, progress=0.0)

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
        beyond_top=beyond_top,
        marks_passed=marks_passed,
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
