"""Modul-Registry: lädt die YAML-Modul-Definitionen (Trackables).

Ein Modul beschreibt deklarativ einen trackbaren Typ (Reisen, Tiere, Länder ...).
Neue Module = neue YAML-Datei, kein Code-Umbau.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import settings


@dataclass
class Module:
    key: str
    label: str
    icon: str | None = None
    color: str | None = None
    # A7: alles Fürs-Frontend-Nötige kommt aus dem YAML — neues Modul = eine Datei
    emoji: str | None = None
    category_labels: dict = field(default_factory=dict)  # category -> deutsches Label
    compendium: bool = False       # eigener Kompendium-Reiter (Entity-Typ = key)
    prompt_rules: str | None = None  # Regeln für den KI-Extraktions-Prompt
    event_categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    known_entities: dict | list | None = None
    entity_schema: dict = field(default_factory=dict)
    statistics: list[dict] = field(default_factory=list)
    compendium_view: dict = field(default_factory=dict)
    # F6: Erfolge deklarativ — je Eintrag eine Metrik + Schwellwerte
    achievements: list[dict] = field(default_factory=list)

    @property
    def known_entity_names(self) -> list[str]:
        """Namen bekannter Entities, egal ob als Liste oder Dict definiert."""
        if isinstance(self.known_entities, dict):
            return list(self.known_entities.keys())
        if isinstance(self.known_entities, list):
            return [str(x) for x in self.known_entities]
        return []


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}

    def load(self, modules_dir: Path) -> None:
        self._modules.clear()
        if not modules_dir.exists():
            return
        for path in sorted(modules_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            module = Module(**data)
            self._modules[module.key] = module

    @property
    def modules(self) -> list[Module]:
        return list(self._modules.values())

    def get(self, key: str) -> Module | None:
        return self._modules.get(key)

    def category_to_module(self, category: str) -> Module | None:
        for module in self._modules.values():
            if category in module.event_categories:
                return module
        return None

    def keys(self) -> list[str]:
        return list(self._modules.keys())

    def prompt_section(self, tracked: list[str] | None = None) -> str:
        """A7/A15: Modul-Regeln für den KI-Prompt — nur getrackte Module.
        tracked=None bedeutet: alle Module aktiv."""
        mods = [m for m in self.modules
                if m.prompt_rules and (tracked is None or m.key in tracked)]
        return "\n".join(m.prompt_rules.strip() for m in mods)


registry = ModuleRegistry()


def load_modules() -> None:
    registry.load(settings.modules_dir)
