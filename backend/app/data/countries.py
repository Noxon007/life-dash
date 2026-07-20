"""Länder-Stammdaten für den Welt-Reiter (F5).

Warum das nötig ist: `country`-Entities entstehen aus dem Reverse-Geocoding
(Nominatim liefert den Landesnamen in der angefragten Sprache) und aus der KI —
beide speichern nur einen **Namen**, keinen ISO-Code (siehe
`routers/tracks.py::_link_country`). Für die eingefärbte Weltkarte und die
Kontinente-Checkliste brauchen wir aber einen stabilen Schlüssel. Diese Tabelle
übersetzt darum Namen (deutsch, englisch, gängige Kurz-/Altformen) → ISO-3166-1
alpha-2 und liefert Kontinent + Kartenzentrum dazu.

Der ISO-Code ist derselbe, den `frontend/world-countries.geojson` je Fläche
trägt (Natural Earth 110m, public domain) — so passen Daten und Karte zusammen.

Kleinstaaten und Inseln ohne eigene Fläche in der 110m-Karte sind bewusst
enthalten: Sie zählen in den Checklisten mit, auch wenn die Karte sie nicht
einfärben kann (`has_area` = False).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

CONTINENTS: dict[str, str] = {
    "EU": "Europa",
    "AS": "Asien",
    "AF": "Afrika",
    "NA": "Nordamerika",
    "SA": "Südamerika",
    "OC": "Ozeanien",
    "AN": "Antarktis",
}

# (ISO-3166-1 alpha-2, deutscher Name, englischer Name, Kontinent, lat, lng)
_ROWS: tuple[tuple[str, str, str, str, float, float], ...] = (
    ("AD", "Andorra", "Andorra", "EU", 42.55, 1.60),
    ("AE", "Vereinigte Arabische Emirate", "United Arab Emirates", "AS", 23.42, 53.85),
    ("AF", "Afghanistan", "Afghanistan", "AS", 33.94, 67.71),
    ("AG", "Antigua und Barbuda", "Antigua and Barbuda", "NA", 17.06, -61.80),
    ("AL", "Albanien", "Albania", "EU", 41.15, 20.17),
    ("AM", "Armenien", "Armenia", "AS", 40.07, 45.04),
    ("AO", "Angola", "Angola", "AF", -11.20, 17.87),
    ("AQ", "Antarktis", "Antarctica", "AN", -75.25, -0.07),
    ("AR", "Argentinien", "Argentina", "SA", -38.42, -63.62),
    ("AT", "Österreich", "Austria", "EU", 47.52, 14.55),
    ("AU", "Australien", "Australia", "OC", -25.27, 133.78),
    ("AZ", "Aserbaidschan", "Azerbaijan", "AS", 40.14, 47.58),
    ("BA", "Bosnien und Herzegowina", "Bosnia and Herzegovina", "EU", 43.92, 17.68),
    ("BB", "Barbados", "Barbados", "NA", 13.19, -59.54),
    ("BD", "Bangladesch", "Bangladesh", "AS", 23.68, 90.36),
    ("BE", "Belgien", "Belgium", "EU", 50.50, 4.47),
    ("BF", "Burkina Faso", "Burkina Faso", "AF", 12.24, -1.56),
    ("BG", "Bulgarien", "Bulgaria", "EU", 42.73, 25.49),
    ("BH", "Bahrain", "Bahrain", "AS", 26.07, 50.56),
    ("BI", "Burundi", "Burundi", "AF", -3.37, 29.92),
    ("BJ", "Benin", "Benin", "AF", 9.31, 2.32),
    ("BN", "Brunei", "Brunei", "AS", 4.54, 114.73),
    ("BO", "Bolivien", "Bolivia", "SA", -16.29, -63.59),
    ("BR", "Brasilien", "Brazil", "SA", -14.24, -51.93),
    ("BS", "Bahamas", "Bahamas", "NA", 25.03, -77.40),
    ("BT", "Bhutan", "Bhutan", "AS", 27.51, 90.43),
    ("BW", "Botswana", "Botswana", "AF", -22.33, 24.68),
    ("BY", "Belarus", "Belarus", "EU", 53.71, 27.95),
    ("BZ", "Belize", "Belize", "NA", 17.19, -88.50),
    ("CA", "Kanada", "Canada", "NA", 56.13, -106.35),
    ("CD", "Demokratische Republik Kongo", "Democratic Republic of the Congo", "AF", -4.04, 21.76),  # noqa: E501
    ("CF", "Zentralafrikanische Republik", "Central African Republic", "AF", 6.61, 20.94),  # noqa: E501
    ("CG", "Republik Kongo", "Republic of the Congo", "AF", -0.23, 15.83),
    ("CH", "Schweiz", "Switzerland", "EU", 46.82, 8.23),
    ("CI", "Elfenbeinküste", "Côte d'Ivoire", "AF", 7.54, -5.55),
    ("CL", "Chile", "Chile", "SA", -35.68, -71.54),
    ("CM", "Kamerun", "Cameroon", "AF", 7.37, 12.35),
    ("CN", "China", "China", "AS", 35.86, 104.20),
    ("CO", "Kolumbien", "Colombia", "SA", 4.57, -74.30),
    ("CR", "Costa Rica", "Costa Rica", "NA", 9.75, -83.75),
    ("CU", "Kuba", "Cuba", "NA", 21.52, -77.78),
    ("CV", "Kap Verde", "Cape Verde", "AF", 16.00, -24.01),
    ("CY", "Zypern", "Cyprus", "EU", 35.13, 33.43),
    ("CZ", "Tschechien", "Czechia", "EU", 49.82, 15.47),
    ("DE", "Deutschland", "Germany", "EU", 51.17, 10.45),
    ("DJ", "Dschibuti", "Djibouti", "AF", 11.83, 42.59),
    ("DK", "Dänemark", "Denmark", "EU", 56.26, 9.50),
    ("DM", "Dominica", "Dominica", "NA", 15.41, -61.37),
    ("DO", "Dominikanische Republik", "Dominican Republic", "NA", 18.74, -70.16),
    ("DZ", "Algerien", "Algeria", "AF", 28.03, 1.66),
    ("EC", "Ecuador", "Ecuador", "SA", -1.83, -78.18),
    ("EE", "Estland", "Estonia", "EU", 58.60, 25.01),
    ("EG", "Ägypten", "Egypt", "AF", 26.82, 30.80),
    ("EH", "Westsahara", "Western Sahara", "AF", 24.22, -12.89),
    ("ER", "Eritrea", "Eritrea", "AF", 15.18, 39.78),
    ("ES", "Spanien", "Spain", "EU", 40.46, -3.75),
    ("ET", "Äthiopien", "Ethiopia", "AF", 9.15, 40.49),
    ("FI", "Finnland", "Finland", "EU", 61.92, 25.75),
    ("FJ", "Fidschi", "Fiji", "OC", -17.71, 178.07),
    ("FK", "Falklandinseln", "Falkland Islands", "SA", -51.80, -59.52),
    ("FM", "Mikronesien", "Micronesia", "OC", 7.43, 150.55),
    ("FR", "Frankreich", "France", "EU", 46.23, 2.21),
    ("GA", "Gabun", "Gabon", "AF", -0.80, 11.61),
    ("GB", "Vereinigtes Königreich", "United Kingdom", "EU", 55.38, -3.44),
    ("GD", "Grenada", "Grenada", "NA", 12.12, -61.68),
    ("GE", "Georgien", "Georgia", "AS", 42.32, 43.36),
    ("GH", "Ghana", "Ghana", "AF", 7.95, -1.02),
    ("GL", "Grönland", "Greenland", "NA", 71.71, -42.60),
    ("GM", "Gambia", "Gambia", "AF", 13.44, -15.31),
    ("GN", "Guinea", "Guinea", "AF", 9.95, -9.70),
    ("GQ", "Äquatorialguinea", "Equatorial Guinea", "AF", 1.65, 10.27),
    ("GR", "Griechenland", "Greece", "EU", 39.07, 21.82),
    ("GT", "Guatemala", "Guatemala", "NA", 15.78, -90.23),
    ("GW", "Guinea-Bissau", "Guinea-Bissau", "AF", 11.80, -15.18),
    ("GY", "Guyana", "Guyana", "SA", 4.86, -58.93),
    ("HN", "Honduras", "Honduras", "NA", 15.20, -86.24),
    ("HR", "Kroatien", "Croatia", "EU", 45.10, 15.20),
    ("HT", "Haiti", "Haiti", "NA", 18.97, -72.29),
    ("HU", "Ungarn", "Hungary", "EU", 47.16, 19.50),
    ("ID", "Indonesien", "Indonesia", "AS", -0.79, 113.92),
    ("IE", "Irland", "Ireland", "EU", 53.41, -8.24),
    ("IL", "Israel", "Israel", "AS", 31.05, 34.85),
    ("IN", "Indien", "India", "AS", 20.59, 78.96),
    ("IQ", "Irak", "Iraq", "AS", 33.22, 43.68),
    ("IR", "Iran", "Iran", "AS", 32.43, 53.69),
    ("IS", "Island", "Iceland", "EU", 64.96, -19.02),
    ("IT", "Italien", "Italy", "EU", 41.87, 12.57),
    ("JM", "Jamaika", "Jamaica", "NA", 18.11, -77.30),
    ("JO", "Jordanien", "Jordan", "AS", 30.59, 36.24),
    ("JP", "Japan", "Japan", "AS", 36.20, 138.25),
    ("KE", "Kenia", "Kenya", "AF", -0.02, 37.91),
    ("KG", "Kirgisistan", "Kyrgyzstan", "AS", 41.20, 74.77),
    ("KH", "Kambodscha", "Cambodia", "AS", 12.57, 104.99),
    ("KI", "Kiribati", "Kiribati", "OC", 1.87, -157.36),
    ("KM", "Komoren", "Comoros", "AF", -11.88, 43.87),
    ("KN", "St. Kitts und Nevis", "Saint Kitts and Nevis", "NA", 17.36, -62.78),
    ("KP", "Nordkorea", "North Korea", "AS", 40.34, 127.51),
    ("KR", "Südkorea", "South Korea", "AS", 35.91, 127.77),
    ("KW", "Kuwait", "Kuwait", "AS", 29.31, 47.48),
    ("KZ", "Kasachstan", "Kazakhstan", "AS", 48.02, 66.92),
    ("LA", "Laos", "Laos", "AS", 19.86, 102.50),
    ("LB", "Libanon", "Lebanon", "AS", 33.85, 35.86),
    ("LC", "St. Lucia", "Saint Lucia", "NA", 13.91, -60.98),
    ("LI", "Liechtenstein", "Liechtenstein", "EU", 47.17, 9.56),
    ("LK", "Sri Lanka", "Sri Lanka", "AS", 7.87, 80.77),
    ("LR", "Liberia", "Liberia", "AF", 6.43, -9.43),
    ("LS", "Lesotho", "Lesotho", "AF", -29.61, 28.23),
    ("LT", "Litauen", "Lithuania", "EU", 55.17, 23.88),
    ("LU", "Luxemburg", "Luxembourg", "EU", 49.82, 6.13),
    ("LV", "Lettland", "Latvia", "EU", 56.88, 24.60),
    ("LY", "Libyen", "Libya", "AF", 26.34, 17.23),
    ("MA", "Marokko", "Morocco", "AF", 31.79, -7.09),
    ("MC", "Monaco", "Monaco", "EU", 43.75, 7.41),
    ("MD", "Moldau", "Moldova", "EU", 47.41, 28.37),
    ("ME", "Montenegro", "Montenegro", "EU", 42.71, 19.37),
    ("MG", "Madagaskar", "Madagascar", "AF", -18.77, 46.87),
    ("MH", "Marshallinseln", "Marshall Islands", "OC", 7.13, 171.18),
    ("MK", "Nordmazedonien", "North Macedonia", "EU", 41.61, 21.75),
    ("ML", "Mali", "Mali", "AF", 17.57, -3.996),
    ("MM", "Myanmar", "Myanmar", "AS", 21.91, 95.96),
    ("MN", "Mongolei", "Mongolia", "AS", 46.86, 103.85),
    ("MR", "Mauretanien", "Mauritania", "AF", 21.01, -10.94),
    ("MT", "Malta", "Malta", "EU", 35.94, 14.38),
    ("MU", "Mauritius", "Mauritius", "AF", -20.35, 57.55),
    ("MV", "Malediven", "Maldives", "AS", 3.20, 73.22),
    ("MW", "Malawi", "Malawi", "AF", -13.25, 34.30),
    ("MX", "Mexiko", "Mexico", "NA", 23.63, -102.55),
    ("MY", "Malaysia", "Malaysia", "AS", 4.21, 101.98),
    ("MZ", "Mosambik", "Mozambique", "AF", -18.67, 35.53),
    ("NA", "Namibia", "Namibia", "AF", -22.96, 18.49),
    ("NC", "Neukaledonien", "New Caledonia", "OC", -20.90, 165.62),
    ("NE", "Niger", "Niger", "AF", 17.61, 8.08),
    ("NG", "Nigeria", "Nigeria", "AF", 9.08, 8.68),
    ("NI", "Nicaragua", "Nicaragua", "NA", 12.87, -85.21),
    ("NL", "Niederlande", "Netherlands", "EU", 52.13, 5.29),
    ("NO", "Norwegen", "Norway", "EU", 60.47, 8.47),
    ("NP", "Nepal", "Nepal", "AS", 28.39, 84.12),
    ("NR", "Nauru", "Nauru", "OC", -0.52, 166.93),
    ("NZ", "Neuseeland", "New Zealand", "OC", -40.90, 174.89),
    ("OM", "Oman", "Oman", "AS", 21.51, 55.92),
    ("PA", "Panama", "Panama", "NA", 8.54, -80.78),
    ("PE", "Peru", "Peru", "SA", -9.19, -75.02),
    ("PG", "Papua-Neuguinea", "Papua New Guinea", "OC", -6.31, 143.96),
    ("PH", "Philippinen", "Philippines", "AS", 12.88, 121.77),
    ("PK", "Pakistan", "Pakistan", "AS", 30.38, 69.35),
    ("PL", "Polen", "Poland", "EU", 51.92, 19.15),
    ("PR", "Puerto Rico", "Puerto Rico", "NA", 18.22, -66.59),
    ("PS", "Palästina", "Palestine", "AS", 31.95, 35.23),
    ("PT", "Portugal", "Portugal", "EU", 39.40, -8.22),
    ("PW", "Palau", "Palau", "OC", 7.51, 134.58),
    ("PY", "Paraguay", "Paraguay", "SA", -23.44, -58.44),
    ("QA", "Katar", "Qatar", "AS", 25.35, 51.18),
    ("RO", "Rumänien", "Romania", "EU", 45.94, 24.97),
    ("RS", "Serbien", "Serbia", "EU", 44.02, 21.01),
    ("RU", "Russland", "Russia", "EU", 61.52, 105.32),
    ("RW", "Ruanda", "Rwanda", "AF", -1.94, 29.87),
    ("SA", "Saudi-Arabien", "Saudi Arabia", "AS", 23.89, 45.08),
    ("SB", "Salomonen", "Solomon Islands", "OC", -9.65, 160.16),
    ("SC", "Seychellen", "Seychelles", "AF", -4.68, 55.49),
    ("SD", "Sudan", "Sudan", "AF", 12.86, 30.22),
    ("SE", "Schweden", "Sweden", "EU", 60.13, 18.64),
    ("SG", "Singapur", "Singapore", "AS", 1.35, 103.82),
    ("SI", "Slowenien", "Slovenia", "EU", 46.15, 14.99),
    ("SK", "Slowakei", "Slovakia", "EU", 48.67, 19.70),
    ("SL", "Sierra Leone", "Sierra Leone", "AF", 8.46, -11.78),
    ("SM", "San Marino", "San Marino", "EU", 43.94, 12.46),
    ("SN", "Senegal", "Senegal", "AF", 14.50, -14.45),
    ("SO", "Somalia", "Somalia", "AF", 5.15, 46.20),
    ("SR", "Suriname", "Suriname", "SA", 3.92, -56.03),
    ("SS", "Südsudan", "South Sudan", "AF", 6.88, 31.31),
    ("ST", "São Tomé und Príncipe", "Sao Tome and Principe", "AF", 0.19, 6.61),
    ("SV", "El Salvador", "El Salvador", "NA", 13.79, -88.90),
    ("SY", "Syrien", "Syria", "AS", 34.80, 38.997),
    ("SZ", "Eswatini", "Eswatini", "AF", -26.52, 31.47),
    ("TD", "Tschad", "Chad", "AF", 15.45, 18.73),
    ("TF", "Französische Süd- und Antarktisgebiete", "French Southern Territories", "AN", -49.28, 69.35),  # noqa: E501
    ("TG", "Togo", "Togo", "AF", 8.62, 0.82),
    ("TH", "Thailand", "Thailand", "AS", 15.87, 100.99),
    ("TJ", "Tadschikistan", "Tajikistan", "AS", 38.86, 71.28),
    ("TL", "Osttimor", "Timor-Leste", "AS", -8.87, 125.73),
    ("TM", "Turkmenistan", "Turkmenistan", "AS", 38.97, 59.56),
    ("TN", "Tunesien", "Tunisia", "AF", 33.89, 9.54),
    ("TO", "Tonga", "Tonga", "OC", -21.18, -175.20),
    ("TR", "Türkei", "Turkey", "AS", 38.96, 35.24),
    ("TT", "Trinidad und Tobago", "Trinidad and Tobago", "NA", 10.69, -61.22),
    ("TV", "Tuvalu", "Tuvalu", "OC", -7.11, 177.65),
    ("TW", "Taiwan", "Taiwan", "AS", 23.70, 120.96),
    ("TZ", "Tansania", "Tanzania", "AF", -6.37, 34.89),
    ("UA", "Ukraine", "Ukraine", "EU", 48.38, 31.17),
    ("UG", "Uganda", "Uganda", "AF", 1.37, 32.29),
    ("US", "Vereinigte Staaten", "United States of America", "NA", 37.09, -95.71),
    ("UY", "Uruguay", "Uruguay", "SA", -32.52, -55.77),
    ("UZ", "Usbekistan", "Uzbekistan", "AS", 41.38, 64.59),
    ("VA", "Vatikanstadt", "Vatican City", "EU", 41.90, 12.45),
    ("VC", "St. Vincent und die Grenadinen", "Saint Vincent and the Grenadines", "NA", 12.98, -61.29),  # noqa: E501
    ("VE", "Venezuela", "Venezuela", "SA", 6.42, -66.59),
    ("VN", "Vietnam", "Vietnam", "AS", 14.06, 108.28),
    ("VU", "Vanuatu", "Vanuatu", "OC", -15.38, 166.96),
    ("WS", "Samoa", "Samoa", "OC", -13.76, -172.10),
    ("XK", "Kosovo", "Kosovo", "EU", 42.60, 20.90),
    ("YE", "Jemen", "Yemen", "AS", 15.55, 48.52),
    ("ZA", "Südafrika", "South Africa", "AF", -30.56, 22.94),
    ("ZM", "Sambia", "Zambia", "AF", -13.13, 27.85),
    ("ZW", "Simbabwe", "Zimbabwe", "AF", -19.02, 29.15),
)

# Zusätzliche Schreibweisen, unter denen Nominatim oder die KI ein Land liefern
# kann — Alt- und Kurzformen, Eigenbezeichnungen, gängige Umgangssprache.
_ALIASES: dict[str, str] = {
    "usa": "US",
    "u.s.a.": "US",
    "united states": "US",
    "amerika": "US",
    "vereinigte staaten von amerika": "US",
    "uk": "GB",
    "england": "GB",
    "schottland": "GB",
    "wales": "GB",
    "nordirland": "GB",
    "grossbritannien": "GB",
    "great britain": "GB",
    "holland": "NL",
    "tschechische republik": "CZ",
    "czech republic": "CZ",
    "tschechei": "CZ",
    "elfenbeinkueste": "CI",
    "ivory coast": "CI",
    "cote d'ivoire": "CI",
    "kongo": "CD",
    "dr kongo": "CD",
    "kongo-kinshasa": "CD",
    "kongo-brazzaville": "CG",
    "birma": "MM",
    "burma": "MM",
    "swasiland": "SZ",
    "weissrussland": "BY",
    "mazedonien": "MK",
    "moldawien": "MD",
    "republik moldau": "MD",
    "kap verde": "CV",
    "cabo verde": "CV",
    "kaiserreich japan": "JP",
    "vae": "AE",
    "emirate": "AE",
    "sued korea": "KR",
    "republik korea": "KR",
    "nord korea": "KP",
    "osttimor": "TL",
    "east timor": "TL",
    "vatikan": "VA",
    "heiliger stuhl": "VA",
    "deutschland (bundesrepublik)": "DE",
    "brd": "DE",
    "oesterreich": "AT",
    "schweiz (confoederatio helvetica)": "CH",
    "suisse": "CH",
    "svizzera": "CH",
    "espana": "ES",
    "italia": "IT",
    "polska": "PL",
    "magyarorszag": "HU",
    "hrvatska": "HR",
    "sverige": "SE",
    "norge": "NO",
    "danmark": "DK",
    "suomi": "FI",
    "island (iceland)": "IS",
    "nederland": "NL",
    "belgie": "BE",
    "belgique": "BE",
    "tuerkiye": "TR",
    "turkiye": "TR",
}


@dataclass(frozen=True)
class Country:
    """Ein Land der Stammdatentabelle."""

    iso: str
    name_de: str
    name_en: str
    continent: str
    lat: float
    lng: float

    @property
    def continent_label(self) -> str:
        return CONTINENTS[self.continent]


BY_ISO: dict[str, Country] = {
    row[0]: Country(iso=row[0], name_de=row[1], name_en=row[2],
                    continent=row[3], lat=row[4], lng=row[5])
    for row in _ROWS
}


def _normalize(name: str) -> str:
    """Vergleichsform: klein, ohne Akzente/Umlaut-Diakritika, ohne Doppelspaces.

    Umlaute werden dabei zu ihrem Grundbuchstaben (ä→a) — deshalb funktioniert
    der Lookup auch, wenn eine Quelle „Osterreich" oder „Turkei" schreibt.
    """
    folded = name.replace("ß", "ss").strip().lower()
    decomposed = unicodedata.normalize("NFD", folded)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.split())


_LOOKUP: dict[str, str] = {}
for _c in BY_ISO.values():
    _LOOKUP[_normalize(_c.name_de)] = _c.iso
    _LOOKUP.setdefault(_normalize(_c.name_en), _c.iso)
for _alias, _iso in _ALIASES.items():
    _LOOKUP.setdefault(_normalize(_alias), _iso)


def resolve(name: str | None) -> Country | None:
    """Findet das Land zu einem freien Namen (deutsch, englisch, Alias, ISO-Code).

    Gibt `None` zurück, wenn nichts passt — der Aufrufer behandelt solche
    Entities als „nicht zuordenbar" und zeigt sie separat an, statt sie
    stillschweigend zu verschlucken.
    """
    if not name:
        return None
    raw = name.strip()
    if len(raw) == 2 and raw.upper() in BY_ISO:
        return BY_ISO[raw.upper()]
    iso = _LOOKUP.get(_normalize(raw))
    return BY_ISO.get(iso) if iso else None


def by_continent() -> dict[str, list[Country]]:
    """Alle Länder je Kontinent, alphabetisch — Grundlage der Checklisten."""
    out: dict[str, list[Country]] = {key: [] for key in CONTINENTS}
    for country in BY_ISO.values():
        out[country.continent].append(country)
    for items in out.values():
        items.sort(key=lambda c: c.name_de)
    return out
