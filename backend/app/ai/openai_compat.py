"""Echter KI-Provider über einen OpenAI-kompatiblen Chat-Endpoint.

Funktioniert mit LM Studio (http://localhost:1234/v1), Ollama (/v1),
OpenAI selbst und jedem anderen kompatiblen Server. Gleiche Schnittstelle
wie der MockProvider, daher austauschbar (AI_PROVIDER=openai).

Nutzt nur die Standardbibliothek (urllib) — keine zusätzliche Abhängigkeit.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime

from dateutil import parser as dateparser

log = logging.getLogger("lifedash.ai")

from app.ai.base import ExtractedEntity, ExtractedEvent, LLMProvider, ProviderUnavailable
from app.ai.mock import KNOWN_PLACES
from app.config import settings

SYSTEM_PROMPT = """Du bist der Extraktions-Assistent von Life-Dash, einer persönlichen Lebens-Datenbank.
Aufgabe: Aus einem frei formulierten (meist deutschen) Text strukturierte Ereignisse extrahieren.

Antworte AUSSCHLIESSLICH mit gültigem JSON nach diesem Schema — keine Erklärungen, kein Markdown:

{
  "events": [
    {
      "title": "kurzer prägnanter Titel",
      "description": "der unveränderte Originaltext",
      "date_start": "YYYY-MM-DD oder null",
      "date_end": "YYYY-MM-DD oder null",
      "date_precision": "exact|day|month|season|year|decade",
      "category": "trip|sighting|sport|concert|meal|milestone|event",
      "confidence": 0.0-1.0,
      "location": {"name": "Ort oder null", "lat": Zahl oder null, "lng": Zahl oder null},
      "entities": [
        {"type": "animal|country|artist|food|movie|game|book", "name": "Name", "attributes": {}}
      ]
    }
  ]
}

REGELN — Datum:
- Das heutige Datum steht im Input. Rechne relative Angaben damit um (gestern, vorgestern, letzte Woche).
- Exaktes Datum -> precision "day", date_start = date_end.
- "Sommer 2002" -> season (2002-06-01 bis 2002-08-31). Frühling=03-01..05-31, Herbst=09-01..11-30, Winter=12-01..02-28.
- "Oktober 2024" -> month (2024-10-01 bis 2024-10-31). "2019" -> year. "in den 90ern" -> decade (1990..1999).
- Keine Zeitangabe -> date_start/date_end null und confidence deutlich senken.

REGELN — Kategorie (genau eine):
- trip = Reise, Urlaub, Ausflug, Städtetrip
- sighting = ein Tier gesehen/beobachtet
- sport = Sport/Bewegung (Laufen, Radfahren, Wandern, Schwimmen)
- concert = Konzert, Festival, Live-Auftritt
- meal = Essen/Mahlzeit (Restaurantbesuch, besonderes Gericht, gekocht)
- milestone = besonderes Lebensereignis: Hochzeit, Verlobung, Geburt, Umzug, Schul-/Studienabschluss, neuer Job, Taufe, Einschulung
- event = alles andere (Treffen, Krankheit, Alltägliches, ...)

REGELN — Entities (das Wichtigste, sei hier gründlich):
- animal: JEDES erwähnte Tier, egal welche Art — Hai, Adler, Delphin, Eichhörnchen, Kuh, Ameise, Qualle ...
  attributes: {"species": "<Tierart>", "wild": true/false}. Name = die Tierart, nicht "ein Tier".
- country: JEDES erwähnte Land (Schweiz, Frankreich, Ägypten, ...). Auch ableiten, wenn nur eine
  Stadt genannt ist und das Land eindeutig ist (Bern -> Schweiz, Prag -> Tschechien) — dann confidence des Events leicht senken.
- artist: Band oder Künstler bei Konzerten/Festivals ("Die Ärzte", "Rammstein", ...).
- food: konkretes Gericht oder Essen ("Ramen", "Pizza Margherita", "Käsespätzle", ...).
- movie / game / book: konkrete Titel von Filmen, Spielen, Büchern.
- Personen sind NIEMALS eine Entity ("mit Anna" -> Anna weglassen). Bands/Künstler zählen NICHT als Personen.

REGELN — Sonstiges:
- title: max. 60 Zeichen, deutsch, ohne Datum ("Hai beim Schnorcheln gesehen", nicht "Am 12.07. ...").
- description: IMMER exakt der Originaltext.
- location.name: konkretester genannter Ort (Adresse > Stadtteil > Stadt > Region > Land). lat/lng nur wenn sicher bekannt, sonst null.
- confidence: ~0.95 = exakt & eindeutig · 0.7-0.85 = leicht unscharf/abgeleitet · unter 0.6 = geraten/mehrdeutig.
- Enthält der Text mehrere unabhängige Ereignisse, erzeuge mehrere Einträge im events-Array.

BEISPIELE

Input:
Heutiges Datum: 2026-07-14
Text: 12.07.2026 war in Detmold und habe einen Adler gesehen
Output:
{"events":[{"title":"Adler in Detmold gesehen","description":"12.07.2026 war in Detmold und habe einen Adler gesehen","date_start":"2026-07-12","date_end":"2026-07-12","date_precision":"day","category":"sighting","confidence":0.95,"location":{"name":"Detmold","lat":51.9375,"lng":8.8797},"entities":[{"type":"animal","name":"Adler","attributes":{"species":"Adler","wild":true}}]}]}

Input:
Heutiges Datum: 2026-07-14
Text: Sommer 2002 Urlaub in Frankreich mit Anna
Output:
{"events":[{"title":"Urlaub in Frankreich","description":"Sommer 2002 Urlaub in Frankreich mit Anna","date_start":"2002-06-01","date_end":"2002-08-31","date_precision":"season","category":"trip","confidence":0.75,"location":{"name":"Frankreich","lat":46.2276,"lng":2.2137},"entities":[{"type":"country","name":"Frankreich","attributes":{}}]}]}

Input:
Heutiges Datum: 2026-07-14
Text: Gestern beim Schnorcheln in Hurghada einen Hai gesehen, danach 5 km am Strand gelaufen
Output:
{"events":[{"title":"Hai beim Schnorcheln in Hurghada gesehen","description":"Gestern beim Schnorcheln in Hurghada einen Hai gesehen, danach 5 km am Strand gelaufen","date_start":"2026-07-13","date_end":"2026-07-13","date_precision":"day","category":"sighting","confidence":0.85,"location":{"name":"Hurghada","lat":27.2579,"lng":33.8116},"entities":[{"type":"animal","name":"Hai","attributes":{"species":"Hai","wild":true}},{"type":"country","name":"Ägypten","attributes":{}}]},{"title":"5 km Strandlauf in Hurghada","description":"Gestern beim Schnorcheln in Hurghada einen Hai gesehen, danach 5 km am Strand gelaufen","date_start":"2026-07-13","date_end":"2026-07-13","date_precision":"day","category":"sport","confidence":0.85,"location":{"name":"Hurghada","lat":27.2579,"lng":33.8116},"entities":[{"type":"country","name":"Ägypten","attributes":{}}]}]}

Input:
Heutiges Datum: 2026-07-14
Text: 01.07.2026 war in der Schweiz in Bern
Output:
{"events":[{"title":"Besuch in Bern","description":"01.07.2026 war in der Schweiz in Bern","date_start":"2026-07-01","date_end":"2026-07-01","date_precision":"day","category":"trip","confidence":0.9,"location":{"name":"Bern","lat":46.948,"lng":7.4474},"entities":[{"type":"country","name":"Schweiz","attributes":{}}]}]}

Input:
Heutiges Datum: 2026-07-14
Text: 01.01.2002 war ich bei einem Konzert von den Ärzten in Bielefeld
Output:
{"events":[{"title":"Die Ärzte live in Bielefeld","description":"01.01.2002 war ich bei einem Konzert von den Ärzten in Bielefeld","date_start":"2002-01-01","date_end":"2002-01-01","date_precision":"day","category":"concert","confidence":0.95,"location":{"name":"Bielefeld","lat":52.0302,"lng":8.5325},"entities":[{"type":"artist","name":"Die Ärzte","attributes":{"genre":"Punkrock"}}]}]}

Input:
Heutiges Datum: 2026-07-14
Text: 15.03.2020 in die neue Wohnung nach Hamburg gezogen
Output:
{"events":[{"title":"Umzug nach Hamburg","description":"15.03.2020 in die neue Wohnung nach Hamburg gezogen","date_start":"2020-03-15","date_end":"2020-03-15","date_precision":"day","category":"milestone","confidence":0.95,"location":{"name":"Hamburg","lat":53.5511,"lng":9.9937},"entities":[]}]}

Input:
Heutiges Datum: 2026-07-14
Text: Heute Mittag beim Vietnamesen in Köln eine Pho gegessen
Output:
{"events":[{"title":"Pho beim Vietnamesen in Köln","description":"Heute Mittag beim Vietnamesen in Köln eine Pho gegessen","date_start":"2026-07-14","date_end":"2026-07-14","date_precision":"day","category":"meal","confidence":0.9,"location":{"name":"Köln","lat":50.9375,"lng":6.9603},"entities":[{"type":"food","name":"Pho","attributes":{"cuisine":"vietnamesisch"}}]}]}"""


def build_system_prompt(tracked: list[str] | None = None) -> str:
    """A7/A15: Basis-Prompt + Regeln der (getrackten) Module aus den YAMLs.
    Neue Module bringen ihre Extraktions-Regeln selbst mit (prompt_rules)."""
    from app.modules.registry import registry

    extra = registry.prompt_section(tracked)
    prompt = SYSTEM_PROMPT
    if extra:
        prompt += ("\n\nAKTIVE MODULE — zusätzliche Regeln (haben Vorrang):\n" + extra)
    if tracked is not None:
        prompt += ("\nDer Nutzer trackt nur die oben gelisteten Module. Nutze andere "
                   "Kategorien/Entity-Typen NICHT — im Zweifel category \"event\" "
                   "und keine Entity.")
    return prompt


class OpenAICompatProvider(LLMProvider):
    def extract(self, raw_text: str,
                tracked: list[str] | None = None) -> list[ExtractedEvent]:
        today = datetime.now().strftime("%Y-%m-%d")
        user = f"Heutiges Datum: {today}\nText: {raw_text}"
        try:
            content = self._chat(build_system_prompt(tracked), user)
        except Exception as err:
            log.warning("KI-Provider-Fehler: %s", err)
            raise ProviderUnavailable(str(err)) from err
        data = self._parse_json(content)

        events: list[ExtractedEvent] = []
        for ev in data.get("events", []):
            events.append(self._to_event(ev, raw_text))
        # Fallback: Wenn die KI nichts lieferte, wenigstens ein Roh-Event
        if not events:
            events.append(
                ExtractedEvent(title=raw_text[:80], description=raw_text, confidence=0.3)
            )
        return events

    # ------------------------------------------------------------------ #
    def embed(self, text: str, kind: str = "document") -> list[float] | None:
        """Embedding über den /embeddings-Endpoint (falls Modell konfiguriert)."""
        if not settings.openai_embed_model or not text.strip():
            return None
        prefix = (
            settings.openai_embed_query_prefix
            if kind == "query"
            else settings.openai_embed_doc_prefix
        )
        # Embeddings können auf einem anderen Endpoint laufen als der Chat
        # (z. B. Chat -> Gemini, Embeddings -> lokales Ollama)
        base_url = settings.openai_embed_base_url or settings.openai_base_url
        api_key = settings.openai_embed_api_key or settings.openai_api_key
        payload = {"model": settings.openai_embed_model, "input": prefix + text}
        req = urllib.request.Request(
            base_url.rstrip("/") + "/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["data"][0]["embedding"]
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, json.JSONDecodeError):
            return None

    # ------------------------------------------------------------------ #
    def _chat(self, system: str, user: str) -> str:
        payload = {
            "model": settings.openai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "stream": False,
        }
        req = urllib.request.Request(
            settings.openai_base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.openai_api_key}",
            },
            method="POST",
        )
        # Überlastete/gedrosselte APIs (429/5xx) gestaffelt neu versuchen.
        # 429 = Rate-Limit (Free-Tier: Anfragen pro Minute) -> lange warten,
        # damit auch Batch-Neuberechnungen zuverlässig durchlaufen.
        last_err: Exception | None = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                return body["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as err:
                last_err = err
                if err.code not in (429, 500, 502, 503, 504):
                    raise
                retry_after = err.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    wait = min(float(retry_after) + 1, 90.0)
                elif err.code == 429:
                    wait = 15.0 * (attempt + 1)
                else:
                    wait = 2.0 * (attempt + 1)
                log.warning("KI-Endpoint HTTP %s — Versuch %d/5, warte %.0fs", err.code, attempt + 1, wait)
                time.sleep(wait)
        raise last_err

    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_json(content: str) -> dict:
        """Robust: schneidet ```-Fences weg und greift das erste JSON-Objekt."""
        text = content.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1] if "```" in text[3:] else text[3:]
            if text.startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"events": []}

    # ------------------------------------------------------------------ #
    def _to_event(self, ev: dict, raw_text: str) -> ExtractedEvent:
        loc = ev.get("location") or {}
        name = loc.get("name")
        lat, lng = loc.get("lat"), loc.get("lng")
        if name and (lat is None or lng is None):
            coords = KNOWN_PLACES.get(str(name).lower())
            if coords:
                lat, lng = coords

        entities = [
            ExtractedEntity(
                type=e.get("type", "thing"),
                name=e.get("name", ""),
                attributes=e.get("attributes") or {},
            )
            for e in ev.get("entities", [])
            if e.get("name")
        ]

        return ExtractedEvent(
            title=ev.get("title") or raw_text[:80],
            description=ev.get("description") or raw_text,
            date_start=self._date(ev.get("date_start")),
            date_end=self._date(ev.get("date_end")),
            date_precision=ev.get("date_precision") or "day",
            category=ev.get("category") or "event",
            confidence=float(ev.get("confidence", 0.7)),
            location_name=name,
            location_lat=lat,
            location_lng=lng,
            entities=entities,
        )

    @staticmethod
    def _date(value) -> datetime | None:
        if not value or value == "null":
            return None
        try:
            return dateparser.parse(str(value))
        except (ValueError, OverflowError):
            return None
