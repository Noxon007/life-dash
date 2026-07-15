"""Kurzbeschreibungen für Kompendium-Entities aus der deutschen Wikipedia.

Zweistufig: Volltextsuche (mit Typ-Kontext gegen Mehrdeutigkeiten wie
"Fuchs") -> Summary-Endpoint des besten Treffers. Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "life-dash/0.2 (self-hosted life database; kontakt: lokal)"
SEARCH_URL = "https://de.wikipedia.org/w/api.php"
SUMMARY_URL = "https://de.wikipedia.org/api/rest_v1/page/summary/"

# Suchkontext je Entity-Typ, damit z. B. "Fuchs" das Tier findet
TYPE_CONTEXT = {
    "animal": "Tier",
    "artist": "Band Musiker",
    "food": "Gericht Speise",
    "movie": "Film",
    "game": "Computerspiel",
    "book": "Buch Roman",
    "country": "",
    "place": "Ort",
}

# Stichworte, die im Artikeltext vorkommen müssen, damit der Treffer als
# passend gilt (verhindert z. B. "Fuchs" -> Fernsehmoderator Bernd Fuchs)
TYPE_KEYWORDS = {
    "animal": ["tier", "gattung", "art ", "familie der", "säuge", "vogel", "vögel",
               "fisch", "insekt", "reptil", "amphib", "raubtier", "greifvogel"],
    "artist": ["band", "musiker", "sänger", "rapper", "musikgruppe", "musikerin", "dj"],
    "food": ["gericht", "speise", "küche", "lebensmittel", "suppe", "nudel", "gebäck"],
    "movie": ["film"],
    "game": ["computerspiel", "videospiel", "spiel"],
    "book": ["roman", "buch", "erzählung", "sachbuch"],
    "country": ["staat", "land", "republik", "königreich", "insel"],
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


def _summary(title: str) -> dict | None:
    """Summary eines Artikels (folgt Redirects); None bei BKL/Fehler/leer."""
    data = _get_json(SUMMARY_URL + urllib.parse.quote(title, safe=""))
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


def _wikidata_article(name: str, keywords: list[str]) -> str | None:
    """Sucht den Begriff auf Wikidata (Label-Suche mit deutscher Kurzbeschreibung)
    und liefert den Titel des passenden de-Wikipedia-Artikels.

    Die kurzen Wikidata-Beschreibungen ("Gattung der Hunde", "Greifvogel")
    sind viel präziser filterbar als Volltext-Suchtreffer."""
    params = urllib.parse.urlencode(
        {"action": "wbsearchentities", "search": name, "language": "de",
         "uselang": "de", "type": "item", "limit": 12, "format": "json"}
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

    for hit in ordered:
        params = urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": hit["id"],
             "props": "sitelinks", "sitefilter": "dewiki", "format": "json"}
        )
        ent = _get_json(f"{WIKIDATA_URL}?{params}")
        sitelinks = (
            (ent or {}).get("entities", {}).get(hit["id"], {}).get("sitelinks", {})
        )
        title = sitelinks.get("dewiki", {}).get("title")
        if title:
            return title
    return None


def fetch_summary(name: str, entity_type: str = "") -> dict | None:
    """Liefert {description, wiki_title, wiki_url, thumbnail} oder None.

    1. Wikidata-Konzeptsuche (präzise Kurzbeschreibungen) -> de-Artikel.
    2. Fallback: Wikipedia-Volltextsuche mit Typ-Kontext.
    """
    keywords = TYPE_KEYWORDS.get(entity_type, [])

    title = _wikidata_article(name, keywords)
    if title:
        info = _summary(title)
        if info:
            return info

    # Fallback: klassische Suche — erst Titel-Suche (findet über den Wortstamm
    # auch Plural-Artikel wie "Bären"), dann Volltext mit Typ-Kontext
    context = TYPE_CONTEXT.get(entity_type, "")
    titles: list[str] = []
    if entity_type == "animal":
        # Tiergruppen-Artikel heißen oft nach dem Plural (Bären, Haie, Füchse);
        # falsche Kandidaten laufen einfach ins 404 und werden übersprungen
        titles.extend([f"{name}en", f"{name}e", f"{name}n"])
    for query in (f"intitle:{name}", f"{name} {context}".strip()):
        params = urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": query,
             "srlimit": 5, "format": "json"}
        )
        search = _get_json(f"{SEARCH_URL}?{params}")
        for hit in (search or {}).get("query", {}).get("search", []):
            if hit["title"] not in titles:
                titles.append(hit["title"])

    fallback: dict | None = None
    for title in titles[:8]:
        info = _summary(title)
        if not info:
            continue
        text = f"{info['wiki_title']} {info['description']}".lower()
        if not keywords or any(kw in text for kw in keywords):
            return info
        if fallback is None:
            fallback = info
    return fallback
