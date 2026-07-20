"""Auth-Endpoints: OIDC-Login, Session, aktueller Nutzer."""
from __future__ import annotations

import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import auth
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import (AdminCreateUser, AuthConfig, LocalLogin, LocalRegister,
                         PasswordChange, UserRead)
from app.services import geocode as geocode_svc

log = logging.getLogger("lifedash.auth")

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _redirect_uri() -> str:
    return settings.public_base_url.rstrip("/") + "/api/auth/callback"


@router.get("/config", response_model=AuthConfig)
def auth_config(db: Session = Depends(get_db)) -> AuthConfig:
    """Sagt dem Frontend, ob und wie ein Login nötig ist."""
    needs_setup = (settings.auth_mode == "local"
                   and db.query(User).count() == 0)
    return AuthConfig(mode=settings.auth_mode,
                      provider_name=settings.oidc_provider_name,
                      needs_setup=needs_setup)


# --------------------------------------------------------------------------- #
# A35 — lokale Konten (nur bei AUTH_MODE=local)
# --------------------------------------------------------------------------- #
def _require_local_mode() -> None:
    if settings.auth_mode != "local":
        raise HTTPException(404, "Lokale Konten sind nicht aktiv (AUTH_MODE=local)")


def _session_response(user: User) -> JSONResponse:
    resp = JSONResponse({"id": user.id, "email": user.email,
                         "display_name": user.display_name, "role": user.role.value})
    resp.set_cookie(
        auth.SESSION_COOKIE,
        auth.sign_cookie({"uid": user.id}, auth.session_max_age()),
        max_age=auth.session_max_age(),
        httponly=True,
        samesite="lax",
        secure=auth.cookie_secure(),
    )
    return resp


@router.post("/local/register")
def local_register(payload: LocalRegister, db: Session = Depends(get_db)) -> JSONResponse:
    """Legt das ERSTE Konto an (wird Admin). Danach ist die öffentliche
    Registrierung zu — weitere Konten legt ein Admin an. So wird aus einer
    frisch aufgesetzten Instanz nicht versehentlich eine offene Anmeldung."""
    _require_local_mode()
    if db.query(User).count() > 0:
        raise HTTPException(
            403, "Es gibt bereits Konten — neue Konten legt ein Administrator an.")
    if "@" not in payload.email:
        raise HTTPException(400, "Bitte eine gültige E-Mail-Adresse angeben")
    user = auth.create_local_user(db, email=payload.email, password=payload.password,
                                  name=payload.display_name)
    log.info("Lokales Erst-Konto angelegt (Admin): %s", user.email)
    return _session_response(user)


@router.post("/local/login")
def local_login(payload: LocalLogin, db: Session = Depends(get_db)) -> JSONResponse:
    """Anmeldung mit E-Mail und Passwort."""
    _require_local_mode()
    locked = auth.login_locked_for(payload.email)
    if locked:
        raise HTTPException(
            429, f"Zu viele Fehlversuche — bitte in {locked // 60 + 1} Minuten erneut.")
    user = auth.authenticate_local(db, payload.email, payload.password)
    if user is None:
        auth.note_login_failure(payload.email)
        # Bewusst dieselbe Meldung für „E-Mail unbekannt" und „Passwort falsch".
        raise HTTPException(401, "E-Mail oder Passwort ist falsch")
    auth.clear_login_failures(payload.email)
    log.info("Lokale Anmeldung: %s", user.email)
    return _session_response(user)


@router.post("/local/change-password")
def local_change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Ändert das eigene Passwort (nur für lokale Konten)."""
    _require_local_mode()
    from app.services import password as pw

    if not user.password_hash or not pw.verify_password(payload.current_password,
                                                        user.password_hash):
        raise HTTPException(400, "Das aktuelle Passwort stimmt nicht")
    user.password_hash = pw.hash_password(payload.new_password)
    db.commit()
    log.info("Passwort geändert: %s", user.email)
    return {"changed": True}


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


# --------------------------------------------------------------------------- #
# Unkritische UI-Einstellungen des eigenen Kontos. Bewusst eine Whitelist —
# User.settings wird später auch Secrets (Immich-Key, PSN-Token) enthalten,
# die NIE ans Frontend gehen.
# --------------------------------------------------------------------------- #
# Karten-Clustering (A18): ab wie vielen Punkten gebündelt wird. Der Rahmen
# schützt die Performance — über MAX einzelnen Markern friert der Browser
# nach großen Timeline-Importen ein (deshalb gab es früher den 300er-Deckel).
CLUSTER_MIN_FLOOR, CLUSTER_MIN_CEIL, CLUSTER_MIN_DEFAULT = 10, 300, 50


def cluster_min_for(user: User) -> int:
    raw = (user.settings or {}).get("map_cluster_min", CLUSTER_MIN_DEFAULT)
    try:
        return max(CLUSTER_MIN_FLOOR, min(CLUSTER_MIN_CEIL, int(raw)))
    except (TypeError, ValueError):
        return CLUSTER_MIN_DEFAULT


def _settings_view(user: User) -> dict:
    from app.modules.registry import registry

    prefs = user.settings or {}
    tracked = prefs.get("tracked_modules")
    return {
        "place_name_parts": geocode_svc.parts_for(user),
        # F10: UI-Sprache — steuert auch, in welcher Sprache Ortsnamen
        # aufgelöst werden (Accept-Language beim Geocoding)
        "lang": geocode_svc.lang_for(user),
        "map_cluster_min": cluster_min_for(user),
        # A15: None/fehlend = noch nie gewählt -> Frontend zeigt Onboarding
        "tracked_modules": tracked if isinstance(tracked, list) else None,
        "all_modules": registry.keys(),
        # A22: Nachtplan pro Job-Typ, z. B. {"weather": {"enabled": true, "hour": 3}}
        "job_schedule": prefs.get("job_schedule") or {},
        # P2.1: Immich-Zugang. Der API-SCHLÜSSEL WIRD NIE ZURÜCKGEGEBEN —
        # nur, ob einer hinterlegt ist. Ein Schlüssel, der bei jedem Laden
        # der Einstellungsseite durchs Netz geht und im Browser steht, ist
        # ein Schlüssel, den man auch weglassen könnte.
        "immich": {
            "url": (prefs.get("immich") or {}).get("url") or "",
            "has_key": bool((prefs.get("immich") or {}).get("api_key")),
        },
    }


@router.get("/me/settings")
def my_settings(user: User = Depends(get_current_user)) -> dict:
    """Anzeige-Einstellungen: Ortsnamen-Bausteine, Karten-Cluster-Schwelle."""
    return _settings_view(user)


@router.patch("/me/settings")
def update_my_settings(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Ändert Anzeige-Einstellungen (nur Whitelist-Schlüssel)."""
    prefs = dict(user.settings or {})
    if "place_name_parts" in payload:
        raw = payload["place_name_parts"]
        if (not isinstance(raw, list)
                or not any(p in geocode_svc.PLACE_NAME_PARTS for p in raw)):
            raise HTTPException(
                400, "place_name_parts: mindestens ein gültiger Baustein "
                     f"aus {list(geocode_svc.PLACE_NAME_PARTS)}")
        prefs["place_name_parts"] = geocode_svc.sanitize_parts(raw)
    if "lang" in payload:
        raw = payload["lang"]
        if raw not in geocode_svc.ACCEPT_LANGUAGE_BY_LANG:
            raise HTTPException(
                400, "lang: unterstützt werden "
                     f"{sorted(geocode_svc.ACCEPT_LANGUAGE_BY_LANG)}")
        prefs["lang"] = raw
    if "map_cluster_min" in payload:
        try:
            wanted = int(payload["map_cluster_min"])
        except (TypeError, ValueError):
            raise HTTPException(400, "map_cluster_min: ganze Zahl erwartet")
        # In den erlaubten Rahmen einpassen statt abzulehnen
        prefs["map_cluster_min"] = max(CLUSTER_MIN_FLOOR,
                                       min(CLUSTER_MIN_CEIL, wanted))
    if "tracked_modules" in payload:
        from app.modules.registry import registry

        raw = payload["tracked_modules"]
        if not isinstance(raw, list):
            raise HTTPException(400, "tracked_modules: Liste von Modul-Keys erwartet")
        prefs["tracked_modules"] = [k for k in registry.keys() if k in raw]
    if "job_schedule" in payload:
        raw = payload["job_schedule"]
        if not isinstance(raw, dict):
            raise HTTPException(400, "job_schedule: Objekt erwartet")
        from app.routers.jobs import SERVER_JOB_TYPES

        sched = {}
        for jtype, cfg in raw.items():
            if jtype not in SERVER_JOB_TYPES or not isinstance(cfg, dict):
                continue
            try:
                hour = max(0, min(23, int(cfg.get("hour", 3))))
            except (TypeError, ValueError):
                hour = 3
            sched[jtype] = {"enabled": bool(cfg.get("enabled")), "hour": hour}
        prefs["job_schedule"] = sched
    if "immich" in payload:
        raw = payload["immich"]
        if not isinstance(raw, dict):
            raise HTTPException(400, "immich: Objekt mit url/api_key erwartet")
        current = dict(prefs.get("immich") or {})
        if "url" in raw:
            url = (raw["url"] or "").strip().rstrip("/")
            if url and not url.startswith(("http://", "https://")):
                raise HTTPException(400, "immich.url: muss mit http:// oder https:// beginnen")
            current["url"] = url
        # Leerer Schlüssel = unverändert lassen. Sonst würde jedes Speichern
        # der Seite den Schlüssel löschen, weil das Feld ihn nie anzeigt.
        if raw.get("api_key"):
            current["api_key"] = str(raw["api_key"]).strip()
        if raw.get("clear"):
            current = {}
        prefs["immich"] = current

    if prefs != (user.settings or {}):
        user.settings = prefs
        db.commit()
    return _settings_view(user)


@router.post("/me/settings/immich/test")
def test_immich(
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """P2.1: Verbindungstest gegen Immich.

    Ohne ihn merkt der Nutzer einen Tippfehler erst daran, dass ein Foto-Lauf
    nichts findet — und sucht die Ursache an der falschen Stelle. Getestet
    wird gegen die übergebenen Werte, sonst gegen die gespeicherten.
    """
    from app.services import immich as immich_api

    url = (payload.get("url") or "").strip().rstrip("/")
    key = (payload.get("api_key") or "").strip()
    if not (url and key):
        stored = immich_api.config_for(user)
        if stored is None:
            raise HTTPException(400, "Immich ist noch nicht eingerichtet")
        url, key = url or stored[0], key or stored[1]
    try:
        return immich_api.check(url, key)
    except immich_api.ImmichError as exc:
        raise HTTPException(400, str(exc)) from exc


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
