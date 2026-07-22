"""Mock-KI-Provider — heuristische Extraktion ohne echtes LLM.

Erkennt per Regeln: Datum (inkl. unscharfer Angaben wie "Sommer 2002"),
Ort, Kategorie (über Modul-Keywords) und bekannte Entities (Tiere, Länder).
Später ersetzbar durch einen echten Ollama-Provider mit gleicher Schnittstelle.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from app.ai.base import ExtractedEntity, ExtractedEvent, LLMProvider
from app.modules.registry import registry

# Ein paar bekannte Orte für die Demo (Ortsname -> Koordinaten)
KNOWN_PLACES: dict[str, tuple[float, float]] = {
    "detmold": (51.9375, 8.8797),
    "hamburg": (53.5511, 9.9937),
    "berlin": (52.5200, 13.4050),
    "münchen": (48.1351, 11.5820),
    "köln": (50.9375, 6.9603),
    "lissabon": (38.7223, -9.1393),
    "paris": (48.8566, 2.3522),
    "prag": (50.0755, 14.4378),
    "wien": (48.2082, 16.3738),
    "amsterdam": (52.3676, 4.9041),
    "frankreich": (46.2276, 2.2137),
    "portugal": (39.3999, -8.2245),
    "spanien": (40.4637, -3.7492),
    "italien": (41.8719, 12.5674),
}

MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag"]

SEASONS = {
    "frühling": (3, 1, 5, 31), "fruehling": (3, 1, 5, 31), "frühjahr": (3, 1, 5, 31),
    "sommer": (6, 1, 8, 31),
    "herbst": (9, 1, 11, 30),
    "winter": (12, 1, 12, 31),
}


class MockProvider(LLMProvider):
    def extract(self, raw_text: str,
                tracked: list[str] | None = None) -> list[ExtractedEvent]:
        text = raw_text.strip()
        low = text.lower()

        date_start, date_end, precision, date_conf = self._parse_date(low)
        location_name, lat, lng = self._parse_location(low)
        # Straßen-Adresse hat Vorrang (präziseres Geocoding downstream)
        address = self._parse_address(text)
        if address:
            if location_name and location_name.lower() not in address.lower():
                location_name = f"{address}, {location_name}"
            else:
                location_name = address
        category, cat_conf = self._parse_category(low)
        entities = self._parse_entities(low)

        # Länder als Entity + ggf. Ortsfallback
        for ent in entities:
            if ent.type == "country" and location_name is None:
                location_name = ent.name
                coords = KNOWN_PLACES.get(ent.name.lower())
                if coords:
                    lat, lng = coords

        title = self._make_title(text, entities, location_name, category)
        confidence = round(min(date_conf, cat_conf, 0.98), 2)

        event = ExtractedEvent(
            title=title,
            description=text,
            date_start=date_start,
            date_end=date_end,
            date_precision=precision,
            category=category,
            confidence=confidence,
            location_name=location_name,
            location_lat=lat,
            location_lng=lng,
            entities=entities,
        )
        return [event]

    # ------------------------------------------------------------------ #
    # Datum
    # ------------------------------------------------------------------ #
    def _parse_date(self, low: str) -> tuple[datetime | None, datetime | None, str, float]:
        # 1) exaktes Datum: 12.07.2026 oder 12.7.2026
        m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", low)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                dt = datetime(y, mo, d)
                return dt, dt, "day", 0.97
            except ValueError:
                pass

        # 2) Jahreszeit + Jahr: "Sommer 2002"
        for name, (sm, sd, em, ed) in SEASONS.items():
            m = re.search(rf"\b{name}\s+(\d{{4}})\b", low)
            if m:
                y = int(m.group(1))
                start = datetime(y, sm, sd)
                end = datetime(y, em, ed)
                return start, end, "season", 0.72

        # 3) Monat + Jahr: "September 2025" / "Sep 2025"
        for name, mo in MONTHS.items():
            if re.search(rf"\b{name[:3]}[a-zä]*\s+\d{{4}}\b", low):
                m = re.search(rf"\b{name[:3]}[a-zä]*\s+(\d{{4}})\b", low)
                if m:
                    y = int(m.group(1))
                    start = datetime(y, mo, 1)
                    # Monatsende grob
                    end_month = mo % 12 + 1
                    end_year = y + (1 if mo == 12 else 0)
                    end = datetime(end_year, end_month, 1)
                    return start, end, "month", 0.85

        # 4) nur Jahr: "2002"
        m = re.search(r"\b(19\d{2}|20\d{2})\b", low)
        if m:
            y = int(m.group(1))
            return datetime(y, 1, 1), datetime(y, 12, 31), "year", 0.65

        # 5) relative Angaben
        if "gestern" in low or "heute" in low or "letzte woche" in low:
            dt = datetime.now()
            return dt, dt, "day", 0.55

        return None, None, "day", 0.4

    # ------------------------------------------------------------------ #
    # Ort
    # ------------------------------------------------------------------ #
    def _parse_location(self, low: str) -> tuple[str | None, float | None, float | None]:
        for place, (lat, lng) in KNOWN_PLACES.items():
            if re.search(rf"\b{re.escape(place)}\b", low):
                return place.capitalize(), lat, lng
        return None, None, None

    # Straßen-Adresse: "Musterstraße 5", "Am Markt 3", "Hauptstr. 12b"
    _ADDRESS_RE = re.compile(
        r"\b([A-ZÄÖÜ][\wäöüß.\-]*\s?(?:straße|strasse|str\.?|weg|platz|allee|gasse|ring|damm|ufer|chaussee))\s+(\d+\s?[a-z]?)\b",
        re.IGNORECASE,
    )

    def _parse_address(self, text: str) -> str | None:
        m = self._ADDRESS_RE.search(text)
        if m:
            return f"{m.group(1).strip()} {m.group(2).strip()}"
        return None

    # ------------------------------------------------------------------ #
    # Kategorie (über Modul-Keywords)
    # ------------------------------------------------------------------ #
    def _parse_category(self, low: str) -> tuple[str, float]:
        for module in registry.modules:
            for kw in module.keywords:
                if kw in low:
                    category = module.event_categories[0] if module.event_categories else module.key
                    return category, 0.88
        # Fitness-/Sport-Heuristik
        if re.search(r"\b(gelaufen|lauf|joggen|gejoggt|km|fahrrad|geradelt)\b", low):
            return "sport", 0.8
        return "event", 0.6

    # ------------------------------------------------------------------ #
    # Entities (Tiere, Länder aus Modulen)
    # ------------------------------------------------------------------ #
    def _parse_entities(self, low: str) -> list[ExtractedEntity]:
        found: list[ExtractedEntity] = []
        for module in registry.modules:
            for name in module.known_entity_names:
                if re.search(rf"\b{re.escape(name.lower())}\b", low):
                    attrs: dict = {}
                    if module.key == "animal":
                        attrs = {"species": name.capitalize(), "wild": True}
                    elif module.key == "country":
                        attrs = {}
                    found.append(
                        ExtractedEntity(type=module.key, name=name.capitalize(), attributes=attrs)
                    )
        # Duplikate (gleicher Typ+Name) entfernen
        unique: dict[tuple[str, str], ExtractedEntity] = {}
        for e in found:
            unique[(e.type, e.name.lower())] = e
        return list(unique.values())

    # ------------------------------------------------------------------ #
    # Titel
    # ------------------------------------------------------------------ #
    def _make_title(self, text, entities, location, category) -> str:
        animal = next((e for e in entities if e.type == "animal"), None)
        if animal and location:
            return f"{animal.name} in {location} gesehen"
        if animal:
            return f"{animal.name} gesehen"
        if category == "trip" and location:
            return f"Reise nach {location}"
        if category == "sport":
            return "Sportliche Aktivität"
        # Fallback: erste ~6 Wörter
        words = text.split()
        return " ".join(words[:8]) + ("…" if len(words) > 8 else "")

    # ------------------------------------------------------------------ #
    # F1: Tages-Zusammenfassung (Vorschlag)
    # ------------------------------------------------------------------ #
    # Der Mock ist kein Sprachmodell und tut auch nicht so. Er baut ein
    # **Gerüst**: Datum als Überschrift, die Stichpunkte darunter, ein Satz
    # zum Schreiben. Das ist offline verlässlich (Tests, AI_PROVIDER=mock)
    # und ehrlicher als ein erfundener Fließtext — der Nutzer sieht sofort,
    # dass hier noch nichts formuliert wurde.
    def summarize_day(self, day: date, lines: list[str]) -> str | None:
        if not lines:
            return None
        head = f"{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.%Y')}"
        body = "\n".join(f"- {line}" for line in lines)
        return f"## {head}\n\n{body}\n\n*(Gerüst aus den Ereignissen des Tages — frei überschreiben.)*"
