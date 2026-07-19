"""Anwendungs-Konfiguration (aus .env / Umgebungsvariablen)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./lifedash.db"
    ai_provider: str = "mock"  # "mock" | "openai"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # OpenAI-kompatibler Endpoint (LM Studio, Ollama /v1, OpenAI, Gemini, ...)
    #   LM Studio: http://localhost:1234/v1  ·  Ollama: http://localhost:11434/v1
    #   Gemini:    https://generativelanguage.googleapis.com/v1beta/openai
    openai_base_url: str = "http://localhost:1234/v1"
    openai_api_key: str = "not-needed"
    openai_model: str = "local-model"

    # Embeddings für semantische Suche (nur mit OpenAI-kompatiblem Endpoint).
    # Leer lassen -> keine Embeddings, Suche fällt auf Volltext zurück.
    openai_embed_model: str = ""
    # Eigener Endpoint für Embeddings (leer = openai_base_url). So können
    # Embeddings lokal bleiben (Ollama), während der Chat z. B. zu Gemini geht.
    openai_embed_base_url: str = ""
    openai_embed_api_key: str = ""
    # Modell-spezifische Präfixe. bge-m3 (empfohlen): leer lassen.
    # nomic-embed-text braucht "search_query: " / "search_document: ".
    openai_embed_query_prefix: str = ""
    openai_embed_doc_prefix: str = ""
    # Mindest-Ähnlichkeit (Cosine) für semantische Treffer (kalibriert für bge-m3)
    semantic_min_similarity: float = 0.4

    seed_demo: bool = True
    confidence_review_threshold: float = 0.75

    # Log-Level für den lifedash.*-Logger-Baum (DEBUG | INFO | WARNING | ERROR)
    log_level: str = "INFO"

    # Geocoding (Nominatim) für präzise Adressen bis Straße/Hausnummer
    geocoding_enabled: bool = True
    # Optionaler Nominatim-kompatibler Dienst statt des öffentlichen OSM-
    # Endpoints (drosselt auf 1 Anfrage/s und liefert bei Volumen 429).
    # Z. B. LocationIQ (kostenlos 5000 Anfragen/Tag, 2/s):
    #   GEOCODER_BASE_URL=https://eu1.locationiq.com/v1
    #   GEOCODER_API_KEY=pk....
    geocoder_base_url: str = "https://nominatim.openstreetmap.org"
    geocoder_api_key: str = ""

    # Verzeichnis mit den YAML-Modul-Definitionen
    modules_dir: Path = BASE_DIR / "modules"

    # Verzeichnis des Frontends (wird vom Backend statisch ausgeliefert)
    frontend_dir: Path = BASE_DIR.parent / "frontend"

    # ------------------------------------------------------------------ #
    # Auth: Multi-User via OIDC (Pocket ID)
    #   AUTH_MODE=dev  -> kein Login, fester Dev-User (lokale Entwicklung)
    #   AUTH_MODE=oidc -> Login über den OIDC-Provider (Pocket ID)
    # ------------------------------------------------------------------ #
    auth_mode: str = "dev"  # "dev" | "oidc"
    oidc_issuer: str = ""  # z. B. https://id.example.home (Pocket ID Basis-URL)
    oidc_client_id: str = ""
    oidc_client_secret: str = ""  # leer bei Public Client (PKCE reicht)
    # Basis-URL, unter der Life-Dash erreichbar ist (für die Redirect-URI)
    public_base_url: str = "http://127.0.0.1:8000"
    # Secret zum Signieren des Session-Cookies — in Produktion ÄNDERN!
    session_secret: str = "dev-secret-change-me"
    session_max_age_days: int = 30


settings = Settings()
