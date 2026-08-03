# CLAUDE.md — Arbeitsanleitung für dieses Repo

## Was ist das
Life-Dash: self-hosted „Lebensdatenbank" (FastAPI + SQLAlchemy/SQLite; Vanilla-JS-PWA
komplett in `frontend/index.html`, wird vom Backend unter `/` ausgeliefert). AGPL-3.0.
**Führendes Dokument: `docs/KONZEPT.md`** — Vision/Architektur + Roadmap in
Kap. 14.2, aber **nur noch OFFENE Pakete** (F20/F21/R1/R2 vor 1.0, P6.1/P5.2 +
Konnektoren danach). Entscheidungen/Anmerkungen in **`docs/DECISIONS.md`**;
**was gebaut wurde und in welcher Version, steht dort in Anhang A**
(seit 2026-08-03, Anm. 161 — vorher KONZEPT 14.1/14.2/14.3). Erst dort gezielt
nachlesen statt Code raten. Drei Dokumente, drei Fragen: KONZEPT = was noch
offen ist, DECISIONS = warum es so gebaut ist + wann es kam, CHANGELOG = was
ein Nutzer merkt.

## Kommandos (Windows!)
- Python: `C:\Users\phili\miniforge3\envs\py313\python.exe` — **kein `python` im PATH**
- Tests: `cd backend` → `<python> -m pytest tests -q` (laufen offline: Mock-KI, Geocoding aus)
  — 625 Tests, ~15 s, SQLite im Arbeitsspeicher
- **Tests gegen echtes PostgreSQL** (das, worauf betrieben wird): `pwsh
  tools/pg-test.ps1` — **kein Docker**, das Skript legt mit den installierten
  Binärdateien einen eigenen Cluster in `backend/_pgtest/` auf Port **55432** an
  und stoppt ihn danach (`-Keep` lässt ihn stehen, `-Stop` räumt auf). ~45 s.
  Setzt `TEST_DATABASE_URL`, das `conftest.py` auswertet; **zwei Riegel davor**,
  weil die Suite das Schema löscht: die URL darf nicht die betriebene sein, und
  der DB-Name muss `test` enthalten.
  **Zwei Fallen, beide 2026-08-03 bezahlt:** (a) ein Test mit
  `with TestClient(app)` fährt den **Lifespan** — der öffnet die KONFIGURIERTE
  Datenbank und startet den Minuten-Ticker; auf SQLite unsichtbar, auf
  PostgreSQL hängt die Suite. Client ohne `with` bauen. (b) Der Cluster startet
  mit `lc_messages=C`, weil ein deutsch installiertes PostgreSQL in cp1252
  meldet und `psycopg2` das als UTF-8 dekodiert — **jeder echte Befund käme
  sonst als `UnicodeDecodeError` an**.
- Wächter: `cd tools` → `npm run check` (33 jsdom-Dateien, ~506 Zusicherungen)
- **Smoke gegen ein HTTP-Doppel** (Immich): `<python> tools/immich_double.py &`
  dann `<python> tools/smoke_a45.py` — findet, was Unit-Tests prinzipiell nicht
  können (Blättern, Zeitzonen, echte DTOs). Immer aus dem Wurzelverzeichnis.
- **API-Kosten messen** statt raten: `<python> tools/_measure_api.py` legt
  20.000 Ereignisse an und misst die Endpunkte (Anm. 140)
- **CI** (`.github/workflows/tests.yml`): fährt bei jedem Push/PR beides — pytest auf
  SQLite *und* auf PostgreSQL — plus die Wächter. Bewusst ohne Pfadfilter und ohne
  `cancel-in-progress`: ein übersprungener Test sieht aus wie ein bestandener.
- Smoke-Server mit Scratch-DB (echte DB nie anfassen):
  `$env:DATABASE_URL="sqlite:///./_smoke.db"; $env:AUTH_MODE="dev"; $env:AI_PROVIDER="mock"`
  dann `<python> -m uvicorn app.main:app --port 8123` aus `backend/`
- JS-Check: Inline-Scripts aus index.html per node `new Function(...)` syntaxprüfen

## Architektur-Kurzfassung
- Vier Schichten: Fragment (Roh-Eingang, nie automatisch löschen) → unconfirmed (Vorschlag)
  → confirmed (**Lebensdatenbank — Maschinen ändern Bestätigtes nie, Anreicherung wie
  Wetter nur ADDITIV**) → Ableitungen (Embeddings/Ansichten, jederzeit neu berechenbar)
- `backend/app/`: `models.py` (Event mit parent_event_id/F7, note=Markdown/F1),
  `migrate.py` (ALTER-TABLE-Migrationen: `_MISSING_COLUMNS`), `routers/` (events,
  moderation, tracks=Timeline-Import+Ortsnamen, jobs=Background-Worker mit Lock pro Typ,
  admin, data=Export/Import, auth=OIDC, world=F5, achievements=F6), `services/`
  (ingestion, enrichment=Wetter, geocode=Nominatim/LocationIQ mit 429-Backoff,
  weather=Open-Meteo, achievements=F6-Metriken), `data/countries.py` (Länder-Stammdaten:
  Name→ISO→Kontinent; passt zu `frontend/world-countries.geojson`)
- `frontend/index.html`: EIN File (CSS+HTML+JS, ~3600 Zeilen) — **gezielt per Grep und
  Read mit offset/limit lesen, nie komplett**
- Module deklarativ: `backend/modules/*.yaml` (Kategorien, Labels, Farben, Kompendium)

## Arbeitsregeln (vom User festgelegt)
- **NIE pushen oder taggen** — Commits ja; Push/Tag macht der User selbst
- **Zwei Gleise (Anmerkung 86):** Push auf `main` → Image `:main` (Testen, ohne
  Version). SemVer-Tag → `:X.Y.Z`/`:latest` (Veröffentlichung). Eine neue
  Version also nur, wenn ein NUTZER einen Unterschied merkt — mehrere Pakete
  dürfen sich eine teilen. Nicht mehr je Arbeitspaket eine Nummer vergeben.
- Jede Version: `backend/app/version.py` + `CHANGELOG.md` (verständliche Produktsprache,
  **keine Paketkürzel** wie „A25") + Paket abhaken. **Abgehakt wird seit
  Anm. 161 in `docs/DECISIONS.md` Anhang A** (✅ + „fertig vX.Y.Z"), nicht mehr
  in KONZEPT — dort steht nur noch Offenes; ein fertiges Paket wird aus 14.2
  ENTFERNT und wandert in den Anhang
- Commit-Stil: deutsch, `feat(bereich): X.Y.Z — Beschreibung` (Historie ansehen)
- Doku derzeit deutsch; Paket F10 stellt sie später einmalig auf Englisch um
- **Vier Schichten, und F20 hat eine VIERTE Sorte Aussage dazugestellt**
  (Anm. 144): `BaselineLocation` = stehende Tatsache mit Gültigkeitszeitraum
  (Lebensdatenbank, eine Zeile), die Tage daraus = Schicht 4, nirgends
  gespeichert (`services/baseline.py`). Wer eine Zahl über Tage bildet, muss
  sie mitzählen; wer eine Zahl über EINTRÄGE bildet, darf es nicht.
- Neue Event-Kategorie? Drei Stellen: KI-Prompt/Module-YAML, Frontend (catLabels/Farben/
  KNOWN_CATS/FILTER_CATS_BASE + CSS), ggf. Selects im HTML
- Allgemeingültigkeit (A27): nichts Homelab-Spezifisches hart verdrahten (Provider-Namen
  etc. aus Config); `.env.example` ist die Setup-Referenz

## Stand
**Doku aufgeteilt (2026-08-02, Anm. 147):** `docs/KONZEPT.md` = was und warum
(Vision, Architektur, Roadmap 14.2/14.3); **`docs/DECISIONS.md` = die
nummerierten Anmerkungen** mit ihrer Begründung. Erst dort nachlesen, nicht
mehr in KONZEPT Kap. 15 — das ist jetzt ein Zeiger mit der Tabelle der noch
OFFENEN Fragen (144–147). Anmerkungen stehen in der Reihenfolge, in der sie
AUFKAMEN, nicht in der sie gebaut wurden — Neues wird angehängt, auch wenn
davor noch Offenes steht.

**F21 gebaut (2026-08-03, Anmerkung 145) — die Lückenprüfung. Direkt hinter
F20, auf `main`.** Vierte Statistik-Ansicht neben Zahlen · Diagrammen ·
Ranglisten: **„wo weiß ich gar nichts?"** — die einzige Frage, die eine
Lebensdatenbank nicht beantworten kann, indem sie ansieht, was sie hat.

**Das FENSTER war der ganze Entwurf.** Anm. 156 hatte entschieden: die Zeit vor
dem ersten Eintrag ist keine Lücke, sondern die Zeit vor dem ersten Eintrag.
Mit einem **Geburts-Meilenstein** kehrt sich das um — dann ist bekannt, dass da
ein Leben war, über das nichts vorliegt, und genau danach wurde gefragt. Also:
**Geburt→heute mit Meilenstein, erster→letzter bekannter Tag ohne**, und
`since_birth` reist bis in die Anzeige. Zwei Lesarten derselben Prozentzahl, und
die eine zu zeigen während man die andere behauptet ist die einzige Art, wie
diese Ansicht lügen kann. Der Kopf nennt deshalb seinen Bezug und sagt, wie man
ihn erweitert.

**„Längste Lücke" in den Ranglisten ist jetzt Platz 1 dieser Liste** — dieselbe
Funktion (`services/gaps.py`), das Anm.-156-Muster. Zwei Rechnungen wären beim
ersten Sonderfall auseinandergelaufen, und die Sonderfälle SIND hier die Ränder.

**Zukunftstage fliegen an der Quelle raus, und das ist keine Kosmetik:** ein
Eintrag mit vertipptem Jahr (2999 statt 1999) öffnete sonst ein
Tausend-Jahre-Fenster — 350.000 Kalenderschritte für eine Kachel, und als Befund
eine Lücke, die es nie gab. Die Grenze musste auch für ÜBERGEBENE Mengen
gelten, weil `_streaks` seine eigene, ungefilterte Liste hereinreicht:
**eine Zusage, die davon abhängt, dass der Aufrufer sie kennt, ist keine.**

**Gespeichert wird nichts** (Anm. 145 hatte den Grund vorweggenommen). Daraus
folgt auch die AKTION: nicht ein Sprung in den Zeitstrahl — eine Lücke ist per
Definition leer, dort stünde nichts —, sondern die Übernahme der Daten ins
Grundort-Formular. F20 und F21 schließen gegenseitig ihre Schleife.

**Nebenbefund:** `check-stats-panes.js` prüfte „es gibt DREI Ansichten". Die
Zahl fiel um, als eine vierte kam, obwohl nichts kaputt war — und hätte
geschwiegen bei dem einzigen echten Defekt (ein Reiter ohne Bereich). Prüft
jetzt, dass Leiste und Bereiche sich in BEIDE Richtungen decken (Anm. 114:
ein Wächter, der nur seinen Auslöser kennt, ist einer für die Vergangenheit).

**F20 gebaut (2026-08-03, Anmerkung 144) — der Grundort. Auf `main`, ohne
Versionssprung.** „Ich möchte irgendwann für jeden Tag einen Eintrag haben, auch
wenn da nur ‚Bad Segeberg' steht — dann kann Wetter angereichert werden."

**Gebaut als ABLEITUNG, nicht als Zeilen.** `BaselineLocation` = eine Zeile je
Zeitraum, zeigt auf ein `Location` (damit reisen Koordinate fürs Wetter,
`city` (A39) und `country` (F4) gratis mit, und jede Statistik fragt dieselbe
Tabelle wie bisher). Die TAGE stehen **nirgends** — `services/baseline.py`
läuft bei jeder Abfrage den Kalender ab (14.600 Iterationen für vierzig Jahre,
die billigere Hälfte jeder Statistik, die sie braucht). Anm. 145 vorweggenommen:
eine gespeicherte Ableitung müsste bei jedem Import, jeder Löschung und jeder
Zeitraum-Änderung nachgeführt werden.

**Die Eigenschaft, auf der alles andere steht: die beiden Tagesmengen sind
disjunkt.** Der Grundort füllt nur Lücken, also hat kein Tag beides. Deshalb
darf jede Statistik einfach ADDIEREN, und deshalb kann die Wetter-Vereinigung
nichts doppelt sehen. `test_f20_baseline.py` nagelt genau das zuerst fest —
alles Nachgelagerte wird still falsch, sobald es nicht mehr gilt.

**Der eigentliche Aufwand war das Wetter, nicht der Grundort.** Wetter hängt an
`Metric.event_id`; ein Grundort-Tag hat kein Ereignis. Neu: `DayMetric` —
**dieselbe FORM wie `Metric`**, bewusst kein JSON je Tag: `weather_day` fasst in
SQL zusammen und die Erfolgs-Schwellen zählen/summieren über genau diese
Abfrage. Gleiche Form heißt EINE Vereinigung (`weather_day._rows`), und jede
Regel darüber gilt unverändert für beide Quellen.

**Drei Stellen, an denen das Paket hätte lügen können.** (a) Die Ranglisten
holen mehr Zeilen, als sie zeigen (`_PRE_N`), BEVOR der Grundort eingerechnet
wird — sonst käme ein Ort mit ein paar Einträgen und 2.000 Grundort-Tagen als
frische Zeile mit „0 Einträgen" zurück. (b) Die Jahres-Sammelzeile zählt einen
abgeleiteten Tag als TAG, nie als Ereignis („365 Ereignisse" über ein Jahr ohne
Erfassung = Anm. 143 an neuer Stelle). (c) Der Zeitstrahl deckelt bei 300,
gleichmäßig verteilt, und die Fußzeile sagt es (`slice(0, N)` war der Defekt aus
Anm. 110 UND 160 — hier wäre es das dritte Mal).

**Zwei Befunde, die der Bau erzwang:** `/api/days/baseline` trägt die
Beschreibung EINMAL mit Index je Tag (Anm. 157: sechs Jahre × „Elternhaus,
Musterweg 1, …" wären 1,4 MB für 30 Byte Auskunft) — diesmal gleich beim ersten
Bau statt nach einer Messung. Und `EventsIndex.revision` musste den Grundort
kennen: ein bloß GEÄNDERTER Zeitraum lässt Zahl und Zeitstempel aller Ereignisse
unberührt, Karte und Ranglisten hätten ihren alten Stand behalten und dabei
vollständig ausgesehen.

**Der PostgreSQL-Lauf fand den letzten Fehler, und der saß im TEST:** die neue
`client`-Fixture benutzte `with TestClient(app)` — im Kontextmanager fährt der
**Lifespan**, der `ensure_schema`/`create_all` auf der KONFIGURIERTEN Datenbank
öffnet und den Minuten-Ticker startet. `test_a35_local_auth.py` hatte genau das
schon aufgeschrieben. Auf SQLite unsichtbar, auf PostgreSQL hing die Suite.
**Zweiter Befund im Werkzeug selbst:** `tools/pg-test.ps1` startete den Cluster
mit deutscher Locale → Servermeldungen in `German_Germany.1252`, und `psycopg2`
dekodiert sie als UTF-8 → **jeder echte Befund kam als `UnicodeDecodeError` an**.
Jetzt `lc_messages=C`, und die `psql`-Probe prüft ihren Rückgabewert, statt ihn
mit `2>$null` zu verschlucken. Danach: 609 Tests, 43 s.

**Fünfter Durchgang 2026-08-03 (Anmerkung 161) — ein Defekt, vier
Entscheidungen, ein Doku-Umbau.**

**Anm. 161 — „Kältester Tag" listete zehnmal denselben 11.1.2026.** Am
Rangfolge-Code hat sich seit Anm. 156 nichts geändert; geändert hat sich der
BESTAND darunter. `_extreme_tops` ordnete EREIGNISSE — solange nur die Kachel
(Platz 1) sichtbar war, fiel das nie auf; Anm. 156 stellte eine Liste von zehn
darunter, und Anm. 139 hatte drei Tage vorher jedes Foto zu einem Ereignis
gemacht. Ein Fototag füllt die Liste allein. **Das ist Anm. 143 zum dritten
Mal: eine Zahl wird zur Aussage über die ZUFUHR, ohne dass jemand den Code
anfasst.** Der Hinweis stand in der Überschrift — die Kachel heißt „…ster
**Tag**", der Klick führt seit Anm. 142 zum Tag, nur die Rangfolge zählte noch
Einträge. **Regel: wo Überschrift und Rechnung sich über die Einheit uneinig
sind, ist die Überschrift meist die ältere und die wahre.**
**Welcher Ort den Tag vertritt, entscheidet die RICHTUNG des Rekords** (kältester
Ort beim kältesten Tag) — kein Widerspruch zu Anm. 119 („der Tageswert ist der
vorsichtige"), sondern eine andere Frage: 119 sagt, was ein Tag BEISTEUERT, ein
Rekord, wie extrem es wurde. `direction` steht schon in `_EXTREMES`, also keine
neue Angabe. Die Verdichtung sitzt in `_extreme_tops`, **nicht im Toplisten-
Aufrufer** — eine Ebene höher wäre die Kachel wieder das Extrem einer anderen
Rangfolge als Platz 1, und der Test, der beide zusammenhält, bliebe grün.

**Anm. 144 entschieden (→ Paket F20), und die Menge war NICHT der Einwand.**
Wunsch: für jeden Tag ein Eintrag, damit Wetter angereichert werden kann.
14.600 Zeilen sind gemessen unkritisch (Anm. 140). **Der eine, entscheidende
Einwand: ein erzeugter Tag wäre `confirmed`** — und Schicht 2 darf keine
Maschine mehr anfassen; eine spätere Zeitraum-Korrektur ließe tausend falsche
Zeilen stehen, die niemand reparieren darf. Gebaut wird deshalb **eine Zeile je
Zeitraum + Tagesableitung in Schicht 4**. Vier Festlegungen des Users:
abgeleitete Tage **zählen voll** (Welt/Top-Orte/Abzeichen), **nur Lücken
füllen**, **ein Grundort zur Zeit**, im Zeitstrahl als abgeleitet markiert.
**Der Aufwand steckt nicht im Grundort, sondern im Wetter:** das hängt an
`Metric.event_id`, ein Tag ohne Ereignis hat keinen Platz dafür → F20 braucht
einen tagesgeschlüsselten Wetter-Speicher (Schicht 4, Geschwister von
`weather_day.day_values`). **Anm. 145 → F21**, danach, nicht davor.
**Anm. 146 (Partner-Ansicht) bestätigt für nach 1.0 → P6.1; vorbereitet wird
NICHTS** — die Vorbereitung, die zählt, ist längst da und besteht aus
Unterlassungen (nichts wird zwischen Konten kopiert, `user_id` filtert an der
Abfrage). **Anm. 147 (Weblate): nein, mit benanntem Auslöser** — dritte Sprache
oder Fremdbeitrag.

**Doku umgebaut (Entscheidung des Users): KONZEPT trägt nur noch OFFENES.**
Kap. 14 war zwei Dokumente unter einer Überschrift — ein Plan und, dreimal so
lang, ein Protokoll von Paketen, über die niemand mehr entscheiden muss.
14.1 („What already works"), die Gruppe-A/B-Tabellen und die Release-Zeilen
0.21–0.39 stehen jetzt **wörtlich** in `docs/DECISIONS.md` **Anhang A**
(A.1–A.4); 14.2 heißt „Open packages" und enthält F20/F21/R1/R2 vor 1.0 und
P6.1/P5.2 + Konnektoren danach. **Nichts wurde beim Verschieben umgeschrieben**
— eine Anmerkung, die „14.1" zitiert, findet ihren Satz weiter. Kap. 15 behält
die Fragen MIT ihrer Antwort statt sie zu löschen: eine Frage, die beim
Beantworten aus dem Index verschwindet, nimmt mit, dass sie je gestellt wurde.

**Sechster Durchgang 2026-08-03 (Anmerkung 163) — die Marke ist ein Tropfen.**
Aus acht nebeneinandergelegten Varianten gewählt (dieselbe Methode wie Anm. 160:
eine Frage, die man ansieht statt liest). **Warum der Tropfen trägt: die Spitze
zeigt auf den Ort.** Bei einer Fläche wandert die Aussage mit wachsender Größe
von „hier" zu „ungefähr hier" — genau deshalb brauchte die Blase davor einen
zweiten, harten Kern, also zwei Kreise für eine Aussage. **EIN Pfad für beide
Stufen** (Nähe-Cluster wie Orts-Gruppe), eine Größenfunktion, eine Farbregel.
**Die Größe ist ABSOLUT statt auf die größte Gruppe im Bild normiert** —
normiert war dieselbe Zwölf beim Blättern mal groß und mal klein, und die
beiden Stufen rechneten zwei Größen für ein Zeichen. Radius weiter aus der
Wurzel (die FLÄCHE ist proportional). **Ein einzelner Eintrag bleibt ein runder
Punkt** — die Form sagt schon, ob eins oder viele.
**Gefragt beim Entscheiden: „clustern die auch?"** Festgehalten, weil daran die
ganze Stufenwahl hängt: in „Nach Nähe" clustert weiter das Plugin (Zusammen-
rücken, Aufteilen, Aufklappen — nur das Symbol ist neu); in „Je Ort"/„Je Stadt"
clustert NICHTS, dort wird nach Ort bzw. Stadt gruppiert, unabhängig vom Zoom.

**Fünfter Durchgang 2026-08-03 (Anmerkung 161) — Rückmeldung zur neuen Leiste.**
Vier Punkte, einer davon eine FRAGE („was ist das für eine Grenze und warum
genau 300?"), und die hatte die teuerste Antwort.

**Die 300 waren keine Grenze über irgendetwas:** in „Jeder Punkt" entstanden je
Eintrag ZWEI Leaflet-Objekte (Marker + nummerierter Kreis darauf), bei 14.747
Punkten also rund dreißigtausend — die Objektlast aus Anm. 153. **Die Ebene
daneben zeichnete zur selben Zeit 20.000 Fotos ohne ein einziges Objekt.** Eine
Regel, die für die eine Punktmenge gilt, gilt auch für die andere; sie stand
nur weiter unten und hieß nach den Fotos (Anm. 141: der Name entscheidet, wer
die Regel findet). Jetzt ist die Leinwand-Ebene ein Bauplan mit Parametern
(`dotLayerProto`), beide Punktmengen benutzen ihn, und **der Deckel ist weg,
nicht erhöht** — samt Hinweis, denn ein Hinweis über einer vollständigen Karte
behauptet einen Verlust, den es nicht gibt. Der EINZIGE verbliebene Deckel
sitzt im Server (50.000, gleichmäßig verteilt).
**Regel aus der Formulierung:** die Meldung führte mit der VERSTECKTEN Zahl
(„14.447 von 14.747 sind ausgeblendet") — daher die Rückfrage „warum werden
genau 300 nicht angezeigt". Ein Hinweis über eine Auswahl nennt zuerst das,
was man ansieht.

**Nummern nur mit Reihenfolge** (die Nummer ist die Beschriftung EINER Linie),
und nur bis 120 Punkte. Gezeichnet auf die Leinwand, nicht als dauerhaftes
Tooltip — das wäre ein DOM-Knoten je Punkt, also genau das, was die Ebene
abschafft. **Eine Marke je Eintrag statt zwei:** der Kreis trug die
Kategoriefarbe, der Marker nichts. **Etiketten über den Blasen weg** (sie
stapelten sich beim Herauszoomen). **Nähe- und Orts-Blase sprechen dieselbe
Bildsprache** — vorher Plugin-Blau mit Ziffer gegen Kategoriefarbe mit
Kern, also zwei Aussehen für eine Aussage. **Ob dieses gemeinsame Aussehen das
richtige ist, ist Anm. 162 und offen.**

**Der englische Katalog hat in dieser Runde die dritte Zusicherung erwischt.**
Unter jsdom startet die Seite ENGLISCH, `applyI18n` ersetzt das deutsche
Markup — eine Prüfung auf gerenderten deutschen Text ist grün, egal was im
Markup steht. Anm. 116 hat das einmal aufgeschrieben; nach drei Fällen ist es
eine Gewohnheit: **wer nutzersichtbaren Text prüft, prüft Anzeige, deutschen
Quelltext UND englischen Katalog.**

**Vierter Durchgang 2026-08-03 (Anmerkung 160) — die Kartenschalter, gebaut.**
Anm. 154 lag als Analyse mit drei Entwürfen da; entschieden wurde an einem
**klickbaren Mockup** (sechs Leisten über EINER Karte, Ist-Zustand als Reiter
null) statt an Prosa. Gewählt: **Entwurf D „Zwei Fragen"**, Blasen statt
Ziffern, eigene Farbe für Fotos.

**Was daraus wurde.** **(a)** Die Leiste ist nach der FRAGE geteilt: „Ebenen"
(woher kommt, was hier liegt) und „Wie dicht"; Vollbild sitzt in der
Kartenecke, wo Fensterfunktionen hingehören. **(c)** 🛰️ gehört dem
Zeitstrahl — der Besuchs-Schalter der Karte trägt dasselbe Zeichen, denselben
Wortlaut und dieselbe Zahl aus demselben Index, die Wege-Ebene bekommt eine
farbige Linie als Marke. Dazu ein dritter Schalter **„Von Hand"**, den der
Zeitstrahl bewusst NICHT bekommt: eigene Einträge in einer Liste des eigenen
Lebens auszublenden ist sinnlos, auf einer Karte unter 6.000 importierten
Besuchen ist es die nützlichste Ansicht. Ein Unterschied im MEDIUM, keine
Inkonsistenz. **(d)** Vier **benannte** Stufen (jeder Punkt · nach Nähe · je
Ort · je Stadt), und die Zoomstufe entscheidet daran **nichts** mehr. Der
300er-Deckel gehört zu genau einer Stufe und steht in ihrem Titel. **A18s
Cluster-Schwelle ist ersatzlos weg** — sobald die Stufe die Frage beantwortet,
ist eine zweite, numerische Antwort in den Einstellungen die Doppelregel, um
die es in dieser ganzen Runde geht.

**Und der Deckel schneidet nicht mehr ab:** `all.slice(0, 300)` nahm die ersten
dreihundert CHRONOLOGISCH — in einem Monat mit 2.000 Besuchen fehlte alles ab
der Mitte. Jetzt gleichmäßig verteilt (`mpEvenSpread`, dieselbe Regel wie
`sqlutil.even_spread`).

**„Fläche statt Ziffer".** Eine Cluster-Blase ist fast immer gleich groß, also
sagt nur die ZIFFER etwas — und zwei Ziffern zu vergleichen heißt lesen,
umrechnen, vergleichen. Radius aus der Wurzel (damit die FLÄCHE proportional
ist, nicht der Durchmesser), normiert auf die größte Gruppe im Bild, harter
Kern für den Ort, Name nur wo Platz ist, Farbe der häufigsten Kategorie.

**Fotos sind nicht mehr orange.** `#f5921b` (Foto) gegen `#f5a623` (Kategorie
`event`, also jeder importierte Google-Besuch): zwei Orangetöne einen Farbwert
auseinander für die zwei Dinge, die man auf dieser Karte am ehesten
auseinanderhalten will. Jetzt Cyan, **als Variable `--photo-dot` in beiden
Themes** — die Karte wechselt ihren Untergrund mit dem Theme (F13), und der
Schalter liest dieselbe Variable (zwei gepflegte Farbwerte für eine Ebene
laufen auseinander). `Location.city` reist für „je Stadt" mit: 99 kB von
2,7 MB, nur an den Pins.

**Drei Wächter waren dabei aus dem falschen Grund grün** (Anm. 108). Einer
prüfte, dass `mpEvenSpread` EXISTIERT, statt dass `renderPeriod` sie BENUTZT —
den Deckel zurückgebaut, und er blieb grün; jetzt liest er den letzten Tag in
der Stopp-Liste. Zwei prüften gerenderten DEUTSCHEN Text: **unter jsdom startet
die Seite englisch**, der Katalog überschreibt das Markup, und ein ins Markup
gebauter Defekt erreicht die Zusicherung nie (Anm. 116 hat genau das schon
einmal aufgeschrieben). Beide prüfen jetzt Anzeige, deutschen Quelltext UND
englischen Katalog.

**Dritter Durchgang 2026-08-03 (Anmerkungen 157–159), auf `main`, ohne
Versionssprung — und diesmal ohne neue Meldung.** Ausgangspunkt war die Liste
dessen, was frühere Runden **gemessen und liegen gelassen** hatten, gefiltert
auf das, was keine Entscheidung des Users braucht.

**Anm. 157 — die Kartenlast, der Rest von Anm. 140.** Gemessen (nicht geraten,
`tools/_measure_api.py`, 20.000 Ereignisse): **643 ms / 6,1 MB → 188 ms /
2,7 MB**. Zwei Hälften. **(a) Ein Foto ist auf der Leitung kein Ereignis,
sondern ein Punkt** — Titel („Foto in Detmold", steht nirgends auf der Karte),
Kategorie, Präzision, Quelle, Ereigniskennung und ein verschachtelter Ort mit
eigener Kennung für etwas, das einen Kreis zeichnet. Jetzt `photos:
{places, cats, points}`, je Punkt `[lat, lng, Zeit, Asset, Ort-Index,
Kat-Index]`; Ortsname und Kategorie werden entdoppelt (der Name ist der längste
Wert je Punkt und für hunderte derselbe). **Die Ereigniskennung geht bewusst
NICHT mit** — das Foto-Popup zeigt das Bild, nie den Bearbeiten-Dialog
(Anm. 139), und die Identität eines Fotos ist sein Asset. Der Foto-Anteil fiel
4,05 → 0,74 MB. **(b) Die Abfrage war die ältere Lehre:** 20.000 ORM-Objekte
samt `selectinload(location)` für eine Antwort, die keins behält — Anm. 80 in
zweiter Auflage (*der Preis ist das ERZEUGEN jeder Zeile*). Jetzt Tupel-Abfrage;
`even_spread` hat dafür ein optionales `selection` bekommen, gebaut über
`query.with_entities`, **damit Joins und Filter der übergebenen Abfrage
erhalten bleiben** — ein frisches `db.query(Location.name, …)` hätte den Join
verloren und still ein Kreuzprodukt geliefert. Der Deckel gilt über beide Formen
zusammen: er ist eine Aussage über die Karte, nicht über eine Ebene.

**Anm. 158 — die Karte hatte seit Anm. 139 kein Wetter, und nichts sagte es.**
Nicht gemeldet, beim Lesen desselben Pfades gefunden. Der Endpunkt antwortete
früher mit einer LISTE, seit dem Deckel-Hinweis mit `{total, shown, events}` —
`mpEnsureWeather` las weiter `wx.map(…)`, warf, und landete im `catch`, das für
„ohne Netz kein Wetter" gedacht war; `MP_WX` hatte den Zeitraum da schon als
geladen vermerkt. **Ein `catch`, das zwei verschiedene Fehler auf dieselbe
Stille abbildet, trägt den Defekt statt ihn zu melden** (Anm. 112, gleiche
Form). Der Fehlschlag löst die Marke jetzt wieder, und der Abruf trägt
`photos=0`. Neuer Wächter `check-map-weather.js` — die Stelle hatte **gar
keinen**, und genau deshalb konnte der Defekt in einem ausgelieferten Pfad
sitzen.

**Anm. 159 — Anm. 154 (b): der Wege-Schalter sagt, wenn er nichts zeichnet.**
Von den vier Befunden aus 154 sind drei Entwurfsfragen (bleiben offen); dieser
ist ein Verstoß gegen eine bestehende Regel: `drawTracks` kehrt oberhalb
Monats-Zoom sofort zurück (richtig — Anm. 141), der Chip leuchtete weiter.
Die Zoomgrenze steht jetzt in **einer** Konstante (`TRACK_ZOOMS`), gelesen vom
Zeichner UND vom Schalter. **`inert` ≠ `off`:** aus hat der Nutzer, außer Kraft
ist die Ansicht. **Der Wächter war zweimal aus dem falschen Grund grün**
(Anm. 108, drittes Mal): erst rief er `mpSyncTrackChip()` selbst auf (dann ist
er grün, sobald es die Funktion GIBT — der `check-a41-cities.js`-Fall), dann
lief er über `renderPeriod()` mit LEERER Karte, die einen eigenen Zweig hat.
Erst **mit Punkten auf der Karte** fällt er beim herausgenommenen Aufruf um.

**Bewusst stehen gelassen, mit Messung statt Änderung: `/api/stats/overview`
bei 225 ms.** Kein Hotspot — ~45 ms Basisabfrage über alle datierten Einträge,
13 ms Wettermetriken, der Rest verteilt über zehn Abfragen und die Aggregation
über jede Zeile; und jede dieser Auskünfte ist eine über den GESAMTEN Bestand.
Der einzige nennenswerte Schnitt hieße, den Ranglisten-Pfad umzubauen, den
Anm. 156 gerade erst zu einer Regel vereinheitlicht hat. Profil in
`docs/DECISIONS.md`, damit es kein drittes Mal genommen werden muss.

**Feedback-Runde 2026-08-03, zweiter Durchgang (Anmerkungen 152–156), auf
`main`, ohne Versionssprung.** Vier Punkte: zwei Defekte, eine neue Ansicht,
und die Kartenschalter **bewusst nur analysiert** (der User entscheidet).

**Anm. 153 — der gemeldete Absturz: Vektorkarte + „Alles".** Die Karte legte
**ein Leaflet-Objekt je Foto** an. A45 hatte die ZEICHENLAST längst auf die
Leinwand verschoben, und das war richtig — es spart zehntausend SVG-Knoten.
Was es nicht spart, ist der Rest eines `L.circleMarker`: jeder ist ein `L.Path`
mit eigenem Ereignis-Abonnement und eigenem Popup, wird bei jedem Kartenschritt
einzeln projiziert, und Leaflets Leinwand geht bei jedem Neuzeichnen ihre ganze
Layer-Liste durch. **Die Zeichenlast war nie das Problem, die OBJEKTLAST war
es.** Jetzt ein Layer mit EINER Leinwand (`PHOTO_DOT_LAYER`), Klick über
Trefferliste. **Regel: der Canvas-Renderer ist die halbe Antwort — die andere
Hälfte ist, kein Objekt je Element zu erzeugen.** Aufgefallen ist es unter der
Vektorkarte, weil darunter eine lebende WebGL-Leinwand liegt: dieselbe Stelle,
an der Anm. 141 die Wege-Ebene umkippen ließ. Der Wächter sichert seitdem nicht
mehr „ein Kreis wird gezeichnet", sondern **„es entsteht KEIN Objekt je Foto"**.

**Anm. 152 — „Schwerin, 12 Besuche" klappte 12 Fotos auf.** Der
Verdichtungsschlüssel trägt seit Anm. 139 die Quelle, die Karte sagte trotzdem
immer „Besuche". Zweite, leisere Hälfte desselben Defekts: das Aufklappen
holte `visits=1` und ließ `photos` auf Standard — **was verdichtet hat und was
aufklappt, muss derselbe Schlüssel sein**, sonst zeigt die Aufklappung mehr,
als die Zahl darüber verspricht.

**Anm. 155/156 — Statistik in drei Ansichten** (Zahlen · Diagramme ·
Ranglisten, Wahl im localStorage wie Anm. 149) plus `/api/stats/toplists`
(`services/stats_toplists.py`). **Die Kachel ist Platz 1 der Liste** —
`_extreme_tops` liefert die Rangfolge, der Überblick nimmt den Kopf; zwei
Rangfolgen liefen beim ersten Sonderfall auseinander, und die stehen längst da
(0 ist beim Regen kein Rekord, beim Tageslicht schon). Zwei Stellen, an denen
eine Zahl unehrlich gewesen wäre: die **Lücke** wird nur zwischen erstem und
letztem Tag gemessen (die Zeit davor ist keine Lücke, sondern die Zeit vor dem
ersten Eintrag — hängt an der offenen Anm. 144), und die **längste Reise** ist
die längste ERFASSTE, keine Ableitung aus importierten Besuchen.

**Anm. 154 — Kartenschalter: analysiert, nicht gebaut.** Vier Befunde, drei
Entwürfe (A/B/C) mit Empfehlung in `docs/DECISIONS.md`. Der teuerste Befund:
**„Punkte zusammenfassen" tut drei Dinge**, und welches, entscheidet die
Zoomstufe — und AUSschalten aktiviert zusätzlich den 300er-Deckel. Der
Kartenhinweis aus Anm. 110 ist ein Pflaster darüber. Dazu: der Wege-Schalter ist
oberhalb Monats-Zoom still wirkungslos (`.inert` fehlt), und 🛰️ heißt auf der
Karte etwas anderes als im Zeitstrahl.

**Feedback-Runde 2026-08-03 (Anmerkungen 148–151), auf `main`, ohne
Versionssprung.** Vier gemeldete Punkte, drei davon in der Sammlung.

**Anm. 150 — der gemeldete 500er, und warum ihn 560 Tests nicht sahen.**
„Sammeleinträge entfernen" (der Aufräum-Knopf aus Anm. 139) löscht im BULK
(`query(...).delete()`), und ein Massenlöschen fragt das ORM nie — also läuft
`cascade="all, delete-orphan"` nicht, und Metriken/Verknüpfungen/Bilder bleiben
mit einem Fremdschlüssel ins Leere stehen. **Auf SQLite ist das eine stille
Waise, auf PostgreSQL ein 500.** Dazu baute das Testdoppel den Tagescluster
NACKT nach — dabei ist er bestätigt und verortet, hat also per Definition
Wetter-Metriken. *Ein Doppel, das ein Feld auslässt, ist keine Vereinfachung,
sondern eine andere Funktion* (Anm. 116, zweites Auftreten). Drei Regeln im
Fix, alle drei standen anderswo schon: Metriken/Links gehen MIT, Wege werden
ABGEHÄNGT (eigene Aufzeichnung, keine Ableitung), **hochgeladene Bilder werden
abgehängt statt gelöscht** (Anm. 57) — und bekommen dabei `captured_at`, sonst
wäre das Abhängen ein stilles Wegwerfen. **Regel: wo `db.delete()` durch
`query().delete()` ersetzt wird, geht die Kaskade verloren — und zwar nur dort
sichtbar, wo Fremdschlüssel erzwungen werden.** `pwsh tools/pg-test.ps1` ist
für genau diese Klasse da.

**Anm. 148/149 — Sammlung: Tage führen, und sie ist sortierbar.** Anm. 143
hatte Welt/Top-Orte/Städte umgestellt und den REST des Kompendiums
alphabetisch nach Einträgen zählen lassen: zwei Kacheln derselben Wand, zwei
verschiedene Dinge (Anm. 106 auf einem Bildschirm). Jetzt alle Typen. Zwei
Fallen im Backend: der Besitzfilter gehört in die **JOIN-Bedingung** (ein
äußerer Join mit gefilterter rechter Seite ist ein innerer — sonst
verschwinden genau die Entities ohne Ereignisse, also die zu bestätigenden),
und `count(EventEntityLink.id)` zählte LINKS, nicht Ereignisse.
**Sortiert wird im Browser, und das ist hier richtig:** beide Endpunkte liefern
ihre Menge vollständig, weil ein Kompendium eine Menge mit Horizont ist
(Anm. 95). Über ein Fenster wäre eine Sortierung eine Lüge. Wahl im
localStorage, reiterübergreifend, Voreinstellung Tage.

**Anm. 151 — „Tage mit Wetter" ist weg.** Sie zählte den Fortschritt des
Wetter-Laufs, also eine Auskunft über den LAUF. Die Zahl bleibt in der Antwort
(Schalter für den Block, Nenner des Regenanteils).

**Wächter gegen den kaputten Stand (Anm. 108), und einer war wieder aus dem
falschen Grund grün:** `check-comp-sort.js` prüfte nur den frisch GEKLICKTEN
Zustand — der ist immer stimmig. Der Fall, der auffällt, ist der ERSTE Blick
nach dem Laden (Leiste sagt „Tage", Kacheln stehen alphabetisch); der Wächter
setzt jetzt `localStorage` VOR dem Parsen. Neu: `check-comp-sort.js`,
`test_anm148_compendium_days.py`, drei Prüfungen in `test_photo_events.py`.
**Auf PostgreSQL gegengefahren** (`pwsh tools/pg-test.ps1`) — bei Anm. 150 ist
das nicht optional, dort liegt der Defekt.

**Feedback-Runde 2026-08-02 (Anmerkungen 139–147), auf `main`, ohne
Versionssprung.** Fünf Punkte gebaut, vier bewusst nur entworfen.

**Anm. 139 — ein Foto ist ein Ereignis.** Die teuerste Änderung dieser Runde,
und die einzige, die ein Modell anfasst. Anm. 138 hatte ZWEI Mechanismen für
dieselben Bilder stehen lassen: `PhotoPoint` (verwerfbare Kartenebene, ein
Punkt je Foto) und einen Lauf, der Fototage zu Ereignissen machte. Jetzt einer:
jedes eigene, verortete, im Immich-Zeitstrahl sichtbare Foto wird ein sofort
bestätigtes Ereignis (`immich:photo:<asset>`), keine Mindestzahl mehr.
**`services/immich_source.py`, `PhotoPoint`, `/api/photos/{index,days,map,
groups}` und der Job `immich_source` sind WEG** — `photo_points.py` ist der
eine verbliebene Lauf und legt Ereignisse an, keine Punkte.
**Die eigentliche Frage war, wo die Koordinate liegt.** `Event.lat/lng` wären
zwei Spalten im Kern für einen Konnektor gewesen — nicht nötig: `PhotoPoint`
war ein Ort + ein Zeitstempel + eine Asset-Kennung, und alle drei haben im
Ereignis-Modell längst einen Platz. Entdoppelt wird über die auf **5 Stellen
gerundete Koordinate** (`immich:pt:<lat>,<lng>`): je Stadt wäre der gemeldete
A45-Defekt („London, 1200 Bilder" = ein Punkt), je Foto wären 20.000
Ortszeilen. Diese Orte tragen `type="photo"` und eine **gesetzte `address`** —
ohne die Marke schickte der A47-Rückfüll-Lauf 20.000 gedrosselte
Nominatim-Abrufe hinterher (Endlos-Abruf-Falle, neunte Auflage).
**Karte und Zeitstrahl zeigen zwei verschiedene Dinge derselben Zeile:** die
Karte das BILD (Punkt auf der Leinwand, Vorschaubild im Popup), der Zeitstrahl
die TATSACHE — `eventPhotos()` ist für `source=immich` ausdrücklich
unterdrückt. Das sieht beim Lesen wie ein Fehler aus und ist deshalb im
Wächter festgenagelt.
**Zwei getrennte Schalter** (🛰️ Google, 📷 Immich) → `_hidden_sources()`,
zwei Zähler im Index, und die A39-Bündelung gruppiert nach **(Tag, Ort,
QUELLE)**. Ohne die Quelle im Schlüssel ließe „📷 aus" eine Gruppe stehen,
deren Vertreter ein Foto ist. Der Client-Rückfallfilter musste mit
(`tlShowsSource`) — er warf die Fotos weg, sobald der Google-Schalter aus
stand; **gefunden vom neuen Wächter, nicht von Hand.**
`_DROPPED_TABLES` in `migrate.py` ist die erste Migration, die etwas WEGNIMMT —
sie darf es, weil `photo_points` Schicht 4 war.

**Anm. 140 — gemessen statt geraten.** „Warum lädt er beim Start alles?" — tut
er nicht: 9 Anfragen, 86 ms, 11 kB bei 20.000 Ereignissen (A37). Teuer ist die
**Karte**: 631 ms / 6,1 MB, und zwar bei JEDEM Öffnen des Reiters. Deshalb
`EventsIndex.revision` (= `total` + `max(updated_at)`) und ein Übersprung in
`mpLoadPoints`. **Kein Zeit-Cache** — der zeigt eine Weile etwas Falsches und
danach etwas Richtiges, beides ohne Anlass. `total` allein reichte nicht: eine
Umbenennung ließe die Zahl gleich, und der Titel steht auf der Karte.
**Offen und bewusst liegen gelassen:** `/api/stats/overview` (224 ms) und die
6,1 MB Nutzlast der Karte — ein Fotopunkt braucht vier Werte, nicht ein volles
Ereignis. Die Messung steht in Anm. 140, damit sie nicht wiederholt werden muss.

**Anm. 141 — die Wege-Ebene fror die Wochenansicht ein.** Zwei Defekte:
`/api/tracks` deckelte bei 1000 **still** und nahm die NEUESTEN (in einem
Monat fehlten die ersten 16 Tage — Anm. 110 in einer anderen Datei), und jeder
Weg ging als SVG-Knoten in den DOM. Die Leinwand-Regel aus A45 stand längst da
— sie hieß nur `mpPhotoCanvas`, also **nach der Foto-Ebene statt nach ihrer
Aufgabe**, und wer die Wege baute, hat sie nicht gesucht. Jetzt `mpCanvas`.
**Regel: ein Name entscheidet, wer die Regel findet.** `sqlutil.even_spread`
(„deckeln heißt nicht abschneiden") steht deshalb jetzt dort, wo jeder sucht.

**Anm. 142 — Rekord-Kacheln führen zu ihrem TAG,** nicht in den
Bearbeiten-Dialog eines Eintrags, der zufällig den Messwert trägt (seit
Anm. 119 kommt der Tageswert aus einer Verdichtung über ALLE Einträge des
Tages). `tl.day` + `tlShowDay()`, serverseitig über `from`/`to`.

**Anm. 143 — Tage führen, Einträge stehen daneben.** Welt, Top-Orte,
Meistbesuchte Städte, Städte-Kompendium. Beide Zahlen bleiben („47 Tage · 312
Einträge") — das beantwortet das „hmm, da villt nicht immer" des Users, ohne
eine Frage unbeantwortbar zu machen. `sqlutil.day_number` statt `func.concat`
(SQLite kann es erst ab 3.44, `extract` liefert auf PG Fließkomma). Die
Abweichung ist als TEST festgehalten, sonst liest der A37-Gleichheitsvergleich
sie beim nächsten Mal als Rückschritt.

**Bewusst NICHT gebaut, mit abgewogenen Alternativen in DECISIONS.md:**
**144** Grundort für Zeiträume ohne Daten („Elternhaus 0–6") — braucht eine
VIERTE Sorte Aussage (stehende Tatsache mit Gültigkeitszeitraum, zur
Abfragezeit beantwortet) und drei Entscheidungen des Users vorher; **145**
Lückenprüfung (hängt an 144; ist eine ANSICHT, kein gespeicherter Zustand);
**146** Partner-Ansicht (P6.1, nach 1.0 — eine falsch gebaute Freigabe ist
kein Fehler, sondern eine Offenlegung: Freigabe je Richtung, widerruflich,
NIE kopieren sondern durch die Freigabe lesen); **147** Weblate (die eigentliche
Frage ist „Katalog aus index.html herauslösen?", also ein Build-Schritt gegen
Anm. 4 — abgelehnt, mit der Reihenfolge für später).

**Drei Zusicherungen waren in dieser Runde aus dem falschen Grund grün**
(Anm. 108): `every` auf einer leeren Liste, eine Negativbedingung über eine
leere Anfrageliste, und `hasattr` auf einem Dict. Alle drei fielen erst auf,
als der Wächter gegen den kaputten Stand gefahren wurde — **die Regel trägt,
aber nur, wenn man sie wirklich anwendet.**

Umgesetzt bis **v0.39.0** (2026-07-23). **Gruppe A ist komplett** (A1–A48),
Gruppe B bis **F19**; **P5.1, F1 und P2.1 (alle drei Stufen) sind fertig**. Offen
ist damit nur noch: **0.40 (sammelt auf `main`)**, **Demo-Modus (0.41)** und
**R1/R2** (1.0, drei Etappen auf `main`). **F20 (Grundort) und F21
(Lückenprüfung) sind seit 2026-08-03 gebaut** und liegen auf `main` —
Gruppe B damit vollständig bis F21.

**Arbeitsweise ab 0.40 (vom User festgelegt, 2026-07-23): alles auf `main`,
kein Versionssprung, bis der User den Demo-Modus ansagt.** Was sich bis dahin
angesammelt hat, wird 0.40.0 — voraussichtlich überwiegend Fixes. `version.py`
bleibt so lange auf **0.39.0**, neue CHANGELOG-Punkte gehen unter
`[Unreleased]`; die Anzeige sagt dann `0.39.0-dev`, und genau dafür gibt es die
Kennung (Anm. 86). **Nicht bei jedem Paket die Version hochziehen** — das war
zweimal die Ursache für den Anm.-91-Defekt: ein Bump als Startschuss statt als
Schlussstrich.
**Tageswetter vereinheitlicht (Anmerkung 119, auf `main` ohne Versionssprung).**
Aus der Frage „ein Tag hat zwei Orte — wo steht dann das Wetter?" fielen VIER
Antworten auf eine Frage: Zeitstrahl = Wetter des A39-Vertreters `min(id)`
(UUIDs, also ein zufälliger von fünf Besuchen), Client-Sammelkarte = gar keins
(sie ruft `eventChips` nicht auf), Erfolge = `min` je Tag, Statistik-Bilanz =
**erstes Ereignis des Tages**. Anm. 106 in Reinform. Jetzt EINE Regel in
`services/weather_day.py` (Schicht 4): Zahlen = Minimum des Tages (der
VORSICHTIGE Wert), Texte nur bei Einigkeit des Tages, dazu `regions` = Zahl der
berührten 0,1°-Zellen NEBEN dem Wert (A40: was nicht alles zeigen kann, muss es
sagen). Endpunkt `/api/days/weather`, Tageskopf im Tages-Zoom.
**Zwei Fragen bleiben bewusst verschieden beantwortet:** OB ein Tag zählt
(Erfolgs-Schwelle) fragt weiter „irgendein Eintrag erreicht es" — sonst würden
verdiente Abzeichen aberkannt (`test_f19_badges.py` seit 0.35) —, WAS er
beisteuert, ist immer der vorsichtige Wert. Als Vorfilter geschrieben macht die
Schwelle beides zugleich (11 h + 3 h mit `min: 10` ergibt 11, nicht 3): deshalb
`having`. Dazu ein Prozess-Cache in `fetch_weather` je (Tag, Koordinate auf 2
Stellen ≈ 1,1 km) — bewusst NICHT gröber (0,1° läge AUF der Auflösung der
Quelle) und **Fehlschläge werden nicht gemerkt** (Gegenrichtung zur
Endlos-Abruf-Falle: ein Prozess-Cache, keine dauerhafte Marke).
**Feedback-Runde: die App tat es und sagte es nicht (Anmerkung 120, auf `main`
ohne Versionssprung).** Sieben gemeldete Punkte, sechs davon derselbe Defekt.
**(a)** „Nachsehen" schrieb sein Ergebnis ans ENDE der Beschreibungsspalte
daneben — auf einem breiten Bildschirm die andere Hälfte, hinter zehn Zeilen
Erklärung; jetzt volle Zeile UNTER dem Knopf (`.action-row.has-result`), dazu
Ladezustand und Toast. **A40 andersherum: eine Ansicht, die etwas zeigen KANN,
muss es dorthin stellen, wo hingeschaut wird.** **(b)** Jeder Job-Start sprang
in den Jobs-Reiter, und das WAR die Rückmeldung — bei zwanzig Jahren
zwanzigmal weg vom Knopf. Jetzt ein Live-Streifen oben in „Meine Daten"
(`#data-jobs`, `startServerJob(..., stay=true)`); **der zuletzt beendete Lauf
bleibt mit seinem Ergebnis stehen**, sonst ist der Satz, für den es den Lauf
gibt, der einzige, den niemand sieht. **(c)** Laufende Jobs rutschten unter
die abgeschlossenen und fielen aus den zwölf Zeilen: **Abgeschlossenes ist
eine Chronik, Laufendes ein Zustand — nur die Chronik wird beschnitten**
(`list_jobs` liefert Aktive vollständig und zuerst). **(d)** `photo_points`
stand als nackter Schlüssel da; das Backend kannte sein Label längst — **ein
Fallback, der wie eine Anzeige aussieht, versteckt die Lücke**, Wächter
`check-job-labels.js` vergleicht `JOB_TYPES` gegen deutsche Tabelle UND
englischen Katalog, in beide Richtungen. **(e) „Alle Jahre" für beide
Immich-Läufe:** die Jahresaufteilung (Anm. 107) war für eine ANFRAGE richtig
(25-s-Budget der Vorschau, abgeleitet aus der Geduld umgekehrter Vertreter),
nie für einen Hintergrund-Job. Die Vorschau geht die Jahre EINZELN durch —
eine Sammelanfrage antwortete mit einem Ausschnitt, und ein Ausschnitt hebt
den Riegel nicht auf („ein Zwanzigstel sehen, alles anlegen") —, und der Lauf
bekommt `imsPreviewedYears`, die Jahre der VORSCHAU, nicht die der Auswahl
(Anm. 106: zwei Angaben über dieselbe Sache laufen auseinander). **(f)**
Fotopunkte wachsen mit dem Zoom, kräftigerer Rand; die REIHENFOLGE bleibt
(Fotos unter den Pins — was oben liegt, sagt, was zählt). **(g) Die siebte
Frage brauchte eine Antwort, keine Änderung:** ein aufgelöster Ortsname
verschiebt die Koordinate NICHT — `reverse_geocode` liefert keine, und im
ganzen Backend gibt es genau eine Zuweisung an `Location.lat` (in einem
ungespeicherten Vorschlag). **Nebenbefund:** das Leaflet-Doppel gab für jede
Eigenschaft sich selbst zurück, also auch für `getZoom()` → jeder Vergleich
`z >= 14` stürzte ab. In 20 Wächter-Dateien dieselbe Kopie. Neu:
`test_multi_year_jobs.py`, `check-job-labels.js`.
**Zwei Selbstfunde:** `round(x, 1)` gibt es auf PostgreSQL nur für `numeric`,
nicht für `double precision` (`sqlutil.weather_cell`, geprüft in
`test_a37_postgres_dialect.py`); und die erste Spannen-Grenze des Endpunkts
(4000 Tage) hätte in einem dünnen Bestand jede Seite von 1994 bis heute
getroffen und das Tageswetter still weggelassen — die Antwort ist ohnehin durch
die 300 Ereignisse der Seite begrenzt. **Eine Grenze aus dem falschen Grund
wird zur stillen Auslassung.** Wächter `tools/check-day-weather.js` +
`tests/test_weather_day.py`, beide gegen fünf injizierte Defekte gefahren
(Anm. 108) — eine Zusicherung war dabei zuerst aus dem falschen Grund grün.

Hinter 1.0 bleiben
nur noch neue Import-Konnektoren (P2.8 OwnTracks, P2.9 Automatisierung,
P2.10 Trakt, P2.11 Dawarich/GPX, P4.1 Health, P4.2 PSN) plus **P5.2**
(Whisper — einzige Ausnahme, schwere neue Laufzeit-Abhängigkeit).

**Releaseplan bis 1.0 steht in KONZEPT Kap. 14.3.** Fertig: 0.21 A28+F14 ·
0.22 F13 · 0.23 F11+F12 · 0.24 F15 (Fotos) · 0.25 P2.1 (Immich, Stufe 1) ·
0.26 A29 (ZIP-Backup) · 0.27 Fixes (A31/A32/A30) · 0.28 F16+A33+A34 ·
0.29 A35 (lokale Konten) · 0.30 P3.1 · 0.31 A36+F17 (schlanke Liste, Alter) ·
0.32 A37 (serverseitiges Zeitfenster) · 0.33 A38+A40 (Mobil-Layout,
Kartenschalter) + dev-Kennung · 0.34 A39+F18+A41 (Städte, Tages-Fotos) · 0.35 F19+A42 (Sammlung) ·
0.36 P5.1+F1-Rest (Erfassen) · 0.37 P2.1 Stufe 2 (Immich als Quelle) ·
0.38 Feedback-Runde (Anm. 110) · 0.39 A45–A48 + P2.1 Stufe 3 (Anm. 116).
Offen: **0.40 (was sich ansammelt)** · **0.41 Demo-Modus** ·
**1.0 = Veröffentlichung**. Kein Termindruck (Anmerkung 58).
Dort nachsehen statt Reihenfolge raten.

**Was hinter 1.0 wartet, entscheidet die ART (Anmerkung 101, 2026-07-22):**
neue Import-Konnektoren warten, alles andere nicht — vorher galt „nicht
dringend", was P5.1, F1-Rest und P2.1 Stufe 2 grundlos nach hinten schob.
Begründung: 1.0 ist per Ausschluss definiert als „vollständiges Werkzeug zum
Erfassen und Erkunden von Hand", und ein Konnektor erweitert die *Zufuhr*,
nicht das Konzept. Ein Paket, das Erfassen oder Erkunden verbessert, ist
deshalb gar kein 1.x-Kandidat. Preis: drei Releases mehr vor dem Demo-Modus,
bewusst in Kauf genommen; Rückzugsreihenfolge steht in 14.3.

**Achtung Tags (Anmerkung 91):** `v0.32.0` wurde gesetzt, als A38 noch
fehlte — deshalb ist A38 zu 0.33.0 geworden und der Rest um eins gerutscht.
Ein Tag ist das einzige Unveränderliche hier: **zuletzt setzen, nicht als
Startschuss für das letzte Paket.** Zum Testen reicht Push auf `main`.
**Zweites Auftreten, beim Nachtaggen am 2026-07-23 gefunden:** der Bump auf
0.38.0 (`567c275`) lag **elf Commits vor** dem Ende dessen, was das CHANGELOG
unter 0.38.0 beschreibt (Anm. 111–113 kamen danach). Nicht der Tag war früh,
sondern der Bump — `v0.38.0` gehört deshalb auf `d753d0d`, den ersten Commit,
bei dem die Sektion vollständig und `[Unreleased]` leer ist. **Der Prüfsatz
für jeden Tag lautet: an diesem Commit muss `[Unreleased]` LEER sein.** Ab 0.40
erübrigt sich die Frage, weil der Bump erst beim Release gesetzt wird.

**Nur noch drei Versionen bis 1.0 (Anmerkung 89).** Härtung,
Projektoberfläche und Freeze-Pass sind KEINE eigenen Versionen mehr,
sondern drei Etappen von 1.0.0 — sie laufen auf `main` (`:main`-Image)
und bekommen einen einzigen Tag. Grund: bis zur Veröffentlichung gibt es
genau einen Betreiber (den User), und der merkt ein gepinntes Base-Image
nicht. Der Plan war älter als Anmerkung 86 und wurde nachgezogen.
**Regel für künftige Einschübe:** eine eigene Version nur bei
Schema-Folge UND beobachteter Beschwerde — sonst reicht `main`.

**A38 fertig (v0.33.0, Anmerkung 82).** Untere Leiste trägt vier Ziele +
„Mehr"-Sheet (statt neun à 40 px); das Sheet wird aus der Sidebar GEKLONT,
also nie zweitpflegen. Bearbeiten-Dialog = die Detailansicht (Klick auf
Karte öffnet ihn) und jetzt Bottom Sheet mit `dvh` + klebender Knopfleiste.
**Zwei Regeln, die `tools/check-a38-mobile.js` erzwingt:** kein Inline
`min-width` (Inline schlägt Stylesheet → Media Query kommt nicht dran) und
kein `max-height` in `vh` (rechnet ohne Adressleiste). Beide Defekte saßen
an mehr Stellen, als die Audit-Liste kannte.

**A40 fertig (v0.33.0, Anmerkung 92).** Kartenschalter: „Zurückgelegte Wege"
(gemessen) vs. „Reihenfolge verbinden" (gezeichnet) — hießen vorher beide
„Route"; „Punkte zusammenfassen" ist EIN Schalter für Bündeln (ab Monat, je
Ort) und Clustern (Tag/Woche, nach Nähe), Schwelle jetzt in den Einstellungen.
**Design-Regel daraus (gilt allgemein):** Ein Bedienelement, das gerade nichts
bewirken kann, muss das ZEIGEN — `.filter-chip.inert` (durchgestrichen +
Begründung im Titel), bewusst anders als `.off` (vom Nutzer ausgeschaltet).
Der wiederkehrende Defekt in diesem Projekt ist nicht Kaputtheit, sondern
**Stille** (siehe auch A37-Kacheln, Anm. 79 Immich-Verknüpfung).

**A39+F18 fertig (v0.34.0).** `Location.city` als echtes Feld (Rückfüllung im
A28-Lauf; **Leerstring = „nachgesehen, keine Stadt", NULL = „nie nachgesehen"** —
ohne die Unterscheidung fragt der Lauf stadtlose Orte ewig neu ab, vgl. F12
`weather_rev`). Zeitstrahl verdichtet importierte Besuche je (Tag, Stadt);
**verdichtet wird VOR dem Blättern**, sonst zerschneidet die Seitengrenze eine
Gruppe und beide Hälften zeigen zu kleine Zahlen. Sammelkarte ist kein
Ereignis → Klick klappt auf statt zu bearbeiten. `MediaRef.event_id` nullable:
Fotos hängen wahlweise am Tag (`captured_at`). **Erste Migration, die eine
Spalte ÄNDERT** — SQLite braucht Tabellen-Neubau (`_relax_not_null` in
migrate.py), und beim Kopieren muss jede NOT-NULL-Spalte einen Ersatzwert
bekommen: Bestandszeilen haben dort NULL, weil die Spalte per ADD COLUMN kam.
**Wer Medien sucht, sucht sie über `user_id`, nicht über Events** — sonst
fehlen Tages-Fotos beim Löschen, Aufräumen und im Export.

**A42+F19 fertig (v0.35.0, Anmerkungen 102–104).** **A42:** Städte haben jetzt
eine Seite wie jeder andere Sammlungstyp — `/api/cities/detail` (Orte,
Ereignis-VORSCHAU mit Gesamtzahl, A37) und `/api/cities/describe` mit
`city_info` als Cache. Städte bleiben bewusst **keine `Entity`** (Anm. 95),
deshalb eigene Endpunkte statt `openEntityDetail`. Drei Regeln daraus:
**(a)** Das Land geht in die Wikidata-Suche, sonst ist „Frankfurt" eine
Begriffsklärung; **(b)** ein Fehlversuch wird GESPEICHERT (Zeile ohne
`description` = „nachgesehen, kein Artikel", Neuversuch nach 30 Tagen) — dieselbe
Endlos-Abruf-Falle wie F12 `weather_rev` und A39-Leerstring, jetzt zum dritten
Mal; **(c)** `city_info` hat bewusst KEINE `user_id` (Wikipedia gehört
niemandem), der Zugriffsschutz sitzt an den eigenen Orten.
`services/wikipedia.py` ist nicht mehr fest deutsch, `Entity.attributes` trägt
`desc_lang`. **F19:** Über Platin zählt eine erzeugte Marke weiter (1 · 2,5 · 5
je Zehnerpotenz) — **aber nur bei unbegrenzten Metriken**: es gibt sieben
Kontinente, „nächste Marke: 10" wäre ein Rechenfehler mit Anspruch (Anm. 104).
**Der eigentliche Grund für vorverdiente Abzeichen war ein Zählfehler, keine
Schwelle** (Anm. 103): die Wettermetriken zählten Einträge, wo überall „Tage"
stand — A31/Anm. 64 hatte in dieser Datei überlebt. Frage bei jeder
Invarianten-Reparatur: *wo gilt derselbe Satz noch?*

**Immich-Durchsicht (Anmerkung 111, in 0.38.0) — zwei Nähte, zwei Defekte,
404 Tests haben keinen bemerkt.** **(a)** `asset_time` las `fileCreatedAt`
(laut Spec **UTC**) und schnitt die Zone ab statt sie anzuwenden → ein Foto vom
13.5. 01:30 Berlin landete auf dem **12.** Nicht eine Stunde daneben, ein TAG —
und am Tag hängen der F18-Behälter und der Platz eines Vorschlags. Immich
liefert `localDateTime` genau dafür („timezone-agnostic … grouping by local
days"). **Regel: bietet eine API zwei Zeitstempel, beantwortet einer eine
andere Frage — und „Zone abschneiden" ist nie „in Ortszeit umrechnen".**
**(b)** Stufe 1 kannte nur `google_timeline` als maschinelle Quelle und hängte
den Fotovorschlägen aus Stufe 2 deren eigene Bilder an — gegen Anm. 107 Fall 6.
**Das ist Anmerkung 106 in genau dem Code, der sie zitiert:** dieselbe Regel
stand zweimal wörtlich da, und die zweite maschinelle Quelle brachte sie zum
Auseinanderlaufen. Jetzt EINE Liste `MACHINE_SOURCES`, die `candidates()` und
`day_candidates()` beide lesen. **Gewohnheit daraus: bekommt ein Paket eine
zweite Stufe, die ältere Hälfte mit den Regeln der neueren lesen** — beide
Befunde saßen dort, wo die Annahme des einen Teils auf die des anderen trifft,
und genau dort greift kein Test von selbst.

**0.39.0 fertig (Anmerkung 116) — A45–A48 + P2.1 Stufe 3.** Drei Beobachtungen
aus der Nutzung, und jede war eine Frage ans MODELL, nicht an die Anzeige.
**A45 (Fotopunkte):** Der geplante Weg — Spalten an `MediaRef` — hätte nicht
getragen, denn `MediaRef` ist auf **zwölf Bilder je Tag** gedeckelt
(`immich_link.MAX_PER_EVENT`), und das ist richtig: es beantwortet „welche
Bilder stehen neben diesem Eintrag?". Die Karte hätte zwölf Punkte je Tag
gezeigt und ausgesehen, als ginge sie. **Zwei Fragen mit zwei Deckelungen
teilen sich keine Tabelle** — in einer Zeile wären es zwei Bedeutungen in
derselben Spalte (Anm. 106 in seiner teuersten Form). Deshalb `photo_points`,
Schicht 4, verwerfbar. **Ein Foto wird trotzdem kein Ereignis** (Anm. 87): die
Punkte sind eine ausblendbare EBENE, im Zeitstrahl je (Tag, Ort) verdichtet.
**A46 (Besuchstage):** eine Zeile Ursache, viel Folge — `date_end` roh aus dem
Google-Besuch übernommen, also war jede Nacht im eigenen Bett ein zweitägiges
Ereignis. Mehrtägig entsteht ab jetzt nur noch von Hand. Der Aufräum-Lauf für
den Bestand fasst BESTÄTIGTES an; daraus folgt jede seiner Grenzen (nur auf
Knopfdruck, nie im Nachtplan, nur `google_timeline`, Vorschau nennt die Zeilen
DANACH). Teuer war die Idempotenz: Bestandszeilen tragen den nackten Hash, und
wer nur die neuen Teil-Schlüssel kennt, legt beim Re-Import alles ein zweites
Mal DANEBEN an. **A47 (Granularität):** Land → Stadt → Ortsteil → Punkt,
serverseitig verdichtet (A39/A37: verdichtet wird VOR dem Blättern). Ortsteil
aus `Location.address` über eine Fallback-Kette — Nominatim nennt die Ebene je
nach Land `suburb`, `city_district`, `neighbourhood` oder `quarter`.
**A48 (Vektorkarte):** Immichs Stil ist `"type": "vector"` (Spezifikation 8) und
gar kein API-Endpunkt, sondern eine Admin-Einstellung — Leaflet kann ihn nicht
zeichnen, es braucht MapLibre plus Brücke. **P2.1 Stufe 3:** Alben nur noch auf
Nachfrage; ein Album war EIN mehrtägiger Vorschlag mit einem Kartenpunkt und der
Zwilling der handerfassten Reise.

**Drei Fallen, die 0.39 ein weiteres Mal gestellt hat:**
**(a) Die Endlos-Abruf-Falle, siebte und achte Auflage** (nach F12
`weather_rev`, A39-Leerstring, A42 „kein Artikel", P2.1-Grabstein, Anm. 114
`_name_defect`): die durchsuchten Foto-Jahre müssen gemerkt werden, und
`Location.address` braucht eine Marke im FEHLSCHLAG. Die zweite ist die
schwierigere, weil die Marke an den **frühen Ausstiegen** sitzt — den Pfaden,
die man nicht als schreibend denkt. **Und sie hat zugeschlagen:** nachdem der
Adress-Nachzug am Ortsnamen-Lauf hing, lief die Testsuite endlos. Sichtbar
gemacht hat es ein Test-Doppel, das das alte Verhalten treu nachbaute — **ein
Doppel, das ein Feld auslässt, ist keine Vereinfachung, sondern eine andere
Funktion.** **(b) JSON-Spalten speichern Python-`None` als JSON-`null`, nicht
als SQL-NULL.** `address IS NULL` traf die Zeilen nicht; ohne
`JSON(none_as_null=True)` hätte der Rückfüll-Lauf sie für immer übersehen und
der Index behauptet, es sei nichts offen. **(c) `= Query(False)` als Default
kommt beim Direktaufruf als Query-OBJEKT an und ist damit wahr** — der
Alben-Schalter stand überall auf AN, wo niemand ihn gesetzt hatte. Die Falle
stand seit A37 in `events.py` aufgeschrieben (`Annotated` statt Query-Default)
und ist hier zum zweiten Mal aufgetreten.

**Wächter gegen den kaputten Stand — und zwei, die im ersten Anlauf wertlos
waren.** Anm. 108 verlangt, jede Prüfung einmal gegen den Defekt zu fahren, den
sie festnageln soll. Dabei fiel auf: eine prüfte auf die Ziffer `4`, die auch im
Datum `2026-07-04` steckt; eine andere injizierte den Defekt in den DEUTSCHEN
Quelltext, während die Seite unter jsdom **englisch** startet — der Defekt
erreichte die Zusicherung nie. Neu: `check-a46-visit-split.js`,
`check-photo-layer.js`, `check-tl-granularity.js`, `check-vector-basemap.js`.
Dazu ein HTTP-Doppel für Immich (`tools/immich_double.py` +
`tools/smoke_a45.py`, Anm. 109): 1200 Assets in den echten DTOs prüfen
Blättern, Besitzfilter, den Mitternachts-Fall aus Anm. 111 und die
Ortsteil-Ableitung in einem Lauf — nichts davon erreichen Unit-Tests, weil sie
den Client komplett ersetzen. **Aus dem Repo-Wurzelverzeichnis starten:**
`<python> tools/immich_double.py &` und `<python> tools/smoke_a45.py`.

**Feedback-Runde nach 0.38.0 (Anmerkung 114) — sechs Punkte, drei davon ein
zweites Mal derselbe Defekt.** Liegt auf `main`, **ohne Versionssprung**
(Anm. 89: eigene Version nur bei Schema-Folge UND Beschwerde — hier gibt es
kein neues Feld). **(a)** Karte auf dem Handy unsichtbar: Anmerkung 34 eine
Ebene höher — der Rahmen für den Kartenhinweis (Anm. 110) trug `flex: 1`,
und in Spaltenrichtung heißt das `flex-basis: 0` in der HÖHE. **Ein Wächter,
der nur seinen Auslöser kennt, ist einer für die Vergangenheit** —
`check-a38-mobile.js` prüft jetzt die ganze Kette zwischen `.map-layout` und
`#map`. **(b)** Fotoleisten standen am ENDE ihrer Gruppe, also hinter
„x weitere anzeigen" — an genau den Tagen, an denen fotografiert wurde. Der
Kommentar darüber sagte „oben"; der Code hängte an. **(c)** „Zuhause"/
„Arbeit" sind keine Ortsnamen (A19 hatte das für „Gesuchte Adresse" schon
entschieden): der `semanticType` geht jetzt in `Location.type` — **und ein
Typ, der an einem Anzeigetext hängt, verschwindet mit ihm**. **(d)**
Endlos-Abruf-Falle, fünfte Auflage: `_name_defect` zählte Kommas, aber
`short_name` stellt den POI-Eigennamen VORAN — jeder benannte Ort galt ewig
als „zu lang". Mit `Location.address` ist es eine Rechnung statt einer
Schätzung. **(e)** Die Bausteine-Auswahl zeigte vier leere Kästchen und
meinte alle vier (`sanitize_parts`): **eine Voreinstellung muss an beiden
Enden dieselbe sein**. **(f)** ~200 im JS gebaute Texte waren nie
übersetzbar; `t()` fällt still auf Deutsch zurück, deshalb drei Jahre
unbemerkt. **Siebte Quelle, direkt danach gemeldet: die Modul-Dateien** —
Abzeichen und Modul-Kennzahlen (`backend/modules/*.yaml`) kommen über die API
in die Oberfläche, sind also Text aus einer anderen Richtung; jeder frühere
Durchgang über `index.html` musste sie verfehlen. Übersetzt wird trotzdem im
Katalog (Präfix `mod.`), **das YAML bleibt deutsch: es ist die Quelle, nicht
die Anzeige.** Neu: `tools/check-i18n-coverage.js` (jeder Schlüssel im Katalog,
kein verwaister Eintrag, kein deutscher Text IM Katalog — und er **liest die
Modul-YAMLs**, denn wer eine Modul-Datei schreibt, denkt nicht an den
englischen Katalog) und `check-place-format.js`. Zahlen/Daten folgen jetzt `LOC()` statt hart
`'de-DE'`. Dazu die sechs F12-Wetterrekorde (UV, Böe, gefühlt, Tageslicht) —
die Werte kommen seit 0.22 mit; **eine Null ist beim Regen kein Rekord, beim
Tageslicht schon** (Polarnacht = kürzester Tag, vgl. Anm. 104).

**Einstieg-Reihenfolge (Anmerkung 115, nach 0.38.0, auf `main` ohne
Versionssprung).** README hat jetzt einen Guide „Getting started — a sensible
order", und „Meine Daten" steht in derselben, nummerierten Reihenfolge:
**Module → Google-Timeline → Ortsnamen → Immich (verbinden → vorschlagen →
bestätigen → Fotos) → Tages-Einträge → Wetter → Backup.** Zwei Gründe, die
keine Vorlieben sind: **Ortsnamen früh**, weil das der einzige von außen
gedrosselte Lauf ist (Nominatim) und weil bis dahin alles „Ort (53.49, 10.00)"
heißt; **Wetter zuletzt**, weil es jede Zeile genau einmal fragt (F12-Marker) —
ein Lauf, der einmal fragt, gehört ans Ende, nicht an den Anfang. Die Abschnitte
standen vorher in ihrer Bauzeitpunkt-Reihenfolge (Backup oben, Module unten):
**das ist ein Änderungsprotokoll, keine Anleitung.**
**„Wetter ergänzen" ist aus dem System-Reiter nach „Meine Daten" gewandert** —
der Reiter ist `admin-only`, der Endpunkt war es NIE: eine reine
Oberflächensperre über einer instanzweiten Aktion. Jetzt filtert
`enrich_weather(user_id=…)` auf das startende Konto; `recompute`/`embeddings`
bleiben in System (die rechnen wirklich über alles). **Die Sperre bleibt
global**: sie schützt nicht die Daten, sondern das Kontingent bei
Open-Meteo/Nominatim/Immich, und das hängt an der Instanz.
**Der stille Befund dabei: der Nachtplan fragte „lief das heute schon?" ohne
„bei wem?"** — ab dem zweiten Konto nimmt der erste Nutzer allen anderen den
Termin, Nacht für Nacht, ohne Fehlermeldung. Galt schon für `resolve_names`,
`immich`, `immich_source`. Jetzt EINE Liste `USER_SCOPED_TYPES` (dieselbe Form
wie `MACHINE_SOURCES`, Anm. 111). Tests: `backend/tests/test_job_scope.py`,
gegengeprüft am kaputten Stand (3 von 8 fallen dort um).

**Feedback-Runde 0.38.0 (Anmerkung 110) — zwei teure Befunde, beide Stille.**
**(a)** Der Bild-Endpunkt hielt seine DB-Verbindung, während er bei Immich auf
das Foto wartete (15 s Zeitlimit). Hinter HTTP/2 feuert der Browser dutzende
Bildabrufe parallel → Pool leer → **jede** Anfrage scheitert, auch die des
Zeitstrahls, der deshalb „endlos lädt". **Regel: ein Proxy-Endpunkt ist kein
Datenbank-Endpunkt** — Verbindung VOR dem Netzaufruf zurückgeben, danach nur
noch Werte anfassen (jeder ORM-Zugriff nach `close()` holt sie sich wieder).
**(b)** Die Karte zeichnete ohne Bündelung `all.slice(0, 300)` — die ersten
300 CHRONOLOGISCH — und schwieg darüber; der Hinweis stand nur in der Liste
daneben. **A40 einen Schritt weiter: auch eine ANSICHT, die nicht alles zeigen
kann, muss das sagen — und zwar dort, wo hingeschaut wird.**
Dazu: `Location.address` bewahrt jetzt die Roh-Bausteine (Umformatieren ohne
Netz statt 1,2 s je Ort), eigene Kachel für unscharfe Daten, Schalter für
importierte Besuche in „An diesem Tag" (der Parameter existierte seit F16, die
Oberfläche hat ihn nie gesetzt — **ein Standard, den man nicht ändern kann, ist
keiner**), Fotoleisten folgen der Zoomstufe (Woche gebündelt, ab Monat 12 von N
und die Beschriftung sagt es). Wächter: `check-map-nothing-hidden.js`,
`check-photo-strips.js`.
**Zwei Entscheidungen festgehalten:** Französisch-Guayana bleibt Frankreich/
Europa (politisch korrekt, Preis bewusst); und die Wikipedia-Frage —
**ein ausgehender Abruf muss einer GESPEICHERTEN eigenen Tatsache dienen**
(Anm. 100), deshalb Stadtbeschreibung ja, Geburtstag „des Tages" nein.

**P2.1 Stufe 2 fertig (v0.37.0, Anmerkung 109).** Immich schlägt jetzt
Ereignisse vor: Fototage (Tag + Ort) und Alben, beide `unconfirmed`, jahresweise
mit **Pflicht-Vorschau**. `services/immich_source.py`, Endpunkte
`/api/immich/years|preview`, Job `immich_source`. **Kein Schema.**
**Identität ist der PLATZ** (`immich:day:<datum>:<ort>`, `immich:album:<id>`),
nie ein Hash über die Assets — sonst wird ein nachgeladenes Foto zum zweiten
Vorschlag. **Grabstein = das Fragment**: `discard_event` löscht das Ereignis,
das Fragment bleibt und trägt den Platz → ein abgelehnter Vorschlag kommt nie
wieder (vierte Auflage der Endlos-Abruf-Falle nach F12/A39/A42).
**Die OpenAPI-Spezifikation lesen, nicht die Attrappe fragen** — zehn Minuten,
drei Entscheidungen gekippt: Alben filtert der Server (`?isOwned=`), **Assets
NICHT** (`MetadataSearchDto` hat kein Besitzfeld → auf der Antwort über
`ownerId` + `/users/me`); `exifInfo` liefert **city/state/country** (kein
Nominatim, und stabiler als ein Koordinatenraster, dessen Zellenrand mitten
durch eine Stadt läuft); `visibility` hält Archiviertes und **Gesperrtes**
draußen. Zweites Mal, dass die Spezifikation eine Annahme dieses Konnektors
umbringt (Stufe 1: `takenAfter` braucht eine Zeitzone).
**Der Smoke-Lauf gegen ein HTTP-Doppel fand, was Unit-Tests nicht konnten:**
die Jahresauswahl kam aus dem EIGENEN Bestand und bot damit ausgerechnet die
Jahre nicht an, für die es das Paket gibt (vor dem Smartphone gibt es keine
Besuche) → jetzt `/timeline/buckets` mit Fotozahl je Jahr.
Wächter: `tools/check-p21-preview.js` (Vorschau-Pflicht, Jahreswechsel
entwertet sie).
**Selbstkontrolle 0.37.0 — fünf Befunde, vier davon an derselben Grenze:** dort,
wo die Test-Attrappe aufhört und der echte Client anfängt. Silvester-Album aufs
Laufjahr beschnitten (das Jahr entscheidet OB, nicht WAS); Scan ohne Herzschlag
→ Job nach 180 s als verwaist eingesammelt, nachdem er alles getan hat; dann
riss das weite Album-Fenster `_stamp` auf (`astimezone()` wirft unter Windows
`OSError` vor 1970 — **das fand nur der Smoke-Lauf**, Unit-Tests ersetzen
`search_assets_paged` komplett); zwei Springfields wären ein Ort geworden
(Anm. 105: Schlüssel ist `(Stadt, Land)` — neu vergeben heißt gleich richtig);
20.000-Grenze schnitt still. **Regel: bei jedem Konnektor zusätzlich ein
HTTP-Doppel fahren, das sich an die echten DTOs hält** — zwanzig Zeilen, drei
Befunde, einer davon für Unit-Tests prinzipiell unerreichbar.

**P5.1+F1 fertig (v0.36.0, Anmerkung 108).** Das Loch beim Offline-Erfassen war
nicht die fehlende Warteschlange, sondern die **Eingangstür**: `init()` hatte
EINEN Zweig für zwei Fehler — „nicht angemeldet" und „Anfrage kam nie an" —,
also stand man ohne Netz vor einer Anmeldemaske, die ohne Netz nicht bedienbar
ist. Unterscheidungsmerkmal ist jetzt `err.status` (vorhanden = der Server hat
GEANTWORTET), und dieselbe Unterscheidung braucht die Warteschlange dreimal:
**puffern** nur ohne Status (ein gepuffertes 422 wird ewig wiederholt),
**abbrechen** bei Netzverlust, **nicht abstempeln** bei 401 (nach dem Anmelden
geht derselbe Eintrag durch — die einzige unumkehrbare Fehlentscheidung in
einem Mechanismus, dessen Zweck Umkehrbarkeit ist). Wiederholen heißt
Doppelte in Kauf nehmen: die `client_id` liegt bewusst im Arbeitsspeicher
(`_seen` in `routers/ingest.py`), **kein Schema** — ein doppelter Vorschlag ist
sichtbar und verwerfbar, eine verlorene Erfassung endgültig. Ohne `client_id`
wird NICHT entdoppelt (zwei gleiche Sätze von Hand sind zwei Erfassungen).
**Eine Warteschlange ist so viel wert wie das, was sie zeigt** — Text, Zähler,
Grund; die manuelle Eingabe bekommt gar keine (sie schreibt Bestätigtes) und
wird stattdessen nach der A40-Regel `inert` gestellt.
**F1 war eine Grenzfrage, keine Textfrage:** der Vorschlag steht NEBEN dem
Tagebuchfeld, „Übernehmen" hängt an (überschreibt nie), der Endpunkt ist ein
GET und speichert nichts — so gilt die Zusage aus 0.15.0 unverändert.
Unbestätigte fließen nicht ein, werden aber GEZÄHLT und genannt; der
Tagebuch-Eintrag ist aus seinem eigenen Material ausgeschlossen, sonst frisst
sich der Text selbst. **Nur `exact`/`day` fließen in einen Tagestext** —
„Sommer 2002" steht mit `date_start=2002-06-01` da und stünde sonst im
Vorschlag für den 1. Juni (dieselbe Regel wie F14 `_ON_THIS_DAY_PRECISIONS`).
Wächter: `tools/check-p51-outbox.js` (stellt `onLine`, Netzfehler und vollen
Speicher HER) und `tools/check-f1-journal-ai.js`.

**Selbstkontrolle 0.36.0 — vier Befunde, drei davon dieselbe Frage.** „Wo gilt
derselbe Satz noch?" (Anm. 103) fand: unscharfe Daten im Tagestext (F14-Regel),
die falsche Begründung, wenn die KI nichts liefert (nicht „nichts erfasst"),
und `_seen` ohne Schloss (KeyError → 500 → die Warteschlange stempelt die
Erfassung als abgelehnt ab). Der vierte kam vom Lesen eines Kommentars GEGEN
seinen Code: `await flushOutbox()` wartete nicht. **Und zwei der Tests dazu
waren im ersten Anlauf wertlos** — der Thread-Test bestand auch ohne Schloss
(das Fenster ist Bytecodes breit, „acht Threads im Kreis" trifft es nie), der
Sprach-Test prüfte die Rückrichtung (jsdom meldet `en-US`, die App startet
englisch). **Neue Regel: jede Prüfung, die einen Fehler festnageln soll, einmal
gegen den kaputten Stand laufen lassen** — `git show HEAD:datei > /tmp/alt` und
den Wächter darauf ansetzen.

**Immich hängt Tages-Fotos an den TAG (Anmerkung 106, in 0.35.0).** Vorher ging
ein Foto an den ersten Besuch, dessen ±6-h-Fenster es traf — bei `exact`-Präzision
der importierten Besuche und 25 km Ortstoleranz entschied faktisch die
Reihenfolge einer Abfrage **ohne ORDER BY**. Und die A39-Sammelkarte zeigt
`min(id)` (UUIDs!), also einen ANDEREN zufälligen Besuch: gemessen vier Fotos
verknüpft, null sichtbar. Jetzt: `targets()` liefert erst Ereignisse (engeres
Fenster, selbst erfasst = Aussage über den Tag), dann Tage aus importierten
Besuchen → `MediaRef` ohne `event_id` (F18-Behälter). **Der Tag filtert bewusst
NICHT nach Ort** — ein Zeit-Behälter mit Ortsfilter wäre in sich widersprüchlich.
Bestandsverknüpfungen an Besuchen werden zu Lauf-Beginn gelöst, sonst gälten sie
über `seen` als vergeben. **Regel:** „wohin gehört das?" hatte drei Antworten in
zwei Dateien (`candidates`, Job-Schleife, `link_batch`) — eine davon hatte die
Entduplizierung verloren. Eine Regel an mehreren Orten widerspricht sich, und
zwar still.

**Wächter prüfen Zustände, die es geben muss.** `check-a41-cities.js` prüfte ein
Jahr lang, dass der Städte-Reiter im Markup steht — im Betrieb ersetzt
`applyModules()` die Leiste Sekundenbruchteile nach dem Start, der Reiter war
also nie zu sehen und die Prüfung trotzdem grün. Wer eine UI-Eigenschaft
absichert, muss den Zustand HERSTELLEN (`w.eval('MODULES = …; applyModules()')`),
nicht den Auslieferungszustand lesen. `npm run check` in `tools/` fährt jetzt
alle Wächter, auch die vier, die man vorher von Hand starten musste.

**Verworfen: ein automatisches Tages-Objekt je Tag** (Anmerkung 87) — das hieße
`parent_event_id` auf Bestätigtem setzen und Tausende leere Container, die jede
Aggregation wieder ausfiltern müsste. Der Container ist das Datum, kein Objekt.
Allgemein: erst prüfen, ob die Zeitachse den Container schon liefert, bevor
eine Zeile entsteht, die für immer gepflegt, gezählt und ausgefiltert wird.

**A36 fertig (v0.31.0):** `/api/events?slim=1` lässt die Roh-Metriken weg
(67 % der Nutzlast) und ersetzt sie durch ein kompaktes `weather`-Objekt;
Zeitstrahl/Heute/Karte nutzen slim, nur die Statistik holt die volle Liste
(fetchEventsFull) beim Öffnen. −60 % (19→8 MB bei 12k). weatherSummary liest
aus e.weather ODER e.metrics — geprüft von tools/check-weather-line.js.

**F17 fertig (v0.31.0):** Alter je Ereignis als Chip auf der Karte, Ableitung
aus dem Meilenstein „Geburt" (Anmerkung 72), „~" bei vager Datierung. BIRTH_DATE
wird in renderTimelineList aus tl.events ermittelt.

**A37 fertig (v0.32.0, Anmerkung 81/85):** Der Zeitstrahl lädt Seiten
(`/api/events?limit&offset`, `TL_PAGE=300`, Nachladen beim Scrollen in
`.content`). **Grundregel ab jetzt: Wer eine Zahl über den GESAMTEN Bestand
braucht, holt sie vom Server** — `/api/events/index` (Gesamt, Unbestätigte,
Jahre, Spanne, Geburts-Meilenstein für F17) und `/api/stats/overview`
(alle Statistik-Kacheln und -Diagramme, `services/stats_overview.py`).
Ein Client-Reduce über `tl.events` zählt nur noch das geladene Fenster.
`tools/check-a37-window.js` prüft genau das (Verkehr + Kacheln). Karte:
eigener Endpunkt `/api/events/map` (ohne Wetter; das kommt je Zeitraum nach —
gemessen 799 vs. 356 Byte je Punkt). Einzelabruf `GET /api/events/{id}` für
Ereignisse außerhalb des Fensters. Gemessen bei 12k über HTTP: Start
12,7 MB/1,49 s → 0,31 MB/0,08 s, Statistik 26 MB/5,5 s → 2 kB/0,39 s.
**Offen bleibt A38 (Mobil-Layout)** im selben Release, Audit-Liste in
Anmerkung 82.

**Kein Ticket-System (Anmerkung 83):** Beobachtungen aus der Nutzung werden als
nummerierte Anmerkung in `docs/DECISIONS.md` festgehalten, Pakete in KONZEPT 14.2/14.3 —
nicht in Linear, Jira o. ä. Eine Wahrheit, und zwar die, die beim Arbeiten
gelesen wird.

**Medien-Invariante (Anmerkung 57, ab F15 bindend):** `provider='local'` sind
hochgeladene Dateien = **Lebensdatenbank**, dürfen von Neuberechnungen NIE
angefasst werden; `provider='immich'` sind Verweise = Ableitung, jederzeit
verwerfbar. Im Code erzwingen, nicht nur dokumentieren. JSON-Export enthält nur
Medien-Metadaten — `MEDIA_DIR` separat sichern.

Marktposition und Abgrenzung stehen seit 2026-07-20 in **KONZEPT Kap. 1.1**;
Anmerkungen 51–56 halten die Entscheidungen dazu fest (Karten, KI-Urheberschaft,
Marktanalyse, Werbung, Wachstum, Medienimporte). **Beitragsmodell: vorerst
keine Fremd-PRs** — bewusst kein CLA/DCO, damit die Lizenzfrage offen bleibt.

**Doku ist ab 0.20.0 englisch** (README, backend/README, DEPLOY, KONZEPT,
CHANGELOG). Diskussion/Input dürfen deutsch bleiben — übersetzt wird beim
Schreiben. Diese Datei (CLAUDE.md) bleibt bewusst deutsch.

## Frontend-Übersetzung (F10)
Deutsch steht im Quelltext und ist die Wahrheit; `I18N_EN` in `index.html`
enthält NUR Englisch. Fehlt ein Schlüssel, erscheint Deutsch — nie ein leeres
Label. Drei Wege: `data-i18n` (HTML-Inhalt), `data-i18n-title`/`data-i18n-ph`
(Attribute), `t('key', 'Deutscher Text')` (JS). Neue UI-Texte immer so anlegen.
**Achtung TDZ:** `LANG`/`I18N_EN` stehen bewusst VOR dem Theme-Block, weil
`applyTheme()` schon beim Laden `t()` ruft. Prüfen mit jsdom statt nur Syntax:
ein Syntaxcheck übersieht genau diese Fehlerklasse.
