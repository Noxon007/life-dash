"""Kurzbeschreibungen für Kompendium-Entities aus Wikipedia.

Zweistufig: Wikidata-Konzeptsuche (mit Typ-Kontext gegen Mehrdeutigkeiten wie
"Fuchs") -> Summary-Endpoint des besten Treffers. Nur Standardbibliothek.

**Sprache (ab 0.35.0):** Bis dahin stand hier fest `de.wikipedia.org` — seit
F10 die Oberfläche zweisprachig ist, hieß das ein deutscher Absatz unter einer
englischen Seite. Jeder Einstieg nimmt jetzt die UI-Sprache entgegen; die
Stichwort-Filter gibt es je Sprache, und fehlt ein Artikel in der einen, wird
die andere versucht — eine Beschreibung in der falschen Sprache ist immer noch
besser als keine (dieselbe Regel wie beim Ortsnamen-Fallback, A10).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "life-dash/0.2 (self-hosted life database; kontakt: lokal)"
DEFAULT_LANG = "de"
LANGS = ("de", "en")


def _api_url(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def _summary_url(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"


def _lang(lang: str | None) -> str:
    return lang if lang in LANGS else DEFAULT_LANG


# Suchkontext je Entity-Typ, damit z. B. "Fuchs" das Tier findet
TYPE_CONTEXT = {
    "de": {"animal": "Tier", "artist": "Band Musiker", "food": "Gericht Speise",
           "movie": "Film", "game": "Computerspiel", "book": "Buch Roman",
           "country": "", "city": "Stadt", "place": "Ort"},
    "en": {"animal": "animal", "artist": "band musician", "food": "dish food",
           "movie": "film", "game": "video game", "book": "book novel",
           "country": "", "city": "city", "place": "place"},
}

# Stichworte, die im Artikeltext vorkommen müssen, damit der Treffer als
# passend gilt (verhindert z. B. "Fuchs" -> Fernsehmoderator Bernd Fuchs)
TYPE_KEYWORDS = {
    "de": {
        "animal": ["tier", "gattung", "art ", "familie der", "säuge", "vogel", "vögel",
                   "fisch", "insekt", "reptil", "amphib", "raubtier", "greifvogel"],
        "artist": ["band", "musiker", "sänger", "rapper", "musikgruppe", "musikerin", "dj"],
        "food": ["gericht", "speise", "küche", "lebensmittel", "suppe", "nudel", "gebäck"],
        "movie": ["film"],
        "game": ["computerspiel", "videospiel", "spiel"],
        "book": ["roman", "buch", "erzählung", "sachbuch"],
        "country": ["staat", "land", "republik", "königreich", "insel"],
        # A42: „Stadt", „Gemeinde", „Ort" — und die Verwaltungsbegriffe, mit
        # denen Wikidata Orte außerhalb des deutschen Sprachraums beschreibt
        "city": ["stadt", "gemeinde", "ort", "kommune", "hauptstadt", "dorf",
                 "siedlung", "municipality", "city", "town", "village"],
    },
    "en": {
        "animal": ["animal", "genus", "species", "family of", "mammal", "bird",
                   "fish", "insect", "reptile", "amphibian"],
        "artist": ["band", "musician", "singer", "rapper", "dj", "group"],
        "food": ["dish", "food", "cuisine", "soup", "pastry", "noodle"],
        "movie": ["film"],
        "game": ["video game", "game"],
        "book": ["novel", "book", "non-fiction"],
        "country": ["country", "state", "republic", "kingdom", "island"],
        "city": ["city", "town", "village", "municipality", "commune",
                 "capital", "settlement"],
    },
}


def _get_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            if err.code == 429:  # Wikipedia drosselt -> kurz warten, neu versuchen
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None
    return None


def _summary(title: str, lang: str = DEFAULT_LANG) -> dict | None:
    """Summary eines Artikels (folgt Redirects); None bei BKL/Fehler/leer."""
    data = _get_json(_summary_url(lang) + urllib.parse.quote(title, safe=""))
    if not data or data.get("type") == "disambiguation":
        return None
    extract = (data.get("extract") or "").strip()
    if not extract:
        return None
    return {
        "description": extract[:600],
        "wiki_title": data.get("title", title),
        "wiki_url": data.get("content_urls", {}).get("desktop", {}).get("page"),
        "thumbnail": (data.get("thumbnail") or {}).get("source"),
    }


WIKIDATA_URL = "https://www.wikidata.org/w/api.php"


def _wikidata_article(name: str, keywords: list[str],
                      lang: str = DEFAULT_LANG) -> str | None:
    """Sucht den Begriff auf Wikidata (Label-Suche mit Kurzbeschreibung) und
    liefert den Titel des passenden Wikipedia-Artikels in `lang`.

    Die kurzen Wikidata-Beschreibungen ("Gattung der Hunde", "Greifvogel")
    sind viel präziser filterbar als Volltext-Suchtreffer."""
    params = urllib.parse.urlencode(
        {"action": "wbsearchentities", "search": name, "language": lang,
         "uselang": lang, "type": "item", "limit": 12, "format": "json"}
    )
    data = _get_json(f"{WIKIDATA_URL}?{params}")
    hits = (data or {}).get("search", [])

    def matches(hit: dict) -> bool:
        if not keywords:
            return True
        desc = (hit.get("description") or "").lower()
        return any(kw in desc for kw in keywords)

    def exact(hit: dict) -> bool:
        return (hit.get("label") or "").lower() == name.lower()

    # Priorität: exakter Label + Stichwort-Treffer ("Fuchs" das Tier, nicht
    # der "Fuchsbandwurm") -> dann Stichwort-Treffer -> ohne Stichworte alle
    ordered, seen = [], set()
    for group in ([h for h in hits if exact(h) and matches(h)],
                  [h for h in hits if matches(h)],
                  [] if keywords else hits):
        for h in group:
            if h["id"] not in seen:
                seen.add(h["id"])
                ordered.append(h)

    wiki = f"{lang}wiki"
    for hit in ordered:
        params = urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": hit["id"],
             "props": "sitelinks", "sitefilter": wiki, "format": "json"}
        )
        ent = _get_json(f"{WIKIDATA_URL}?{params}")
        sitelinks = (
            (ent or {}).get("entities", {}).get(hit["id"], {}).get("sitelinks", {})
        )
        title = sitelinks.get(wiki, {}).get("title")
        if title:
            return title
    return None


def _fetch_in(name: str, entity_type: str, lang: str,
              search_terms: list[str] | None = None) -> dict | None:
    """Ein Versuch in EINER Sprache — der eigentliche Ablauf."""
    keywords = TYPE_KEYWORDS.get(lang, {}).get(entity_type, [])

    for term in (search_terms or [name]):
        title = _wikidata_article(term, keywords, lang)
        if title:
            info = _summary(title, lang)
            if info:
                return info

    # Fallback: klassische Suche — erst Titel-Suche (findet über den Wortstamm
    # auch Plural-Artikel wie "Bären"), dann Volltext mit Typ-Kontext
    context = TYPE_CONTEXT.get(lang, {}).get(entity_type, "")
    titles: list[str] = []
    if entity_type == "animal" and lang == "de":
        # Tiergruppen-Artikel heißen oft nach dem Plural (Bären, Haie, Füchse);
        # falsche Kandidaten laufen einfach ins 404 und werden übersprungen
        titles.extend([f"{name}en", f"{name}e", f"{name}n"])
    for query in (f"intitle:{name}", f"{name} {context}".strip()):
        params = urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": query,
             "srlimit": 5, "format": "json"}
        )
        search = _get_json(f"{_api_url(lang)}?{params}")
        for hit in (search or {}).get("query", {}).get("search", []):
            if hit["title"] not in titles:
                titles.append(hit["title"])

    fallback: dict | None = None
    for title in titles[:8]:
        info = _summary(title, lang)
        if not info:
            continue
        text = f"{info['wiki_title']} {info['description']}".lower()
        if not keywords or any(kw in text for kw in keywords):
            return info
        if fallback is None:
            fallback = info
    return fallback


def _both_langs(lang: str | None) -> tuple[str, ...]:
    """Wunschsprache zuerst, die andere als Rückfall (wie A10 bei Ortsnamen)."""
    primary = _lang(lang)
    return (primary, *[a for a in LANGS if a != primary])


def fetch_summary(name: str, entity_type: str = "",
                  lang: str | None = None) -> dict | None:
    """Liefert {description, wiki_title, wiki_url, thumbnail} oder None.

    1. Wikidata-Konzeptsuche (präzise Kurzbeschreibungen) -> Artikel.
    2. Fallback: Wikipedia-Volltextsuche mit Typ-Kontext.
    3. Fällt beides aus, dieselbe Runde in der anderen Sprache.
    """
    for attempt in _both_langs(lang):
        info = _fetch_in(name, entity_type, attempt)
        if info:
            return info
    return None


def fetch_city_summary(name: str, country: str | None = None,
                       lang: str | None = None) -> dict | None:
    """A42: Beschreibung einer STADT — mit dem Land als Unterscheidung.

    Städtenamen sind auf eine Weise mehrdeutig, wie Tier- und Ländernamen es
    nie waren: „Frankfurt", „Springfield", „San José" gibt es mehrfach, und
    Wikidata liefert bei der bloßen Label-Suche irgendeine davon. Mit dem Land
    vorne („Frankfurt Deutschland") trifft dieselbe Suche die richtige — und
    ohne Land bleibt der nackte Name als zweiter Versuch, weil eine Stadt ohne
    gespeichertes Land trotzdem eine Beschreibung verdient.
    """
    terms = [f"{name} {country}".strip()] if country else []
    terms.append(name)
    for attempt in _both_langs(lang):
        info = _fetch_in(name, "city", attempt, search_terms=terms)
        if info:
            return info
    return None
