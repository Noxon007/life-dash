"""A35 — Passwörter für lokale Konten: hashen und prüfen.

Das erste Geheimnis, das Life-Dash von Menschen speichert. Deshalb bewusst
konservativ:

* **scrypt** aus der Standardbibliothek — speicherhart, kein zusätzliches
  (kompiliertes) Paket wie argon2. Für ein self-hosted Tool zählt „läuft
  überall ohne Baukette" mehr als das letzte Quäntchen Härte.
* **Zufälliger Salt pro Passwort**, im Hash-String mitgeführt — ein geleakter
  Hash lässt sich nicht per Regenbogentabelle umkehren.
* **`compare_digest`** beim Prüfen — kein früher Abbruch, der über Timing die
  Anzahl gemeinsamer Zeichen verriete.

Format (ein String, alles zum Prüfen Nötige enthalten):

    scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# Interaktive Login-Parameter. N=2^15 ≈ 32 MB Speicher pro Prüfung — spürbar
# für einen Angreifer mit Millionen Versuchen, unmerklich beim einzelnen Login.
_N = 2 ** 15
_R = 8
_P = 1
_SALT_BYTES = 16
_DKLEN = 32
# scrypt in OpenSSL verlangt eine Speicherobergrenze; großzügig über dem Bedarf.
_MAXMEM = 128 * 1024 * 1024

MIN_LENGTH = 8


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt,
                          n=n, r=r, p=p, dklen=_DKLEN, maxmem=_MAXMEM)


def hash_password(password: str) -> str:
    """Erzeugt den zu speichernden Hash-String."""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = _derive(password, salt, _N, _R, _P)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Prüft ein Passwort gegen den gespeicherten Hash.

    Ein fehlender oder unlesbarer Hash ist immer „falsch" — nie ein Fehler,
    der den Aufrufer zu einer Sonderbehandlung verleitet.
    """
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = _derive(password, salt, int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Ein gültiger Dummy-Hash, gegen den beim unbekannten Konto geprüft wird —
# so kostet ein Login mit falscher E-Mail genauso viel Zeit wie einer mit
# richtiger E-Mail und falschem Passwort (keine Enumeration über Timing).
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
