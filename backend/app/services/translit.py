"""Umschrift fremdschriftlicher Ortsnamen in lateinische Buchstaben.

**Warum es das gibt.** Nominatim liefert den Namen in der Wunschsprache, wenn
OSM einen hat (`name:de`, `name:en`). Für eine Landstraße auf Antipaxos oder
eine Kapelle bei Gaios hat es keinen — dort steht nur `name`, und der ist
griechisch. Bis 0.39 endete das in einer Liste „Was der Lauf nicht benennen
konnte", die bei jedem Durchgang identisch blieb: der Ortsnamen-Lauf fragte
denselben Ort erneut, bekam denselben griechischen Namen und meldete denselben
Mangel. Ein Abruf, der nichts ändern KANN, ist kein Fortschritt.

Umschreiben kann er dagegen ohne jede Nachfrage — die Buchstaben stehen schon
da. Deshalb ist das hier eine Rechnung und kein Dienst: keine Netzanfrage,
keine Drossel, kein Schlüssel. Der bestehende Lauf „Ortsnamen auflösen" nimmt
sie über `_rename_from_stored` mit (die Bausteine liegen seit Anmerkung 110
gespeichert vor) und repariert damit den Bestand rückwirkend, ohne einen
einzigen Geocoder-Aufruf.

**Was es NICHT ist.** Keine Übersetzung. „Αεροδρόμιο" wird „Aerodromio" und
nicht „Flughafen" — der Ort heißt so, wie er heißt, nur in Buchstaben, die
hier jemand lesen kann. Und es ist kein Ersatz für `name:de`/`name:en`: die
haben Vorrang, sie sind die Auskunft der Quelle, das hier ist unsere.

**Welche Schriften.** Griechisch (ELOT 743, die Umschrift auf griechischen
Ausweisen und Straßenschildern) und Kyrillisch. Für Schriften ohne Tabelle
(CJK, Arabisch, Hebräisch, Thai, Devanagari) gibt `romanize` `None` zurück —
„geht hier nicht" ist eine Antwort und darf nicht wie „nichts zu tun"
aussehen. Was der Aufrufer daraus macht, entscheidet er (siehe
`geocode.short_name`: das Segment fällt weg, aber nur, solange danach noch
etwas übrig bleibt, das den Ort benennt).
"""
from __future__ import annotations

import unicodedata

# --------------------------------------------------------------------------- #
# Griechisch — ELOT 743 / ISO 843 (Umschrift, nicht Transkription)
# --------------------------------------------------------------------------- #
_GREEK: dict[str, str] = {
    "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
    "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
    "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
}
# Vor diesen Lauten wird αυ/ευ/ηυ stimmhaft („av"), sonst stimmlos („af").
# Genau diese Regel macht aus „Ελευθερίου" ein „Eleftheriou" statt eines
# „Eleytherioy" — der Unterschied zwischen einem lesbaren Straßennamen und
# einer Buchstabenkette.
_GREEK_VOICED = set("αβγδεζηιλμνορυω")

# --------------------------------------------------------------------------- #
# Kyrillisch — russische Grundtabelle plus die Buchstaben, die andere Sprachen
# eigenständig führen (ukrainisch, serbisch, mazedonisch)
# --------------------------------------------------------------------------- #
_CYRILLIC: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    # außerhalb des Russischen
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ѐ": "e", "ѝ": "i",
    "ђ": "dj", "ј": "j", "љ": "lj", "њ": "nj", "ћ": "c", "џ": "dz",
    "ѓ": "gj", "ќ": "kj", "ѕ": "dz",
}

# Die beiden Tafeln zusammen — was hier fehlt, hat keine Umschrift.
_TABLES = (_GREEK, _CYRILLIC)

# Buchstaben, die eine der Tafeln kennt. Woran `romanize` erkennt, ob es
# überhaupt zuständig ist.
_KNOWN = set(_GREEK) | set(_CYRILLIC)

# Trema (ϊ, ϋ) trennt zwei Vokale, die sonst ein Doppelzeichen bilden:
# „Μάιος" ist nicht „Μάυος". Die Zerlegung unten hebt es vom Buchstaben ab,
# hier steht, wonach dabei zu suchen ist.
_DIAERESIS = "̈"


def _split(text: str) -> list[tuple[str, bool, bool]]:
    """Zerlegt in (Grundbuchstabe klein, war groß, trägt Trema).

    Akzente fallen vom Buchstaben ab: „ά" ist „α" mit einem Akutzeichen, und
    das Akutzeichen interessiert die Umschrift nicht. Das Trema dagegen schon —
    es ist keine Betonung, sondern eine Trennung („Μάιος" ist nicht „Μάυος").

    **Erst fragen, dann zerlegen.** Blind über NFD zu gehen wäre falsch: „й"
    und „ї" sind eigene Buchstaben mit eigener Umschrift („y", „yi"), zerfallen
    aber in „и"/„і" plus ein Zeichen — aus „Київ" würde „Kiiv" statt „Kyiv".
    Eine Zerlegung ist eine Notlösung für das, was die Tafel NICHT kennt.
    """
    out: list[tuple[str, bool, bool]] = []
    for ch in unicodedata.normalize("NFC", text):
        low = ch.lower()
        upper = ch != low
        if low in _KNOWN:
            out.append((low, upper, False))
            continue
        parts = unicodedata.normalize("NFD", low)
        base = "".join(c for c in parts if not unicodedata.combining(c))
        trema = any(c == _DIAERESIS for c in parts)
        out.append((base or low, upper, trema))
    return out


def _cased(chunk: str, upper: bool, next_upper: bool) -> str:
    """Großschreibung übertragen.

    Ein griechisches Θ wird zu zwei lateinischen Buchstaben — und ob daraus
    „Th" oder „TH" wird, hängt am NÄCHSTEN Zeichen: „Θεσσαλονίκη" ist
    „Thessaloniki", „ΘΕΣΣΑΛΟΝΙΚΗ" ist „THESSALONIKI". Ohne diesen Blick nach
    vorn schriee jede Abkürzung.
    """
    if not upper or not chunk:
        return chunk
    return chunk.upper() if next_upper else chunk[:1].upper() + chunk[1:]


def _greek(chars: list[tuple[str, bool, bool]], i: int) -> tuple[str, int] | None:
    """Griechische Doppelzeichen an Position `i` — oder None für Einzelbuchstaben."""
    base, _, _ = chars[i]
    nxt = chars[i + 1] if i + 1 < len(chars) else None
    if not nxt or nxt[2]:          # kein nächster Buchstabe oder Trema: kein Paar
        return None
    nbase = nxt[0]
    if base == "ο" and nbase == "υ":
        return "ou", 2
    if base in ("α", "ε", "η") and nbase == "υ":
        after = chars[i + 2][0] if i + 2 < len(chars) else ""
        tail = "v" if after in _GREEK_VOICED else "f"
        return {"α": "a", "ε": "e", "η": "i"}[base] + tail, 2
    if base == "γ":
        if nbase == "γ":
            return "ng", 2
        if nbase == "ξ":
            return "nx", 2
        if nbase == "χ":
            return "nch", 2
    return None


def romanize(text: str | None) -> str | None:
    """Fremdschriftlichen Text in lateinische Buchstaben umschreiben.

    Gibt `None` zurück, wenn keine der Tafeln zuständig ist — „konnte ich
    nicht" darf nicht wie „war nichts zu tun" aussehen. Enthält der Text
    ZUSÄTZLICH Zeichen aus einer Schrift ohne Tafel, kommen sie unverändert
    zurück; ob das Ergebnis taugt, entscheidet der Aufrufer, indem er es
    erneut gegen `NON_LATIN_RE` hält (siehe `geocode.latinize`). Lateinische
    Anteile bleiben unangetastet: gemischte Namen wie „Γεώργiου" (mit
    lateinischem i) kommen vollständig durch.
    """
    if not text:
        return None
    chars = _split(text)
    # Zuständig nur, wenn wenigstens ein Buchstabe aus einer Tafel vorkommt —
    # und keiner, den keine Tafel kennt und der trotzdem fremd ist.
    if not any(c[0] in _KNOWN for c in chars):
        return None
    out: list[str] = []
    i = 0
    while i < len(chars):
        base, upper, _ = chars[i]
        pair = _greek(chars, i) if base in _GREEK else None
        if pair:
            chunk, step = pair
        elif base in _GREEK:
            chunk, step = _GREEK[base], 1
        elif base in _CYRILLIC:
            chunk, step = _CYRILLIC[base], 1
        else:
            # Alles andere unverändert übernehmen — Leerzeichen, Bindestriche,
            # Ziffern und lateinische Buchstaben stehen so schon richtig da.
            out.append(base.upper() if upper else base)
            i += 1
            continue
        nxt = chars[i + step] if i + step < len(chars) else None
        out.append(_cased(chunk, upper, bool(nxt and nxt[1])))
        i += step
    return "".join(out)
