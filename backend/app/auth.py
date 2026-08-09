"""Auth: Multi-User via OIDC + Dev-Modus.

Zwei Betriebsarten (AUTH_MODE):
  dev  -> kein Login; ein fester Dev-User (Admin). Für lokale Entwicklung.
  oidc -> Authorization Code Flow mit PKCE gegen einen beliebigen
          standardkonformen OIDC-Provider (Authentik, Keycloak, Pocket ID,
          Zitadel, Auth0, ...). Das Backend führt den Flow aus, validiert das
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
import logging
import secrets
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, get_db
from app.migrate import adopt_orphan_rows
from app.models import User, UserRole
from app.version import APP_VERSION

log = logging.getLogger("lifedash.auth")

SESSION_COOKIE = "lifedash_session"
STATE_COOKIE = "lifedash_oidc_state"

# Manche Reverse Proxies / Bot-Filter (Traefik, CrowdSec u. ä.)
# blocken den Default-User-Agent von urllib ("Python-urllib/…") mit HTTP 403.
# Darum bei allen Server-zu-Server-Aufrufen an den OIDC-Provider einen eigenen
# User-Agent senden.
# Der User-Agent nennt die Software (nicht die Instanz) — die Projekt-URL ist
# hier die Identität von Life-Dash selbst und bleibt darum fest verdrahtet.
HTTP_HEADERS = {
    "User-Agent": f"Life-Dash/{APP_VERSION} (+https://github.com/Noxon007/life-dash)",
    "Accept": "application/json",
}

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
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            _discovery_cache = json.loads(resp.read().decode("utf-8"))
    return _discovery_cache


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(oidc_discovery()["jwks_uri"], headers=HTTP_HEADERS)
    return _jwks_client


def bearer_audience() -> str:
    """Für WEN ein Bearer-Token ausgestellt sein muss.

    Anmerkung 209 (offener Punkt aus Anmerkung 200): Der Bearer-Pfad nahm
    bisher jedes Token an, das der Issuer signiert hatte — `verify_aud=False`.
    Solange genau eine Anwendung am Identitätsanbieter hängt, fällt das nicht
    auf; sobald eine zweite dazukommt, ist ein Token, das der Nutzer DIESER
    zweiten Anwendung gegeben hat, hier ein gültiger Login. Das ist der ganze
    Zweck des `aud`-Claims, und er war abgeschaltet.

    Standard ist die eigene Client-ID. `OIDC_AUDIENCE` gibt es, weil manche
    Provider Access-Token auf eine RESSOURCE ausstellen statt auf den Client —
    dann steht dort deren Kennung, und ohne diesen Schalter bliebe nur, die
    Prüfung wieder ganz abzuschalten.
    """
    return (settings.oidc_audience or settings.oidc_client_id).strip()


def validate_oidc_token(token: str, *, verify_aud: bool = True) -> dict:
    """Validiert ein vom Provider signiertes JWT (ID- oder Access-Token)."""
    key = _jwks().get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        key,
        algorithms=["RS256", "ES256"],
        issuer=oidc_discovery()["issuer"],
        audience=bearer_audience() if verify_aud else None,
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
    now = int(time.time())
    data["exp"] = now + max_age_seconds
    # Anmerkung 209: Ausstellungszeit. Ohne sie lässt sich eine Sitzung nicht
    # widerrufen — ein Cookie ohne Alter kann man nur ablaufen lassen.
    data.setdefault("iat", now)
    return jwt.encode(data, settings.session_secret, algorithm="HS256")


def read_cookie(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.session_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def session_max_age() -> int:
    return settings.session_max_age_days * 86400


# --------------------------------------------------------------------------- #
#  Anmerkung 209: Sitzungen widerrufen — ohne Sitzungstabelle
# --------------------------------------------------------------------------- #
# Der dritte offene Punkt aus Anmerkung 200: „Sitzungen nicht widerrufbar, 30
# Tage, Passwortwechsel beendet nichts". Ein gestohlenes Cookie war damit einen
# Monat lang gültig, und die eine Handlung, die ein Mensch in dieser Lage
# ausführt — das Passwort ändern — half nicht.
#
# **Eine Sitzungstabelle wäre die naheliegende und die falsche Antwort.** Sie
# beantwortet „welche Sitzungen gibt es?", und diese Frage stellt hier niemand;
# gestellt wird „gilt diese noch?". Dafür genügt EIN Zeitstempel je Nutzer: das
# Cookie trägt seine Ausstellungszeit, und alles, was älter ist als der Schnitt,
# ist ungültig. Kein Schreibzugriff je Anfrage, keine Tabelle, die wächst, und
# keine zweite Stelle, an der ein Nutzer gelöscht werden muss.
#
# Der Preis steht hier, damit er nicht später als Fehler gemeldet wird: EINZELNE
# Sitzungen lassen sich damit nicht beenden, nur alle. Für ein System mit einem
# Betreiber und ohne Geräteliste ist „überall abmelden" die Handlung, die es
# tatsächlich gibt.
def _naive_utc(epoch: float) -> datetime:
    """Sekunden seit 1970 als NAIVES UTC — die Form, in der diese Spalte liegt.

    `DateTime` ohne Zeitzone auf beiden Datenbanken; ein zeitzonenbehafteter
    Wert auf der einen Seite des Vergleichs und ein nackter auf der anderen
    ist ein `TypeError` in einer Anfrage, die nur beim Widerruf überhaupt
    vorkommt — also der Fehler, den keine Testrunde von selbst sieht.
    """
    return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)


def revoke_sessions(user: User) -> None:
    """Beendet alle laufenden Sitzungen dieses Nutzers.

    Eine Sekunde in die ZUKUNFT, und das ist kein Schmutz: Cookie-`iat` und
    dieser Zeitstempel können in dieselbe Sekunde fallen (Anmelden und sofort
    Passwort ändern), und `iat >= cutoff` ließe das gerade widerrufene Cookie
    stehen. Lieber eine Sekunde zu streng — der Nutzer meldet sich ohnehin neu
    an.
    """
    user.sessions_valid_from = _naive_utc(time.time()) + timedelta(seconds=1)


def session_still_valid(user: User, claims: dict) -> bool:
    cutoff = user.sessions_valid_from
    if cutoff is None:            # nie widerrufen — der Normalfall
        return True
    iat = claims.get("iat")
    # Ein Cookie ohne Ausstellungszeit stammt von vor dieser Änderung. Es gilt
    # als widerrufen: die Alternative wäre, dass genau die alten Sitzungen,
    # derentwegen jemand widerruft, als einzige überleben.
    if not isinstance(iat, (int, float)):
        return False
    # Ein Wert aus der Datenbank kann zeitzonenbehaftet zurückkommen (PostgreSQL
    # mit `timestamptz` in einer Altinstallation) — dann auf dieselbe Form
    # bringen, statt am Vergleich zu scheitern.
    if cutoff.tzinfo is not None:
        cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
    return _naive_utc(iat) >= cutoff


def cookie_secure() -> bool:
    """Secure-Flag für Cookies, sobald Life-Dash über HTTPS erreichbar ist.

    Hinter einem Reverse Proxy mit TLS (Produktion) ist PUBLIC_BASE_URL eine
    https-URL -> Cookies nur verschlüsselt übertragen. Lokal (http) aus."""
    return settings.public_base_url.lower().startswith("https")


def set_auth_cookie(response, name: str, value: str, max_age: int) -> None:
    """Setzt einen Anmelde-Cookie — mit ALLEN Schutzmerkmalen, an einer Stelle.

    Anmerkung 200: Diese Funktion gibt es, weil die Merkmale vorher an jeder
    Setzstelle einzeln aufgezählt waren, und eine Aufzählung, die man
    wiederholt, wird beim Wiederholen kürzer. Der lokale Login trug
    `secure=cookie_secure()`, der OIDC-Rückweg nicht — dieselbe Zusage,
    zweimal geschrieben, eine Hälfte nachgezogen (die wiederkehrende Falle
    „eine Regel an zwei Orten"). Bei OIDC-Betrieb hinter TLS ging das
    Sitzungs-JWT damit auch über eine unverschlüsselte Verbindung mit.

    Wer künftig einen dritten Anmeldeweg baut, ruft das hier und bekommt die
    Merkmale, statt sie sich zu merken.
    """
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,      # kein Zugriff aus JavaScript
        samesite="lax",     # nicht bei fremden Formular-POSTs mitgeschickt
        secure=cookie_secure(),
        path="/",
    )


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
# A35 — lokale Konten (AUTH_MODE=local): E-Mail + Passwort
# --------------------------------------------------------------------------- #
from app.services import password as pw  # noqa: E402

LOCAL_PREFIX = "local:"


def _local_sub(email: str) -> str:
    """Stabiler, eindeutiger Identitätsschlüssel eines lokalen Kontos.

    Über `oidc_subject` (unique) — so erzwingt schon die Datenbank, dass jede
    E-Mail nur einmal existiert, ohne eine zweite Unique-Spalte."""
    return LOCAL_PREFIX + email.strip().lower()


def find_local_user(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.oidc_subject == _local_sub(email)).first()


def create_local_user(db: Session, *, email: str, password: str,
                      name: str | None = None, role: UserRole | None = None) -> User:
    """Legt ein lokales Konto an. Der ERSTE Nutzer überhaupt wird Admin und
    adoptiert Altdaten ohne user_id (wie beim OIDC-Erstlogin)."""
    is_first = db.query(User).count() == 0
    user = User(
        oidc_subject=_local_sub(email),
        email=email.strip(),
        display_name=(name or "").strip() or email.split("@")[0],
        password_hash=pw.hash_password(password),
        role=role or (UserRole.admin if is_first else UserRole.user),
    )
    db.add(user)
    db.commit()
    if is_first:
        adopt_orphan_rows(engine, user.id)
    return user


# In-Prozess-Sperre gegen Passwort-Raten. Bewusst einfach: ein Zähler je
# E-Mail, kein Redis. Bei mehreren Workern gilt sie pro Prozess — als Basis
# gegen Brute Force reicht das; das dokumentiert DEPLOY.md so.
_FAIL_MAX = 5
_LOCK_SECONDS = 900          # 15 Minuten
# email -> (Versuche, Ende des Fensters). **Der Zeitstempel ist beides:** bis
# `_FAIL_MAX` das Ende der laufenden SERIE, danach das Ende der SPERRE. Zwei
# getrennte Zeitstempel wären zwei Antworten auf „ist das noch aktuell?", und
# die eine würde beim Aufräumen vergessen — den Fall hatte diese Datei schon
# (siehe `login_locked_for`).
_fail_state: dict[str, tuple[int, float]] = {}
# Anmerkung 209: Die Tabelle hat eine Grenze. Sie hatte keine — ein Eintrag je
# probierter E-Mail, und probieren darf jeder, der die Anmeldeseite erreicht.
# Ein Wörterbuch, das ein Fremder füllen kann, ist Speicher, den ein Fremder
# vergibt. Die Zahl ist großzügig: 5.000 Einträge sind unter einem Megabyte,
# und eine echte Instanz kommt nie in ihre Nähe.
_FAIL_STATE_MAX = 5000


def login_locked_for(email: str) -> int:
    """Verbleibende Sperrsekunden für diese E-Mail (0 = frei).

    **Ein abgelaufenes Fenster nimmt den Zähler mit.** Ohne das blieb `count`
    bei 5 stehen: die fünfzehn Minuten liefen ab, und der nächste Tippfehler
    sperrte sofort wieder fünfzehn Minuten — wer einmal fünfmal danebengegriffen
    hat, wäre danach dauerhaft EINEN Vertipper von der Sperre entfernt gewesen.
    Eine Bremse gegen Raten muss nach ihrer Zeit wieder loslassen, sonst ist sie
    keine Bremse, sondern eine Strafe.

    Dasselbe gilt für die Serie darunter: vier Fehlversuche vor einem Jahr sind
    kein Rateversuch von heute. Aufgeräumt wird deshalb am ZEITSTEMPEL und nicht
    an der Frage, ob gerade gesperrt ist — sonst verfiele nur die Sperre und die
    Serie liefe ewig weiter.
    """
    key = email.lower()
    count, until = _fail_state.get(key, (0, 0.0))
    if not until:
        return 0
    if until <= time.time():
        _fail_state.pop(key, None)
        return 0
    # Innerhalb des Fensters, aber noch unter der Grenze: mitgezählt, nicht
    # gesperrt.
    return int(until - time.time()) if count >= _FAIL_MAX else 0


def _prune_fail_state() -> None:
    """Abgelaufenes wegwerfen, und wenn das nicht reicht, das Älteste.

    Zwei Schritte, weil der erste allein nicht genügt: wer im Sekundentakt
    neue Adressen probiert, hat lauter FRISCHE Einträge, und ein Aufräumen nach
    Ablauf findet nichts zum Wegwerfen. Der zweite Schritt ist deshalb kein
    Schönheitsfehler, sondern die eigentliche Grenze.

    Was dabei verloren geht, ist der Zähler eines Angreifers — nicht der eines
    Nutzers: geräumt wird nach dem ÄLTESTEN Fenster, und ein laufender
    Rateversuch schiebt seines mit jedem Versuch nach vorn.
    """
    now = time.time()
    for key in [k for k, (_, until) in _fail_state.items() if until <= now]:
        _fail_state.pop(key, None)
    if len(_fail_state) <= _FAIL_STATE_MAX:
        return
    for key, _ in sorted(_fail_state.items(), key=lambda kv: kv[1][1]
                         )[:len(_fail_state) - _FAIL_STATE_MAX]:
        _fail_state.pop(key, None)


def note_login_failure(email: str) -> None:
    key = email.lower()
    # Erst aufräumen: ist das Fenster durch, beginnt dieser Versuch eine neue
    # Serie, statt eine längst vergessene fortzusetzen.
    login_locked_for(key)
    count, _ = _fail_state.get(key, (0, 0.0))
    # Jeder Fehlversuch schiebt das Fenster — sowohl die Serie als auch eine
    # bereits stehende Sperre. Wer während der Sperre weiterrät, verlängert sie.
    _fail_state[key] = (count + 1, time.time() + _LOCK_SECONDS)
    # Aufräumen NACH dem Eintragen, nicht davor. Davor wäre die Tabelle nach
    # dem Eintrag wieder eins über der Grenze — und, was mehr wiegt: der
    # gerade geschriebene Eintrag ist der jüngste und damit der letzte, den
    # der Deckel wegwirft. Wer aktiv rät, verliert seine Sperre also nicht,
    # indem er die Tabelle vollmacht.
    _prune_fail_state()


def clear_login_failures(email: str) -> None:
    _fail_state.pop(email.lower(), None)


def authenticate_local(db: Session, email: str, password: str) -> User | None:
    """Prüft E-Mail + Passwort. Gibt den Nutzer zurück oder None.

    Kein Aufschluss darüber, WELCHE Angabe falsch war: existiert die E-Mail
    nicht, wird trotzdem gegen einen Dummy-Hash geprüft, damit ein Angreifer
    gültige von ungültigen Adressen nicht an der Antwortzeit unterscheidet.
    """
    user = find_local_user(db, email)
    if user is None:
        pw.verify_password(password, pw.DUMMY_HASH)   # Timing angleichen
        return None
    if not pw.verify_password(password, user.password_hash):
        return None
    return user


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
            if user and session_still_valid(user, data):
                return user

    # 2) Bearer-Token (API-Clients): direkt vom Provider signiertes JWT.
    # Anmerkung 209: MIT Audience-Prüfung — siehe `bearer_audience()`.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            claims = validate_oidc_token(auth_header[7:])
        except Exception as exc:  # jede Validierungspanne ist 401
            # Der Grund gehört ins Log, nicht in die Antwort: ein Angreifer
            # soll nicht erfahren, WORAN sein Token gescheitert ist. Der
            # Betreiber schon — sonst ist eine plötzlich abgewiesene
            # Integration nicht zu erklären.
            log.info("Bearer-Token abgewiesen (erwartete Audience %r): %s",
                     bearer_audience(), exc)
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
