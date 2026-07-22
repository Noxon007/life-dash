"""F1 (zweite Hälfte): Vorschlag für einen Tagebuch-Text aus den Ereignissen eines Tages.

Was hier NICHT passiert: schreiben. Der Dienst liest den Tag, formt Stichpunkte
und lässt den KI-Provider daraus Prosa machen — das Ergebnis geht als Vorschlag
an den Editor zurück. Gespeichert wird erst, wenn der Mensch im Tagebuch-Dialog
auf Speichern drückt, und zwar über den ganz normalen Weg (`note`). Damit gilt
die Zusage aus 0.15.0 unverändert weiter: *die KI fasst `note` nie an.*

Zwei Entscheidungen, die man dem Ergebnis sonst nicht ansieht:

* **Nur Bestätigtes fließt ein.** Unbestätigte Ereignisse sind Vorschläge; aus
  einem Vorschlag einen Tagebuchsatz zu bauen, hieße eine Vermutung als eigene
  Erinnerung auszugeben. Sie werden aber GEZÄHLT und mitgeliefert, damit die
  Oberfläche „3 unbestätigte Ereignisse sind nicht eingeflossen" sagen kann —
  die Alternative wäre Stille darüber, warum der Tag dünn aussieht.
* **Der Tagebuch-Eintrag selbst bleibt draußen.** Sonst fasst der zweite Aufruf
  den ersten Vorschlag zusammen und der Text frisst sich selbst.
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy.orm import Session, selectinload

from app.ai import get_provider
from app.models import (ConfirmState, DatePrecision, Event, EventEntityLink,
                        MediaRef, Source)

# Kategorien, die im Tagebuch nichts zu suchen haben: der Eintrag selbst.
_SKIP_CATEGORIES = {"journal"}


def _category_labels() -> dict[str, str]:
    """A7: die Beschriftungen stehen in den Modul-YAMLs, nicht hier."""
    from app.modules.registry import registry

    labels: dict[str, str] = {}
    for module in registry.modules:
        labels.update(module.category_labels or {})
    return labels


def _weather_phrase(event: Event) -> str | None:
    """„18 °C, bewölkt" — aus den Wetter-Metriken des Ereignisses (F3/F12).

    Additiv gelesen: fehlt eine Metrik, fehlt eben der Teil. Ein fehlendes
    Wetter ist kein Fehler, sondern ein Ort ohne Koordinaten.
    """
    wx = {m.key: m for m in event.metrics if m.source == Source.weather}
    parts: list[str] = []
    tmax = wx.get("temp_max_c")
    if tmax is not None and tmax.value is not None:
        parts.append(f"{tmax.value:.0f} °C")
    cond = wx.get("weather")
    if cond is not None and cond.value_text:
        parts.append(cond.value_text)
    return ", ".join(parts) or None


def day_material(db: Session, user_id: str, day: date) -> tuple[list[str], int, int]:
    """Stichpunkte des Tages + Anzahl verwendeter und übergangener Ereignisse.

    Rückgabe: (Zeilen, Anzahl bestätigter Ereignisse, Anzahl unbestätigter).
    """
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)
    # A12: Nutzer-Einschränkung in JEDER Abfrage, ohne Ausnahme.
    events = (db.query(Event)
              .options(selectinload(Event.metrics), selectinload(Event.location),
                       selectinload(Event.entity_links).selectinload(
                           EventEntityLink.entity))
              .filter(Event.user_id == user_id,
                      Event.date_start.isnot(None),
                      Event.date_start >= start, Event.date_start <= end,
                      Event.category.notin_(_SKIP_CATEGORIES))
              .order_by(Event.date_start.asc(), Event.id.asc())
              .all())

    labels = _category_labels()
    lines: list[str] = []
    unconfirmed = 0
    for event in events:
        if event.confirmed != ConfirmState.confirmed:
            unconfirmed += 1
            continue
        bits: list[str] = []
        # Uhrzeit nur bei `exact` — bei Tagesgenauigkeit wäre „00:00" eine
        # Behauptung, die die Daten nicht hergeben (Kap. 3.1).
        if event.date_precision == DatePrecision.exact and event.date_start:
            bits.append(event.date_start.strftime("%H:%M"))
        bits.append(event.title or "(ohne Titel)")
        label = labels.get(event.category)
        if label:
            bits.append(f"[{label}]")
        if event.location and event.location.name:
            bits.append(f"in {event.location.name}")
        names = [link.entity.name for link in event.entity_links
                 if link.entity and link.entity.name]
        if names:
            bits.append("(" + ", ".join(names[:5]) + ")")
        weather = _weather_phrase(event)
        if weather:
            bits.append(f"— Wetter: {weather}")
        lines.append(" ".join(bits))

    used = len(lines)

    # F18: Fotos hängen wahlweise am TAG statt an einem Ereignis — wer sie über
    # Events sucht, findet genau die des Tages nicht (Anmerkung 106). Deshalb
    # beide Behälter: die Bilder der Ereignisse dieses Tages und die, die am
    # Datum selbst hängen. Sie zählen nicht als Ereignis, sind aber ein
    # Stichpunkt: „an dem Tag habe ich 12 Fotos gemacht" sagt etwas über ihn.
    day_event_ids = [e.id for e in events]
    photos = (db.query(MediaRef)
              .filter(MediaRef.user_id == user_id,
                      MediaRef.event_id.in_(day_event_ids) if day_event_ids
                      else MediaRef.id.is_(None))
              .count())
    photos += (db.query(MediaRef)
               .filter(MediaRef.user_id == user_id,
                       MediaRef.event_id.is_(None),
                       MediaRef.captured_at.isnot(None),
                       MediaRef.captured_at >= start, MediaRef.captured_at <= end)
               .count())
    if photos:
        lines.append(f"{photos} Foto{'s' if photos != 1 else ''} an diesem Tag")

    return lines, used, unconfirmed


def suggest(db: Session, user_id: str, day: date) -> tuple[str | None, int, int]:
    """Vorschlagstext für den Tag (oder None) + die beiden Zählungen.

    Wirft `ProviderUnavailable` weiter — ein nicht erreichbares Modell ist eine
    Antwort, die der Nutzer sehen muss, kein leerer Vorschlag.
    """
    lines, used, unconfirmed = day_material(db, user_id, day)
    if not lines:
        return None, 0, unconfirmed
    return get_provider().summarize_day(day, lines), used, unconfirmed
