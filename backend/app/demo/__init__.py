"""R1a — der Demo-Bestand: ein erfundenes Leben hinter EINEM Schalter.

**Warum es das gibt.** Niemand bewertet eine Lebensdatenbank anhand seines
eigenen Lebens — dazu müsste er sie erst einmal füllen, und genau davor steht
die Entscheidung, ob er sie überhaupt installiert. Ohne einen mitgelieferten
Bestand gibt es außerdem keine Screenshots, und das ist das Erste, was ein
Fremder ansieht. Deshalb ist dies das Paket, das alle anderen des
Veröffentlichungs-Gatters freischaltet.

**Der Bestand wird GEBAUT, nicht durch die Pipeline gejagt.** Der alte
Demo-Seed schickte sieben Sätze durch `ingest_fragment`, und für sieben Sätze
war das richtig: es zeigte den Weg Fragment → Vorschlag → Lebensdatenbank. Für
dreißig Jahre ist es der falsche Weg, und zwar aus einem Grund, der nichts mit
Geschwindigkeit zu tun hat: **das Ergebnis hinge dann am KI-Anbieter.** Derselbe
Schalter ergäbe mit Mock-KI einen anderen Bestand als mit Gemini, jeder
Screenshot wäre ein Einzelstück, und ein Fehler in der Erkennung sähe aus wie
ein Fehler in der Demo. Was hier entsteht, ist das ERGEBNIS der Pipeline, und
das ist die einzige Zusage, die ein Schaufenster machen soll.

**Die drei Schichten bleiben trotzdem sichtbar.** Ein Bestand, in dem alles
bestätigt ist, zeigt die halbe App nicht — deshalb landen ein paar unverarbeitete
Fragmente und ein paar unbestätigte Vorschläge mit im Bestand. Wer nur die
Lebensdatenbank sieht, sieht eine Datenbank mit Formular.

**Wo der Zufall sitzt und wo nicht.** Die Biografie (`life.py`) ist geschrieben:
Wohnorte, Reisen, Konzerte. Gewürfelt wird nur, was in einem echten Bestand auch
beliebig ist — an welchem Dienstag jemand laufen war. Und auch das aus einem
festen Startwert, damit zweimal aufgebaut zweimal denselben Bestand ergibt:
sonst wäre jeder Screenshot ein Einzelstück und jede Messung gegen den
Demo-Bestand unwiederholbar.

**Das Wetter kommt nicht aus dem Netz** (siehe `demo/weather.py`) — und es trägt
denselben Revisionsmarker wie echtes. Ohne den würde der Wetter-Lauf den ganzen
Demo-Bestand für unbearbeitet halten und beim ersten Klick elftausend Abrufe
gegen Open-Meteo starten: die Endlos-Abruf-Falle in neuem Gewand, diesmal
eingebaut vom Erbauer statt vom Abrufer.
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.demo import life, photos
from app.demo.weather import synth_weather
from app.models import (BaselineLocation, ConfirmState, DatePrecision, DayMetric,
                        Entity, Event, EventEntityLink, Fragment, FragmentStatus,
                        Location, MediaRef, Metric, Source, Track, User)
from app.services import geocode, media
from app.services.enrichment import WEATHER_REVISION, _too_recent

log = logging.getLogger("lifedash.demo")

# Ein fester Startwert — der Demo-Bestand ist reproduzierbar, siehe Modulkopf.
SEED = 20260809

# Ab hier gibt es importierte Gerätedaten. Vorher hatte diese Person kein
# Smartphone, das Wege aufzeichnet — ein Zeitstrahl, der 2003 schon
# Google-Besuche zeigt, erzählt eine Geschichte über die Zufuhr, die nicht
# stimmt.
TIMELINE_FROM = date(2016, 1, 1)

# Die Schlüssel, unter denen `weather.synth_weather` seine Werte liefert, und
# wie sie in der Datenbank heißen. **Dieselbe Abbildung wie in
# `enrichment._WEATHER_METRICS`** — sie hier zu wiederholen wäre die doppelte
# Regel, vor der dieses Projekt an sechs Stellen warnt, deshalb wird sie
# importiert und nicht abgeschrieben.
from app.services.enrichment import (_WEATHER_METRICS,  # noqa: E402
                                     _WEATHER_TEXT_METRICS)


def _uuid() -> str:
    return str(uuid.uuid4())


def _noon(day: date, hour: int = 12, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute))


class _Builder:
    """Sammelt Zeilen im Speicher und schreibt sie am Stück.

    Einzeln über den ORM wären es sechsstellig viele Aufrufe für einen Bestand,
    den niemand danach noch bearbeitet. Gesammelt und als Core-Insert
    geschrieben ist derselbe Bestand eine Sache von Sekunden — und der ORM
    bleibt für alles zuständig, was danach damit passiert.
    """

    def __init__(self, db: Session, user: User) -> None:
        self.db = db
        self.user = user
        self.rng = random.Random(SEED)
        self.locations: dict[str, Location] = {}
        self.entities: dict[tuple[str, str], Entity] = {}
        self.events: list[dict] = []
        self.links: list[dict] = []
        self.tracks: list[dict] = []
        self.metrics: list[dict] = []
        self.day_metrics: list[dict] = []
        self.media: list[dict] = []
        self.today = date.today()
        # **Der Alltag endet gestern.** Ein Tagebucheintrag von heute 21 Uhr,
        # angelegt um halb elf am Morgen, ist ein Ereignis in der Zukunft — die
        # App behandelt solche Tage überall als Sonderfall (kein Wetter, keine
        # Wertung), und ein Schaufenster sollte den Sonderfall nicht als
        # Normalfall zeigen. Die Vorschläge in der Warteschlange rechnen
        # weiterhin von `today` zurück; sie sind ja gerade das Frische.
        self.last_day = self.today - timedelta(days=1)

    # -- Orte ------------------------------------------------------------- #
    def place(self, key: str) -> Location:
        """Ein Ort aus dem Verzeichnis, einmal angelegt und wiederverwendet.

        Ein zweiter Ort mit denselben Koordinaten wäre in jeder Rangliste eine
        zweite Zeile — genau der Befund aus Anmerkung 198, nur selbst gebaut.
        """
        if key not in self.locations:
            name, city, country, lat, lng = life.PLACES[key]
            self.locations[key] = self._location(name, city, country, lat, lng)
        return self.locations[key]

    def _location(self, name: str, city: str, country: str,
                  lat: float, lng: float, type_: str = "poi") -> Location:
        """Ein Ort. `name_manual` folgt der Wahrheit über den NAMEN.

        **Anmerkung 222: nicht mehr pauschal `True`.** Die Marke bedeutet „ein
        Mensch hat diesen Namen getippt" (Anmerkung 148) und schützt ihn vor
        dem nächsten Auflöse-Lauf. Für „Kirschenallee 12" stimmt das. Für den
        Koordinaten-Platzhalter „Ort (53.555, 9.966)" hat sie nie jemand
        getippt, und die Folge war sichtbar: `_resolve_candidates` lässt von
        Hand benannte Orte aus, also meldete „Ortsnamen auflösen" **null
        offene Orte, während 3.633 unaufgelöst dastanden**.

        Ein Platzhalter ist damit genau das, was er ist: ein Ort, dessen Name
        noch aussteht. `address` bleibt für ihn ebenfalls offen (NULL statt
        `{}`) — das ist der Zustand „nie nachgesehen", und nur in dem hat der
        Lauf etwas zu holen. Bei den benannten Orten bleibt beides wie bisher,
        damit für ein erfundenes Café kein echter Geocoder befragt wird.
        """
        placeholder = geocode.is_coordinate_name(name)
        loc = Location(id=_uuid(), user_id=self.user.id, name=name, type=type_,
                       lat=lat, lng=lng, city=city, country=country,
                       # Benannt: `{}` und nicht NULL — „nachgesehen, nichts
                       # bekommen". NULL hieße „nie nachgesehen", und der
                       # Rückfüll-Lauf würde für einen erfundenen Ort echtes
                       # Geocoding fahren.
                       address=None if placeholder else {},
                       name_manual=not placeholder)
        self.db.add(loc)
        return loc

    def trip_place(self, trip) -> Location:
        _, _, _, name, city, country, lat, lng, _ = trip
        key = f"trip:{name}:{city}"
        if key not in self.locations:
            self.locations[key] = self._location(name, city, country, lat, lng, "city")
        return self.locations[key]

    # -- Kompendium -------------------------------------------------------- #
    def entity(self, type_: str, name: str) -> Entity:
        key = (type_, name.lower())
        if key not in self.entities:
            ent = Entity(id=_uuid(), user_id=self.user.id, type=type_, name=name,
                         attributes={}, confirmed=ConfirmState.confirmed)
            self.db.add(ent)
            self.entities[key] = ent
        return self.entities[key]

    def link(self, event_id: str, entity: Entity, role: str = "subject") -> None:
        self.links.append({"id": _uuid(), "event_id": event_id,
                           "entity_id": entity.id, "role": role})

    # -- Ereignisse -------------------------------------------------------- #
    def event(self, when: date, title: str, category: str, loc: Location, *,
              hour: int = 12, minute: int = 0, note: str | None = None,
              source: Source = Source.manual, confirmed: bool = True,
              confidence: float = 1.0, precision: DatePrecision = DatePrecision.day,
              confirmed_by: str = "manual", until: date | None = None,
              parent: str | None = None) -> str:
        """Ein Ereignis.

        `until` macht daraus einen MEHRTÄGER, `parent` ein Tages-Kind (F7).

        Anmerkung 222: Es gab hier kurz ein `weather=False`, um dem Elternteil
        einer Reise die Wetterwerte zu ersparen. Es ist wieder weg — jedes
        bestätigte Ereignis bekommt sie, weil `enrichment` es genauso täte, und
        ein Schalter ohne Aufrufer ist die Einladung, den Fehler zu wiederholen
        (siehe `_trips`).
        """
        eid = _uuid()
        start = _noon(when, hour, minute)
        self.events.append({
            "id": eid, "user_id": self.user.id, "title": title, "description": None,
            "date_start": start,
            "date_end": _noon(until, 20) if until else None,
            "date_precision": precision,
            "category": category, "note": note, "confidence": confidence,
            "confirmed": ConfirmState.confirmed if confirmed else ConfirmState.unconfirmed,
            "confirmed_at": start if confirmed else None,
            "confirmed_by": confirmed_by if confirmed else None,
            "field_overrides": {}, "source": source, "location_id": loc.id,
            "origin_fragment_id": None, "parent_event_id": parent, "embedding": None,
            "external_id": None, "created_at": start, "updated_at": start,
        })
        if confirmed:
            self._weather_for(eid, loc, when)
        return eid

    # -- Bilder ------------------------------------------------------------ #
    def photo(self, when: date, caption: str, loc: Location, *,
              event_id: str | None = None, hour: int = 12, order: int = 0) -> None:
        """Ein erzeugtes Platzhalterbild, gespeichert wie ein Upload.

        `event_id=None` hängt es an den TAG statt an ein Ereignis (F18) — der
        Ort, an den ein Foto am ehesten gehört, und bis 0.34 der einzige, an
        den es nicht konnte. Beide Fälle kommen im Bestand vor, weil die
        Foto-Statistik beide liest und nur eine Hälfte zu füllen eine
        Auswertung ergäbe, die vollständig aussieht.
        """
        data = photos.make_photo(loc.city or loc.name, when.isoformat(), caption)
        stored = media.store(self.user.id, data)
        captured = _noon(when, hour, 0)
        self.media.append({
            "id": _uuid(), "user_id": self.user.id, "event_id": event_id,
            "provider": "local", "external_id": stored["filename"],
            "captured_at": captured, "mime": stored["mime"],
            "bytes": stored["bytes"], "width": stored["width"],
            "height": stored["height"], "caption": caption,
            "sort_order": order, "created_at": captured,
        })

    # -- Wetter ------------------------------------------------------------ #
    def _weather_rows(self, loc: Location, day: date) -> list[tuple[str, float | None, str | None, str | None]]:
        """(Schlüssel, Zahl, Text, Einheit) für einen Ort an einem Tag."""
        w = synth_weather(loc.lat, loc.lng, day)
        rows: list[tuple[str, float | None, str | None, str | None]] = []
        for src, (key, unit) in _WEATHER_METRICS.items():
            if w.get(src) is not None:
                rows.append((key, w[src], None, unit))
        rows.append(("weather", None, w["condition"], None))
        for src, key in _WEATHER_TEXT_METRICS.items():
            rows.append((key, None, w[src], None))
        # Die Marke, ohne die der nächste Wetter-Lauf alles noch einmal fragte.
        rows.append(("weather_rev", float(WEATHER_REVISION), None, None))
        return rows

    def _weather_for(self, event_id: str, loc: Location, day: date) -> None:
        # **Die Grenze wird GEFRAGT, nicht abgeschrieben.** Hier stand eine 6,
        # weil das Archiv sechs Tage hinterherhinkt — dieselbe Zahl, die
        # `weather.ERA5_LAG_DAYS` trägt, nur zusätzlich um einen Tag verschoben,
        # weil sie von `last_day` statt von heute rechnete. Ergebnis: zwei Tage,
        # deren Ereignisse ohne Wetter blieben, obwohl der Lauf sie für
        # anreicherbar hält — also genau die Kandidaten, die der Demo-Bestand
        # nicht hinterlassen soll.
        if _too_recent(day):
            return
        now = datetime.now()
        for key, value, text, unit in self._weather_rows(loc, day):
            self.metrics.append({"id": _uuid(), "event_id": event_id, "key": key,
                                 "value": value, "value_text": text, "unit": unit,
                                 "source": Source.weather, "enriched_at": now})

    def day_weather(self, day: date, loc: Location) -> None:
        now = datetime.now()
        for key, value, text, unit in self._weather_rows(loc, day):
            self.day_metrics.append({"id": _uuid(), "user_id": self.user.id, "day": day,
                                     "key": key, "value": value, "value_text": text,
                                     "unit": unit, "source": Source.weather,
                                     "enriched_at": now})

    # -- Schreiben --------------------------------------------------------- #
    def flush(self) -> None:
        self.db.flush()          # Orte und Entities brauchen ihre IDs
        # **Reihenfolge ist hier eine Zusage, keine Bequemlichkeit.** Die
        # Core-Inserts gehen an den ORM-Beziehungen vorbei, die sonst
        # dafür sorgen; Bilder und Verknüpfungen verweisen auf
        # Ereignisse, also stehen sie dahinter. Auf SQLite fiele ein
        # Fehler hier gar nicht auf.
        for table, rows in ((Event, self.events), (EventEntityLink, self.links),
                            (MediaRef, self.media), (Track, self.tracks),
                            (Metric, self.metrics), (DayMetric, self.day_metrics)):
            for chunk in _chunks(rows, 5000):
                self.db.execute(table.__table__.insert(), chunk)


def _chunks(rows: list, size: int):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def _weighted(rng: random.Random, weighted: list[tuple[str, int]]) -> str:
    total = sum(w for _, w in weighted)
    roll = rng.randrange(total)
    for name, weight in weighted:
        roll -= weight
        if roll < 0:
            return name
    return weighted[-1][0]


# --------------------------------------------------------------------------- #
# Die einzelnen Kapitel
# --------------------------------------------------------------------------- #
def _residences(b: _Builder) -> list[tuple[date, date, Location, str]]:
    """Die Wohnorte als stehende Tatsachen — und ihre Zeiträume zurück.

    Anmerkung 222: Der SCHLÜSSEL des Wohnorts steht mit im Zeitraum, weil der
    Timeline-Import ihn braucht — an ihm hängen die Orte des Alltags
    (`life.ERRANDS`). Über die Location allein ginge es nicht: Altona und
    Eimsbüttel liegen beide in Hamburg, und ihre Alltagsorte sind verschieden.
    """
    spans: list[tuple[date, date, Location, str]] = []
    for label, key, start, end in life.RESIDENCES:
        loc = b.place(key)
        b.db.add(BaselineLocation(id=_uuid(), user_id=b.user.id, location_id=loc.id,
                                  label=label, date_start=start, date_end=end))
        spans.append((start, end or b.last_day, loc, key))
    return spans


def _home_at(spans: list[tuple[date, date, Location, str]], day: date) -> Location:
    """Wo diese Person an diesem Tag zu Hause war.

    **Der letzte Abschnitt, der begonnen hat — nicht der, der ihn enthält.**
    Die Wohnorte haben eine Lücke (siehe `life.RESIDENCES`), und in ihr gibt es
    trotzdem Alltag. Die naheliegende Fassung („der Abschnitt, in dem der Tag
    liegt, sonst der letzte") ließ die Ereignisse dieser zweieinhalb Monate am
    HEUTIGEN Wohnort stattfinden — 2020 in einer Wohnung, die es erst 2022 gab.
    Eine Zeile, die niemand ansieht, und eine Landkarte, die es doch tut.
    """
    home = spans[0][2]
    for start, _end, loc, _key in spans:
        if start <= day:
            home = loc
    return home


def _home_key_at(spans: list[tuple[date, date, Location, str]], day: date) -> str:
    """Derselbe Griff wie `_home_at`, nur der Schlüssel — für `life.ERRANDS`.

    Dieselbe Regel ausgeschrieben wäre die stille Doppelregel; deshalb dieselbe
    Schleife über dieselbe Liste, und wer eine ändert, sieht die andere.
    """
    key = spans[0][3]
    for start, _end, _loc, k in spans:
        if start <= day:
            key = k
    return key


def _milestones(b: _Builder) -> None:
    for when, title, key in life.MILESTONES:
        loc = b.place(key)
        eid = b.event(when, title, "milestone", loc, hour=10)
        b.photo(when, title, loc, event_id=eid, hour=10)


def _day_photos(b: _Builder, spans: list[tuple[date, date, Location, str]]) -> None:
    """Bilder, die an einem TAG hängen und an keinem Ereignis (F18).

    **Beide Sorten müssen vorkommen.** Die Foto-Statistik liest `captured_at`
    ersatzweise das Datum des Ereignisses — wer nur eine Hälfte füllt, bekommt
    eine Auswertung, die vollständig aussieht und es nicht ist. Und der Tag ist
    der Ort, an den ein Bild am ehesten gehört: bis 0.34 war er der einzige, an
    den es nicht konnte.
    """
    day = date(2015, 1, 1)
    while day <= b.last_day:
        day += timedelta(days=9 + b.rng.randrange(28))
        if day > b.last_day or life.in_blank(day):
            continue
        home = _home_at(spans, day)
        b.photo(day, f"Aus dem Alltag in {home.city}", home, hour=17)


def _trips(b: _Builder) -> None:
    for trip in life.TRIPS:
        start, days, title, _, city, country, _, _, programme = trip
        loc = b.trip_place(trip)
        country_entity = b.entity("country", country)
        last = min(start + timedelta(days=days - 1), b.last_day)
        if start > b.last_day:
            continue
        # **Anmerkung 222: die Reise selbst ist ein Ereignis, die Tage sind ihre
        # Kinder (F7).** Bis hierher gab es nur die Tage — mit der Begründung,
        # ein ungeteilter Mehrtäger belege nur seinen Anfangstag und der Wohnort
        # fülle die übrigen. Die Begründung stimmt, die Schlussfolgerung war zu
        # weit: genau dafür gibt es Tages-Kinder. Die Kinder tragen die Tage
        # (die Statistik bleibt also richtig), der Elternteil trägt die SPANNE.
        #
        # Ohne ihn zeigte der ausgelieferte Bestand vier Dinge nicht, die es
        # gibt: „Längste Reise" stand dauerhaft auf „—", F7 hatte kein einziges
        # Eltern/Kind-Paar, die Mittelung der wärmsten Reise über
        # `parent_event_id` lief nie, und die Abfrage, die dafür in
        # `weather_values` steht, gab in jedem Lauf null Zeilen zurück.
        #
        # **Der Elternteil bekommt Wetter wie jedes andere Ereignis**, obwohl
        # eine Temperatur für dreizehn Tage keine Angabe ist. Der erste Entwurf
        # ließ es weg — und `test_the_weather_run_has_nothing_left_to_fetch`
        # wurde sofort rot: `enrichment` sieht `date_end` überhaupt nicht an,
        # ein Mehrtäger bekommt dort das Wetter seines ANFANGSTAGS. Ohne
        # Metriken fehlt dem Elternteil damit der Revisionsmarker, und der
        # Wetter-Knopf hätte im Schaufenster neunundzwanzig Abrufe gegen
        # Open-Meteo gestartet — die Endlos-Abruf-Falle, diesmal selbst gebaut.
        #
        # Die Lehre ist die Regel dieses Moduls: **der Demo-Bestand ist das
        # ERGEBNIS der Pipeline und keine schönere Fassung davon.** Was die
        # Anreicherung an einem Mehrtäger täte, muss hier stehen, auch wenn ich
        # es anders gebaut hätte.
        parent = b.event(start, title, "trip", loc, hour=8, until=last,
                         note=f"{(last - start).days + 1} Tage")
        b.link(parent, country_entity, "mentioned")
        for offset in range(days):
            day = start + timedelta(days=offset)
            if day > b.last_day:
                break
            if offset < len(programme):
                heading = programme[offset]
            elif offset == days - 1:
                heading = f"Abreise aus {city}"
            else:
                heading = life.FILLER_DAYS[offset % len(life.FILLER_DAYS)]
            hour = 9 + (offset * 3) % 9
            eid = b.event(day, heading, "trip", loc, hour=hour, parent=parent)
            b.link(eid, country_entity, "mentioned")
            # Auf einer Reise wird fotografiert, zu Hause seltener — deshalb
            # sitzen die Bilder hier und nicht gleichverteilt über den Bestand.
            # Ein Foto-Jahr, das aussieht wie jedes andere, wäre eine Aussage
            # über den Generator statt über ein Leben.
            for k in range(b.rng.randrange(3)):
                b.photo(day, heading, loc, event_id=eid, hour=hour, order=k)


def _concerts(b: _Builder) -> None:
    for when, artist, venue, key in life.CONCERTS:
        if when > b.last_day:
            continue
        loc = b.place(key)
        eid = b.event(when, f"{artist} — {venue}", "concert", loc, hour=20)
        b.link(eid, b.entity("artist", artist))
        if b.rng.random() < 0.6:
            b.photo(when, artist, loc, event_id=eid, hour=20)


def _habits(b: _Builder, spans: list[tuple[date, date, Location, str]]) -> None:
    """Der Alltag: verteilt über die Jahre, gewichtet nach Lebensabschnitt."""
    for category, since, until, per_year in life.HABITS:
        day = max(since, life.BIRTH)
        stop = min(until or b.last_day, b.last_day)
        while day <= stop:
            # Der Abstand schwankt um den Mittelwert, statt fest zu sein — ein
            # Bestand mit exakt alle 3,8 Tage einem Eintrag sieht aus wie ein
            # Cronjob und nicht wie ein Leben.
            gap = max(1, int(365 / per_year * (0.35 + 1.3 * b.rng.random())))
            day += timedelta(days=gap)
            if day > stop:
                break
            if life.in_blank(day):
                continue
            home = _home_at(spans, day)
            _one_habit(b, category, day, home)


def _one_habit(b: _Builder, category: str, day: date, home: Location) -> None:
    city = home.city or ""
    if category == "sport":
        spots = life.SPORT_SPOTS.get(city, [])
        loc = b.place(b.rng.choice(spots)) if spots else home
        kind, lo, hi = life.SPORT_KINDS[b.rng.randrange(len(life.SPORT_KINDS))]
        km = round(lo + (hi - lo) * b.rng.random(), 1)
        b.event(day, f"{kind}, {km} km", "sport", loc,
                hour=7 + b.rng.randrange(12))
    elif category == "journal":
        b.event(day, "Tagebuch", "journal", home, hour=21,
                note=life.JOURNAL_LINES[b.rng.randrange(len(life.JOURNAL_LINES))])
    elif category == "meal":
        names = life.RESTAURANTS.get(city) or ["Zu Hause"]
        where = names[b.rng.randrange(len(names))]
        dish = life.DISHES[b.rng.randrange(len(life.DISHES))]
        eid = b.event(day, f"{dish} — {where}", "meal", home, hour=19)
        b.link(eid, b.entity("food", dish))
    elif category == "sighting":
        animal = _weighted(b.rng, life.ANIMALS)
        eid = b.event(day, f"{animal} gesehen", "sighting", home,
                      hour=6 + b.rng.randrange(14))
        b.link(eid, b.entity("animal", animal))
    elif category == "media":
        roll = b.rng.random()
        if roll < 0.45:
            title, type_, verb = (life.MOVIES[b.rng.randrange(len(life.MOVIES))],
                                  "movie", "Gesehen")
        elif roll < 0.8:
            title, type_, verb = (life.BOOKS[b.rng.randrange(len(life.BOOKS))],
                                  "book", "Gelesen")
        else:
            title, type_, verb = (life.GAMES[b.rng.randrange(len(life.GAMES))],
                                  "game", "Gespielt")
        eid = b.event(day, f"{verb}: {title}", "media", home, hour=20)
        b.link(eid, b.entity(type_, title))


def _timeline_import(b: _Builder, spans: list[tuple[date, date, Location, str]]) -> None:
    """Was ein Google-Timeline-Import hinterlässt: Besuche und Wege.

    Eigene Quelle und `confirmed_by="import"` — Gerätedaten werden beim Import
    bestätigt, und der Zeitstrahl kann sie deshalb als Gruppe wieder
    ausblenden. Ohne diesen Teil zeigte die Demo weder den Wege-Reiter noch den
    Schalter, der die Hälfte des Zeitstrahls betrifft.
    """
    day = TIMELINE_FROM
    while True:
        # Erst zählen, dann prüfen — die Schleife stand andersherum da und
        # legte genau EINEN Besuch am heutigen Tag an, also in der Zukunft.
        # Ein Ereignis, das nicht auffällt, weil es eines von achttausend ist.
        day += timedelta(days=1)
        if day > b.last_day:
            break
        if b.rng.random() > 0.55:      # nicht jeder Tag hinterlässt eine Spur
            continue
        if life.in_blank(day):
            continue
        home, home_key = _home_at(spans, day), _home_key_at(spans, day)
        for _ in range(1 + b.rng.randrange(3)):
            loc = _visit_place(b, home, home_key)
            hour = 7 + b.rng.randrange(14)
            eid = b.event(day, f"Besuch in {home.city}", "event", loc,
                          hour=hour, source=Source.google_timeline,
                          confirmed_by="import")
            _track(b, day, hour, home, eid)
    _imported_stays(b)


def _imported_stays(b: _Builder) -> None:
    """Besuche über mehrere Tage — die Arbeit für „Mehrtägiges aufteilen".

    Anmerkung 222: Der Lauf greift ausschließlich `google_timeline`-Ereignisse
    mit einer Spanne und ohne Tages-Kinder (`_scan_multiday_visits`). Der
    Demo-Bestand hatte kein einziges davon, also fand der Knopf nichts — und
    ein Knopf, der in der Demo nichts findet, sieht aus wie einer, der nicht
    geht. Sie bleiben ABSICHTLICH ungeteilt: geteilt hätte der Lauf wieder
    nichts zu tun.
    """
    for start, nights, name, city, country, lat, lng in life.IMPORTED_STAYS:
        end = start + timedelta(days=nights)
        if start < TIMELINE_FROM or end > b.last_day or life.in_blank(start):
            continue
        key = f"stay:{name}"
        if key not in b.locations:
            b.locations[key] = b._location(name, city, country, lat, lng)
        b.event(start, f"Besuch in {city}", "event", b.locations[key],
                hour=16, until=end, source=Source.google_timeline,
                confirmed_by="import")


def _visit_place(b: _Builder, home: Location, home_key: str) -> Location:
    """Wohin dieser Besuch führte.

    **Anmerkung 222: fast immer an einen Ort, an dem diese Person schon war.**
    Hier stand ein zufälliger Punkt je Besuch, gerundet auf drei Nachkommastellen
    und benannt nach seiner eigenen Koordinate. Über vier Jahre wurden daraus
    3.633 Orte — 99 % des Ortsbestands —, und der Zeitstrahl, die Karte und jede
    Rangliste zeigten „Ort (53.555, 9.966)" statt eines Namens.

    Das war nicht nur hässlich, sondern falsch: ein Standortverlauf besteht zum
    allergrößten Teil aus WIEDERHOLUNGEN — derselbe Supermarkt, dasselbe Büro,
    derselbe Weg zum Bahnhof. Genau deshalb ist die Ortsrangliste in dieser App
    überhaupt eine interessante Ansicht, und mit lauter Einzelbesuchen war sie
    eine Liste von Zufallszahlen.

    Ein kleiner Rest bleibt unbenannt (`life.STRAY_VISITS` je Wohnort): der Ort,
    den der Geocoder nicht kennt, ist ein echter Fall, und „Ortsnamen auflösen"
    soll etwas zu tun haben. Vier statt siebenhundert je Wohnort.
    """
    errands = life.ERRANDS.get(home_key, ())
    if errands and b.rng.random() < life.ERRAND_SHARE:
        name, city, country, lat, lng = errands[b.rng.randrange(len(errands))]
        key = f"errand:{home_key}:{name}"
        if key not in b.locations:
            b.locations[key] = b._location(name, city, country, lat, lng)
        return b.locations[key]

    # Der unbenannte Rest — aus einem festen kleinen Vorrat je Wohnort, damit
    # er sich wiederholt wie alles andere auch. Ein neuer Punkt je Besuch wäre
    # wieder der alte Bestand, nur mit anderem Mischungsverhältnis.
    n = b.rng.randrange(life.STRAY_VISITS)
    lat = round(home.lat + (n - life.STRAY_VISITS / 2) * 0.011, 3)
    lng = round(home.lng + (n - life.STRAY_VISITS / 2) * 0.017, 3)
    key = f"visit:{home_key}:{n}"
    if key not in b.locations:
        b.locations[key] = b._location(
            f"{geocode.COORD_NAME_PREFIX}{lat:.3f}, {lng:.3f})",
            home.city or "", home.country or "", lat, lng)
    return b.locations[key]


def _track(b: _Builder, day: date, hour: int, home: Location, event_id: str) -> None:
    minutes = 8 + b.rng.randrange(50)
    start = _noon(day, hour, 0) - timedelta(minutes=minutes)
    mode = ("walk", "drive", "cycle", "transit")[b.rng.randrange(4)]
    speed = {"walk": 5.0, "cycle": 17.0, "drive": 38.0, "transit": 25.0}[mode]
    km = round(speed * minutes / 60, 2)
    steps = 6 + b.rng.randrange(14)
    lat, lng = home.lat, home.lng
    points = []
    for i in range(steps):
        points.append([round(lat + i * 0.0015 * (b.rng.random() - 0.3), 6),
                       round(lng + i * 0.0021 * (b.rng.random() - 0.3), 6)])
    b.tracks.append({
        "id": _uuid(), "user_id": b.user.id, "date_start": start,
        "date_end": _noon(day, hour, 0), "points": points, "activity_type": mode,
        "distance_m": km * 1000, "source": Source.google_timeline,
        "external_id": f"demo-{day.isoformat()}-{hour}", "event_id": event_id,
        "origin_fragment_id": None, "created_at": datetime.now(),
    })


def _residence_days(b: _Builder, spans: list[tuple[date, date, Location, str]]) -> None:
    """Wetter für die Tage, an denen NICHTS erfasst wurde (F20).

    Das ist der Teil, für den es `day_metrics` überhaupt gibt: die frühen
    Jahre dieses Lebens haben kaum Einträge, und ohne den Wohnort wären sie in
    jeder Wetter-Bilanz einfach nicht da. **Die beiden Tagesmengen sind
    disjunkt** — deshalb wird hier abgezogen, was schon ein Ereignis hat, statt
    beide Quellen nebeneinander zu schreiben.
    """
    taken = {row["date_start"].date() for row in b.events}
    for start, end, loc, _key in spans:
        day = start
        while day <= end:
            if day not in taken and not _too_recent(day):
                b.day_weather(day, loc)
            day += timedelta(days=1)


def _queue(b: _Builder) -> None:
    """Die beiden oberen Schichten: Roh-Eingang und Vorschläge."""
    for text in life.PENDING_FRAGMENTS:
        b.db.add(Fragment(id=_uuid(), user_id=b.user.id, raw_text=text,
                          source=Source.manual, status=FragmentStatus.pending))
    for days_ago, title, category, key, confidence in life.PROPOSALS:
        b.event(b.today - timedelta(days=days_ago), title, category, b.place(key),
                source=Source.ai, confirmed=False, confidence=confidence)


# --------------------------------------------------------------------------- #
# Der eine Einstiegspunkt
# --------------------------------------------------------------------------- #
def seed_demo(db: Session, user: User) -> None:
    """Legt den Demo-Bestand an, falls das Konto noch leer ist.

    **Die Leere-Prüfung fragt nach EREIGNISSEN, nicht nach Fragmenten.** Der
    alte Seed fragte nach Fragmenten, und dieser Bestand legt nur eine Handvoll
    davon an — nach der alten Frage wäre er ab dem zweiten Start „schon da"
    gewesen, obwohl die Ereignisse fehlen könnten. Gefragt wird nach dem, was
    gebaut wird.
    """
    if db.query(Event).filter(Event.user_id == user.id).first() is not None:
        return
    started = datetime.now()
    b = _Builder(db, user)
    spans = _residences(b)
    _milestones(b)
    _trips(b)
    _concerts(b)
    _habits(b, spans)
    _timeline_import(b, spans)
    _day_photos(b, spans)
    _queue(b)
    _residence_days(b, spans)
    b.flush()
    db.commit()
    log.info("Demo-Bestand angelegt: %d Ereignisse, %d Wege, %d Orte, %d Bilder, "
             "%d Wetterwerte am Ereignis, %d am Wohnort-Tag (%.1f s)",
             len(b.events), len(b.tracks), len(b.locations), len(b.media),
             len(b.metrics), len(b.day_metrics),
             (datetime.now() - started).total_seconds())
