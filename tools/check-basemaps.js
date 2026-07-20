const fs = require('fs');
const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('offline'));
    w.matchMedia = () => ({ matches:false, addEventListener(){}, addListener(){} });
    w.L = new Proxy(function(){ return w.L; }, { get: () => w.L, apply: () => w.L });
  },
});
setTimeout(() => {
  const w = dom.window, ls = w.localStorage;
  let fail = 0;
  const ok = (n, c) => { console.log((c ? '  ok   ' : '  FAIL ') + n); if (!c) fail++; };
  const pick = k => { ls.setItem('lifedash_basemap', k); return w.currentBasemap(); };

  ok('Standard ist die themenabhängige Karte', w.basemapSetting() === 'auto');
  ok('auto liefert Carto-Kacheln', /cartocdn/.test(w.tileUrl()));
  ok('auto ist als themenabhängig markiert', pick('auto').followsTheme === true);
  ok('osm liefert tile.openstreetmap.org', /tile\.openstreetmap\.org/.test((pick('osm'), w.tileUrl())));
  ok('Satellit liefert Esri-Imagery', /World_Imagery/.test((pick('satellite'), w.tileUrl())));
  ok('Satellit folgt dem Theme NICHT', !pick('satellite').followsTheme);
  ok('OpenTopoMap deckelt den Zoom bei 17', pick('topo').maxZoom === 17);

  for (const k of ['auto', 'osm', 'topo', 'satellite']) {
    const b = pick(k);
    ok(`${k}: Attribution vorhanden`, typeof b.attribution() === 'string' && b.attribution().length > 5);
    ok(`${k}: URL hat {z}/{x}/{y}`, /\{z\}/.test(b.url()) && /\{x\}/.test(b.url()) && /\{y\}/.test(b.url()));
  }

  ls.setItem('lifedash_basemap', 'custom');
  ok('„Eigene Karte" ohne URL fällt auf auto zurück', w.basemapSetting() === 'auto');
  ls.setItem('lifedash_tileurl', 'https://t.example.org/{z}/{x}/{y}.png');
  ok('„Eigene Karte" mit URL greift', w.basemapSetting() === 'custom');
  ok('eigene URL wird verwendet', w.tileUrl() === 'https://t.example.org/{z}/{x}/{y}.png');
  ls.setItem('lifedash_basemap', 'quatsch');
  ok('unbekannter Wert fällt auf auto zurück', w.basemapSetting() === 'auto');

  // Einstellungsfelder + Validierung
  ls.removeItem('lifedash_tileurl');
  const url = w.document.getElementById('tile-url'), attr = w.document.getElementById('tile-attr');
  ok('Einstellungsfelder existieren', !!url && !!attr);
  url.value = 'https://kaputt.example.org/kacheln.png';
  w.document.getElementById('tile-save').click();
  ok('URL ohne Platzhalter wird abgelehnt', !ls.getItem('lifedash_tileurl'));
  url.value = 'https://t.example.org/{z}/{x}/{y}.png';
  attr.value = '© Testanbieter';
  w.document.getElementById('tile-save').click();
  ok('gültige URL wird gespeichert', ls.getItem('lifedash_tileurl') === url.value);
  ok('Attribution wird gespeichert', ls.getItem('lifedash_tileattr') === '© Testanbieter');

  console.log(fail ? `\n${fail} FEHLER` : '\nalle F13-Prüfungen bestanden');
  process.exit(fail ? 1 : 0);
}, 2500);
