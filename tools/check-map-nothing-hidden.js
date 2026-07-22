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
      polyline: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
      latLngBounds: () => ({ pad: () => ({}) }),
      divIcon: () => ({}), control: { layers: () => ({ addTo() {} }) },
    };
    w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
  },
});

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};

setTimeout(() => {
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
    ok('…mit beiden Zahlen', /1\.?703/.test(note().textContent)
       && /2\.?003/.test(note().textContent), note().textContent);
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

  console.log(fail ? `\nKarte: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nKarte: alles grün');
  process.exit(fail ? 1 : 0);
}, 120);
