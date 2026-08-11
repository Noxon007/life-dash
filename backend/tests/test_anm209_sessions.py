"""Anmerkung 209 — die letzten drei offenen Punkte aus Anmerkung 200.

Sitzungen widerrufbar, die Sperrtabelle gedeckelt, der Bearer-Pfad mit
Audience-Prüfung.

**Die interessante Prüfung ist die Gegenrichtung**, wie schon bei der
Login-Sperre in Anmerkung 201: ein Widerruf, der auch gültige Sitzungen
beendet, ist keine Sicherheit, sondern ein Ausloggen im Zufallstakt. Und ein
Deckel auf der Sperrtabelle, der die Sperre eines gerade laufenden
Rateversuchs mitwegwirft, hat die Bremse gelöst, um Speicher zu sparen.
"""
from __future__ import annotations

import time
from datetime import timedelta

import pytest

from app import auth
from app.models import User


@pytest.fixture(autouse=True)
def clean_fail_state():
    auth._fail_state.clear()
    yield
    auth._fail_state.clear()


def _user(**kw) -> User:
    u = User(id="u1", oidc_subject="local:a@b.c", email="a@b.c")
    for k, v in kw.items():
        setattr(u, k, v)
    return u


# --------------------------------------------------------------------------- #
#  Widerruf
# --------------------------------------------------------------------------- #
def test_a_fresh_cookie_is_valid_and_stays_valid():
    """Der Normalfall — und der teuerste Fehlalarm, den es hier gäbe."""
    user = _user()
    claims = {"uid": "u1", "iat": int(time.time())}
    assert auth.session_still_valid(user, claims)
    # Auch ohne jeden Widerruf in der Vergangenheit: NULL heißt gültig.
    assert user.sessions_valid_from is None


def test_revoking_invalidates_a_cookie_issued_before_it():
    user = _user()
    before = {"uid": "u1", "iat": int(time.time())}
    auth.revoke_sessions(user)
    assert not auth.session_still_valid(user, before)


def test_a_cookie_issued_after_the_revocation_is_valid_again():
    """Sonst wäre „überall abmelden" ein Konto, das sich nicht mehr anmelden kann."""
    user = _user()
    auth.revoke_sessions(user)
    after = {"uid": "u1", "iat": int(time.time()) + 5}
    assert auth.session_still_valid(user, after)


def test_revocation_beats_a_cookie_from_the_same_second():
    """Anmelden und sofort Passwort ändern fällt in dieselbe Sekunde.

    Ohne die Sekunde Vorlauf in `revoke_sessions` überlebte genau das Cookie,
    das gerade widerrufen wurde.
    """
    user = _user()
    now = int(time.time())
    auth.revoke_sessions(user)
    assert not auth.session_still_valid(user, {"uid": "u1", "iat": now})


def test_a_cookie_without_an_issue_time_counts_as_revoked():
    """Cookies von vor dieser Änderung tragen kein `iat`.

    Sie durchzulassen hieße: die alten Sitzungen — also genau die, derentwegen
    jemand widerruft — sind die einzigen, die überleben.
    """
    user = _user()
    auth.revoke_sessions(user)
    assert not auth.session_still_valid(user, {"uid": "u1"})
    # Ohne Widerruf gelten sie weiter; niemand soll durch das Update ausgeloggt
    # werden, ohne dass es einen Anlass gab.
    assert auth.session_still_valid(_user(), {"uid": "u1"})


def test_signed_cookies_carry_an_issue_time():
    """Anmerkung 219: eine ZAHL, und ausdrücklich nicht mehr nur eine ganze.

    Hier stand `isinstance(…, int)`. Die ganze Sekunde war genau das Problem:
    ein Cookie, das kurz VOR einem Widerruf ausgestellt wurde, und eines kurz
    DANACH tragen dieselbe Zahl — damit war die eine Frage, die
    `session_still_valid` stellt, an der Auflösung nicht zu entscheiden.
    RFC 7519 lässt für `NumericDate` nicht-ganzzahlige Werte ausdrücklich zu.
    """
    iat = auth.read_cookie(auth.sign_cookie({"uid": "u1"}, 60))["iat"]
    assert isinstance(iat, (int, float)) and not isinstance(iat, bool)
    # **Und die Auflösung ist wirklich feiner als eine Sekunde.** Den Typ nur
    # zu lockern wäre eine Prüfung, die nichts prüft: `int` ist auch ein
    # `(int, float)`, ein zurückgedrehtes `int(time.time())` käme also durch.
    # Fünf Ausstellungen, von denen KEINE eine Nachkommastelle trägt, gibt es
    # bei ~0,5 µs Auflösung nicht — gegen den abgeschnittenen Stand ist das
    # hier sicher rot.
    stamps = [auth.read_cookie(auth.sign_cookie({"uid": "u1"}, 60))["iat"]
              for _ in range(5)]
    assert any(s != int(s) for s in stamps), stamps


def test_an_aware_cutoff_from_the_database_still_compares():
    """PostgreSQL kann den Wert zeitzonenbehaftet zurückgeben.

    Ein `TypeError` an dieser Stelle träfe nur Konten, die widerrufen haben —
    also den Fall, den keine Testrunde von selbst betritt.
    """
    from datetime import datetime, timezone

    user = _user(sessions_valid_from=datetime.now(timezone.utc) - timedelta(hours=1))
    assert auth.session_still_valid(user, {"uid": "u1", "iat": int(time.time())})


# --------------------------------------------------------------------------- #
#  Die Sperrtabelle hat eine Grenze
# --------------------------------------------------------------------------- #
def test_fail_state_stays_bounded():
    for i in range(auth._FAIL_STATE_MAX + 500):
        auth.note_login_failure(f"nutzer{i}@example.org")
    assert len(auth._fail_state) <= auth._FAIL_STATE_MAX


def test_a_flood_cannot_wash_away_a_lock_that_is_being_earned():
    """Die Gegenrichtung, und der eigentliche Punkt des Deckels.

    Der Angriff, gegen den er halten muss: mit zehntausend erfundenen Adressen
    die Tabelle vollmachen, damit die eigene Sperre hinausfliegt. Geräumt wird
    nach dem ÄLTESTEN Fenster, und wer aktiv rät, schiebt seines mit jedem
    Versuch nach vorn — die Sperre eines LAUFENDEN Rateversuchs ist damit das
    Letzte, was der Deckel wegwirft. Ein Deckel ohne diese Eigenschaft hätte
    die Bremse gegen Speicher getauscht.
    """
    opfer = "opfer@example.org"
    for i in range(auth._FAIL_STATE_MAX + 200):
        auth.note_login_failure(f"rauschen{i}@example.org")
        if i % 100 == 0:                      # dazwischen weiter am Konto raten
            auth.note_login_failure(opfer)
    assert auth.login_locked_for(opfer) > 0
    assert len(auth._fail_state) <= auth._FAIL_STATE_MAX


def test_a_lock_nobody_is_pushing_may_be_evicted():
    """Und die Ehrlichkeit dazu: eine Sperre, an der niemand mehr rüttelt,
    kann der Deckel wegwerfen. Das ist der Preis und keine Lücke — sie läuft
    ohnehin nach fünfzehn Minuten ab, und wer sie zurückhaben will, muss dafür
    weiter raten, was die Sperre gerade wieder herstellt."""
    opfer = "still@example.org"
    for _ in range(auth._FAIL_MAX):
        auth.note_login_failure(opfer)
    assert auth.login_locked_for(opfer) > 0
    for i in range(auth._FAIL_STATE_MAX + 200):
        auth.note_login_failure(f"rauschen{i}@example.org")
    assert auth.login_locked_for(opfer) == 0


def test_expired_entries_go_first():
    auth.note_login_failure("alt@example.org")
    auth._fail_state["alt@example.org"] = (3, time.time() - 1)
    auth.note_login_failure("neu@example.org")
    assert "alt@example.org" not in auth._fail_state
    assert "neu@example.org" in auth._fail_state


# --------------------------------------------------------------------------- #
#  Bearer-Audience
# --------------------------------------------------------------------------- #
def test_bearer_audience_defaults_to_the_client_id(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "oidc_client_id", "life-dash")
    monkeypatch.setattr(settings, "oidc_audience", "")
    assert auth.bearer_audience() == "life-dash"
    # …und eine eigene Angabe gewinnt, für Provider, die auf eine Ressource
    # ausstellen statt auf den Client.
    monkeypatch.setattr(settings, "oidc_audience", "https://api.example.org")
    assert auth.bearer_audience() == "https://api.example.org"


def test_token_validation_asks_for_the_audience(monkeypatch):
    """Der Befund aus Anmerkung 200 war ein einzelnes `verify_aud=False`.

    Geprüft wird deshalb genau das: dass `jwt.decode` die Audience gesetzt
    bekommt und die Prüfung eingeschaltet ist. Ein Test gegen einen echten
    Provider ginge hier nicht ohne Netz — und die Regression, die es zu
    verhindern gilt, ist ein umgekipptes Flag.
    """
    seen = {}

    monkeypatch.setattr(auth, "_jwks", lambda: type("K", (), {
        "get_signing_key_from_jwt": staticmethod(lambda t: type("S", (), {"key": "k"}))
    })())
    monkeypatch.setattr(auth, "oidc_discovery", lambda: {"issuer": "https://id.example.org"})
    monkeypatch.setattr(auth.jwt, "decode",
                        lambda *a, **kw: seen.update(kw) or {"sub": "s"})

    auth.validate_oidc_token("tok")
    assert seen["options"]["verify_aud"] is True
    assert seen["audience"] == auth.bearer_audience()
