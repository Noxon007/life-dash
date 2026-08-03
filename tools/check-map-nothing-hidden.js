// Die Karte darf keinen Punkt LAUTLOS weglassen (Anmerkung 110).
//
// Gemeldet wurde: „vereinzelte Besuche in Amerika werden nicht mehr angezeigt".
// Nachgestellt mit 2000 Besuchen an 250 deutschen Orten plus drei einzelnen in
// den USA ergab sich das hier:
//
//     „Punkte zusammenfassen" AN  -> 253 Marker, USA dabei
//     „Punkte zusammenfassen" AUS -> 300 Marker, USA WEG
//
// Denn ohne Bündelung zeichnet die Karte `all.slice(0, 300)` — die ersten
// dreihundert **chronologisch**. Alles ab der Monatsmitte fehlt, und ein
// einzelner Besuch ist mit Sicherheit dabei. Der Deckel selbst ist vertretbar
// (tausende nummerierte Marker sind unbedienbar); **still** ist er es nicht.
//
// Dieser Wächter prüft deshalb nicht „sind alle Punkte da?", sondern die
// Eigenschaft, die den Bericht überhaupt erst ausgelöst hat: *wenn* die Karte
// etwas weglässt, muss sie es auf der KARTE sagen — nicht in der Liste daneben,
// die beim Draufschauen niemand liest.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-map-nothing-hidden.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const placed = [];
const lines = [];          // gezeichnete Linienzüge samt Optionen
const calls = [];          // abgesetzte Anfragen
const tooltips = [];       // dauerhafte Etiketten — Anmerkung 161: es darf keine geben
const icons = [];          // divIcon-Optionen (Cluster-Blase, Einzelpunkt im Cluster)

const layer = name => ({ _n: name, clearLayers() {}, addTo() { return this; },
                         addLayer() { return this; }, removeLayer() { return this; } });

function makeEvents(nDe, nLocs) {
  const out = [];
  for (let i = 0; i < nDe; i++) {
    const p = i % nLocs;
    out.push({ id: 'de' + i, title: 'Besuch: Ort ' + p, category: 'event',
      date_start: `2024-05-${String((i % 28) + 1).padStart(2, '0')}T10:00:00`,
      date_precision: 'exact', confirmed: 'confirmed', source: 'google_timeline',
      location: { id: 'loc' + p, name: 'Ort ' + p, lat: 51 + p * 0.004, lng: 8 + p * 0.004 },
      entities: [], metrics: [], media: [] });
  }
  [['New York', 40.71, -74.0], ['Chicago', 41.88, -87.63], ['Denver', 39.74, -104.99]]
    .forEach(([n, lat, lng], k) => out.push({
      id: 'us' + k, title: 'Besuch: ' + n, category: 'event',
      date_start: `2024-05-1${k}T15:00:00`, date_precision: 'exact',
      confirmed: 'confirmed', source: 'google_timeline',
      location: { id: 'us-' + k, name: n, lat, lng }, entities: [], metrics: [], media: [] }));
  return out;
}

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = {
      map: () => ({ setView() { return this; }, addLayer() {}, removeLayer() {},
                    fitBounds() {}, invalidateSize() {}, on() {}, getZoom: () => 5,
                    eachLayer() {}, remove() {} }),
      tileLayer: () => ({ addTo() { return this; }, remove() {} }),
      layerGroup: () => layer('mapMarkers'),
      markerClusterGroup: () => layer('mapCluster'),
      // Anmerkung 163: die Optionen gehen MIT — an ihnen hängt das Symbol, und
      // am Symbol hängt die Zusage „Größe = Menge". Ein Doppel, das sie
      // wegwirft, prüft eine Karte ohne Marken.
      marker: (ll, opt) => ({ addTo(l) { placed.push([l && l._n, ll[0], ll[1], opt || null, 'marker']); return this; },
                       bindPopup() { return this; }, bindTooltip() { return this; },
                       on() { return this; } }),
      // Anmerkung 160: Gruppen sind jetzt FLÄCHEN (circleMarker), keine
      // Standard-Marker. Ein Doppel, das sie nicht mitzählt, prüfte eine
      // Karte, auf der nichts liegt — und wäre still grün.
      circleMarker: (ll, opt) => ({ addTo(l) { placed.push([l && l._n, ll[0], ll[1], opt, 'circle']); return this; },
                             bindTooltip() { return this; },
                             bindPopup() { return this; } }),
      // Anmerkung 161: die dauerhaften Etiketten über den Blasen sind weg —
      // sie überlagerten sich beim Herauszoomen genau dort, wo die Karte am
      // dichtesten ist. Gezählt wird, damit sie nicht unbemerkt zurückkommen.
      tooltip: () => { tooltips.push(1);
                       return { setLatLng() { return this; },
                                setContent() { return this; },
                                addTo() { return this; } }; },
      polyline: (pts, opt) => { lines.push(opt || {});
                                return { addTo() { return this; }, bindPopup() { return this; } }; },
      // Muss es GEBEN: fehlt `L.canvas`, fällt `mpCanvas()` still auf Leaflets
      // Standard-Renderer zurück — also auf genau das SVG, dessen Zeichenlast
      // die Wochenansicht eingefroren hat. Ein Doppel ohne diese Funktion
      // prüfte einen Zustand, in dem die Prüfung nicht scheitern KANN.
      canvas: () => ({ _n: 'canvas' }),
      latLngBounds: () => ({ pad: () => ({}) }),
      // Die Symbol-Optionen werden behalten: an ihnen hängt die Zusage, dass
      // Nähe-Blase und Orts-Blase DIESELBE Bildsprache sprechen (Anm. 161).
      divIcon: (opt) => { icons.push(opt || {}); return opt || {}; },
      control: { layers: () => ({ addTo() {} }) },
    };
    w.fetch = (u) => {
      const p = String(u);
      calls.push(p);
      // 900 Wege im Bestand, 400 geliefert — die Antwortform von `list_tracks`.
      const body = /api\/tracks/.test(p)
        ? { total: 900, shown: 2, tracks: [
            { id: 't1', date_start: '2024-05-01T08:00:00', date_end: '2024-05-01T09:00:00',
              points: [[51, 8], [51.1, 8.1]], activity_type: 'walk', distance_m: 1200 },
            { id: 't2', date_start: '2024-05-30T08:00:00', date_end: '2024-05-30T09:00:00',
              points: [[51, 8], [51.1, 8.1]], activity_type: 'drive', distance_m: 4200 }] }
        : [];
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    };
  },
});

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};

const wait = ms => new Promise(r => setTimeout(r, ms));

setTimeout(async () => {
  const w = dom.window, d = w.document;
  const note = () => d.getElementById('mp-cap-note');
  const noteVisible = () => note() && note().style.display !== 'none';
  // Anmerkung 160: statt `condense` (ein Ein/Aus, dessen Bedeutung die
  // Zoomstufe entschied) die gewählte STUFE.
  const render = (density, events) => {
    placed.length = 0;
    w.eval(`
      mapObj = L.map('map'); mapMarkers = L.layerGroup();
      mapCluster = L.markerClusterGroup(); mapRoute = L.layerGroup();
      mapTracks = L.layerGroup();
      mp.located = ${JSON.stringify(events)};
      mp.mode = 'month'; mp.catFilter = new Set(FILTER_CATS_BASE.concat(['event']));
      mp.periods = ['2024-05']; mp.index = 0; mp.density = '${density}';
      renderPeriod();`);
  };
  // Gezählt werden ORTE, nicht Zeichenaufrufe: eine Gruppe ist seit
  // Anmerkung 160 eine Fläche PLUS ein Kern, also zwei Kreise an derselben
  // Stelle. Ein Wächter, der Aufrufe zählt, meldete dann sechs Amerika-Punkte
  // und hätte recht — nur nicht in der Sache, um die es geht.
  const far = () => new Set(placed.filter(p => p[2] < -50).map(p => p[1] + ',' + p[2])).size;
  const markers = () => placed.filter(p => p[4] === 'marker').length;

  // **Anmerkung 161 — die Zusage ist STÄRKER geworden: die Karte lässt
  // clientseitig gar nichts mehr weg.**
  //
  // Der Bericht von damals hing an einem Deckel von 300, und der hing daran,
  // dass jeder Eintrag zwei Leaflet-Objekte anlegte. Seit die Einzelpunkte auf
  // derselben Leinwand liegen wie die Fotos (die dort seit Anmerkung 153
  // zwanzigtausend ohne ein einziges Objekt zeichnet), gibt es weder Objekte
  // je Punkt noch einen Grund für den Deckel. Geprüft wird deshalb nicht mehr
  // „wenn sie etwas weglässt, sagt sie es", sondern **„sie lässt nichts weg" —
  // und die Objektlast wächst trotzdem nicht mit der Punktzahl.**
  const onCanvas = () => w.eval('mpPinPoints.length');
  const objects = () => placed.length;

  // --- 1. Der Normalfall -------------------------------------------------- //
  render('point', makeEvents(20, 8));
  ok('Kleine Menge: alle Punkte auf der Karte', onCanvas() === 23,
     `${onCanvas()} von 23`);
  ok('…und kein Hinweis, der nicht zutrifft', !noteVisible());
  const smallObjects = objects();

  // --- 2. Der gemeldete Fall, in seiner heutigen Form --------------------- //
  const many = makeEvents(2000, 250);
  render('point', many);
  ok('Zweitausend Punkte kommen VOLLSTÄNDIG auf die Karte',
     onCanvas() === many.length, `${onCanvas()} von ${many.length}`);
  ok('…und dabei entsteht kein Objekt je Punkt', objects() === smallObjects,
     `${objects()} Objekte bei ${many.length} Punkten, ${smallObjects} bei 23 — `
     + 'genau die Last, wegen der es den Deckel überhaupt gab');
  ok('…es gibt also nichts zu melden', !noteVisible(),
     'ein Hinweis über einer vollständigen Karte behauptet einen Verlust, den '
     + 'es nicht gibt');
  // Die drei einzelnen Punkte in Amerika WAREN der Bericht.
  const usOnCanvas = w.eval('mpPinPoints.filter(e => e.location.lng < -50).length');
  ok('Die seltenen Orte sind dabei', usOnCanvas === 3,
     `${usOnCanvas} von 3 Amerika-Punkten`);

  // --- 2b. Die LISTE daneben deckelt weiterhin, und zwar gleichmäßig ------ //
  //
  // **Anmerkung 160: gedeckelt heißt gleichmäßig, nicht vorne.** `slice(0, 300)`
  // lieferte die ersten dreihundert CHRONOLOGISCH — bei einem Monat mit 2.000
  // Besuchen fehlte alles ab der Mitte. Dieselbe Regel wie
  // `sqlutil.even_spread` im Backend, nur dass sie seit Anmerkung 161 nur noch
  // für die Liste gilt: die Karte zeigt alles.
  //
  // **Geprüft wird am ERGEBNIS, nicht an der Funktion.** Im ersten Anlauf stand
  // hier `mpEvenSpread([...])` — die Funktion allein. Gegen den kaputten Stand
  // gefahren (Deckel zurück auf `slice(0, 300)`) blieb das grün: die Funktion
  // gab es ja weiterhin, sie wurde nur nicht mehr benutzt. Anmerkung 108, und
  // schon wieder in der Form „prüft, dass es das GIBT, statt dass es WIRKT".
  //
  // Die Tage stehen in der Stopp-Liste. Nimmt die Karte die ersten dreihundert
  // chronologisch, endet sie bei rund 2.000 Besuchen im Monat am 4. oder 5.;
  // greift sie gleichmäßig, reicht sie bis zum Monatsende.
  const stopDays = () => [...d.getElementById('mp-stops').textContent
    .matchAll(/(\d{2})\.05\.2024/g)].map(m => +m[1]);
  const lastDay = Math.max(0, ...stopDays());
  ok('Die Liste greift gleichmäßig über den Zeitraum', lastDay >= 25,
     `letzter gezeigter Tag: ${lastDay}. Mai — „die ersten 300" hören Anfang `
     + 'des Monats auf, und die Liste sieht trotzdem voll aus');
  ok('…und beginnt trotzdem am Anfang', Math.min(...stopDays()) <= 2,
     `erster gezeigter Tag: ${Math.min(...stopDays())}.`);
  // In BEIDEN Sprachen: unter jsdom startet die Seite englisch, der Katalog
  // ersetzt den deutschen Text — eine Prüfung nur auf „alle" wäre hier rot,
  // ohne dass etwas fehlt (Anmerkung 116, und in dieser Runde zum dritten Mal).
  ok('…und sagt, dass die KARTE alles zeigt',
     /(alle|all) 2[.,]?003/.test(d.getElementById('mp-stops').textContent),
     d.getElementById('mp-stops').textContent.slice(0, 160));
  ok('…und trifft das Budget genau',
     w.eval('mpEvenSpread(Array.from({length: 8120}, (_, i) => i), 5000).length') === 5000,
     'jede n-te trifft es nur, wenn es aufgeht — bei 8.120 auf 5.000 wären es 4.060');

  // --- 2c. Nummern nur mit Reihenfolge ------------------------------------ //
  //
  // Gemeldet: „bei jedem Punkt wird immer die Zahl angezeigt — das ist bei
  // Jahr, Jahrzehnt und Alles nicht sinnvoll". Die Nummer ist die Beschriftung
  // EINER Linie; ohne Linie ist sie die Antwort auf eine ungestellte Frage.
  const labels = () => w.eval(
    '(function () { const c = PIN_DOT_LAYER._cfg; let n = 0;'
    + ' mpPinPoints.forEach((e, i) => { if (c.label && c.label(e, i + 1)) n++; });'
    + ' return n; })()');
  render('point', makeEvents(12, 5));
  w.eval('mp.showRoute = false; renderPeriod();');
  ok('Ohne „Reihenfolge verbinden" trägt kein Punkt eine Nummer', labels() === 0,
     `${labels()} nummerierte Punkte`);
  w.eval('mp.showRoute = true; renderPeriod();');
  ok('…mit Reihenfolge schon', labels() === 15, `${labels()} von 15`);
  // …aber nicht bei tausenden: über hundert nummerierte Kreise sind keine
  // Reihenfolge mehr, sondern ein Muster.
  render('point', many);
  w.eval('mp.showRoute = true; renderPeriod();');
  ok('…und bei zweitausend Punkten wieder nicht', labels() === 0,
     `${labels()} nummerierte Punkte bei ${many.length}`);

  // --- 3. Zusammengefasst ist wirklich alles da --------------------------- //
  render('place', many);
  ok('Je Ort sind die seltenen Orte da', far() === 3,
     `${far()} von 3 Amerika-Punkten — das war der Bericht`);
  ok('…und der Hinweis verschwindet wieder', !noteVisible(),
     'ein Hinweis, der über einer vollständigen Karte stehen bleibt, lügt');

  // **„Fläche statt Ziffer" (Anmerkung 160):** ein Ort mit 59 Besuchen muss
  // GRÖSSER sein als einer mit 2. Bis 0.39 sahen beide gleich aus und die Zahl
  // stand nur im Popup — also hinter einem Klick, den man erst macht, wenn man
  // schon weiß, dass sich einer lohnt.
  const sizes = placed
    .map(p => p[3] && p[3].icon && p[3].icon.iconSize && p[3].icon.iconSize[0])
    .filter(x => typeof x === 'number');
  // Der Prüfstand kennt genau zwei Gruppengrößen (250 Orte mit je acht
  // Besuchen, dazu drei einzelne in Amerika), also kann er auch nur zwei
  // Markengrößen zeigen. `> 2` zu verlangen hieße, etwas zu prüfen, das die
  // Daten nicht hergeben — die Abstufung selbst steht darunter.
  ok('Die Marken haben verschiedene Größen', new Set(sizes).size >= 2,
     `${new Set(sizes).size} verschiedene Größen bei ${sizes.length} Marken`);
  // Gemeldet: „das Textfeld über den Blasen finde ich nicht so hübsch und es
  // überlagert sich beim Herauszoomen." Es ist weg, und zwar ganz.
  ok('…und KEIN dauerhaftes Etikett darüber', tooltips.length === 0,
     `${tooltips.length} Etiketten — sie stapeln sich genau dort, wo die Karte `
     + 'am dichtesten ist');

  // --- 3b. Beide Blasen sprechen dieselbe Bildsprache (Anmerkung 161) ----- //
  //
  // Gemeldet: „Nach Nähe hat zu Je Ort einen anderen Stil." Das war kein
  // Geschmacksurteil, sondern ein Befund: die Nähe-Blase kam vom Plugin
  // (immer blau, immer mit Zahl), die Orts-Blase von der Leinwand
  // (Kategoriefarbe, durchscheinend). Zwei Aussehen für dieselbe Aussage
  // „hier steckt mehr als eins drin", je nachdem, welche Stufe gewählt war.
  //
  // Festgenagelt wird die FARBREGEL, weil sie die Aussage trägt: beide nehmen
  // die Farbe der häufigsten Kategorie darin.
  icons.length = 0;
  w.eval("mpClusterIcon({ getChildCount: () => 12, getAllChildMarkers: () => ["
       + "{ options: { ldCat: 'concert' } }, { options: { ldCat: 'concert' } },"
       + "{ options: { ldCat: 'trip' } }] })");
  const bubbleHtml = String((icons[icons.length - 1] || {}).html || '');
  const groupColor = w.eval("mpGroupColor([{category:'concert'},"
                          + "{category:'concert'},{category:'trip'}])");
  ok('Der Nähe-Tropfen trägt die Farbe seiner häufigsten Kategorie',
     bubbleHtml.includes(`fill="${groupColor}"`),
     `${bubbleHtml.slice(0, 90)} — erwartet fill="${groupColor}"`);
  ok('…also dieselbe, die die Orts-Gruppe nähme',
     groupColor === w.eval("catColor('concert')"),
     `${groupColor} / ${w.eval("catColor('concert')")}`);
  // **Und dieselbe FORM.** Beide Stufen zeichnen denselben Pfad; zwei
  // Zeichnungen desselben Zeichens sind zwei Zeichen, sobald jemand eine
  // davon anfasst (Anmerkung 161, letzte Hälfte).
  ok('…und denselben Tropfen-Pfad',
     bubbleHtml.includes(w.eval('MP_DROP_PATH')),
     bubbleHtml.slice(0, 120));
  ok('Die Spitze sitzt auf dem Ort, nicht die Mitte',
     (() => { const ic = w.eval("mpDropIcon('trip', 12)");
              return ic.iconAnchor[1] === ic.iconSize[1]; })(),
     'ein Tropfen, der mit seiner Mitte auf der Koordinate klebt, zeigt daneben');
  ok('…und die größte gehört zum meistbesuchten Ort',
     Math.max(...sizes) > Math.min(...sizes) * 1.4,
     `${Math.min(...sizes)} … ${Math.max(...sizes)}`);
  // **Anmerkung 163: die Größe ist ABSOLUT, nicht auf die größte Gruppe im
  // Bild normiert.** Sonst wäre dieselbe Zwölf beim Blättern mal groß und mal
  // klein, und die beiden Stufen rechneten zwei Größen für dasselbe Zeichen.
  const dropAt = n => w.eval(`mpDropIcon('trip', ${n}).iconSize[0]`);
  // Die Abstufung, die der Prüfstand oben nicht hergibt: mehr ist größer, und
  // zwar mit der Wurzel — sonst sähe der zehnfache Wert hundertfach aus.
  ok('Mehr Einträge, größere Marke',
     dropAt(1) < dropAt(8) && dropAt(8) < dropAt(30) && dropAt(30) < dropAt(59),
     [1, 8, 30, 59].map(n => `${n}:${dropAt(n)}`).join(' '));
  ok('…und zwar mit der Wurzel, nicht linear',
     (dropAt(59) - dropAt(1)) < (dropAt(8) - dropAt(1)) * 8,
     'linear wäre die 59 achtmal so weit von der 1 entfernt wie die 8');
  ok('…und unabhängig von der größten Gruppe im Bild',
     (() => { render('place', makeEvents(30, 3)); const a = dropAt(12);
              render('place', makeEvents(2000, 250)); return a === dropAt(12); })(),
     'normiert wäre dieselbe Zahl je nach Zeitraum eine andere Marke');

  // --- 4. Der Knopf im Hinweis tut, was er verspricht --------------------- //
  render('point', many);
  if (d.getElementById('mp-cap-fix')) {
    d.getElementById('mp-cap-fix').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('Der Knopf führt in eine Stufe, die alles zeigt',
       w.eval('mp.density') === 'near', w.eval('mp.density'));
  }

  // --- 5. Und dieselbe Zusage für die WEGE (Anmerkung 141) ---------------- //
  //
  // Gemeldet als „Vektorkarte an, dann Wochenansicht, alles friert ein, kein
  // Fehler im Log". Dahinter steckten dieselben zwei Sätze wie oben, nur eine
  // Ebene tiefer: `/api/tracks` schnitt bei 1000 ab und schwieg, und jeder Weg
  // wurde als SVG-Pfad in den DOM gelegt. Über einer Vektorkarte liegt dort
  // eine lebende WebGL-Leinwand, die bei jedem Bild neu zusammengesetzt wird —
  // deshalb fiel es genau dort auf und nirgends sonst.
  //
  // Geprüft wird nicht, ob es schnell ist (das kann jsdom nicht), sondern die
  // drei Eigenschaften, an denen es hing.
  lines.length = 0; calls.length = 0;
  // `.catch` ist Pflicht, nicht Vorsicht: gefahren gegen den kaputten Stand
  // (Anmerkung 108) bekommt der alte `drawTracks` die neue Antwortform und
  // wirft — ohne diesen Fang stirbt der Wächter mit einem Stack-Trace, statt
  // zu SAGEN, welche Zusage fehlt. Ein Wächter, der abstürzt, benennt nichts.
  let boom = null;
  await w.eval(`
    mapTracks = L.layerGroup(); mp.showTracks = true;
    mp.mode = 'week'; mp.periods = ['2024-W22']; mp.index = 0;
    drawTracks('2024-W22');`).catch(e => { boom = e; });
  await wait(60);
  ok('Die Wege-Ebene übersteht die Antwort des Servers', !boom,
     boom ? `${boom.message} — der Client liest eine andere Antwortform, als `
            + '`list_tracks` liefert' : '');
  const trackCall = calls.find(p => /api\/tracks/.test(p));
  ok('Die Wochenansicht holt Wege', !!trackCall, JSON.stringify(calls));
  ok('…mit einem Deckel in der Anfrage', /[?&]limit=\d+/.test(trackCall || ''),
     `${trackCall} — 1000 volle Punktlisten sind mehrere Megabyte je Klick`);
  ok('…und der Deckel ist kleiner als der alte 1000er',
     +((trackCall || '').match(/[?&]limit=(\d+)/) || [0, 99999])[1] <= 500,
     trackCall);
  ok('Ein Weg wird auf die LEINWAND gezeichnet',
     lines.length > 0 && lines.every(o => o.renderer && o.renderer._n === 'canvas'),
     `${lines.length} Linien, Renderer: ${JSON.stringify(lines.map(o => o.renderer))} — `
     + 'als SVG ist jede Linie ein DOM-Knoten, der bei jedem Verschieben neu projiziert wird');
  // `lines.length > 0` gehört in die Bedingung, nicht daneben: `every` auf
  // einer LEEREN Liste ist wahr. Gegen den kaputten Stand gefahren stand hier
  // erst „ok …und vereinfacht" über null gezeichneten Linien — eine Zusicherung,
  // die aus dem falschen Grund grün war (Anmerkung 108, schon zum zweiten Mal).
  ok('…und vereinfacht',
     lines.length > 0 && lines.every(o => (o.smoothFactor || 1) > 1),
     `${lines.length} Linien — ein Timeline-Pfad bringt hunderte Stützpunkte mit, `
     + 'die auf dieser Zoomstufe auf denselben Bildpunkt fallen');
  const tnote = d.getElementById('mp-track-note');
  ok('Es gibt einen Platz für den Hinweis', !!tnote,
     'ohne ihn kann die Karte nicht sagen, was sie weglässt');
  if (tnote) {
    ok('Die Deckelung steht AUF der Karte', tnote.style.display !== 'none',
       'sonst fehlen drei Wochen des Monats, und die Karte sieht vollständig aus');
    ok('…mit beiden Zahlen',
       /900/.test(tnote.textContent) && /\b2\b/.test(tnote.textContent),
       tnote.textContent);
    ok('…und im Kartenbereich, nicht in der Liste daneben', !!tnote.closest('.map-wrap'));

    // Und er verschwindet wieder, sobald er nicht mehr zutrifft.
    await w.eval("mp.showTracks = false; drawTracks('2024-W22');").catch(() => {});
    await wait(30);
    ok('Ohne Wege-Ebene steht kein Hinweis mehr', tnote.style.display === 'none',
       'ein Hinweis über einer leeren Ebene lügt');
  }

  console.log(fail ? `\nKarte: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nKarte: alles grün');
  process.exit(fail ? 1 : 0);
}, 120);
