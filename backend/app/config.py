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

    # Embeddings — **ohne Verbraucher.** Die Suche ist reiner Volltext, seit
    # Anmerkung 121 die semantische ausgebaut hat; `events.embedding` und
    # `_run_embeddings` stehen für eine spätere Suche IN der Datenbank
    # (pgvector). Was hier entsteht, liest bis dahin nichts.
    openai_embed_model: str = ""
    # Eigener Endpoint für Embeddings (leer = openai_base_url). So können
    # Embeddings lokal laufen, während der Chat zu einem Cloud-Anbieter geht.
    openai_embed_base_url: str = ""
    openai_embed_api_key: str = ""
    # Modell-spezifische Präfixe. bge-m3 (empfohlen): leer lassen.
    # nomic-embed-text braucht "search_query: " / "search_document: ".
    openai_embed_query_prefix: str = ""
    openai_embed_doc_prefix: str = ""
    # `semantic_min_similarity` stand hier bis zur Release-Durchsicht: die
    # Mindest-Ähnlichkeit der semantischen Suche, die es seit Anmerkung 121
    # nicht mehr gibt. Gelesen hat sie danach nichts mehr — sie stand nur noch
    # in `.env.example`, in der Compose und in DEPLOY.md und versprach dort
    # eine Funktion. **Ein Schalter ohne Verbraucher ist eine Zusage**, und
    # zwar die teuerste Sorte: er kostet nichts und wirkt trotzdem.

    # R1a: Beim ersten Start ein erfundenes Leben anlegen (`app/demo/`) —
    # dreißig Jahre mit Reisen, Wohnorten, Wetter und Erfolgen. Nur im
    # dev-Modus und nur, solange das Konto noch keine Ereignisse hat.
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
    #   AUTH_MODE=dev   -> kein Login, fester Dev-User (lokale Entwicklung)
    #   AUTH_MODE=oidc  -> Login über den OIDC-Provider
    #   AUTH_MODE=local -> E-Mail + Passwort, ohne Identitätsanbieter (A35);
    #                      erster registrierter Nutzer wird Admin
    # ------------------------------------------------------------------ #
    auth_mode: str = "dev"  # "dev" | "oidc" | "local"
    # Anmerkung 208 (R1d): `AUTH_MODE=dev` heißt KEIN Login — wer die Adresse
    # kennt, ist angemeldet, und zwar als der Nutzer, dem alles gehört. Das ist
    # für die lokale Entwicklung richtig und in einer erreichbaren Instanz eine
    # offene Tür. Der Start bricht deshalb ab, wenn die Instanz nach Produktion
    # AUSSIEHT (siehe `app/startup_checks.py`).
    #
    # Diese Schalter ist die ausdrückliche Ausnahme, und sie hat einen echten
    # Anwendungsfall: eine öffentliche DEMO-Instanz mit `SEED_DEMO=true`, in der
    # ohne Login jeder das erfundene Leben ansehen soll. Sie heißt nach ihrer
    # Wirkung, nicht nach ihrem Anlass — „für die Demo" wäre in einem Jahr die
    # Begründung für etwas ganz anderes.
    dev_auth_allow_public: bool = False
    # A27: Anzeigename des Providers für den Login-Screen (rein kosmetisch);
    # leer = neutraler SSO-Text, damit nichts Fremdes hart verdrahtet ist
    oidc_provider_name: str = ""
    oidc_issuer: str = ""  # Basis-URL des Providers, z. B. https://id.example.com
    oidc_client_id: str = ""
    oidc_client_secret: str = ""  # leer bei Public Client (PKCE reicht)
    # Anmerkung 209: Für WEN ein Bearer-Token ausgestellt sein muss (`aud`).
    # Leer = die eigene Client-ID, und das ist der Normalfall. Nur setzen, wenn
    # der Provider Access-Token auf eine Ressource statt auf den Client
    # ausstellt — sonst lehnt der Bearer-Pfad jedes Token ab.
    oidc_audience: str = ""
    # Basis-URL, unter der Life-Dash erreichbar ist (für die Redirect-URI)
    public_base_url: str = "http://127.0.0.1:8000"
    # Secret zum Signieren des Session-Cookies — in Produktion ÄNDERN!
    session_secret: str = "dev-secret-change-me"
    session_max_age_days: int = 30


settings = Settings()
