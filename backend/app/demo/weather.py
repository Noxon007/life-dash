"""Wetter für den Demo-Datensatz — erfunden, aber nicht zufällig.

**Warum der Demo-Modus nicht bei Open-Meteo fragt.** Ein Demo-Bestand über
dreißig Jahre braucht Wetter für rund elftausend Tage. Das echte Archiv liefert
das gern, aber ein Aufruf je Ort und Tag heißt: eine halbe Stunde Wartezeit beim
ersten Start, ein Datensatz, der ohne Netz nicht entsteht, und eine Zahl in der
Statistik, die morgen anders aussieht als heute. Ein Schaufenster, das sich bei
jedem Aufbau ändert, ist keines.

**Deterministisch heißt hier: aus (Ort, Tag) gerechnet, nicht gewürfelt.**
Zweimal aufgebaut ergibt zweimal denselben Bestand — sonst wäre jeder
Screenshot ein Einzelstück und jede Messung gegen den Demo-Bestand
unwiederholbar. Der Zufall kommt aus einem Hash über Koordinate und Datum
(`blake2b`) und nicht aus `random`: ein Hash ist über Python-Versionen hinweg
derselbe, ein Zufallsgenerator verspricht das nicht.

**Was es NICHT ist: eine Wettervorhersage für die Vergangenheit.** Die Werte
sind plausibel für Breite und Jahreszeit — Hamburg im Januar ist kalt und
trüb, Lissabon im Juli warm und trocken —, aber sie sind erfunden. Der einzige
echt gerechnete Wert ist die **Tageslänge**: Sonnenauf- und -untergang folgen
der Sonnenstandsformel, weil „längster Tag" eine Rangliste in dieser App ist
und ein erfundener Sonnenlauf sie zu einer Aussage über den Zufallsgenerator
machen würde.

Die Ausgabe hat genau die Form von `services.weather.fetch_weather` — dieselben
Schlüssel, dieselben Einheiten. Sonst wäre dies eine zweite Wetterquelle mit
eigenen Regeln, und die Anreicherung müsste beide kennen.
"""
from __future__ import annotations

import hashlib
import math
import struct
from datetime import date

from app.services.weather import WMO

# Kalendertag, an dem die Nordhalbkugel ihr Temperaturmaximum hat. Nicht der
# 21. Juni: das Meer und der Boden hinken der Sonne rund vier Wochen hinterher,
# und ohne diese Verschiebung wäre der wärmste Tag des Demo-Jahres regelmäßig
# im Juni statt Ende Juli — sichtbar in genau der Rangliste, für die es die
# Werte gibt.
_PEAK_DOY = 202


def _noise(lat: float, lng: float, day: date, salt: str) -> float:
    """Gleichverteilt in [0, 1), reproduzierbar aus Ort, Tag und Zweck.

    `salt` trennt die Fragen: Temperatur und Regen desselben Tages dürfen sich
    nicht denselben Wert teilen, sonst wäre jeder warme Tag auch der nasseste.
    """
    raw = f"{salt}|{lat:.3f}|{lng:.3f}|{day.isoformat()}".encode()
    digest = hashlib.blake2b(raw, digest_size=8).digest()
    return struct.unpack("<Q", digest)[0] / 2**64


def _bell(lat: float, lng: float, day: date, salt: str) -> float:
    """Etwa normalverteilt um 0, Streuung ~1 — die Summe dreier Gleichverteilter.

    Wetter streut nicht gleichverteilt: die meisten Januartage in Hamburg
    liegen nah beieinander, und die zwei Ausreißer sind die, die in einer
    Rangliste landen. Gleichverteiltes Rauschen ergäbe genauso viele
    Extremtage wie durchschnittliche.
    """
    return sum(_noise(lat, lng, day, f"{salt}{i}") for i in range(3)) * 2 - 3


def _solar_declination(doy: int) -> float:
    """Sonnendeklination in Grad, Näherung nach Cooper."""
    return 23.44 * math.sin(math.radians(360 / 365 * (doy - 81)))


def daylight_hours(lat: float, day: date) -> float:
    """Tageslänge in Stunden — echt gerechnet, siehe Modulkopf.

    Polartag und Polarnacht kommen dabei von selbst heraus: `cos(ω)` verlässt
    den gültigen Bereich, und die Klammerung macht daraus 24 bzw. 0 Stunden.
    Ohne sie wäre `acos` ein Absturz — bei einem Demo-Bestand, der Island und
    Nordnorwegen enthält, kein theoretischer Fall.
    """
    decl = math.radians(_solar_declination(day.timetuple().tm_yday))
    phi = math.radians(max(-89.5, min(89.5, lat)))
    cos_omega = -math.tan(phi) * math.tan(decl)
    if cos_omega <= -1:
        return 24.0
    if cos_omega >= 1:
        return 0.0
    return 2 * math.degrees(math.acos(cos_omega)) / 15


def _clock(hour: float) -> str:
    """Dezimalstunde → „HH:MM", wie Open-Meteo es liefert (Ortszeit)."""
    hour = max(0.0, min(23.99, hour))
    return f"{int(hour):02d}:{int(round((hour % 1) * 60)) % 60:02d}"


def _season(lat: float, day: date) -> float:
    """+1 im Hochsommer, −1 im Hochwinter — auf der Südhalbkugel umgekehrt.

    Das Vorzeichen der Breite trägt den Halbkugelwechsel. Ohne ihn hätte ein
    Demo-Bestand mit Reisen nach Peru oder Australien dort Schnee im Juli, und
    zwar lautlos: die Zahl sähe für sich genommen richtig aus.
    """
    doy = day.timetuple().tm_yday
    phase = math.cos(2 * math.pi * (doy - _PEAK_DOY) / 365.25)
    return phase if lat >= 0 else -phase


def synth_weather(lat: float, lng: float, day: date) -> dict:
    """Ein Tageswetter in der Form von `weather.fetch_weather`."""
    season = _season(lat, day)
    abs_lat = abs(lat)

    # Jahresmittel fällt mit der Breite, der Jahresgang wächst mit ihr —
    # das ist der Unterschied zwischen Lissabon und Kiel in zwei Zahlen.
    annual_mean = 27.0 - 0.42 * abs_lat
    amplitude = 2.0 + 0.20 * abs_lat
    mean = annual_mean + amplitude * season + 2.2 * _bell(lat, lng, day, "t")

    # Die Tagesspanne ist im Sommer und über Land größer. `swing` bleibt
    # positiv, sonst läge das Minimum über dem Maximum — eine Zeile, die
    # niemand ansieht, und ein „kältester Tag", der der wärmste ist.
    swing = 5.0 + 2.5 * season + 2.0 * _noise(lat, lng, day, "s")
    swing = max(2.0, swing)
    tmax = round(mean + swing / 2, 1)
    tmin = round(mean - swing / 2, 1)

    light = daylight_hours(lat, day)
    # Niederschlagsneigung: im Winter und in höheren Breiten häufiger.
    wet_bias = 0.28 + 0.10 * -season + 0.0035 * abs_lat
    wet_roll = _noise(lat, lng, day, "r")
    wet = wet_roll < wet_bias

    rain_mm = snow_cm = 0.0
    rain_h = 0.0
    if wet:
        # Menge exponentiell verteilt: viele kleine Regentage, wenige große.
        strength = -math.log(max(1e-6, _noise(lat, lng, day, "q")))
        rain_h = round(min(light, 1.0 + strength * 3.0), 1)
        amount = round(strength * 4.0, 1)
        if tmax < 1.5:
            snow_cm, rain_mm = round(amount * 0.8, 1), 0.0
        else:
            rain_mm = amount

    # Sonnenstunden können die Tageslänge nie überschreiten — die Zusicherung
    # gehört hierher und nicht in die Statistik, die sie sonst als Messfehler
    # ausweisen müsste.
    cloud = min(1.0, (0.25 + 0.55 * _noise(lat, lng, day, "c")) + (0.35 if wet else 0.0))
    sun_h = round(max(0.0, light * (1 - cloud)), 1)

    # **Anmerkung 222: Wind ist ein seltenes Ereignis, keine Gleichverteilung.**
    # Hier stand `6 + 22 * _noise(...)`, also gleichverteilt zwischen 6 und 36
    # km/h — und damit war 36,0 nicht der stärkste Sturm in zweiunddreißig
    # Jahren, sondern der DECKEL. Die Kachel „Windigster Tag" zeigte ihn, und
    # die Rangliste darunter zeigte ihn zehnmal.
    #
    # Das ist genau die Klasse, für die Anmerkung 216 vier Kacheln gestrichen
    # hat („ein Extremwert über eine gedeckelte Größe beschreibt den Deckel,
    # nicht den Tag") — nur saß der Deckel diesmal nicht in der Auswertung,
    # sondern im erfundenen Wetter. Eine Demo, die einen Rekord zeigt, den
    # jeder Norddeutsche als zu klein erkennt, kostet mehr Vertrauen als eine
    # leere Kachel.
    #
    # Exponentiell wie der Regen darüber: viele ruhige Tage, wenige Stürme, und
    # kein oberes Ende. Über elftausend Tage kommt der stärkste damit in die
    # Gegend von 70 km/h mit Böen um 110 — ein plausibler Rekord für die
    # Nordseeküste statt einer frischen Brise.
    gale = -math.log(max(1e-6, _noise(lat, lng, day, "w")))
    wind = round(4.0 + 6.5 * gale + (5.0 if wet else 0.0), 1)
    gust = round(wind * (1.35 + 0.35 * _noise(lat, lng, day, "g")), 1)

    # UV aus Sonnenhöhe und Bewölkung — im Winter in Kiel nahe null, im
    # Sommer in Lissabon zweistellig.
    decl = _solar_declination(day.timetuple().tm_yday)
    elevation = max(0.0, 90 - abs(lat - decl))
    uv = round(max(0.0, 12.0 * math.sin(math.radians(elevation)) ** 2 * (1 - 0.7 * cloud)), 1)

    if snow_cm > 4:
        code = 75
    elif snow_cm > 0:
        code = 71
    elif rain_mm > 12:
        code = 65
    elif rain_mm > 4:
        code = 63
    elif rain_mm > 0:
        code = 61
    elif cloud > 0.75:
        code = 3
    elif cloud > 0.45:
        code = 2
    elif cloud > 0.2:
        code = 1
    else:
        code = 0

    # Gefühlt: Wind kühlt, Sonne wärmt. Bewusst grob — es ist eine erfundene
    # Zahl, die sich nur nicht selbst widersprechen soll.
    apparent_max = round(tmax - wind * 0.06 + (2.0 if sun_h > light * 0.6 else 0.0), 1)
    apparent_min = round(tmin - wind * 0.09, 1)

    return {
        "temp_c": round((tmax + tmin) / 2, 1),
        "temp_min_c": tmin,
        "temp_max_c": tmax,
        "sun_h": sun_h,
        "rain_mm": rain_mm,
        "snow_cm": snow_cm,
        "wind_max_kmh": wind,
        "condition": WMO[code],
        "code": code,
        "apparent_max_c": apparent_max,
        "apparent_min_c": apparent_min,
        "rain_h": rain_h,
        "daylight_h": round(light, 1),
        "gust_max_kmh": gust,
        "uv_max": uv,
        "sunrise": _clock(12 - light / 2),
        "sunset": _clock(12 + light / 2),
    }
