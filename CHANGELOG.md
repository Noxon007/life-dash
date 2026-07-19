# Changelog

Alle nennenswerten Änderungen an Life-Dash. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/) (`MAJOR.MINOR.PATCH`).

Solange die Version bei `0.x` steht, gilt die App als in Entwicklung: neue
Features erhöhen `MINOR`, Fehlerbehebungen `PATCH`; Breaking Changes können in
jedem `MINOR` vorkommen.

## [Unreleased]

## [0.17.0] – 2026-07-19

### Hinzugefügt
- **🖨️ Zeitstrahl drucken:** Neuer Knopf „Drucken" im Zeitstrahl — druckt
  die aktuelle Ansicht (mit gewähltem Zoom, Filtern und Suche) in hellem,
  druckfreundlichem Layout ohne Navigation; über den Browser-Druckdialog
  auch als PDF sicherbar. Erste Ausbaustufe der Druckansicht: Zeitraum
  wählst du über die normalen Filter, eingeklappte Gruppen vorher über
  „weitere anzeigen" aufklappen.

## [0.16.0] – 2026-07-19

### Geändert
- **Karte nutzt den Bildschirm:** Statt fester 520 Pixel wächst die Karte
  jetzt mit dem Fenster (die Stopp-Liste daneben auch), und ein neuer
  Umschalter **„⛶ Vollbild"** zeigt sie bildschirmfüllend (Esc beendet).
- **Ein Ortsnamen-Lauf statt drei Knöpfe:** „Ortsnamen auflösen",
  „Adressen kürzen" und „Fremdschrift eindeutschen" waren serverseitig
  schon derselbe Lauf — jetzt gibt es dafür einen Knopf mit Auswahl
  (Fehlende Namen / Lange Adressen / Fremdschrift). Die Format-Bausteine
  (Straße/Ortsteil/Stadt/Land) stehen direkt darunter.
- **„Meine Daten" ist aufgeräumt:** Der Reiter gliedert sich jetzt in
  klare Blöcke — **Sichern & Zurückspielen**, **Importe**, **Ortsnamen**
  und **Tracking** — statt einer langen gewachsenen Liste.
- **Login-Screen ist jetzt allgemeingültig:** Der Anmelde-Text nannte
  hart „Pocket ID" — jetzt steht dort ein neutraler SSO-Hinweis; wer mag,
  trägt den Namen seines Anmelde-Dienstes über `OIDC_PROVIDER_NAME` in
  der `.env` ein.

## [0.15.2] – 2026-07-19

### Behoben
- **Ortsnamen-Auflösung geht besser mit der Nominatim-Drossel um:** Meldet
  der Geocoding-Dienst „429 Too many requests", wartet Life-Dash jetzt die
  angeforderte Zeit ab und versucht es einmal erneut, statt im Sekundentakt
  gegen die Sperre weiterzufeuern; der Abstand zwischen Anfragen ist leicht
  erhöht (1,2 s), damit die Sperre gar nicht erst greift.

### Hinzugefügt
- **Optionaler schnellerer Geocoding-Dienst:** In der `.env` lässt sich ein
  Nominatim-kompatibler Dienst mit API-Key eintragen (z. B. LocationIQ,
  kostenlos 5.000 Anfragen/Tag statt ~1/Sekunde) — `GEOCODER_BASE_URL` +
  `GEOCODER_API_KEY`, sonst ändert sich nichts. Ohne Eintrag bleibt alles
  beim öffentlichen OpenStreetMap-Nominatim.

## [0.15.1] – 2026-07-19

### Behoben
- **Ältere Einträge bekommen jetzt auch die neuen Wetterwerte:** „Wetter
  ergänzen" übersprang bisher jedes Ereignis, das schon irgendein Wetter
  hatte — Einträge aus der Zeit vor 0.14.0 blieben deshalb dauerhaft ohne
  Höchst-/Tiefsttemperatur, Sonnenstunden, Regen, Schnee und Wind. Der
  Lauf rüstet die fehlenden Tageswerte jetzt **additiv** nach: Vorhandene
  Werte (alte Temperatur, Wetterlage) bleiben unverändert stehen, es
  kommen nur die fehlenden dazu. Einfach einmal „🌤️ Wetter ergänzen"
  starten (oder den Nachtplan machen lassen).
- **Wetter-Lauf stoppt sauber statt endlos zu probieren:** Kam der Lauf
  nicht voran (z. B. Open-Meteo nicht erreichbar oder Datum ohne
  Archivdaten), fragte er dieselben Ereignisse in Dauerschleife ab. Jetzt
  endet er mit dem Hinweis, wie viele Ereignisse nicht anreicherbar waren.

## [0.15.0] – 2026-07-19

### Hinzugefügt
- **📖 Reisetagebuch:** Im Zeitstrahl gibt es jetzt „Tagebuch schreiben" —
  ein formatierter Eintrag pro Tag (Markdown: **fett**, Überschriften,
  Listen, Zitate, Links), mit Vorschau im Schreibfenster. Der Eintrag
  erscheint als Tageskopf über den Ereignissen des Tages; existiert für
  den gewählten Tag schon einer, wird er zum Weiterschreiben geladen.
  Die KI fasst Tagebuchtexte grundsätzlich nie an. Auch der Kommentar an
  normalen Ereignissen kann jetzt länger sein und wird als Markdown
  formatiert angezeigt (sicher gerendert, ohne fremde Bibliotheken).
- **📅 Mehrtägige Ereignisse mit Tages-Einträgen:** Ein Urlaub bleibt EIN
  Ereignis, bekommt aber im Bearbeiten-Dialog den Knopf „Tages-Einträge
  anlegen": je Tag der Spanne entsteht ein eigenes Ereignis
  („Mallorca — Tag 3"), das Ort und Bestätigung erbt und **eigenes Wetter
  pro Tag** bekommt. Im Zeitstrahl bleiben die Tage eingeklappt unterm
  Haupt-Ereignis (Chip „📅 N Tages-Einträge" klappt auf; der Tages-Zoom
  zeigt sie einzeln). Der Knopf ist gefahrlos mehrfach nutzbar — er füllt
  nur fehlende Tage auf. Beim Löschen des Haupt-Ereignisses fragt
  Life-Dash, ob die Tages-Einträge mitgehen oder als eigenständige
  Ereignisse bleiben.
- **☀️ Heller Modus:** Neben dem dunklen gibt es jetzt ein helles
  Erscheinungsbild. Der Knopf oben rechts wechselt zwischen **Auto**
  (folgt der Systemeinstellung, auch live z. B. bei Sonnenuntergang),
  **Hell** und **Dunkel**; die Wahl wird pro Gerät gespeichert. Die
  Karten wechseln ihren Kartenstil mit.

## [0.14.0] – 2026-07-19

### Hinzugefügt
- **📍 Standort beim Erfassen:** Beim Quick-Capture und in der manuellen
  Eingabe gibt es jetzt einen Standort-Knopf — nie automatisch, nur auf
  Klick. Bei der KI-Analyse wird der Gerätestandort zum Ortsvorschlag,
  wenn der Text selbst keinen Ort nennt (Text hat immer Vorrang); die
  Roh-Koordinaten wandern mit in den Roh-Eingang, damit eine spätere
  Neuberechnung sie kennt. Im manuellen Formular füllt der Knopf das
  Ortsfeld mit der aktuellen Adresse (überschreibbar). Braucht die
  Standort-Freigabe des Browsers (HTTPS).
- **Länder-Kompendium füllt sich aus Importen:** Beim Auflösen von
  Ortsnamen wird das Land jetzt mitgenommen, am Ort gespeichert und als
  Länder-Eintrag mit allen Besuchen dort verknüpft — rückwirkend über
  „Ortsnamen auflösen"/„Adressen kürzen". Damit stimmt „In wie vielen
  Ländern war ich?" endlich auch für importierte Bewegungsdaten.

### Geändert
- **Volleres, ehrlicheres Wetter:** Gespeichert werden jetzt die reinen
  **Tageswerte**: Höchst- und Tiefsttemperatur getrennt, **Sonnenstunden**,
  **Regen (mm)**, **Schnee (cm)**, **maximaler Wind (km/h)** und die
  Tages-Wetterlage. In Event-Karten und Karten-Popups erscheint alles als
  eine kompakte Zeile („12–17,4 °C · Nieselregen · ☀️ 9,1 h · 🌧️ 5,1 mm";
  Wind nur, wenn nennenswert). Bereits geholtes Wetter bleibt unverändert —
  Fakten werden nie überschrieben.
- **Statistik mit Wetter-Extremen:** Neben „Heißester/Kältester Tag" (die
  jetzt echte Tages-Höchst-/Tiefstwerte nutzen) gibt es neue Kacheln
  **Sonnigster**, **Nassester**, **Windigster** und **Schneereichster Tag**
  — Klick öffnet wie gewohnt das jeweilige Ereignis.

### Behoben
- **„Was möchtest du tracken?"-Fenster ließ sich nicht schließen:** Der
  Dialog verwendete eine falsche CSS-Klasse und blieb dauerhaft sichtbar.

## [0.13.0] – 2026-07-19

### Hinzugefügt
- **Du bestimmst, was getrackt wird:** Beim ersten Start fragt Life-Dash,
  welche Bereiche dich interessieren (Reisen, Tiere, Länder, Künstler,
  Essen, Meilensteine, Filme, Spiele, Bücher) — jederzeit änderbar unter
  Verwaltung → Meine Daten. Abgewählte Bereiche verschwinden aus
  Kompendium, Filtern, Formularen, Statistik **und** aus dem KI-Prompt
  (die KI schlägt sie nicht mehr vor); vorhandene Daten bleiben erhalten
  und tauchen nach dem Wieder-Anwählen sofort wieder auf.
- **Läufe laufen jetzt im Hintergrund auf dem Server:** Wetter ergänzen,
  KI-Vorschläge neu berechnen, Embeddings und alle Ortsnamen-Läufe laufen
  weiter, wenn du die Seite schließt. Im Jobs-Reiter gibt es dafür einen
  **Stopp-Knopf** pro laufendem Job und eine Live-Aktualisierung. Neu:
  **Nachtplan** — ausgewählte Läufe starten automatisch einmal täglich zur
  eingestellten Stunde (pro Lauf ein-/ausschaltbar). Datei-Importe bleiben
  browser-gebunden (die Datei liegt dort).
- **Drei neue Sammel-Bereiche: Filme, Spiele, Bücher** — die KI erkennt
  entsprechende Titel und legt Kompendium-Einträge an.

### Geändert
- **Module sind jetzt vollständig deklarativ:** Farben, Emojis,
  Kategorie-Namen, Kompendium-Reiter, Formular-Optionen und die
  KI-Erkennungsregeln kommen aus den Modul-Definitionsdateien — ein neuer
  Bereich ist damit eine einzige YAML-Datei, ohne Code-Änderung (die drei
  neuen Bereiche sind genau so entstanden).

## [0.12.0] – 2026-07-19

> Ab dieser Version sind Changelog-Einträge in Produktsprache geschrieben —
> ohne interne Paketkürzel (die leben nur noch im Konzept).
> Die Version 0.11.0 wurde übersprungen.

### Behoben
- **Karte auf dem Smartphone war unsichtbar:** Ein CSS-Fehler ließ die
  Kartenfläche im mobilen Layout auf Höhe 0 zusammenfallen (die kleine
  Kompendium-Karte war nicht betroffen). Die Karte hat mobil jetzt eine
  feste Höhe von 55 % des Bildschirms.
- **Suche ohne Rückmeldung:** Scheiterte die Server-Suche (z. B. weil der
  KI-Dienst für die Bedeutungssuche nicht erreichbar war), sprang die App
  zum Zeitstrahl, filterte aber still gar nichts. Jetzt greift in dem Fall
  eine einfache Textsuche über Titel/Beschreibung/Ort als Ersatz, und ein
  Hinweis erklärt die Einschränkung.
- **„Gesuchte Adresse" verschwindet:** Dieses Google-Label beschreibt nur,
  wie der Aufenthalt erkannt wurde, und hat keinen eigenen Wert. Neue
  Importe legen solche Besuche als unbenannte Orte an (bekommen beim
  Auflösen die reine Adresse); vorhandene „Gesuchte Adresse — …"-Namen und
  Besuchs-Titel werden beim App-Start automatisch bereinigt, nackte
  „Gesuchte Adresse"-Orte löst „Ortsnamen auflösen" in echte Adressen auf.

### Hinzugefügt
- **Export mit Auswahl:** Beim Daten-Export lässt sich per Häkchen der
  komplette Google-Timeline-Anteil weglassen (importierte Besuche, Routen
  und deren Roh-Belege) — für ein handliches Backup der handgepflegten
  Einträge ohne zehntausende Import-Zeilen.

### Sonstiges
- **Lizenz:** Life-Dash ist seit diesem Release offiziell freie Software
  unter **AGPL-3.0-or-later** (LICENSE-Datei + README-Abschnitt; vorher
  keine Lizenz = „alle Rechte vorbehalten").

### Geändert
- **Verständliche Sprache statt Fachjargon:** Die Oberfläche spricht nicht
  mehr von „Stufe 1/2/3" — stattdessen: **Roh-Eingang** (deine
  unveränderten Texte), **Vorschläge** (KI-Entwürfe zum Bestätigen),
  **Lebensdatenbank** (bestätigte Einträge samt Fakten wie Wetter) und
  **Ansichten** (alles Berechnete). Betrifft u. a. Statistik-Kacheln,
  Eingabe-Hinweise, Admin-Aktionen und die Datenbank-Ansicht; der Knopf
  „Stufe 2 neu berechnen" heißt jetzt „KI-Vorschläge neu berechnen".

## [0.10.1] – 2026-07-16

## [0.10.1] – 2026-07-16

### Geändert
- **Karten-Clustering weniger aggressiv:** Cluster-Radius von 45 auf 30 px
  gesenkt — nahe Punkte bündeln sich erst, wenn sie sich wirklich drängen;
  Mini-Bubbles („3") über halbe Kontinente werden deutlich seltener.
  Dazu erklärt der Tooltip an „Cluster ab N Punkten" jetzt die Semantik:
  Die Schwelle schaltet zwischen Einzelmarker/Route und Cluster-Modus um;
  innerhalb des Cluster-Modus bündelt die Karte zoomabhängig (Klick/Zoom
  teilt Bubbles auf).
- **Konzept:** Lizenz-Vorschlag ergänzt (Kap. 15, Anmerkung 31) — Empfehlung
  **AGPL-3.0** (Repo hat bisher keine LICENSE = „alle Rechte vorbehalten").

## [0.10.0] – 2026-07-16

### Hinzugefügt
- **A14 — Verwaltung mit Reitern statt Scroll-Seite:** Die frühere
  „Admin & Moderation"-Seite heißt jetzt **„Verwaltung"** und ist in Reiter
  gegliedert: **📋 Moderation** (Queue, Bulk-Bestätigen, unscharfe Zeiten),
  **📦 Meine Daten** (Export/Import, Ortsnamen-Aktionen, Anzeige-Format),
  **⏱️ Jobs** — für alle Nutzer; **⚙️ System** (Drei-Schichten-Erklärung,
  Neuberechnung/Wetter/Embeddings, Daten-Wipe), **👥 Nutzer**,
  **🗄️ Datenbank** und **📜 Logs** nur für Admins. Jeder Reiter lädt seine
  Daten beim Öffnen.
- **A17 — Log-Ansicht in der UI:** Neuer Admin-Reiter „Logs" zeigt die
  letzten App-Log-Zeilen (Ring-Puffer im Speicher, max. 500 seit
  Prozessstart) mit Mindest-Level-Filter (DEBUG–ERROR) und Aktualisieren-
  Knopf (`GET /api/admin/logs`). Kein Datei-Zugriff, nichts wird
  persistiert — `docker logs` bleibt die vollständige Quelle.

## [0.9.0] – 2026-07-16

### Hinzugefügt
- **A11 — Jobs mit Sperre + Job-Ansicht:** Lang laufende Aktionen (Wetter,
  Stufe-2-Neuberechnung, Embeddings, Ortsnamen-Läufe, Timeline-/JSON-Import)
  sind jetzt als **Jobs** registriert (`/api/jobs`): Typ, Status, Fortschritt,
  gestartet von/wann, Ergebnis. **Ein Lock pro Job-Typ** — startet eine zweite
  Instanz denselben Typ (zweiter Browser, zweiter Nutzer), kommt „läuft
  bereits (gestartet von …)" statt eines Doppel-Laufs mit doppelten
  API-Kosten. Verwaiste Läufe (Browser zu) blockieren nach 3 Minuten ohne
  Heartbeat nicht mehr. Neue **Jobs-Tabelle** im Admin-Bereich zeigt laufende
  und letzte Läufe (alle Nutzer sehen sie — der Lock ist global).
  Dazu **DB-seitiger Wetter-Dubletten-Schutz**: partieller Unique-Index
  (`event_id`+`key` für `source=weather`) inkl. einmaliger Bereinigung
  vorhandener Doppel-Metriken; die Anreicherung committet pro Event und
  übergeht Kollisionen paralleler Läufe sauber.
- **A4 — DB-Rohansicht mit Leitplanken:** Rohes Bearbeiten validiert jetzt
  gegen das Modell (Enums nur mit gültigen Werten, JSON muss parsen, Zeiten/
  Zahlen typgeprüft, Pflichtspalten nicht leerbar) — 400 mit klarer Meldung
  statt stiller Datenkorruption. **Folge-Neuberechnungen** laufen automatisch
  und werden im Toast angezeigt: Titel/Beschreibung geändert → Embedding
  zurückgesetzt; Zeit/Ort geändert → Wetter folgt den neuen Fakten (P2.4-
  Pfad). **Lösch-Leitplanken:** Fragmente (Beweisarchiv) und Nutzer (→
  Nutzerverwaltung) sind in der Rohansicht gesperrt; Event-Löschung räumt
  Metriken/Medien/Verknüpfungen mit ab, Entity-Löschung ihre Links,
  Orts-Löschung hängt betroffene Events sauber ab (statt verwaister Verweise).
- **A18 — Karten-Clustering erst ab Schwelle (einstellbar):** Neues Feld
  „Cluster ab N Punkten" auf der Karte (Standard 50). Darunter Einzelmarker
  bzw. die nummerierte Route, darüber Bündelung. Pro Nutzer gespeichert
  (`map_cluster_min` in den Einstellungen), begrenzt auf **10–300** — die
  Obergrenze schützt die Performance (mehr Einzelmarker frieren den Browser
  nach großen Importen ein).

### Behoben
- **A16 — Monats-Präzision fehlte bei den unscharfen Zeiten:** „Juni Urlaub
  Dänemark" (korrekt als `month` gespeichert) tauchte nicht in der
  Unscharfe-Zeiten-Liste auf — sie filterte nur Jahreszeit/Jahr/Jahrzehnt/
  ohne Datum. `month` zählt jetzt mit.
- **API-Fehlermeldungen im UI:** Das Frontend zeigt jetzt die Backend-
  Begründung (`detail`) statt nacktem Statuscode — wichtig für Validierungs-
  fehler (A4) und „Job läuft bereits" (A11).

### Tests
- Neue Offline-Tests für A4 (Enum-/JSON-/Zeit-Validierung, Embedding-Reset,
  Wetter-Nachzug, Lösch-Leitplanken und Aufräumen), A11 (Job-Lock, Stale-
  Aufräumung, Wetter-Unique-Index) und A18 (Schwellen-Klemmung 10–300).

## [0.8.0] – 2026-07-16

### Hinzugefügt
- **A5 (Rest) — Besuchs-Verdichtung:** Wiederholte Besuche desselben Orts
  werden gebündelt statt einzeln gelistet. **Karte:** ab Monats-Ansicht ein
  Marker + eine Listenzeile je Ort („59× Zuhause — …", mit Zeitspanne),
  Alltagsorte fallen damit automatisch zusammen; abschaltbar über den neuen
  Chip **„🔁 Orte bündeln"**. In Tag/Woche bleibt die nummerierte Route.
  **Timeline:** gleiche Google-Besuche einer Zeitgruppe erscheinen als eine
  Sammelkarte („🔁 59× Besuch: X"), die per Klick zu Einzelkarten aufklappt —
  vorher füllten Alltagsorte die 25-Karten-Kappe der Gruppen komplett.
- **A12 — Timeline-Import: semantische Orte → echte Adressen:** Orte, die der
  Geräte-Export nur als Label kennt („Zuhause", „Arbeit", „Gesuchte
  Adresse" …), werden jetzt mit reverse-geocodet — das Label bleibt als
  Präfix erhalten („Zuhause — Musterstraße 1, Detmold"); Ort-Typ (z. B.
  `home`) und getrennte `place_id`s (mehrere Wohnorte im Lebenslauf) bleiben
  unverändert. Gilt beim Import (Auto-Auflösung kleiner Mengen) und
  rückwirkend über „Ortsnamen auflösen". Dazu ein optionaler Import-Filter
  **Mindest-Ortssicherheit** (`min_probability`): Besuche mit unsicherer
  Ortszuordnung (häufig bei „Gesuchte Adresse") lassen sich beim Import
  überspringen; der Ergebnis-Toast weist sie aus.
- **Kompakte Ortsnamen (konfigurierbar):** Aufgelöste Adressen werden nicht
  mehr als volle Nominatim-Kette gespeichert („…, Gemeinde Korfu-Mitte und
  Inseln, Regionalbezirk Korfu, …, 491 00, Griechenland"), sondern aus
  strukturierten Bausteinen zusammengesetzt: **Straße · Ortsteil · Stadt ·
  Land** — per Checkboxen im Admin-Bereich pro Nutzer wählbar
  (`GET/PATCH /api/auth/me/settings`, Whitelist). Benannte Orte (Restaurant,
  Museum, Bahnhof …) behalten ihren Eigennamen immer vorn. Gilt für
  Timeline-Auflösung **und** Vorwärts-Geocoding (KI-Pipeline, manuelle
  Eingabe, Bearbeiten-Dialog). Neue Aktion **„📐 Adressen kürzen"**
  formatiert bestehende lange Adressen nach (`resolve-names?scope=verbose`,
  Batch-Lauf mit Stopp-Knopf); Besuchs-Events werden mit umbenannt, manuell
  umbenannte bleiben unangetastet. Besuchs-Titel tragen jetzt das volle
  Kurzformat (vorher nur das erste Adress-Segment ohne Stadt).
- **A6 — Nutzerverwaltungs-UI:** Neuer Admin-Bereich „Nutzer": Liste aller
  Konten (Name, E-Mail, Rolle, Datenumfang, dabei seit), Rolle per Auswahl
  ändern, Nutzer **mitsamt all ihren Daten** löschen (mit Sicherheitsabfrage).
  Leitplanken: das eigene Konto kann weder gelöscht noch herabgestuft werden,
  der letzte Admin bleibt immer erhalten
  (`GET/PATCH/DELETE /api/admin/users`).

### Behoben
- **Import-Auto-Auflösung benannte frische Besuchs-Events nicht um:** Beim
  direkten Reverse-Geocoding kleiner Ortsmengen im Import wurden die gerade
  angelegten Events nicht gefunden (Session ohne Autoflush) — ihre Titel
  blieben „Besuch: Ort (lat, lng)", obwohl der Ort aufgelöst war.

### Tests
- Neue Offline-Tests für A12 (Label-Präfix, Idempotenz, `field_overrides`-
  Schutz, `min_probability`), A6 (Letzter-Admin-Guard, Löschen inkl.
  Datenzeilen, Selbstlösch-Sperre) und das Ortsnamen-Format (`short_name`-
  Bausteine, POI-Eigenname, Nutzer-Einstellung, `scope=verbose`,
  Settings-Whitelist) in `backend/tests/`.

## [0.7.0] – 2026-07-16

### Hinzugefügt
- **A9 — Logging & Beobachtbarkeit:** Zentrale Logging-Konfiguration
  (`lifedash.*`-Logger, einheitliches Format mit Zeitstempel), steuerbar über
  `LOG_LEVEL` (.env / Compose). Geloggt werden jetzt u. a. App-Start (Version,
  Auth-/KI-/DB-Modus), Export/Import mit Zeilenzahlen, Admin-Aktionen
  (Neuberechnung, Wetter-/Embedding-Batches, Rohansicht-Änderungen,
  Daten-Wipe), Geocoding-/Open-Meteo-Fehler und die Ortsnamen-Auflösung.
  Docker Compose bekommt Log-Rotation (`max-size: 10m`, `max-file: 5`).
- **A10 — Ortsnamen konsequent auf Deutsch/Latein:** Nominatim wird mit
  Sprach-Fallback `de,en` angefragt; liefert OSM keinen deutschen Namen,
  kommt die englische/lateinische Umschrift statt Lokalschrift (z. B.
  Griechisch). Zusätzlich bevorzugt `namedetails` den besten lateinischen
  Namen. Neue Admin-Aktion **„Fremdschrift-Namen eindeutschen"** löst
  bestehende Orte mit nicht-lateinischer Schrift erneut auf
  (`resolve-names?scope=nonlatin`); Besuchs-Events werden mit umbenannt,
  manuell umbenannte Einträge bleiben unangetastet.
- **A13 — Uhrzeiten anzeigen & bearbeiten:** Events mit `date_precision =
  exact` zeigen jetzt Datum **und Uhrzeit** („12.07.2026, 14:30–16:05") —
  damit werden importierte Timeline-Besuche als Tagesablauf lesbar. Der
  Bearbeiten-Dialog bekommt optionale Uhrzeit-Felder und die Präzision
  „Tag + Uhrzeit"; eine eingegebene Uhrzeit hebt die Präzision automatisch
  auf `exact`. Uhrzeiten bleiben lokale Wanduhrzeit („wie erlebt", keine
  UTC-Umrechnung).
- **A5 (Karten-Teil) — Marker-Clustering statt 300er-Deckel:** Die Karte
  zeigt jetzt **alle** Punkte eines Zeitraums. Bis 300 Stopps bleibt die
  nummerierte Tagesroute; darüber werden die Marker gebündelt
  (Leaflet.markercluster) statt abgeschnitten. Die Stopp-Liste bleibt als
  DOM-Schutz gedeckelt und sagt das dazu.
- **A8 — Export-Rückmeldung:** Der Daten-Export meldet Erfolg per Toast
  (Anzahl Events/Fragmente/Objekte/Orte/Routen/Metriken, Dateigröße,
  Dateiname) bzw. Fehler als Fehler-Toast; der Button ist während des
  Exports deaktiviert.

### Behoben
- **Stiller Präzisions-Downgrade beim Bearbeiten:** Der Bearbeiten-Dialog
  stufte `exact`-Events beim Speichern unbemerkt auf `day` herab (die
  Uhrzeit ging verloren). Jetzt bleibt `exact` erhalten und ist wählbar.

## [0.6.0] – 2026-07-16

### Hinzugefügt
- **A1 — Saubere UI-Dialoge statt Browser-Popups:** Alle nativen
  `alert()`/`confirm()`/`prompt()`-Dialoge (~20 Stellen: Export, Import,
  Batch-Läufe, Löschen …) ersetzt durch **Toasts** im App-Stil (Erfolg /
  Warnung / Fehler, Klick schließt) und ein **Bestätigungs-Modal** — inkl.
  Tipp-Bestätigung („LÖSCHEN") beim Daten-Wipe. Auf Mobil erscheinen Toasts
  über der Bottom-Navigation.
- **A2 — Fortschrittsbalken bei großen Importen:** Google-Timeline-Import
  und JSON-Restore laufen bei großen Dateien in Etappen mit echtem
  Fortschritt („12.000 / 48.500 Segmente") statt unbestimmtem Spinner —
  gefahrlos, weil beide Importe idempotent sind. Beim Etappen-Import wird
  das automatische Reverse-Geocoding übersprungen (neuer Query-Param
  `auto_resolve=false`); Chunk-Grenzen halten zusammengehörige
  Geräte-Export-Segmente (Route + Aktivität) beieinander.
- **A3 — Versionsnummer im UI:** Die Sidebar zeigt unten links die laufende
  Version (z. B. „Life-Dash v0.6.0"). Eine Quelle der Wahrheit:
  `backend/app/version.py` speist UI, `/health` und die OpenAPI-Doku
  (dort stand bis jetzt fälschlich 0.2.0).

## [0.5.0] – 2026-07-16

### Hinzugefügt
- **P2.5 — Bulk-Bestätigen:** Die Moderations-Queue kann viele korrekte
  KI-Vorschläge auf einmal übernehmen — Filter nach Kategorie, Quelle,
  Mindest-Confidence und Zeitraum, immer zweistufig: erst **Vorschau** der
  betroffenen Events, dann Bestätigen. Neue Endpoints
  `POST /api/moderation/bulk-confirm/preview` und `…/bulk-confirm`.
- **P2.6 — Invarianten-Test „Bestätigtes ist unantastbar":** Automatische
  Tests (`backend/tests/`, pytest) fahren alle Recompute-/Enrichment-/
  Import-Pfade gegen die Invariante aus KONZEPT Kap. 3.1: Neuberechnung
  verschont bestätigte Fragmente samt Geschwister-Events, Wetter ist additiv
  und idempotent, Bulk-Bestätigen kippt nur den Status, Re-Import erzeugt
  keine Duplikate und fasst Bestätigtes nicht an, die Ortsnamen-Auflösung
  respektiert manuell umbenannte Titel, Embedding-Neuberechnung ändert nur
  das Embedding.
- **P2.7 — Bestätigungs-Provenienz:** Jedes Event speichert jetzt, **wann**
  und **wodurch** es bestätigt wurde (`confirmed_at`, `confirmed_by`:
  manuell / Sammel-Bestätigung / Import) — sichtbar im Bearbeiten-Dialog.
  Bestandsdaten werden migriert (Import-Besuche → „Import", Rest → „manuell",
  Zeitpunkt = letzte Änderung); erneutes Bestätigen/Bearbeiten überschreibt
  die ursprüngliche Provenienz nicht.
- **P2.4 — Auto-Enrichment nach der Eingabe:** Neue Events (KI-Analyse und
  manuelle Eingabe) bekommen ihr Wetter sofort beim Anlegen statt erst über
  den Admin-Knopf (best effort — schlägt der Abruf fehl, trägt der Admin-Lauf
  später nach); Embeddings entstehen weiterhin direkt beim Anlegen. Korrigiert
  der Nutzer Zeit oder Ort eines Events, wird dessen Wetter passend zu den
  neuen Fakten neu geholt (nutzergestartete Korrektur — keine
  Maschinen-Änderung an Bestätigtem).
- **P2.2 — Google-Timeline-Import:** Upload des Timeline-Exports (Geräte-Export
  `semanticSegments` und altes Takeout-Format `timelineObjects`) unter
  Admin → „Meine Daten". Besuche werden zu bestätigten Events
  (source `google_timeline`), Bewegungen zu `Track`-Zeilen (Stufe 3, Punkte
  unvereinfacht). Re-Import ist idempotent (Segment-Hash als `external_id`).
  Neue Endpoints: `POST /api/import/timeline`, `GET /api/tracks?start=&end=`.
- **Routen als Karten-Layer:** Timeline-Routen erscheinen auf der Karte als
  farbige Linien nach Aktivität (zu Fuß/Rad/Auto/Transit), zuschaltbar über
  den Chip „🛰️ Timeline-Routen", gefiltert auf den angezeigten Zeitraum.
- **Vier-Schichten-Modell präzisiert** (KONZEPT Kap. 3.1): Eingang →
  Vorschlagsraum → **Lebensdatenbank (fix)** → Ableitungen. Harte Invariante:
  Maschinen ändern Bestätigtes nie, nur additiv ergänzen. Konsequenz:
  **Wetter ist Fakten-Anreicherung** — der Knopf „Stufe 3 neu berechnen"
  (der Wetter verwarf und neu holte) ist entfernt; Wetter wird nur noch
  ergänzt, wo es fehlt. Embeddings bleiben als Ableitung neu berechenbar.
- **Stopp-Knopf & Anfragen-Ticker für alle Admin-Läufe:** Stufe-2-Neuberechnung,
  Stufe 3, Wetter, Embeddings und Ortsnamen laufen jetzt in Etappen — der
  Aktions-Knopf zeigt live die verbrauchten Anfragen („⏹ Stoppen — 120
  KI-Anfragen · noch ~340") und stoppt auf Klick nach dem laufenden Batch.
  Fortschritt bleibt erhalten, derselbe Knopf setzt fort. Die Stufe-2-Neuberechnung
  fasst Import-Fragmente (Timeline) nicht mehr an — KI-Extraktion über
  Import-Zusammenfassungen hätte Unsinn erzeugt.
- **Ortsnamen für importierte Besuche:** Der Geräte-Export enthält keine
  Ortsnamen — neuer Button „📍 Ortsnamen auflösen" (Admin → Meine Daten) holt
  Adressen per Reverse-Geocoding (Nominatim, 1 Anfrage/s, etappenweise
  fortsetzbar) und benennt Orte samt Besuchs-Events um; manuell geänderte
  Titel bleiben geschützt. Kleine Folge-Importe (≤ 30 neue Orte) lösen Namen
  direkt beim Import auf.
- **P2.3 — Unscharfe-Zeiten-Review:** Admin-Bereich listet alle Events mit
  grober Zeitangabe (Jahreszeit/Jahr/Jahrzehnt/ohne Datum); Klick öffnet die
  Schnellbearbeitung.
- **Statistik ist klickbar** (wie im Kompendium): Kacheln führen zu
  Kompendium/Timeline (kategorie-gefiltert)/Karte/Moderation, der heißeste/
  kälteste Tag öffnet das Event, Chart-Balken (Kategorien, Tiere) springen zu
  Timeline-Filter bzw. Kompendium-Detailseite.

### Geändert
- **PostgreSQL ist jetzt der Compose-Standard** (kein `--profile postgres`
  mehr): `docker compose up -d` startet App + DB, `POSTGRES_PASSWORD` in
  `.env` genügt. Version: **`postgres:18-alpine`** (Support bis Nov. 2030,
  Async-I/O). Achtung Image-Eigenheit ab 18: Der Daten-Mount zeigt auf
  `/var/lib/postgresql` (nicht mehr `…/data`) — Upgrade von einer
  bestehenden 16er-DB via JSON-Export (docs/DEPLOY.md Kap. 6).
- **Daten liegen als Ordner neben der Compose-Datei** (Bind-Mounts statt
  Docker-Volumes): `./db` = PostgreSQL-Datenverzeichnis, `./data` =
  App-Daten (SQLite beim Minimal-Setup). Backup = Ordner sichern oder
  `pg_dump`; bestehende Volume-Installationen ziehen per JSON-Export um. **Migration von SQLite:** JSON-Export ziehen, `DATABASE_URL`
  aus `.env` entfernen, `up -d`, Export importieren (docs/DEPLOY.md Kap. 6).
  SQLite bleibt via `DATABASE_URL`-Override + `up -d --no-deps app` möglich.
- **Performance für importierte Massendaten** (>10k Timeline-Events):
  - `/api/events` lädt Verknüpfungen jetzt eager (Sammel-Queries statt
    N+1-Lazy-Loading): 11,7k Events in 0,7 s statt 4,4 s.
  - Timeline, Karte, Statistik und Unscharfe-Zeiten teilen sich **einen**
    Events-Abruf (vorher 4 × mehrere MB).
  - Timeline rendert pro Zeitgruppe zunächst 25 Karten („▼ weitere anzeigen"),
    statt 10k+ DOM-Knoten auf einmal.
  - Importierte Google-Besuche sind im Zeitstrahl standardmäßig ausgeblendet
    (Toggle „🛰️ Besuche") — auf der Karte bleiben sie immer sichtbar.
  - Karte deckelt Marker/Stopp-Liste bei 300 pro Zeitraum; Timeline-Routen
    werden nur bis Monats-Zoom gezeichnet; `/api/tracks` hat ein Server-Limit
    (Default 1000, max. 5000).
- Datenexport/-import und „Alle Daten löschen" erfassen jetzt auch Tracks;
  Schema-Migration ergänzt `events.external_id` in Bestands-DBs automatisch.

## [0.4.0] – 2026-07-15

### Hinzugefügt
- **Verknüpfte Objekte im Bearbeiten-Dialog editierbar** (z. B. „Seeadler" →
  „Adler" korrigieren, Objekte ergänzen/entfernen). `PATCH /api/moderation/{id}`
  akzeptiert dazu ein `entities`-Feld, das die Verknüpfungen vollständig
  ersetzt; verwaiste Entities werden aufgeräumt, die Änderung ist als Override
  vor KI-Neuberechnungen geschützt.

## [0.3.2] – 2026-07-15

### Behoben
- **Karte wurde auf Mobilgeräten nicht angezeigt.** Leaflet vermisst sich jetzt
  mehrfach neu (`invalidateSize` nach Einblenden) und reagiert auf
  Drehen/Resize — Mobil meldete direkt nach dem Einblenden oft Höhe 0.
- **Eingabe-Symbol in der Mobil-Navigation** hatte einen blauen runden
  FAB-Hintergrund; entfernt, das Icon sieht jetzt aus wie die übrigen Tabs.

### Hinzugefügt
- **Sichtbarer Lade-Overlay während der KI-Analyse** (Spinner + Text). Auf Mobil
  war die einzige Rückmeldung bisher der Button-Text, der oft außerhalb des
  Sichtfelds lag.

## [0.3.1] – 2026-07-15

### Behoben
- **OIDC-Login scheiterte hinter dem Reverse Proxy mit HTTP 403.** Die
  Server-zu-Server-Aufrufe an Pocket ID (Discovery, JWKS, Token-Tausch) senden
  jetzt einen expliziten `User-Agent`; der Default `Python-urllib/…` wurde von
  Bot-Filtern (Traefik/Pangolin, CrowdSec) geblockt.

## [0.3.0] – 2026-07-15

### Geändert
- **Versionierung auf SemVer umgestellt** (`vMAJOR.MINOR.PATCH`) + dieses
  CHANGELOG eingeführt. Der Release-Workflow erzeugt aus einem Git-Tag `vX.Y.Z`
  automatisch die Image-Tags `X.Y.Z`, `X.Y` und `latest`.
- KI-Stack aufgeräumt: **Gemini API als Standardweg**, Defaults auf
  `gemini-3.5-flash` / `gemini-embedding-2` gesetzt.
- **Ollama-Service aus dem Compose-Stack entfernt** (lokales Ollama bleibt als
  Alternative dokumentiert, ist aber nicht Teil des ausgelieferten Stacks).

## [0.2.0] – 2026-07-15

### Behoben
- **Multi-Arch-Image** (`linux/amd64` + `linux/arm64`); v0.1 war amd64-only und
  auf dem Raspberry Pi 5 (ARM64) nicht lauffähig.

## [0.1.0] – 2026-07-15

### Hinzugefügt
- Erstveröffentlichung (P0 + P1): FastAPI-Backend, responsive PWA-Frontend,
  OIDC-Multi-User (Pocket ID), Homelab-Deployment via Docker Compose und
  GHCR-Release-Workflow.

<!-- Die Tags v0.1/v0.2 (zweistellig) stammen aus der Zeit vor der
     SemVer-Umstellung; ab v0.3.0 gilt durchgehend MAJOR.MINOR.PATCH. -->
