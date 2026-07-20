"""P3.1 — deklarative Statistik-Widgets aus den Modul-YAMLs.

Ein Modul deklariert seine Kennzahlen im YAML (`statistics:`), statt sie im
Frontend hart zu verdrahten (baut auf A7 auf). Drei Typen:

    - id: species_count
      label: "Beobachtete Arten"
      type: count_distinct          # verschiedene Objekte des Modul-Typs
      field: entity.species         #   nach Name (entity.name) oder Attribut

    - id: milestones_count
      type: count                   # bestätigte Ereignisse in den Kategorien

    - id: trips_per_year
      type: timeseries              # bestätigte Ereignisse je Jahr

Schicht-4-Ableitung: nichts gespeichert, alles bei jeder Abfrage neu gerechnet.
Gezählt wird ausschließlich **Bestätigtes** und nur aus Modulen, die der Nutzer
trackt (A15) — dieselben Regeln wie bei den Erfolgen (F6).
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import ConfirmState, Entity, Event, EventEntityLink
from app.modules.registry import Module, registry
from app.services.ingestion import tracked_modules


def _count(db: Session, user_id: str, module: Module) -> int:
    """Bestätigte Ereignisse in den Kategorien des Moduls."""
    if not module.event_categories:
        return 0
    return (db.query(func.count(Event.id))
            .filter(Event.user_id == user_id,
                    Event.confirmed == ConfirmState.confirmed,
                    Event.category.in_(module.event_categories))
            .scalar()) or 0


def _count_distinct(db: Session, user_id: str, module: Module, field: str) -> int:
    """Verschiedene bestätigte Objekte des Modul-Typs.

    `field` ist `entity.name` (Standard) oder `entity.<attribut>`. Ein Attribut
    liegt im JSON `Entity.attributes`; fehlt es, zählt der Eintrag nicht mit.
    Groß-/Kleinschreibung wird bei Namen zusammengefasst („Adler"/„adler").
    """
    base = (db.query(Entity)
            .filter(Entity.user_id == user_id, Entity.type == module.key,
                    Entity.confirmed == ConfirmState.confirmed))
    attr = field.split(".", 1)[1] if "." in field else "name"
    if attr == "name":
        return (base.with_entities(func.count(func.distinct(func.lower(Entity.name))))
                .scalar()) or 0
    # Attribut: in Python entduplizieren — JSON-Zugriff ist über SQLite/Postgres
    # hinweg nicht portabel, und die Objektzahl je Nutzer ist überschaubar.
    seen = set()
    for (attrs,) in base.with_entities(Entity.attributes).all():
        val = (attrs or {}).get(attr)
        if val is not None and str(val).strip():
            seen.add(str(val).strip().lower())
    return len(seen)


def _timeseries(db: Session, user_id: str, module: Module) -> dict[str, int]:
    """Bestätigte Ereignisse der Modul-Kategorien je Jahr (Jahr -> Anzahl)."""
    if not module.event_categories:
        return {}
    rows = (db.query(Event.date_start)
            .filter(Event.user_id == user_id,
                    Event.confirmed == ConfirmState.confirmed,
                    Event.category.in_(module.event_categories),
                    Event.date_start.isnot(None))
            .all())
    per_year: dict[str, int] = {}
    for (when,) in rows:
        y = str(when.year)
        per_year[y] = per_year.get(y, 0) + 1
    return dict(sorted(per_year.items()))


def compute_widgets(db: Session, user_id: str) -> list[dict]:
    """Alle deklarierten Widgets der getrackten Module.

    Ein Widget ohne verwertbaren Wert (0 bzw. leere Reihe) fällt heraus — eine
    Statistik-Kachel „0 Länder" für ein Modul, das jemand nie nutzt, ist nur
    Rauschen. Erfüllte Nullwerte kommen wieder, sobald echte Daten da sind.
    """
    tracked = tracked_modules(db, user_id)
    out: list[dict] = []
    for module in registry.modules:
        if tracked is not None and module.key not in tracked:
            continue
        for spec in module.statistics:
            wtype = spec.get("type")
            widget = {
                "module": module.key,
                "id": spec.get("id", ""),
                "label": spec.get("label", spec.get("id", "")),
                "emoji": module.emoji,
                "type": wtype,
            }
            if wtype == "count":
                value = _count(db, user_id, module)
                if not value:
                    continue
                widget["value"] = value
            elif wtype == "count_distinct":
                value = _count_distinct(db, user_id, module, spec.get("field", "entity.name"))
                if not value:
                    continue
                widget["value"] = value
            elif wtype == "timeseries":
                series = _timeseries(db, user_id, module)
                if not series:
                    continue
                widget["series"] = series
                widget["value"] = sum(series.values())   # Summe als Kennzahl
            else:
                continue   # unbekannter Typ -> überspringen, nicht crashen
            out.append(widget)
    return out
