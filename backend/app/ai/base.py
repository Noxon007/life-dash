"""Abstraktes KI-Provider-Interface.

Jeder Provider (Mock, später Ollama) liefert aus einem Roh-Text eine Liste
strukturierter Event-Vorschläge (Stufe 2). So bleibt die KI austauschbar.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ExtractedEntity:
    type: str            # animal|country|...
    name: str
    attributes: dict = field(default_factory=dict)


@dataclass
class ExtractedEvent:
    title: str
    description: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    date_precision: str = "day"           # exact|day|month|season|year|decade
    category: str = "event"
    confidence: float = 0.8
    location_name: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    entities: list[ExtractedEntity] = field(default_factory=list)


class ProviderUnavailable(Exception):
    """KI-Endpoint nicht erreichbar oder gedrosselt (Rate-Limit/Quota).

    Der Aufrufer entscheidet: Einzel-Ingest legt ein Roh-Fallback-Event an
    (Capture first), Batch-Neuberechnung bricht ab und behält den Altbestand.
    """


class LLMProvider(ABC):
    """Schnittstelle für alle KI-Provider."""

    @abstractmethod
    def extract(self, raw_text: str) -> list[ExtractedEvent]:
        """Extrahiert strukturierte Event-Vorschläge aus Roh-Text."""
        raise NotImplementedError

    def embed(self, text: str, kind: str = "document") -> list[float] | None:
        """Vektor-Embedding für semantische Suche.

        kind: "document" (zu indexierender Text) oder "query" (Suchanfrage) —
        manche Modelle (z. B. nomic-embed-text) erwarten dafür Präfixe.
        Default: None (Provider kann keine Embeddings) -> die Suche
        fällt automatisch auf Volltext zurück.
        """
        return None
