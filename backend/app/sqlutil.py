"""Kleine SQL-Bausteine, die in beiden Dialekten gleich funktionieren.

Der Testlauf ist SQLite, die Anlage des Autors PostgreSQL — ein Unterschied,
den `test_a37_postgres_dialect.py` schon einmal teuer gemacht hat. Was hier
steht, wurde deshalb bewusst aus einem Router herausgezogen: sobald eine
zweite Stelle dieselbe Frage stellt („welcher Kalendertag ist das?"), darf es
nicht zwei Antworten geben.
"""
from __future__ import annotations

from sqlalchemy import func


def day_parts(col):
    """Jahr/Monat/Tag eines Zeitstempels — dialektneutral.

    `date(x)` gibt es so nur in SQLite, `x::date` nur in Postgres; `extract`
    können beide. Gedacht zum Gruppieren: `group_by(*day_parts(Event.date_start))`
    fasst alles zusammen, was am selben Kalendertag liegt.
    """
    return (func.extract("year", col), func.extract("month", col),
            func.extract("day", col))


def weather_cell(lat_col, lng_col):
    """Eine Zahl je Wetter-Gitterzelle (0,1° ≈ 11 km) — dialektneutral.

    Gedacht zum ZÄHLEN: `count(distinct weather_cell(...))` beantwortet „wie
    viele Wetterregionen berührt dieser Tag?". Nicht zum Vergleichen mit einem
    festen Wert — die Zahl selbst hat keine Bedeutung.

    Zwei Fallen stecken hier drin, beide vom Dialekt:
    * `round(x, 1)` gibt es in PostgreSQL **nur für `numeric`**, nicht für
      `double precision` — `Location.lat` ist ein Float, die Abfrage stürbe
      also erst auf der Anlage des Autors (genau der Fall, für den es
      `test_a37_postgres_dialect.py` gibt). Einstelliges `round(x)` können
      beide.
    * An der exakten Hälfte (x,x5) rundet SQLite von der Null weg, PostgreSQL
      zur geraden Zahl. Das verschiebt einen Zellenrand um eine halbe Zelle und
      ist hier folgenlos: gezählt wird, ob zwei Punkte AUSEINANDER liegen, und
      dafür ist die Lage des Rasters gleichgültig.

    Der Multiplikator trennt die beiden Achsen: Längengrade liegen in
    [-1800, 1800] nach der Skalierung, 3601 Werte — mehr als der Abstand
    zweier Breitenstufen, also kann keine Kombination auf eine andere fallen.
    """
    return func.round(lat_col * 10) * 3601 + func.round(lng_col * 10)


# A47: Welche Nominatim-Bausteine als „Ortsteil" gelten, in dieser Reihenfolge.
# Nominatim benennt dieselbe Ebene je nach Land und Ortsgröße anders — in
# Deutschland meist `suburb`, in Großstädten `city_district`, anderswo
# `neighbourhood` oder `quarter`. Eine einzige Abfrage auf `suburb` fände
# deshalb in halb Europa nichts und sähe aus wie „es gibt keinen Ortsteil".
DISTRICT_KEYS = ("suburb", "city_district", "neighbourhood", "quarter",
                 "borough", "town", "village")


def addr_part(col, *keys):
    """Ein Feld aus einer JSON-Spalte — dialektneutral, mit Fallback-Kette.

    Derselbe Grund wie bei `day_parts`: SQLite kann `json_extract`, PostgreSQL
    kennt `->>`, und `test_a37_postgres_dialect.py` hält fest, was es kostet,
    wenn ein Router den einen Dialekt fest verdrahtet — der Testlauf ist
    SQLite, die Anlage des Autors PostgreSQL.

    SQLAlchemys `col[key].as_string()` erzeugt in beiden Dialekten das
    Richtige; `coalesce` über mehrere Schlüssel liefert den ersten, der da ist.
    """
    parts = [col[key].as_string() for key in keys]
    return func.coalesce(*parts) if len(parts) > 1 else parts[0]
