"""Auth: Multi-User via OIDC (Pocket ID) + Dev-Modus.

Zwei Betriebsarten (AUTH_MODE):
  dev  -> kein Login; ein fester Dev-User (Admin). Für lokale Entwicklung.
  oidc -> Authorization Code Flow mit PKCE gegen den OIDC-Provider
          (Pocket ID). Das Backend führt den Flow aus, validiert das
          ID-Token gegen den JWKS-Endpoint und setzt ein signiertes
          HttpOnly-Session-Cookie. Nutzer werden beim ersten Login
          automatisch angelegt (JIT-Provisioning über den sub-Claim).

Der erste jemals angelegte Nutzer wird Admin und "adoptiert" Altdaten
ohne user_id (Single-User-Bestand).
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import urllib.request

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, get_db
from app.migrate import adopt_orphan_rows
from app.models import User, UserRole

SESSION_COOKIE = "lifedash_session"
STATE_COOKIE = "lifedash_oidc_state"

# --------------------------------------------------------------------------- #
# OIDC-Discovery & JWKS (gecacht)
# --------------------------------------------------------------------------- #
_discovery_cache: dict | None = None
_jwks_client: jwt.PyJWKClient | None = None


def oidc_discovery() -> dict:
    """Lädt (einmalig) die OIDC-Konfiguration des Providers."""
    global _discovery_cache
    if _discovery_cache is None:
        if not settings.oidc_issuer:
            raise HTTPException(500, "OIDC_ISSUER ist nicht konfiguriert")
        url = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
        with urllib.request.urlopen(url, timeout=10) as resp:
            _discovery_cache = json.loads(resp.read().decode("utf-8"))
    return _discovery_cache


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(oidc_discovery()["jwks_uri"])
    return _jwks_client


def validate_oidc_token(token: str, *, verify_aud: bool = True) -> dict:
    """Validiert ein vom Provider signiertes JWT (ID- oder Access-Token)."""
    key = _jwks().get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        key,
        algorithms=["RS256", "ES256"],
        issuer=oidc_discovery()["issuer"],
        audience=settings.oidc_client_id if verify_aud else None,
        options={"verify_aud": verify_aud},
    )


# --------------------------------------------------------------------------- #
# PKCE & Session-Cookies (HS256-signierte Kurz-JWTs)
# --------------------------------------------------------------------------- #
def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


def sign_cookie(payload: dict, max_age_seconds: int) -> str:
    data = dict(payload)
    data["exp"] = int(time.time()) + max_age_seconds
    return jwt.encode(data, settings.session_secret, algorithm="HS256")


def read_cookie(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.session_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def session_max_age() -> int:
    return settings.session_max_age_days * 86400


def cookie_secure() -> bool:
    """Secure-Flag für Cookies, sobald Life-Dash über HTTPS erreichbar ist.

    Hinter einem Reverse Proxy mit TLS (Produktion) ist PUBLIC_BASE_URL eine
    https-URL -> Cookies nur verschlüsselt übertragen. Lokal (http) aus."""
    return settings.public_base_url.lower().startswith("https")


# --------------------------------------------------------------------------- #
# Nutzer-Verwaltung (JIT-Provisioning)
# --------------------------------------------------------------------------- #
def get_or_create_user(
    db: Session, *, sub: str, email: str | None = None, name: str | None = None
) -> User:
    user = db.query(User).filter(User.oidc_subject == sub).first()
    if user:
        # Profil-Claims aktuell halten
        if email and user.email != email:
            user.email = email
        if name and user.display_name != name:
            user.display_name = name
        db.commit()
        return user

    is_first = db.query(User).count() == 0
    user = User(
        oidc_subject=sub,
        email=email,
        display_name=name,
        role=UserRole.admin if is_first else UserRole.user,
    )
    db.add(user)
    db.commit()
    if is_first:
        adopt_orphan_rows(engine, user.id)
    return user


def get_dev_user(db: Session) -> User:
    return get_or_create_user(
        db, sub="dev-user", email="dev@localhost", name="Dev-User"
    )


# --------------------------------------------------------------------------- #
# FastAPI-Dependencies
# --------------------------------------------------------------------------- #
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Liefert den angemeldeten Nutzer — 401, wenn nicht angemeldet."""
    if settings.auth_mode == "dev":
        return get_dev_user(db)

    # 1) Session-Cookie (Browser)
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        data = read_cookie(raw)
        if data and (uid := data.get("uid")):
            user = db.get(User, uid)
            if user:
                return user

    # 2) Bearer-Token (API-Clients): direkt vom Provider signiertes JWT
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            claims = validate_oidc_token(auth_header[7:], verify_aud=False)
        except Exception:  # jede Validierungspanne ist 401
            raise HTTPException(401, "Ungültiges Token")
        return get_or_create_user(
            db,
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name") or claims.get("preferred_username"),
        )

    raise HTTPException(401, "Nicht angemeldet")


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(403, "Nur für Administratoren")
    return user
