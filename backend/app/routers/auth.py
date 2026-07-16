"""Auth-Endpoints: OIDC-Login (Pocket ID), Session, aktueller Nutzer."""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import auth
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import AuthConfig, UserRead
from app.services import geocode as geocode_svc

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _redirect_uri() -> str:
    return settings.public_base_url.rstrip("/") + "/api/auth/callback"


@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    """Sagt dem Frontend, ob ein Login nötig ist."""
    return AuthConfig(mode=settings.auth_mode)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


# --------------------------------------------------------------------------- #
# Unkritische UI-Einstellungen des eigenen Kontos. Bewusst eine Whitelist —
# User.settings wird später auch Secrets (Immich-Key, PSN-Token) enthalten,
# die NIE ans Frontend gehen.
# --------------------------------------------------------------------------- #
@router.get("/me/settings")
def my_settings(user: User = Depends(get_current_user)) -> dict:
    """Anzeige-Einstellungen: Bausteine für aufgelöste Ortsnamen."""
    return {"place_name_parts": geocode_svc.parts_for(user)}


@router.patch("/me/settings")
def update_my_settings(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Ändert Anzeige-Einstellungen (nur Whitelist-Schlüssel)."""
    if "place_name_parts" in payload:
        raw = payload["place_name_parts"]
        if (not isinstance(raw, list)
                or not any(p in geocode_svc.PLACE_NAME_PARTS for p in raw)):
            raise HTTPException(
                400, "place_name_parts: mindestens ein gültiger Baustein "
                     f"aus {list(geocode_svc.PLACE_NAME_PARTS)}")
        prefs = dict(user.settings or {})
        prefs["place_name_parts"] = geocode_svc.sanitize_parts(raw)
        user.settings = prefs
        db.commit()
    return {"place_name_parts": geocode_svc.parts_for(user)}


@router.get("/login")
def login() -> RedirectResponse:
    """Startet den OIDC Authorization Code Flow (mit PKCE)."""
    if settings.auth_mode != "oidc":
        return RedirectResponse("/")
    disco = auth.oidc_discovery()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = auth.make_pkce()

    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": _redirect_uri(),
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = disco["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)
    resp = RedirectResponse(url)
    resp.set_cookie(
        auth.STATE_COOKIE,
        auth.sign_cookie({"state": state, "nonce": nonce, "verifier": verifier}, 600),
        max_age=600,
        httponly=True,
        samesite="lax",
    )
    return resp


@router.get("/callback")
def callback(request: Request, code: str, state: str, db: Session = Depends(get_db)) -> RedirectResponse:
    """OIDC-Redirect zurück: Code gegen Token tauschen, Nutzer anlegen, Session setzen."""
    raw = request.cookies.get(auth.STATE_COOKIE)
    data = auth.read_cookie(raw) if raw else None
    if not data or data.get("state") != state:
        raise HTTPException(400, "Ungültiger OIDC-State (Login bitte erneut starten)")

    disco = auth.oidc_discovery()
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(),
        "client_id": settings.oidc_client_id,
        "code_verifier": data["verifier"],
    }
    if settings.oidc_client_secret:
        payload["client_secret"] = settings.oidc_client_secret
    req = urllib.request.Request(
        disco["token_endpoint"],
        data=urllib.parse.urlencode(payload).encode(),
        headers={**auth.HTTP_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tokens = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")[:300]
        raise HTTPException(502, f"Token-Austausch fehlgeschlagen: {detail}")

    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(502, "Provider lieferte kein ID-Token")
    claims = auth.validate_oidc_token(id_token)
    if claims.get("nonce") != data.get("nonce"):
        raise HTTPException(400, "Ungültige Nonce")

    user = auth.get_or_create_user(
        db,
        sub=claims["sub"],
        email=claims.get("email"),
        name=claims.get("name") or claims.get("preferred_username"),
    )

    resp = RedirectResponse("/")
    resp.delete_cookie(auth.STATE_COOKIE)
    resp.set_cookie(
        auth.SESSION_COOKIE,
        auth.sign_cookie({"uid": user.id}, auth.session_max_age()),
        max_age=auth.session_max_age(),
        httponly=True,
        samesite="lax",
    )
    return resp


@router.post("/logout")
@router.get("/logout")
def logout() -> RedirectResponse:
    resp = RedirectResponse("/")
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp
