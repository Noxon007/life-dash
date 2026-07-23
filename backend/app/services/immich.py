"""P2.1 — Immich-Konnektor: Fotos zu Ereignissen finden.

**Verweise, keine Kopien** (KONZEPT Kap. 9). Die Bilder bleiben in Immich;
Life-Dash merkt sich nur die Asset-ID und reicht Vorschaubilder durch. Damit
sind Immich-Verknüpfungen eine **Ableitung** (Schicht 4, Anmerkung 57): sie
dürfen jederzeit verworfen und neu berechnet werden — anders als die
hochgeladenen Dateien aus F15, die zur Lebensdatenbank gehören.

Der Konnektor ist bewusst isoliert und defensiv: Immich ist ein fremder
Dienst, der nicht läuft, langsam antworten oder seine API ändern kann. Nichts
davon darf die App mitreißen — im Zweifel gibt es einfach keine Fotos.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

log = logging.getLogger("lifedash.immich")

TIMEOUT = 15
# Immich deckelt die Trefferzahl je Seite; mehr als das braucht ein einzelnes
# Ereignis ohnehin nicht.
PAGE_SIZE = 250


class ImmichError(RuntimeError):
    """Immich nicht erreichbar oder Antwort unbrauchbar — Text geht an den Nutzer.

    `status` trägt den HTTP-Code, wenn Immich **geantwortet** hat, sonst None.
    Dieselbe Unterscheidung wie `err.status` im Frontend (P5.1, Anmerkung 108):
    „der Server hat geantwortet" und „die Anfrage kam nie an" sind zwei
    verschiedene Lagen, und wer sie zusammenwirft, trifft die falsche
    Entscheidung. Hier hängt daran, ob es sich lohnt, dieselbe Frage mit
    anderen Parametern noch einmal zu stellen (`photo_years`).
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def config_for(user) -> tuple[str, str] | None:
    """(Basis-URL, API-Schlüssel) aus den Nutzereinstellungen — oder None.

    Pro Nutzer, nicht global: in einem Mehrpersonen-Setup hat jeder seine
    eigene Immich-Bibliothek (Kap. 9)."""
    prefs = (user.settings or {}).get("immich") or {}
    url, key = (prefs.get("url") or "").strip().rstrip("/"), (prefs.get("api_key") or "").strip()
    return (url, key) if url and key else None


# Ein Reverse-Proxy vor Immich (Nginx, Traefik …) liefert bei Last oder einem
# kurzen Neustart gern ein 502/503/504. Das ist vorübergehend — einmal kurz
# warten und erneut versuchen, statt den ganzen Foto-Lauf abzubrechen.
_TRANSIENT = (502, 503, 504)
_RETRIES = 2
_RETRY_WAIT = 1.5


def _request(url: str, key: str, path: str, *, payload: dict | None = None,
             raw: bool = False):
    """Ein Aufruf gegen Immich. `payload` -> POST (JSON), sonst GET."""

    target = f"{url}/api{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    last: ImmichError | None = None
    for attempt in range(_RETRIES + 1):
        req = urllib.request.Request(target, data=data, method="POST" if data else "GET")
        req.add_header("x-api-key", key)
        req.add_header("Accept", "application/octet-stream" if raw else "application/json")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = resp.read()
                return body if raw else json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ImmichError("Immich lehnt den API-Schlüssel ab (401/403)",
                                  exc.code) from exc
            if exc.code == 404:
                raise ImmichError(f"Immich kennt {path} nicht (404) — "
                                  "passt die URL und die Immich-Version?",
                                  exc.code) from exc
            if exc.code in _TRANSIENT and attempt < _RETRIES:
                last = ImmichError(f"Immich vorübergehend nicht bereit ({exc.code})",
                                   exc.code)
                log.info("Immich %d bei %s — erneuter Versuch %d/%d",
                         exc.code, path, attempt + 1, _RETRIES)
                time.sleep(_RETRY_WAIT)
                continue
            # Der Text der Antwort steht drin: Immich sagt bei 400 genau,
            # welcher Parameter ihm nicht passt („property size should not
            # exist"). Ohne das steht im Log „antwortet mit 400" — wahr und
            # nutzlos.
            detail = ""
            try:
                detail = (exc.read() or b"").decode("utf-8", "replace")[:300].strip()
            except Exception:  # pragma: no cover - Antwort schon gelesen
                pass
            raise ImmichError(
                f"Immich antwortet mit {exc.code}" + (f": {detail}" if detail else ""),
                exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < _RETRIES:
                last = ImmichError(f"Immich nicht erreichbar: {exc}")
                time.sleep(_RETRY_WAIT)
                continue
            raise ImmichError(f"Immich nicht erreichbar: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ImmichError("Immich liefert keine gültige JSON-Antwort — "
                              "zeigt die URL wirklich auf Immich?") from exc
    raise last or ImmichError("Immich nicht erreichbar")


def check(url: str, key: str) -> dict:
    """Verbindungstest für die Einstellungen.

    Gibt es diesen Knopf nicht, merkt der Nutzer einen Tippfehler erst daran,
    dass ein Foto-Lauf nichts findet — und sucht die Ursache an der falschen
    Stelle.

    Bewusst `/server/about` und NICHT `/server/ping`: ping antwortet ohne
    jede Authentifizierung und würde einen falschen API-Schlüssel als Erfolg
    melden — also genau den Fehler verschweigen, den der Test finden soll.
    """
    info = _request(url.rstrip("/"), key, "/server/about")
    return {"ok": True, "version": (info or {}).get("version") or "unbekannt"}


def _stamp(when: datetime) -> str:
    """Zeitstempel im Format, das Immich akzeptiert.

    Wichtig: Immich validiert `takenAfter`/`takenBefore` gegen ein Muster, das
    eine **Zeitzone verlangt** (`Z` oder `±hh:mm`). Ein nacktes
    `2024-05-01T00:00:00` wird mit 400 abgelehnt. Life-Dash speichert Zeiten
    als lokale Wanduhrzeit (A13), also wird genau die lokale Zone angehängt —
    `Z` würde das Fenster um den UTC-Versatz verschieben und an Tagesgrenzen
    die falschen Fotos einsammeln.
    """
    if when.tzinfo:
        return when.isoformat()
    try:
        return when.astimezone().isoformat()
    except (OSError, OverflowError, ValueError):
        # `astimezone()` fragt das Betriebssystem nach der Zone zu DIESEM
        # Zeitpunkt — und Windows antwortet für alles vor 1970 mit OSError.
        # Aufgefallen erst im Smoke-Lauf: die Album-Abfrage von Stufe 2 fragt
        # bewusst ohne Zeitfenster (ab 1900), und damit sah diese Funktion nach
        # fünf Releases zum ersten Mal ein Datum vor der Epoche. Ersatz ist der
        # heutige lokale Versatz — für eine Fenstergrenze, die ein ganzes
        # Jahrhundert weit offen steht, ist eine Stunde Sommerzeit belanglos.
        return when.replace(tzinfo=datetime.now().astimezone().tzinfo).isoformat()


def search_assets(url: str, key: str, start: datetime, end: datetime) -> list[dict]:
    """Assets in einem Zeitfenster (Aufnahmezeit), neueste zuerst."""
    body = {
        "takenAfter": _stamp(start),
        "takenBefore": _stamp(end),
        "size": PAGE_SIZE,
        "page": 1,
        "withExif": True,
    }
    data = _request(url, key, "/search/metadata", payload=body)
    items = (((data or {}).get("assets") or {}).get("items")) or []
    # Nur Bilder und Videos mit Aufnahmezeit — alles andere lässt sich einem
    # Ereignis nicht sinnvoll zuordnen.
    return [a for a in items if a.get("id")]


def thumbnail(url: str, key: str, asset_id: str) -> bytes:
    """Vorschaubild eines Assets — durchgereicht, nie zwischengespeichert."""
    return _request(url, key, f"/assets/{asset_id}/thumbnail?size=preview", raw=True)


# --------------------------------------------------------------------------- #
# P2.1 Stufe 2 — was die API wirklich hergibt
#
# Anmerkung 107 ließ eine Frage offen und schrieb dazu, sie sei GEGEN DIE
# SPEZIFIKATION zu klären, nicht gegen eine Attrappe: Wie unterscheidet man
# eigene von geteilten Assets und Alben? Antwort aus
# `open-api/immich-openapi-specs.json` (OpenAPI 3.0.3) — und sie ist für die
# beiden Zweige **verschieden**, was eine Attrappe nie verraten hätte:
#
#   * **Alben:** `GET /albums?isOwned=true|false` gibt es, dokumentiert als
#     „true = only owned, false = only shared-with-me". Der Server filtert.
#   * **Assets:** `MetadataSearchDto` hat **kein** Besitz-Feld — kein
#     `isOwned`, kein `ownerId`, kein `withPartners`. Gefiltert werden muss
#     also auf der ANTWORT: `AssetResponseDto.ownerId` ist Pflichtfeld, die
#     eigene Kennung liefert `GET /users/me`.
#
# Zwei weitere Funde, die das Paket überhaupt erst tragfähig machen:
#   * `exifInfo` enthält **city/state/country** — Immich hat schon
#     rückwärts-geokodiert. Der Ort eines Fotoclusters kostet damit KEINEN
#     Nominatim-Aufruf, und die Gruppierung nach Ortsnamen ist stabiler als
#     jedes Koordinatenraster (kein Zellenrand mitten durch eine Stadt).
#   * `visibility` (archive|timeline|hidden|locked) sagt, was der Nutzer
#     bewusst aus seinem Zeitstrahl genommen hat. Ein Vorschlag aus dem
#     gesperrten Ordner wäre ein Vertrauensbruch.
# --------------------------------------------------------------------------- #
def own_user_id(url: str, key: str) -> str | None:
    """Die eigene Immich-Nutzerkennung (`GET /users/me`).

    Ohne sie lässt sich ein fremdes Foto nicht erkennen — dann wird lieber
    NICHTS geclustert (siehe `is_own`), statt fremde Urlaubsfotos als eigenen
    Tag vorzuschlagen.
    """
    data = _request(url, key, "/users/me")
    return (data or {}).get("id")


def is_own(asset: dict, my_id: str | None) -> bool:
    """Gehört das Asset mir? Ohne bekannte eigene Kennung: nein.

    Bewusst streng. `ownerId` ist laut Spezifikation Pflichtfeld; fehlt es
    trotzdem, ist die Lage unklar — und im Unklaren ein fremdes Foto zum
    eigenen Tagesvorschlag zu machen, ist der teurere Fehler.
    """
    return bool(my_id) and asset.get("ownerId") == my_id


def is_in_timeline(asset: dict) -> bool:
    """Nur was im Immich-Zeitstrahl steht, darf ein Ereignis vorschlagen.

    `visibility` ist erst in neueren Immich-Versionen dabei; fehlt das Feld,
    gilt das Asset als sichtbar (ältere Server kannten nur `isArchived`, das
    hier ersatzweise gilt). Was fehlt, wird nicht als Verbot gelesen —
    sonst schlüge der Lauf auf einem älteren Immich gar nichts mehr vor.
    """
    vis = asset.get("visibility")
    if vis is not None:
        return vis == "timeline"
    return not asset.get("isArchived", False)


def asset_place(asset: dict) -> str | None:
    """Ortsname aus Immichs eigener Rückwärts-Geokodierung.

    Die Leiter city → state → country ist Absicht: in der Wildnis kennt
    Immich keine Stadt, aber fast immer eine Region. „34 Fotos in
    (51.9, 8.8)" wäre keine Erinnerung, „34 Fotos in Lappland" ist eine.
    """
    exif = asset.get("exifInfo") or {}
    for field in ("city", "state", "country"):
        value = (exif.get(field) or "").strip()
        if value:
            return value
    return None


class ScanAborted(RuntimeError):
    """Der Aufrufer (ein Job) will nicht weiter — sauber abbrechen.

    Bewusst eine Ausnahme statt „gib zurück, was du hast": eine halb geladene
    Albumspanne sähe aus wie eine vollständige und stünde als Datum in einem
    Vorschlag. Ein abgebrochener Lauf darf nichts anlegen.
    """


def search_assets_paged(url: str, key: str, start: datetime, end: datetime, *,
                        album_id: str | None = None,
                        heartbeat=None,
                        max_items: int = 20000) -> list[dict]:
    """Alle Assets eines Zeitraums — über alle Seiten.

    `search_assets` holt bewusst nur die erste Seite: für EIN Ereignis reichen
    250 Treffer weit. Ein Jahreslauf ist das Gegenteil, da sind 250 die
    ersten Tage im Januar — und der Rest des Jahres wäre still verschwunden.

    Geblättert wird über `nextPage` (laut Spezifikation ein **String**-Token,
    kein Zähler); `max_items` ist die Reißleine gegen eine Bibliothek, die
    größer ist als der Arbeitsspeicher.

    `heartbeat` wird nach JEDER Seite gerufen und darf `False` liefern, um
    abzubrechen. Das ist kein Beiwerk: ein Job gilt nach drei Minuten ohne
    Lebenszeichen als verwaist (`STALE_SECONDS`), und genau die Bibliothek,
    für die dieses Paket gebaut ist, blättert länger als drei Minuten. Ohne
    den Schlag hier hätte der Lauf die ganze Arbeit gemacht und anschließend
    „gestoppt" gemeldet.
    """
    out: list[dict] = []
    page = 1
    while page and len(out) < max_items:
        if heartbeat is not None and heartbeat() is False:
            raise ScanAborted("Lauf gestoppt")
        body = {
            "takenAfter": _stamp(start),
            "takenBefore": _stamp(end),
            "size": PAGE_SIZE,
            "page": page,
            "withExif": True,
        }
        if album_id:
            body["albumIds"] = [album_id]
        data = _request(url, key, "/search/metadata", payload=body)
        block = ((data or {}).get("assets") or {})
        out.extend(a for a in (block.get("items") or []) if a.get("id"))
        nxt = block.get("nextPage")
        try:
            page = int(nxt) if nxt else 0
        except (TypeError, ValueError):
            # Sollte Immich je ein undurchsichtiges Token liefern, lieber
            # aufhören als endlos dieselbe Seite zu holen.
            log.info("Immich: nextPage '%s' ist keine Seitenzahl — Ende", nxt)
            page = 0
    if len(out) >= max_items and page:
        # Stille ist in diesem Projekt der teuerste Defekt: ein Jahr, das an
        # der Reißleine abgeschnitten wird, sähe sonst aus wie ein Jahr, das
        # eben nicht mehr hergibt.
        log.warning("Immich: Grenze von %d Assets erreicht — dieses Fenster "
                    "wird nur teilweise ausgewertet (%s)", max_items,
                    f"Album {album_id}" if album_id else f"{start:%Y-%m-%d} bis {end:%Y-%m-%d}")
    return out


def asset_country(asset: dict) -> str | None:
    """Land aus `exifInfo` — unterscheidet gleichnamige Orte."""
    return ((asset.get("exifInfo") or {}).get("country") or "").strip() or None


def photo_years(url: str, key: str, my_id: str | None) -> dict[int, int]:
    """Jahr -> Anzahl eigener, georeferenzierter Fotos im Immich-Zeitstrahl.

    `GET /timeline/buckets` liefert Monatszähler statt Assets — die Frage
    „welche Jahre lohnen einen Lauf?" kostet damit EINEN Aufruf statt eines
    Bibliotheks-Vollscans.

    Warum das nicht aus den eigenen Daten kommt, obwohl es billiger wäre:
    Anmerkung 107 nennt ausgerechnet die Jahre **ohne** Timeline-Daten als die
    wertvollsten („die Erinnerungen von vor dem Smartphone"). Eine Auswahlliste
    aus den eigenen Ereignissen böte genau die nicht an — sie zeigte 2026 und
    verstecke 2004.

    **Die Parameter dieses Endpunkts sind eine wandernde Grenze** (Anmerkung
    113). `size=MONTH` war bis Immich 1.133 **Pflicht** und ist seit 1.134
    **verboten** — die Bucket-Größe wurde ersatzlos gestrichen, ohne Eintrag im
    Änderungsprotokoll. Immich validiert streng: ein Parameter, den die
    laufende Version nicht kennt, ist ein **400**, keine Warnung. Genauso
    kamen `visibility` und `withCoordinates` erst später dazu; davor hieß es
    `isArchived`.

    Deshalb eine Leiter statt einer Annahme: gefragt wird von der neuesten
    Form abwärts, und ein 400 heißt „diese Version kennt das nicht — nächste
    Sprosse". Bei 401 oder „nicht erreichbar" wird NICHT weitergeraten; das
    Problem läge woanders und drei Fehlversuche machten es nur langsamer.
    """
    ladder = [
        # Ab Immich 1.134: keine Bucket-Größe mehr, immer Monatsschritte.
        ["visibility=timeline", "withCoordinates=true", "withPartners=false"],
        # 1.133 abwärts: `size` war Pflicht.
        ["size=MONTH", "visibility=timeline", "withCoordinates=true",
         "withPartners=false"],
        # Noch älter: kein `visibility`, kein `withCoordinates`. Die Zahl zählt
        # dann auch Fotos ohne Koordinaten, ist also zu hoch — sie ist eine
        # Empfehlung („lohnt sich 2004?"), kein Versprechen.
        ["size=MONTH", "isArchived=false", "withPartners=false"],
    ]
    last: ImmichError | None = None
    for params in ladder:
        query = list(params)
        if my_id:
            query.append(f"userId={urllib.parse.quote(my_id)}")
        try:
            data = _request(url, key, "/timeline/buckets?" + "&".join(query))
        except ImmichError as exc:
            if exc.status != 400:
                raise
            log.info("Immich mag %s nicht (%s) — nächster Versuch",
                     "&".join(params), exc)
            last = exc
            continue
        years: dict[int, int] = {}
        for bucket in data or []:
            stamp = str(bucket.get("timeBucket") or "")[:4]
            if not stamp.isdigit():
                continue
            years[int(stamp)] = years.get(int(stamp), 0) + int(bucket.get("count") or 0)
        return years
    raise last or ImmichError("Immich liefert keine Zeitachse")


def albums(url: str, key: str, *, owned: bool | None = None) -> list[dict]:
    """Alben. `owned=True` nur eigene, `owned=False` nur mit mir geteilte.

    Hier filtert der Server (`isOwned`), anders als bei den Assets — das ist
    keine Inkonsequenz von Life-Dash, sondern der Stand der Immich-API.
    """
    path = "/albums"
    if owned is not None:
        path += f"?isOwned={'true' if owned else 'false'}"
    data = _request(url, key, path)
    return [a for a in (data or []) if a.get("id")]


# --------------------------------------------------------------------------- #
# Zuordnung Asset -> Ereignis
# --------------------------------------------------------------------------- #
def asset_time(asset: dict) -> datetime | None:
    """Aufnahmezeit als **Ortszeit des Fotografen** — naiv, wie A13 sie speichert.

    Die Reihenfolge ist keine Geschmacksfrage, sondern steht so in der
    Spezifikation:

    * `localDateTime` — „the local date and time when the photo was taken …
      **timezone-agnostic** … used for timeline grouping by *local* days". Also
      genau das, was Life-Dash braucht, und von Immich schon fertig gerechnet.
    * `exifInfo.dateTimeOriginal` — trägt in der Regel den ursprünglichen
      Versatz; ohne Zone gelesen ergibt das ebenfalls Ortszeit.
    * `fileCreatedAt` — laut Spezifikation **UTC**. Nur als letzter Ausweg, und
      dann umgerechnet: die Zone einfach abzuschneiden ergäbe UTC-Wanduhrzeit.

    Genau das tat diese Funktion bis 0.38: sie schnitt bei jedem Format die
    Zone ab. Ein Foto vom 13. Mai, 01:30 Uhr in Berlin kommt als
    `2024-05-12T23:30:00Z` an und landete damit auf dem **12.** — in Mitteleuropa
    betrifft das jedes Foto der späten Abendstunden, und es verschiebt nicht nur
    die Uhrzeit, sondern den TAG. Am Tag hängen aber der Behälter (F18/Anm. 106)
    und der Platz eines Vorschlags (`immich:day:<datum>:<ort>`).
    """
    local = asset.get("localDateTime")
    if local:
        parsed = _parse_stamp(local)
        if parsed is not None:
            # Bewusst ohne Umrechnung: das Feld IST schon Ortszeit, ein
            # angehängtes „Z" ist bei einer zonenlosen Angabe Dekoration.
            return parsed.replace(tzinfo=None)

    exif_raw = (asset.get("exifInfo") or {}).get("dateTimeOriginal")
    if exif_raw:
        parsed = _parse_stamp(exif_raw)
        if parsed is not None:
            return parsed.replace(tzinfo=None)

    raw = asset.get("fileCreatedAt")
    if not raw:
        return None
    parsed = _parse_stamp(raw)
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        # Echte UTC-Angabe -> in die Zone dieses Servers holen, sonst wandern
        # die Abendfotos einen Tag zurück.
        try:
            return parsed.astimezone().replace(tzinfo=None)
        except (OSError, OverflowError, ValueError):
            return parsed.replace(tzinfo=None)
    return parsed


def _parse_stamp(raw) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def asset_geo(asset: dict) -> tuple[float, float] | None:
    exif = asset.get("exifInfo") or {}
    lat, lng = exif.get("latitude"), exif.get("longitude")
    if lat is None or lng is None:
        return None
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Grobe Entfernung in km. Bewusst ohne Haversine: für „war das Foto in
    der Nähe?" reicht die flache Näherung, und sie kostet keine Bibliothek."""
    from math import cos, radians, sqrt

    dlat = (a[0] - b[0]) * 111.0
    dlng = (a[1] - b[1]) * 111.0 * cos(radians((a[0] + b[0]) / 2))
    return sqrt(dlat * dlat + dlng * dlng)


def window_for(event, *, pad_hours: int = 6) -> tuple[datetime, datetime] | None:
    """Zeitfenster, in dem Fotos zu diesem Ereignis passen könnten.

    Die Genauigkeit des Ereignisses entscheidet: bei `exact` sind es Stunden
    um den Zeitpunkt, bei einem Tag der ganze Tag, bei einer Reise die ganze
    Spanne. Vage Angaben (Monat, Jahreszeit, Jahr, Jahrzehnt) bekommen KEIN
    Fenster — „Sommer 2002" würde sonst wahllos Fotos einsammeln, und ein
    falsches Foto am Eintrag ist schlimmer als gar keins.
    """
    from app.models import DatePrecision

    if event.date_start is None:
        return None
    if event.date_precision not in (DatePrecision.exact, DatePrecision.day):
        return None
    start = event.date_start
    end = event.date_end or event.date_start
    if event.date_precision == DatePrecision.exact:
        return start - timedelta(hours=pad_hours), end + timedelta(hours=pad_hours)
    # Tagesgenau: vom Beginn des ersten bis zum Ende des letzten Tages
    return (start.replace(hour=0, minute=0, second=0, microsecond=0),
            end.replace(hour=23, minute=59, second=59, microsecond=999999))


def matches(event, asset: dict, *, max_km: float = 25.0) -> bool:
    """Passt dieses Asset zu diesem Ereignis?

    Die Zeit hat der Suchaufruf schon geprüft. Bleibt der Ort: hat sowohl das
    Ereignis als auch das Foto Koordinaten, müssen sie zusammenpassen — sonst
    landen die Urlaubsfotos anderer Leute am selben Tag im eigenen Eintrag.
    Fehlt einem von beiden die Position, entscheidet allein die Zeit; das ist
    absichtlich großzügig, denn ungetaggte Fotos sind häufig.
    """
    loc = getattr(event, "location", None)
    if not loc or loc.lat is None or loc.lng is None:
        return True
    geo = asset_geo(asset)
    if geo is None:
        return True
    return _km(geo, (loc.lat, loc.lng)) <= max_km
