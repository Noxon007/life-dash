"""Anwendungs-Konfiguration (aus .env / Umgebungsvariablen)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./lifedash.db"
    ai_provider: str = "mock"  # "mock" | "openai"

    # OpenAI-kompatibler Endpoint — welcher Anbieter dahintersteht, ist der App
    # egal. Beispiele (keine Empfehlung, nur Formate):
    #   LM Studio: http://localhost:1234/v1  ·  Ollama: http://localhost:11434/v1
    #   OpenAI:    https://api.openai.com/v1
    #   Gemini:    https://generativelanguage.googleapis.com/v1beta/openai
    openai_base_url: str = "http://localhost:1234/v1"
    openai_api_key: str = "not-needed"
    openai_model: str = "local-model"

    # Embeddings für semantische Suche (nur mit OpenAI-kompatiblem Endpoint).
    # Leer lassen -> keine Embeddings, Suche fällt auf Volltext zurück.
    openai_embed_model: str = ""
    # Eigener Endpoint für Embeddings (leer = openai_base_url). So können
    # Embeddings lokal laufen, während der Chat zu einem Cloud-Anbieter geht.
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

    # F15: Verzeichnis für hochgeladene Bilder. ACHTUNG — hier liegen die
    # einzigen Daten, die der JSON-Export NICHT enthalten kann: eigenes
    # Docker-Volume, eigene Sicherung (siehe DEPLOY.md).
    media_dir: Path = BASE_DIR / "media"
    # Obergrenze je Datei. Handyfotos liegen bei 3–8 MB; 25 MB lassen auch
    # Kamera-JPEGs zu, ohne dass ein Fehlgriff die Platte füllt.
    media_max_mb: int = 25
    # Kantenlänge der serverseitig erzeugten Vorschau (Timeline, Druck)
    media_thumb_px: int = 640

    # ------------------------------------------------------------------ #
    # Auth: Multi-User via OIDC — funktioniert mit jedem standardkonformen
    # Provider (Authentik, Keycloak, Pocket ID, Zitadel, Auth0, ...).
    #   AUTH_MODE=dev  -> kein Login, fester Dev-User (lokale Entwicklung)
    #   AUTH_MODE=oidc -> Login über den OIDC-Provider
    # ------------------------------------------------------------------ #
    auth_mode: str = "dev"  # "dev" | "oidc"
    # A27: Anzeigename des Providers für den Login-Screen (rein kosmetisch);
    # leer = neutraler SSO-Text, damit nichts Fremdes hart verdrahtet ist
    oidc_provider_name: str = ""
    oidc_issuer: str = ""  # Basis-URL des Providers, z. B. https://id.example.com
    oidc_client_id: str = ""
    oidc_client_secret: str = ""  # leer bei Public Client (PKCE reicht)
    # Basis-URL, unter der Life-Dash erreichbar ist (für die Redirect-URI)
    public_base_url: str = "http://127.0.0.1:8000"
    # Secret zum Signieren des Session-Cookies — in Produktion ÄNDERN!
    session_secret: str = "dev-secret-change-me"
    session_max_age_days: int = 30


settings = Settings()
