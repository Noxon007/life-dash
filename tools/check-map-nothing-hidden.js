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
      marker: ll => ({ addTo(l) { placed.push([l && l._n, ll[0], ll[1]]); return this; },
                       bindPopup() { return this; }, bindTooltip() { return this; },
                       on() { return this; } }),
      circleMarker: () => ({ addTo() { return this; }, bindTooltip() { return this; },
                             bindPopup() { return this; } }),
      polyline: (pts, opt) => { lines.push(opt || {});
                                return { addTo() { return this; }, bindPopup() { return this; } }; },
      // Muss es GEBEN: fehlt `L.canvas`, fällt `mpCanvas()` still auf Leaflets
      // Standard-Renderer zurück — also auf genau das SVG, dessen Zeichenlast
      // die Wochenansicht eingefroren hat. Ein Doppel ohne diese Funktion
      // prüfte einen Zustand, in dem die Prüfung nicht scheitern KANN.
      canvas: () => ({ _n: 'canvas' }),
      latLngBounds: () => ({ pad: () => ({}) }),
      divIcon: () => ({}), control: { layers: () => ({ addTo() {} }) },
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
  const render = (condense, events) => {
    placed.length = 0;
    w.eval(`
      mapObj = L.map('map'); mapMarkers = L.layerGroup();
      mapCluster = L.markerClusterGroup(); mapRoute = L.layerGroup();
      mapTracks = L.layerGroup();
      mp.located = ${JSON.stringify(events)};
      mp.mode = 'month'; mp.catFilter = new Set(FILTER_CATS_BASE.concat(['event']));
      mp.periods = ['2024-05']; mp.index = 0; mp.condense = ${condense};
      renderPeriod();`);
  };
  const far = () => placed.filter(p => p[2] < -50).length;

  // --- 1. Der Normalfall: nichts wird weggelassen, nichts wird behauptet -- //
  render(false, makeEvents(20, 8));
  ok('Kleine Menge: alle Punkte auf der Karte', placed.length === 23,
     `${placed.length} Marker`);
  ok('…und kein Hinweis, der nicht zutrifft', !noteVisible());

  // --- 2. Der gemeldete Fall ---------------------------------------------- //
  const many = makeEvents(2000, 250);
  render(false, many);
  const droppedOff = placed.length < many.length;
  ok('Ohne Bündelung deckelt die Karte (Vorbedingung des Berichts)', droppedOff,
     `${placed.length} von ${many.length} — der Deckel greift nicht mehr?`);
  if (droppedOff) {
    ok('…und sagt es AUF DER KARTE', noteVisible(),
       'genau die Stille, die den Bericht ausgelöst hat');
    // Der Tausendertrenner hängt seit Anmerkung 114 an der Sprache (LOC()):
    // „1.703" auf Deutsch, „1,703" auf Englisch. Beides ist dieselbe Zahl —
    // die Prüfung gilt der ZAHL, nicht dem Punkt.
    ok('…mit beiden Zahlen', /1[.,]?703/.test(note().textContent)
       && /2[.,]?003/.test(note().textContent), note().textContent);
    ok('…und mit dem Weg hinaus', !!d.getElementById('mp-cap-fix'),
       'ein Hinweis ohne Ausweg ist eine Entschuldigung');
  }

  // --- 3. Mit Bündelung ist wirklich alles da ----------------------------- //
  render(true, many);
  ok('Mit Bündelung sind die seltenen Orte da', far() === 3,
     `${far()} von 3 Amerika-Punkten — das war der Bericht`);
  ok('…und der Hinweis verschwindet wieder', !noteVisible(),
     'ein Hinweis, der über einer vollständigen Karte stehen bleibt, lügt');

  // --- 4. Der Knopf im Hinweis tut, was er verspricht --------------------- //
  render(false, many);
  if (d.getElementById('mp-cap-fix')) {
    d.getElementById('mp-cap-fix').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    ok('Der Knopf schaltet die Bündelung ein', w.eval('mp.condense') === true);
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
