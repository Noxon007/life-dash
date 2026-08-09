"""Das erfundene Leben — die Stammdaten des Demo-Bestands (R1a).

**Warum es diese Datei gibt.** Der Demo-Modus soll ein Leben zeigen, kein
Datenrauschen: Wohnorte, die aufeinander folgen, Reisen, die zu einem Alter
passen, Konzerte in Städten, in denen die Person damals wohnte. Das ist eine
BIOGRAFIE und keine Zufallsverteilung, also steht sie als Text hier und wird
nicht gewürfelt. Gewürfelt wird nur, was in einem echten Bestand auch beliebig
ist — an welchem Dienstag jemand laufen war.

**Alles hier ist frei erfunden.** Die Orte sind echt (sonst fiele die Karte
auseinander und die Länder-Stammdaten fänden nichts), die Person ist es nicht.

**Die Zahlen kommen aus der Form des Lebens, nicht aus einer Zielvorgabe.**
Wer „ungefähr fünftausend Ereignisse" als Vorgabe nimmt, bekommt fünftausend
gleich verteilte — und damit einen Zeitstrahl, in dem 1999 aussieht wie 2024.
Ein echter Bestand ist vorne dünn und hinten dicht: die ersten Jahre kennt man
aus Erzählungen, die letzten aus Fotos und Importen.
"""
from __future__ import annotations

from datetime import date, timedelta

# --------------------------------------------------------------------------- #
# Die Person
# --------------------------------------------------------------------------- #
BIRTH = date(1994, 3, 12)
DISPLAY_NAME = "Mira Halden"

# Ein Ort: (Name, Stadt, Land, Breite, Länge). Der Name ist der, der im
# Zeitstrahl steht; Stadt und Land sind die Felder, über die gruppiert wird
# (A39 — die Stadt aus dem Namen zu schneiden war genau das, was A39 abgeschafft
# hat).
Place = tuple[str, str, str, float, float]

PLACES: dict[str, Place] = {
    # --- Wohnorte ---
    "elternhaus":   ("Kirschenallee 12, Bad Segeberg", "Bad Segeberg", "Deutschland", 53.9366, 10.3103),
    "wg-kiel":      ("Knooper Weg 84, Kiel", "Kiel", "Deutschland", 54.3298, 10.1279),
    "hh-altona":    ("Bahrenfelder Straße 5, Hamburg", "Hamburg", "Deutschland", 53.5503, 9.9330),
    "lissabon":     ("Rua da Prata 41, Lisboa", "Lisboa", "Portugal", 38.7107, -9.1373),
    "hh-eimsbuettel": ("Osterstraße 118, Hamburg", "Hamburg", "Deutschland", 53.5772, 9.9540),
    # --- Rund um die Wohnorte: wo der Alltag stattfindet ---
    "segeberger-see": ("Großer Segeberger See", "Bad Segeberg", "Deutschland", 53.9280, 10.3260),
    "kalkberg":     ("Kalkberg", "Bad Segeberg", "Deutschland", 53.9345, 10.3020),
    "kiel-foerde":  ("Kiellinie", "Kiel", "Deutschland", 54.3389, 10.1500),
    "kiel-uni":     ("Christian-Albrechts-Universität", "Kiel", "Deutschland", 54.3395, 10.1215),
    "elbstrand":    ("Elbstrand Övelgönne", "Hamburg", "Deutschland", 53.5432, 9.8917),
    "stadtpark-hh": ("Hamburger Stadtpark", "Hamburg", "Deutschland", 53.5983, 10.0130),
    "alster":       ("Außenalster", "Hamburg", "Deutschland", 53.5686, 10.0004),
    "hh-hafen":     ("Landungsbrücken", "Hamburg", "Deutschland", 53.5459, 9.9686),
    "isartor-lx":   ("Miradouro da Senhora do Monte", "Lisboa", "Portugal", 38.7175, -9.1320),
    "belem":        ("Torre de Belém", "Lisboa", "Portugal", 38.6916, -9.2160),
    "cascais":      ("Praia da Rainha, Cascais", "Cascais", "Portugal", 38.6968, -9.4207),
    "sintra":       ("Palácio da Pena, Sintra", "Sintra", "Portugal", 38.7876, -9.3904),
}

# --------------------------------------------------------------------------- #
# Die weiße Stelle — der Grund, warum der Lückenbericht etwas zu sagen hat
# --------------------------------------------------------------------------- #
# **Ein Bestand ohne eine einzige Lücke lässt den Lückenbericht leer**, und eine
# Ansicht, die in der Demo nichts zu sagen hat, sieht aus wie eine kaputte. Die
# Geschichte dazu ist die häufigste, die es gibt: der Umzug ins Ausland verschob
# sich, die Wohnung war schon gekündigt, und aus diesen Wochen hat nie jemand
# etwas eingetragen — weder wo er wohnte noch was er tat.
#
# **Eine Definition, drei Leser.** Die Wohnorte lassen hier ihre Lücke, der
# Alltagsgenerator schweigt in ihr, und der Timeline-Import auch. Stünden die
# Daten dreimal getippt da, wäre die Lücke beim nächsten Verschieben an zwei
# Stellen zu und an einer offen — und das Ergebnis wäre kein Fehler, sondern
# eine stille Halbheit.
_DAY = timedelta(days=1)
BLANK: tuple[date, date] = (date(2020, 3, 1), date(2020, 5, 14))


def in_blank(day: date) -> bool:
    """Liegt der Tag in der weißen Stelle?"""
    return BLANK[0] <= day <= BLANK[1]


# --------------------------------------------------------------------------- #
# Wohnorte — die vierte Sorte Aussage (F20)
# --------------------------------------------------------------------------- #
# (Bezeichnung, Ortsschlüssel, von, bis). `None` heißt „bis heute" und ist
# bewusst kein eingetragenes Datum: das wäre eine Behauptung, die morgen falsch
# ist. Die Abschnitte stoßen lückenlos aneinander — eine Lücke hieße, dass
# jemand nirgends gewohnt hat, und der Lückenbericht würde sie auch genau so
# melden.
RESIDENCES: list[tuple[str, str, date, date | None]] = [
    ("Elternhaus",           "elternhaus",      BIRTH,             date(2013, 8, 31)),
    ("Studium in Kiel",      "wg-kiel",         date(2013, 9, 1),  date(2017, 7, 31)),
    ("Erste eigene Wohnung", "hh-altona",       date(2017, 8, 1),  BLANK[0] - _DAY),
    ("Die Jahre in Lissabon", "lissabon",       BLANK[1] + _DAY,   date(2022, 9, 30)),
    ("Eimsbüttel",           "hh-eimsbuettel",  date(2022, 10, 1), None),
]

# --------------------------------------------------------------------------- #
# Meilensteine — die Ankerpunkte, an denen der Rest hängt
# --------------------------------------------------------------------------- #
MILESTONES: list[tuple[date, str, str]] = [
    (BIRTH,              "Geboren",                            "elternhaus"),
    (date(2000, 8, 14),  "Erster Schultag",                    "elternhaus"),
    (date(2004, 6, 19),  "Schwimmen gelernt",                  "segeberger-see"),
    (date(2010, 7, 2),   "Erstes eigenes Fahrrad",             "elternhaus"),
    (date(2013, 6, 21),  "Abitur",                             "elternhaus"),
    (date(2013, 9, 1),   "Umzug nach Kiel",                    "wg-kiel"),
    (date(2016, 10, 4),  "Bachelorarbeit abgegeben",           "kiel-uni"),
    (date(2017, 7, 14),  "Master abgeschlossen",               "kiel-uni"),
    (date(2017, 8, 1),   "Umzug nach Hamburg",                 "hh-altona"),
    (date(2017, 9, 4),   "Erster Arbeitstag",                  "hh-hafen"),
    # Der Tag, an dem die weiße Stelle endet — nicht der, an dem die Hamburger
    # Wohnung auslief. Genau diese zweieinhalb Monate dazwischen sind die
    # Lücke, und ein Meilenstein mitten in ihr würde sie bestreiten.
    (BLANK[1] + _DAY,    "Angekommen in Lissabon",             "lissabon"),
    (date(2021, 5, 30),  "Portugiesisch-Prüfung bestanden",    "lissabon"),
    (date(2022, 10, 1),  "Zurück nach Hamburg",                "hh-eimsbuettel"),
    (date(2024, 4, 18),  "Erste eigene Ausstellung",           "hh-hafen"),
    (date(2025, 9, 6),   "Zehn Jahre Laufen",                  "stadtpark-hh"),
]

# --------------------------------------------------------------------------- #
# Reisen
# --------------------------------------------------------------------------- #
# (Anreise, Tage, Titel, Ort, Stadt, Land, lat, lng, Programm).
# Das Programm ist die Liste der Tagesüberschriften; ist sie kürzer als die
# Reise, füllt der Generator mit allgemeinen Tagen auf. **Ein Eintrag je
# Reisetag und kein Mehrtäger:** ein ungeteilter Mehrtäger belegt nur seinen
# Anfangstag, und der Wohnort füllte die übrigen — die Reise stünde dann in der
# Statistik zu Hause.
Trip = tuple[date, int, str, str, str, str, float, float, tuple[str, ...]]

TRIPS: list[Trip] = [
    (date(1999, 7, 24), 12, "Sommer an der Ostsee", "Timmendorfer Strand", "Timmendorfer Strand", "Deutschland", 53.9958, 10.7758,
     ("Ankunft im Ferienhaus", "Erster Tag am Strand", "Sandburgenwettbewerb", "Ausflug nach Lübeck")),
    (date(2001, 8, 3), 14, "Ferien in Dänemark", "Blåvand", "Blåvand", "Dänemark", 55.5578, 8.0836,
     ("Fähre und Ankunft", "Leuchtturm Blåvandshuk", "Bernstein gesucht", "Regentag im Ferienhaus")),
    (date(2003, 7, 19), 10, "Frankreich mit den Eltern", "Carnac", "Carnac", "Frankreich", 47.5847, -3.0797,
     ("Lange Autofahrt", "Menhire von Carnac", "Austern in Quiberon", "Gewitter am Atlantik")),
    (date(2005, 8, 6), 9, "Gardasee", "Riva del Garda", "Riva del Garda", "Italien", 45.8858, 10.8407,
     ("Über den Brenner", "Erstes Mal Segeln", "Wanderung zur Bastione", "Eis in Torbole")),
    (date(2007, 10, 12), 5, "Herbstferien in Prag", "Prag", "Praha", "Tschechien", 50.0755, 14.4378,
     ("Ankunft mit dem Nachtzug", "Karlsbrücke im Nebel", "Astronomische Uhr")),
    (date(2009, 7, 28), 13, "Andalusien", "Sevilla", "Sevilla", "Spanien", 37.3891, -5.9845,
     ("Ankunft in der Hitze", "Alcázar", "Tagesausflug nach Córdoba", "Flamenco in Triana", "Der heißeste Tag")),
    (date(2011, 4, 15), 4, "Klassenfahrt nach Berlin", "Berlin", "Berlin", "Deutschland", 52.5200, 13.4050,
     ("Ankunft am Hauptbahnhof", "Reichstagskuppel", "Museumsinsel")),
    (date(2012, 8, 1), 21, "Interrail durch Europa", "Wien", "Wien", "Österreich", 48.2082, 16.3738,
     ("Abfahrt in Hamburg", "Nachtzug nach Wien", "Prater", "Weiter nach Budapest", "Donau bei Nacht")),
    (date(2013, 3, 9), 6, "Amsterdam mit Freunden", "Amsterdam", "Amsterdam", "Niederlande", 52.3676, 4.9041,
     ("Ankunft im Hostel", "Grachtenrundfahrt", "Van-Gogh-Museum", "Fahrradtour")),
    (date(2014, 6, 21), 8, "Norwegen — Fjorde", "Bergen", "Bergen", "Norwegen", 60.3913, 5.3221,
     ("Fähre nach Bergen", "Bryggen", "Fahrt auf den Fløyen", "Regen, den ganzen Tag")),
    (date(2015, 2, 12), 5, "Winter in Tromsø", "Tromsø", "Tromsø", "Norwegen", 69.6492, 18.9553,
     ("Ankunft in der Polarnacht", "Nordlicht über dem Fjord", "Hundeschlitten")),
    (date(2015, 9, 5), 10, "Island im Herbst", "Reykjavík", "Reykjavík", "Island", 64.1466, -21.9426,
     ("Ankunft in Keflavík", "Golden Circle", "Jökulsárlón", "Sturm an der Südküste", "Blaue Lagune")),
    (date(2016, 5, 20), 7, "Schottland", "Edinburgh", "Edinburgh", "Vereinigtes Königreich", 55.9533, -3.1883,
     ("Ankunft in Edinburgh", "Arthur's Seat", "Zug in die Highlands", "Loch Ness")),
    (date(2016, 12, 27), 6, "Jahreswechsel in Wien", "Wien", "Wien", "Österreich", 48.2082, 16.3738,
     ("Anreise", "Schönbrunn im Schnee", "Silvester am Stephansplatz")),
    (date(2017, 4, 8), 9, "Marokko", "Marrakesch", "Marrakesh", "Marokko", 31.6295, -7.9811,
     ("Ankunft in Marrakesch", "Souks", "Atlasgebirge", "Nacht in der Wüste", "Rückweg über Essaouira")),
    (date(2018, 3, 24), 11, "Japan im Frühling", "Kyoto", "Kyoto", "Japan", 35.0116, 135.7681,
     ("Ankunft in Tokio", "Shinkansen nach Kyoto", "Fushimi Inari", "Kirschblüte am Kamo", "Nara und die Rehe", "Zurück nach Tokio")),
    (date(2018, 9, 15), 5, "Kopenhagen", "Kopenhagen", "København", "Dänemark", 55.6761, 12.5683,
     ("Zug über den Belt", "Nyhavn", "Louisiana-Museum")),
    (date(2019, 6, 1), 16, "Peru", "Cusco", "Cusco", "Peru", -13.5319, -71.9675,
     ("Ankunft in Lima", "Weiter nach Cusco", "Höhenanpassung", "Salkantay-Trek beginnt", "Machu Picchu",
      "Zurück nach Cusco", "Titicacasee")),
    (date(2019, 11, 8), 4, "Wochenende in Paris", "Paris", "Paris", "Frankreich", 48.8566, 2.3522,
     ("Thalys nach Paris", "Marais", "Musée d'Orsay")),
    (date(2021, 6, 18), 8, "Azoren", "Ponta Delgada", "Ponta Delgada", "Portugal", 37.7412, -25.6756,
     ("Flug ab Lissabon", "Sete Cidades", "Walbeobachtung", "Heiße Quellen in Furnas")),
    (date(2021, 9, 3), 6, "Andalusien, zum zweiten Mal", "Granada", "Granada", "Spanien", 37.1773, -3.5986,
     ("Bus über die Grenze", "Alhambra", "Sierra Nevada", "Tapas im Albaicín")),
    (date(2022, 5, 12), 12, "Kanada — Westen", "Vancouver", "Vancouver", "Kanada", 49.2827, -123.1207,
     ("Ankunft in Vancouver", "Stanley Park", "Fähre nach Vancouver Island", "Wale vor Tofino",
      "Banff", "Lake Louise")),
    (date(2023, 2, 3), 5, "Winterwochenende in Prag", "Prag", "Praha", "Tschechien", 50.0755, 14.4378,
     ("Anreise im Schneetreiben", "Vyšehrad", "Kafka-Museum")),
    (date(2023, 7, 22), 14, "Thailand", "Chiang Mai", "Chiang Mai", "Thailand", 18.7883, 98.9853,
     ("Ankunft in Bangkok", "Nachtzug nach Chiang Mai", "Doi Suthep", "Kochkurs", "Elefanten-Auffangstation",
      "Zurück nach Bangkok", "Letzter Tag am Fluss")),
    (date(2024, 5, 30), 9, "Italien mit dem Zug", "Bologna", "Bologna", "Italien", 44.4949, 11.3426,
     ("Nachtzug nach München", "Weiter nach Bologna", "Tortellini und Portici", "Tagesausflug nach Ravenna",
      "Florenz")),
    (date(2024, 10, 11), 4, "Herbst in Amsterdam", "Amsterdam", "Amsterdam", "Niederlande", 52.3676, 4.9041,
     ("Anreise", "Rijksmuseum", "Nebel über den Grachten")),
    (date(2025, 3, 14), 7, "New York", "New York", "New York", "Vereinigte Staaten", 40.7128, -74.0060,
     ("Ankunft in Newark", "Central Park im Regen", "MoMA", "Brooklyn Bridge", "Letzter Tag")),
    (date(2025, 8, 9), 11, "Australien — Ostküste", "Sydney", "Sydney", "Australien", -33.8688, 151.2093,
     ("Ankunft nach 24 Stunden", "Bondi to Coogee", "Blue Mountains", "Flug nach Cairns",
      "Great Barrier Reef", "Zurück nach Sydney")),
    (date(2026, 4, 3), 6, "Griechenland — Korfu", "Korfu", "Kerkyra", "Griechenland", 39.6243, 19.9217,
     ("Ankunft in Kerkyra", "Altstadt", "Bootstour nach Paxos", "Agios Georgios")),
]

# Allgemeine Tagesüberschriften, wenn das Programm einer Reise kürzer ist als
# sie selbst. Bewusst allgemein: ein erfundener Programmpunkt wäre eine
# Behauptung über einen Ort, die niemand geprüft hat.
FILLER_DAYS = ("Unterwegs", "Ein ruhiger Tag", "Zu Fuß durch die Stadt",
               "Markttag", "Nachmittag am Wasser", "Ausschlafen und lesen")

# --------------------------------------------------------------------------- #
# Konzerte — (Datum, Künstler, Veranstaltungsort, Ortsschlüssel oder Ort)
# --------------------------------------------------------------------------- #
CONCERTS: list[tuple[date, str, str, str]] = [
    (date(2011, 6, 18), "Element of Crime", "Freilichtbühne", "kalkberg"),
    (date(2012, 9, 22), "Kraftklub", "Docks", "hh-hafen"),
    (date(2013, 11, 30), "Bon Iver", "Kieler Schloss", "kiel-foerde"),
    (date(2014, 5, 17), "Sigur Rós", "MAX-Nachttheater", "kiel-foerde"),
    (date(2014, 12, 6), "AnnenMayKantereit", "Schaubude", "kiel-foerde"),
    (date(2015, 7, 11), "Beirut", "Stadtpark Freilichtbühne", "stadtpark-hh"),
    (date(2016, 3, 5), "The National", "Sporthalle", "hh-hafen"),
    (date(2016, 8, 20), "Aurora", "Kieler Woche", "kiel-foerde"),
    (date(2017, 10, 14), "Fleet Foxes", "Laeiszhalle", "hh-hafen"),
    (date(2018, 2, 9), "Agnes Obel", "Elbphilharmonie", "hh-hafen"),
    (date(2018, 6, 30), "Hurricane Festival", "Eichenring", "hh-hafen"),
    (date(2019, 4, 27), "Nils Frahm", "Kampnagel", "stadtpark-hh"),
    (date(2019, 9, 21), "Isolation Berlin", "Molotow", "hh-hafen"),
    (date(2021, 7, 24), "Salvador Sobral", "Coliseu dos Recreios", "lissabon"),
    (date(2021, 10, 2), "Rodrigo Leão", "Teatro Tivoli", "lissabon"),
    (date(2022, 5, 28), "Caribou", "LAV", "lissabon"),
    (date(2022, 8, 13), "Nick Cave", "NOS Alive", "lissabon"),
    (date(2023, 3, 18), "Big Thief", "Fabrik", "hh-hafen"),
    (date(2023, 9, 9), "Sufjan Stevens", "Elbphilharmonie", "hh-hafen"),
    (date(2024, 1, 20), "Bonobo", "Docks", "hh-hafen"),
    (date(2024, 6, 15), "Jungle", "Stadtpark Freilichtbühne", "stadtpark-hh"),
    (date(2024, 11, 8), "Hania Rani", "Elbphilharmonie", "hh-hafen"),
    (date(2025, 5, 3), "Khruangbin", "Sporthalle", "hh-hafen"),
    (date(2025, 8, 30), "Fontaines D.C.", "Stadtpark Freilichtbühne", "stadtpark-hh"),
    (date(2026, 2, 21), "Black Country, New Road", "Kampnagel", "stadtpark-hh"),
]

# --------------------------------------------------------------------------- #
# Kompendium: was in einem Leben wiederkehrt
# --------------------------------------------------------------------------- #
# Tiere mit der Wahrscheinlichkeit, sie zu sehen — ein Eichhörnchen häufiger
# als ein Seeadler. Ohne die Gewichtung wäre die Sammlung eine Liste, in der
# jede Art gleich oft vorkommt, und das ist die einzige Verteilung, die
# garantiert falsch ist.
ANIMALS: list[tuple[str, int]] = [
    ("Eichhörnchen", 30), ("Reh", 22), ("Fuchs", 14), ("Hase", 13),
    ("Kranich", 8), ("Reiher", 10), ("Eule", 5), ("Seeadler", 3),
    ("Schweinswal", 2), ("Robbe", 6), ("Igel", 9), ("Specht", 7),
    ("Schwan", 12), ("Kormoran", 6), ("Fledermaus", 4),
]

DISHES: list[str] = [
    "Franzbrötchen", "Fischbrötchen", "Labskaus", "Grünkohl", "Pastéis de nata",
    "Bacalhau à Brás", "Caldo verde", "Ramen", "Gyoza", "Tortellini",
    "Pasta al pesto", "Tapas", "Paella", "Falafel", "Pho", "Massaman-Curry",
    "Kanelbulle", "Rote Grütze", "Matjes", "Bifana",
]

RESTAURANTS: dict[str, list[str]] = {
    "Bad Segeberg": ["Zum Alten Kalkberg", "Seeterrassen"],
    "Kiel": ["Lüneburg-Haus", "Ratsdiele", "Aalborg"],
    "Hamburg": ["Nil", "Oma's Apotheke", "Bullerei", "Kleine Pause", "Erikas Eck"],
    "Lisboa": ["Cervejaria Ramiro", "Time Out Market", "A Merendeira", "Tasca do Chico"],
}

MOVIES: list[str] = [
    "Das Leben der Anderen", "Spirited Away", "Arrival", "Der Pate", "Parasite",
    "Lost in Translation", "Blade Runner 2049", "Amélie", "Der Herr der Ringe",
    "Whiplash", "Moonlight", "Dune", "Everything Everywhere All at Once",
    "Das Schweigen der Lämmer", "Portrait de la jeune fille en feu",
]

BOOKS: list[str] = [
    "Der Steppenwolf", "Die Wand", "Solaris", "Der Zauberberg", "Middlesex",
    "Tschick", "Austerlitz", "Die Vegetarierin", "Der Report der Magd",
    "Ein wenig Leben", "Norwegian Wood", "Die Känguru-Chroniken",
    "Stolz und Vorurteil", "Der Schwarm", "Das Buch der Unruhe",
]

GAMES: list[str] = [
    "The Legend of Zelda: Breath of the Wild", "Portal 2", "Stardew Valley",
    "Hollow Knight", "Outer Wilds", "Disco Elysium", "Celeste",
    "Return of the Obra Dinn", "Firewatch", "Journey", "Hades",
]

# --------------------------------------------------------------------------- #
# Der Alltag — was sich wiederholt, und ab wann
# --------------------------------------------------------------------------- #
# (Kategorie, ab, bis, Ereignisse je Jahr, Ortsschlüssel je Wohnort-Stadt).
# Die Zahlen steigen mit dem Alter: ein Zwölfjähriger führt kein Tagebuch, und
# vor dem ersten Smartphone gibt es keine importierten Wege.
HABITS: list[tuple[str, date, date | None, int]] = [
    ("sport",   date(2010, 4, 1), None, 95),
    ("journal", date(2012, 1, 1), None, 70),
    ("meal",    date(2012, 6, 1), None, 34),
    ("sighting", date(2005, 1, 1), None, 9),
    ("media",   date(2008, 1, 1), None, 26),
]

# Wo der Sport stattfindet, je Wohnort-Stadt — ein Lauf beginnt zu Hause.
SPORT_SPOTS: dict[str, list[str]] = {
    "Bad Segeberg": ["segeberger-see", "kalkberg"],
    "Kiel": ["kiel-foerde", "kiel-uni"],
    "Hamburg": ["elbstrand", "stadtpark-hh", "alster"],
    "Lisboa": ["isartor-lx", "belem", "cascais"],
}

SPORT_KINDS: list[tuple[str, float, float]] = [
    # (Bezeichnung, Kilometer min, max)
    ("Laufen", 5.0, 14.0),
    ("Radfahren", 15.0, 55.0),
    ("Schwimmen", 1.0, 2.5),
    ("Wanderung", 8.0, 22.0),
]

JOURNAL_LINES: list[str] = [
    "Langer Tag, aber ein guter. Abends noch draußen gesessen.",
    "Nichts Besonderes passiert — und das war genau richtig.",
    "Der erste Tag in diesem Jahr, an dem es wirklich nach Frühling roch.",
    "Viel zu lange am Schreibtisch. Morgen früher raus.",
    "Regen den ganzen Tag. Buch zu Ende gelesen.",
    "Telefonat mit zu Hause, danach war der Kopf leichter.",
    "Auf dem Rückweg hat der Himmel angefangen zu brennen.",
    "Alles ein bisschen zu viel heute. Früh ins Bett.",
    "Neues Café ausprobiert, bleibt.",
    "Zum ersten Mal seit Wochen wieder richtig ausgeschlafen.",
    "Die Stadt war leer, als würde sie jemandem gehören.",
    "Kalt geworden. Der Winter meint es diesmal ernst.",
]

# --------------------------------------------------------------------------- #
# Die Warteschlange — was ein Demo-Bestand zeigen muss, ohne es zu bestätigen
# --------------------------------------------------------------------------- #
# **Ein Demo-Bestand, in dem alles bestätigt ist, zeigt die halbe App nicht.**
# Die drei Schichten Fragment → Vorschlag → Lebensdatenbank sind der Kern
# dieses Systems; wer nur die dritte sieht, sieht eine Datenbank mit Formular.
PENDING_FRAGMENTS: list[str] = [
    "letzten Samstag mit J. auf dem Flohmarkt in der Schanze",
    "irgendwann im Mai 2019 Kurzurlaub auf Sylt",
    "Rezept von Oma: Grünkohl mit Kohlwurst, unbedingt aufschreiben",
]

# (Tage vor heute, Titel, Kategorie, Ortsschlüssel, Zuversicht)
PROPOSALS: list[tuple[int, str, str, str, float]] = [
    (3,  "Spaziergang an der Außenalster", "sport",    "alster",       0.62),
    (6,  "Abendessen im Nil",              "meal",     "hh-eimsbuettel", 0.71),
    (11, "Reiher am Kanal gesehen",        "sighting", "stadtpark-hh", 0.55),
    (18, "Konzert im Molotow",             "concert",  "hh-hafen",     0.48),
]
