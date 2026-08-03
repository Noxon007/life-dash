"""Stufe-3-Enrichment: reichert verortete Events mit Wetter an (Metric).

Läuft on-demand über das Admin-Panel und ist jederzeit neu berechenbar,
ohne Stufe 2 zu verändern.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from datetime import time as time_

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import BaselineLocation, DayMetric, Event, Location, Metric, Source
from app.services import baseline
from app.services.weather import fetch_weather

log = logging.getLogger("lifedash.enrichment")


# Welche Wetter-Generation trägt ein Event? Hochzählen, wenn neue Felder
# dazukommen — dann rüstet der nächste Lauf Bestandsdaten additiv nach.
#   1 = 0.14.0, F3-Tageswerte (Min/Max, Sonne, Regen, Schnee, Wind)
#   2 = 0.23.0, F12-Zusatzwerte (gefühlt, Regenstunden, Sonnenlauf, Böen, UV)
WEATHER_REVISION = 2
_REVISION_KEY = "weather_rev"

# F3-Tageswerte — fehlen sie ALLE, stammt das Wetter noch aus der Zeit vor
# 0.14.0 (nur temperature_c + Bedingung). Bleibt als Erkennung für Bestände,
# die noch gar keinen Revisionsmarker tragen.
_DAILY_KEYS = {"temp_min_c", "temp_max_c", "sunshine_h", "rain_mm",
               "snow_cm", "wind_max_kmh"}


def _needs_weather(event: Event) -> bool:
    """Verortet, datiert, nicht in der Zukunft — und Wetter fehlt oder ist
    noch Alt-Format (vor 0.14.0, ohne Tageswerte)?"""
    today = datetime.now(timezone.utc).date()
    loc = event.location
    if not loc or loc.lat is None or event.date_start is None:
        return False
    if event.date_start.date() > today:
        return False  # Zukunft hat noch kein Wetter
    weather = [m for m in event.metrics if m.source == Source.weather]
    if not weather:
        return True
    # Alt-Bestand additiv nachrüsten (KONZEPT F3: „Bestandsdaten per
    # Re-Enrichment additiv ergänzbar") — vorhandene Werte bleiben
    # unangetastet, es kommen nur fehlende Schlüssel dazu.
    #
    # Entscheidend ist der Revisionsmarker, NICHT das Vorhandensein einzelner
    # Felder: Open-Meteo liefert nicht für jeden Ort und jedes Datum jedes
    # Feld (UV und Böen fehlen in alten Archivjahren regelmäßig). Würde man
    # auf die Felder selbst prüfen, geriete so ein Event in eine Endlosschleife
    # und würde bei JEDEM Lauf erneut abgefragt. Der Marker sagt „für diese
    # Generation wurde gefragt" — unabhängig davon, was zurückkam.
    rev = next((m.value for m in weather if m.key == _REVISION_KEY), None)
    if rev is None:
        # Kein Marker: entweder Vor-0.14.0-Bestand (nur temperature_c) oder
        # F3-Bestand aus 0.14.0–0.22.0. Beides bekommt einen Nachrüst-Lauf.
        return True
    return rev < WEATHER_REVISION


def _weather_candidates(db: Session, user_id: str | None = None) -> list[Event]:
    """Verortete, datierte, nicht-zukünftige Events ohne Wetter-Metrik.

    `user_id` grenzt auf ein Konto ein. Der Lauf ist seit 0.38 eine Aktion
    unter „Meine Daten": Wetter ist eine Tatsache über MEINE Ereignisse, kein
    Systemdienst — und ohne diese Eingrenzung würde der Knopf eines Nutzers
    die Ereignisse aller anderen anfassen. Ohne `user_id` (Admin-Endpunkt,
    Tests) bleibt es der alte Rundum-Lauf.

    Diese Suche läuft VOR JEDEM Batch. Sie holte bis 0.34 den GANZEN Bestand
    (`query(Event).all()`) und filterte in Python — samt Lazy-Load von
    `location` und `metrics` je Event. Bei 12 000 Ereignissen war das Suchen
    teurer als das Anreichern (Anmerkung 97). Jetzt entscheidet SQL alles, was
    SQL entscheiden kann; in Python bleibt nur die Revisionsfrage, die aus den
    Metriken kommt (Anmerkung 85: dieselbe Annahme „der Bestand passt in den
    Speicher", die A37 im Frontend beseitigt hat).
    """
    t0 = time.monotonic()
    # `date_start` ist naiv gespeichert (DateTime ohne Zeitzone) — der Vergleich
    # muss es auch sein, sonst vergleicht SQLite Zeichenketten mit und ohne
    # Offset. Grenze ist Mitternacht NACH heute, weil `_needs_weather`
    # tagesgenau urteilt („Zukunft hat noch kein Wetter").
    tomorrow = datetime.combine(datetime.now(timezone.utc).date(), time_.min) \
        + timedelta(days=1)
    q = (db.query(Event)
         .join(Location, Event.location_id == Location.id)
         .filter(Location.lat.isnot(None),
                 Event.date_start.isnot(None),
                 Event.date_start < tomorrow)
         .options(selectinload(Event.metrics),
                  joinedload(Event.location)))
    if user_id is not None:
        q = q.filter(Event.user_id == user_id)
    rows = q.all()
    hits = [e for e in rows if _needs_weather(e)]
    log.debug("Wetter-Kandidaten: %d von %d vorgefilterten Ereignissen (%.1f s)",
              len(hits), len(rows), time.monotonic() - t0)
    return hits


# F3: gespeicherte Tageswerte -> Metrik-Schlüssel + Einheit
_WEATHER_METRICS = {
    "temp_c": ("temperature_c", "°C"),   # Tagesmittel (Kompatibilität/Statistik)
    "temp_min_c": ("temp_min_c", "°C"),
    "temp_max_c": ("temp_max_c", "°C"),
    "sun_h": ("sunshine_h", "h"),
    "rain_mm": ("rain_mm", "mm"),
    "snow_cm": ("snow_cm", "cm"),
    "wind_max_kmh": ("wind_max_kmh", "km/h"),
    # --- F12 (0.23.0) ---
    "apparent_max_c": ("apparent_temp_max_c", "°C"),
    "apparent_min_c": ("apparent_temp_min_c", "°C"),
    "rain_h": ("rain_h", "h"),
    "daylight_h": ("daylight_h", "h"),
    "gust_max_kmh": ("gust_max_kmh", "km/h"),
    "uv_max": ("uv_max", None),
}

# F12: Werte, die als Text gespeichert werden (Uhrzeiten statt Zahlen)
_WEATHER_TEXT_METRICS = {
    "sunrise": "sunrise",
    "sunset": "sunset",
}


def _add_weather(db: Session, event: Event) -> bool:
    """Holt Wetter für EIN Event und hängt es als Metriken an (ohne Commit).
    F3: reine Tageswerte — Min/Max, Sonnenstunden, Regen, Schnee, Wind.
    Nur FEHLENDE Schlüssel werden angelegt (0.15.1: Alt-Bestand wird additiv
    vervollständigt; Fakten werden nie überschrieben)."""
    w = fetch_weather(event.location.lat, event.location.lng, event.date_start)
    if not w:
        return False
    have = {m.key for m in event.metrics if m.source == Source.weather}
    added = 0
    for src, (key, unit) in _WEATHER_METRICS.items():
        if key in have or w.get(src) is None:
            continue
        db.add(Metric(event_id=event.id, key=key, value=w[src],
                      unit=unit, source=Source.weather))
        added += 1
    if "weather" not in have and w.get("condition"):
        db.add(Metric(event_id=event.id, key="weather",
                      value_text=w["condition"], source=Source.weather))
        added += 1
    for src, key in _WEATHER_TEXT_METRICS.items():   # F12: Sonnenauf-/-untergang
        if key in have or not w.get(src):
            continue
        db.add(Metric(event_id=event.id, key=key,
                      value_text=w[src], source=Source.weather))
        added += 1
    # Revisionsmarker setzen bzw. hochziehen — auch wenn die Quelle diesmal
    # kein einziges neues Feld geliefert hat. Genau das verhindert, dass
    # dasselbe Event bei jedem Lauf erneut abgefragt wird.
    marker = next((m for m in event.metrics
                   if m.source == Source.weather and m.key == _REVISION_KEY), None)
    if marker is None:
        db.add(Metric(event_id=event.id, key=_REVISION_KEY,
                      value=WEATHER_REVISION, source=Source.weather))
        added += 1
    elif (marker.value or 0) < WEATHER_REVISION:
        marker.value = WEATHER_REVISION
        added += 1
    return added > 0


def auto_enrich_events(db: Session, events: list[Event]) -> int:
    """Auto-Enrichment direkt nach Ingest/Eingabe (P2.4): Wetter für die
    gerade erzeugten Events ergänzen, statt auf den Admin-Knopf zu warten.

    Best effort — Fehler (z. B. Open-Meteo nicht erreichbar) dürfen die
    Erfassung nie scheitern lassen; fehlendes Wetter trägt später der
    Admin-Lauf nach. Commit macht der Aufrufer."""
    enriched = 0
    for event in events:
        try:
            if _needs_weather(event) and _add_weather(db, event):
                enriched += 1
        except Exception as exc:  # noqa: BLE001 — Anreicherung ist nie kritisch
            # Nicht mehr stumm: ohne Spur bleibt „warum hat mein Eintrag kein
            # Wetter?" unbeantwortbar (Punkt 5). DEBUG, damit es das Log bei
            # zeitweiligen Open-Meteo-Aussetzern nicht flutet.
            log.debug("Auto-Anreicherung übersprungen (%s): %s",
                      getattr(event, "id", "?"), exc)
            continue
    return enriched


# --------------------------------------------------------------------------- #
# F20 — Wetter für Tage, an denen KEIN Ereignis steht (Grundort)
# --------------------------------------------------------------------------- #
def _baseline_users(db: Session, user_id: str | None) -> list[str]:
    """Wessen Grundorte dieser Lauf anfasst.

    Mit `user_id` genau dieses Konto (der Weg über „Meine Daten", Anmerkung
    115). Ohne — der alte Rundum-Lauf — alle Konten, die überhaupt einen
    Grundort haben; über alle Nutzer zu iterieren, um dann fast überall nichts
    zu finden, wäre eine Abfrage je Konto für nichts.
    """
    if user_id is not None:
        return [user_id]
    return [uid for (uid,) in
            db.query(BaselineLocation.user_id).distinct().all() if uid]


def _day_weather_candidates(db: Session, user_id: str | None = None
                            ) -> list[tuple[str, object, Location]]:
    """(Konto, Tag, Ort) für Grundort-Tage, die noch keine Wettermarke tragen.

    **Dieselbe Marker-Regel wie bei den Ereignissen** (`weather_rev`), und aus
    demselben Grund: Open-Meteo liefert nicht für jeden Ort und jedes Datum
    jedes Feld, also darf „ein Feld fehlt" nicht heißen „noch mal fragen" —
    sonst fragt derselbe Tag bei jedem Lauf erneut (die Endlos-Abruf-Falle,
    deren Auflagen dieses Projekt inzwischen durchnummeriert).

    **Und dieselbe Behandlung des Fehlschlags:** kam gar keine Antwort, wird
    NICHT markiert und der Tag beim nächsten Lauf erneut versucht. Das ist
    bewusst identisch mit `_add_weather` — ein zweites Verhalten an derselben
    Frage wäre die Doppelregel, gegen die diese Datei ohnehin schon einmal
    verloren hat.
    """
    out: list[tuple[str, object, Location]] = []
    for uid in _baseline_users(db, user_id):
        days = baseline.inferred_days(db, uid)
        if not days:
            continue
        done = {d for (d,) in
                db.query(DayMetric.day)
                .filter(DayMetric.user_id == uid,
                        DayMetric.key == _REVISION_KEY,
                        DayMetric.value >= WEATHER_REVISION).all()}
        for day in sorted(days):
            if day in done:
                continue
            loc = days[day].location
            if loc is not None and loc.lat is not None and loc.lng is not None:
                out.append((uid, day, loc))
    return out


def _add_day_weather(db: Session, user_id: str, day, loc: Location) -> bool:
    """Wetter für EINEN Grundort-Tag holen und als `DayMetric` ablegen.

    Spiegelt `_add_weather` Zeile für Zeile — dieselben Schlüssel, dieselben
    Einheiten, dasselbe „nur Fehlendes anlegen", derselbe Revisionsmarker. Das
    ist Absicht und keine Kopierfaulheit: die Tabelle daneben hat dieselbe Form,
    damit `weather_day` beide vereinigen kann, und ein zweites Schlüsselschema
    hier hieße, dass die Vereinigung zwei verschiedene Dinge addiert.
    """
    w = fetch_weather(loc.lat, loc.lng, day)
    if not w:
        return False
    have = {k for (k,) in db.query(DayMetric.key)
            .filter(DayMetric.user_id == user_id, DayMetric.day == day).all()}
    added = 0

    def put(key: str, *, value=None, text=None, unit=None) -> None:
        nonlocal added
        db.add(DayMetric(user_id=user_id, day=day, key=key, value=value,
                         value_text=text, unit=unit, source=Source.weather))
        added += 1

    for src, (key, unit) in _WEATHER_METRICS.items():
        if key not in have and w.get(src) is not None:
            put(key, value=w[src], unit=unit)
    if "weather" not in have and w.get("condition"):
        put("weather", text=w["condition"])
    for src, key in _WEATHER_TEXT_METRICS.items():
        if key not in have and w.get(src):
            put(key, text=w[src])
    if _REVISION_KEY not in have:
        put(_REVISION_KEY, value=WEATHER_REVISION)
    else:
        marker = (db.query(DayMetric)
                  .filter(DayMetric.user_id == user_id, DayMetric.day == day,
                          DayMetric.key == _REVISION_KEY).first())
        if marker is not None and (marker.value or 0) < WEATHER_REVISION:
            marker.value = WEATHER_REVISION
            added += 1
    return added > 0


def enrich_weather(db: Session, limit: int | None = None,
                   user_id: str | None = None) -> tuple[int, int]:
    """Hängt Temperatur + Bedingung an Events ohne Wetter (Batch fürs Admin-UI).

    Gibt (angereichert, verbleibend) zurück. Wetter ist Fakten-Anreicherung
    (KONZEPT Kap. 3.1): einmal geholt = dauerhaft; es wird nur ergänzt,
    nie verworfen und neu berechnet.

    `user_id` grenzt auf ein Konto ein (siehe `_weather_candidates`).
    """
    candidates = _weather_candidates(db, user_id)
    batch = candidates if limit is None else candidates[:limit]
    # Pro Event committen: der Unique-Index (A11, ux_metrics_weather) weist
    # Dubletten aus parallelen Läufen ab — dann verliert nur DIESES Event
    # (bereits angereichert), nicht der ganze Batch.
    enriched = 0
    blank: list[str] = []
    for event in batch:
        try:
            if _add_weather(db, event):
                db.commit()
                enriched += 1
                log.debug("Wetter: %s (%s) angereichert",
                          event.title, event.date_start.date())
            else:
                blank.append(f"{event.title} ({event.date_start.date()})")
        except IntegrityError:
            db.rollback()  # parallele Instanz war schneller — kein Schaden
    # Ereignisse, für die es nichts gab, sind der Grund, aus dem ein Lauf mit
    # „nicht anreicherbar" stehen bleibt. Ohne Beispiel im Log ist diese
    # Meldung nicht nachvollziehbar — welches Datum, welcher Ort?
    if blank:
        log.info("Wetter: %d von %d ohne Daten (z. B. %s)",
                 len(blank), len(batch), "; ".join(blank[:3]))

    # --- F20: die Grundort-Tage, NACH den Ereignissen -----------------------
    # Die Reihenfolge ist eine Aussage: ein Ereignis ist eine erfasste Tatsache,
    # ein Grundort-Tag ist die Ableitung darüber. Wer den Lauf abbricht, soll
    # das Erfasste vollständig haben und nicht die Hälfte von beidem. Dass die
    # Ableitung überhaupt in DIESEN Lauf gehört und nicht in einen eigenen, ist
    # dieselbe Entscheidung: „Wetter ergänzen" ist eine Aussage über den
    # eigenen Bestand, und zwei Knöpfe für eine Absicht sind der Weg, auf dem
    # der zweite nie gedrückt wird.
    day_total, day_done = 0, 0
    room = None if limit is None else max(0, limit - len(batch))
    if room != 0:
        days = _day_weather_candidates(db, user_id)
        day_total = len(days)
        for uid, day, loc in (days if room is None else days[:room]):
            try:
                if _add_day_weather(db, uid, day, loc):
                    db.commit()
                    day_done += 1
            except IntegrityError:
                db.rollback()  # paralleler Lauf war schneller — kein Schaden

    # Zwei Reste, getrennt gerechnet und dann addiert. Zusammengezählt VOR dem
    # Abziehen käme Unsinn heraus, sobald beide Quellen im selben Durchgang
    # etwas beitragen — der angereicherte Grundort-Tag zöge dann die Zahl der
    # offenen EREIGNISSE herunter.
    return enriched + day_done, (len(candidates) - enriched) + (day_total - day_done)
