"""KI-Provider — Interface + Factory."""
from app.ai.base import ExtractedEntity, ExtractedEvent, LLMProvider
from app.ai.mock import MockProvider
from app.config import settings


def get_provider() -> LLMProvider:
    """Liefert den konfigurierten KI-Provider.

    MVP: nur "mock". Später: "ollama" (gleiche Schnittstelle).
    """
    if settings.ai_provider == "mock":
        return MockProvider()
    if settings.ai_provider in ("openai", "openai_compat", "ollama", "lmstudio"):
        # Lazy-Import, damit der Mock-Betrieb keine zusätzlichen Module braucht
        from app.ai.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider()
    raise ValueError(
        f"AI-Provider '{settings.ai_provider}' ist unbekannt. "
        "Nutze AI_PROVIDER=mock oder AI_PROVIDER=openai."
    )


__all__ = ["LLMProvider", "ExtractedEvent", "ExtractedEntity", "get_provider"]
