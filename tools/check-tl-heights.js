// Anmerkung 227 — der Zeitstrahl zeichnet nur, was man sieht, und springt
// dabei nicht.
//
// Die Gruppen tragen `content-visibility: auto`: Chrome lässt Layout und Malen
// für alles außerhalb des Bildschirms aus. Im Tages-Zoom waren das zwei Drittel
// der Zeit je nachgeladener Seite (1.800 Einträge, 44.500 Knoten: 435 → 105 ms,
// unter vierfacher CPU-Drossel 2,5 → 0,7 s).
//
// **Der Preis dafür ist eine Zusage, die man leicht bricht.** Der Browser merkt
// sich die Höhe einer gezeichneten Gruppe AM ELEMENT, und `renderTimelineList`
// ersetzt per `innerHTML` jedes Element. Ohne Gegenmaßnahme fiel bei jeder
// Seite alles über dem Bildschirm auf die Schätzung zurück, und die Ansicht
// sprang um eine halbe Million Pixel — gemessen, nicht vermutet. Die
// Gegenmaßnahme liest die Höhen VOR dem Neuaufbau und schreibt sie danach als
// Platzhalter zurück, je Gruppe über ihren Schlüssel.
//
// Drei Zusagen, alle gegen den kaputten Stand gefahren:
//   1. Jede Gruppe trägt ihren Schlüssel (sonst findet die Höhe nicht zurück).
//   2. Nach einem Neuaufbau trägt jede Gruppe GENAU ihre alte Höhe — mit
//      Nachkommastellen: gerundet summiert sich der Fehler über tausend Gruppen.
//   3. Die Regel selbst steht im CSS, und der Rand der Zeitlinie gehört der
//      Gruppe: `content-visibility` schneidet ab, was über den Kasten
//      hinausragt, und die Punkte (`left:-30px`) ragen hinaus.
//
// **Was jsdom nicht kann:** Layout. `getBoundingClientRect` ist dort immer
// null — die Höhen werden deshalb je Element vorgegeben und nicht gemessen. Den
// Sprung selbst misst nur ein echter Browser; die Zahlen oben stammen daher.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-tl-heights.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

const START = new Date('2024-12-31T12:00:00Z').getTime();
// Ein Eintrag je sechs Stunden: 40 Einträge über zehn Tage, also zehn Gruppen
// im Tages-Zoom.
const EVENTS = Array.from({ length: 40 }, (_, n) => ({
  id: 'e' + n, title: 'Eintrag ' + n, category: 'event', source: 'manual',
  date_start: new Date(START - n * 6 * 3600e3).toISOString().slice(0, 19),
  date_precision: 'exact', confirmed: 'confirmed', entities: [], metrics: [], media: [],
}));

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    const base = new Proxy(function () { return base; }, {
      get: (_t, k) => (k === 'getZoom' ? () => 6 : base), apply: () => base,
    });
    w.L = base;
    w.fetch = u => {
      const p = String(u);
      let body = [];
      if (/api\/events\?/.test(p)) body = EVENTS;
      else if (/events\/index/.test(p)) {
        body = { total: 40, dated: 40, undated: 0, unconfirmed: 0, fuzzy: 0, visits: 0,
                 photo_events: 0, machine_proposals: 0, years: [{ year: 2024, count: 40 }],
                 baseline_days: 0, baseline_years: [] };
      } else if (/days\/(baseline|media|weather)/.test(p)) body = {};
      else if (/auth\/config/.test(p)) body = { mode: 'dev' };
      else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
      else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
      else if (/\/api\/modules/.test(p)) body = [];
      else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
      else if (/\/api\/jobs/.test(p)) body = [];
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
  await wait(200);
  w.eval("tl.zoom = 'day'; tl.autoPages = 99;");
  await w.loadTimeline();
  await wait(100);

  const groups = () => [...d.querySelectorAll('#timeline-list .tl-year')];
  const first = groups();
  ok('Der Tages-Zoom hat mehrere Gruppen', first.length >= 5, `${first.length} Gruppen`);

  // (1) Schlüssel
  const keys = first.map(g => g.dataset.tlKey);
  ok('Jede Gruppe trägt ihren Schlüssel', keys.length && keys.every(Boolean),
     `${keys.filter(Boolean).length} von ${keys.length} — ohne ihn findet die `
     + 'gemessene Höhe nach dem Neuaufbau nicht zu ihrer Gruppe zurück');
  ok('…und jeder Schlüssel ist eindeutig', new Set(keys).size === keys.length,
     'zwei Gruppen mit einem Schlüssel tauschten ihre Höhen');

  // (2) Höhen über den Neuaufbau. Jede Gruppe bekommt eine eigene, krumme
  // Höhe — gleich hohe Gruppen könnten eine Verwechslung nicht zeigen.
  const want = new Map();
  first.forEach((g, i) => {
    const h = 100 + i * 37.25;
    want.set(g.dataset.tlKey, h);
    g.getBoundingClientRect = () => ({ top: 0, left: 0, right: 0, bottom: h, width: 0, height: h });
  });
  w.eval('renderTimeline();');
  const second = groups();
  ok('Der Neuaufbau ersetzt die Elemente (sonst prüft das hier nichts)',
     second.length && second[0] !== first[0],
     'dieselben Elemente behielten ihre Höhe ohnehin');
  const bad = second.filter(g => {
    const m = /contain-intrinsic-size:\s*auto\s+([\d.]+)px/.exec(g.getAttribute('style') || '');
    return !m || Math.abs(+m[1] - want.get(g.dataset.tlKey)) > 1e-6;
  });
  ok('Nach dem Neuaufbau trägt jede Gruppe genau ihre alte Höhe', bad.length === 0,
     `${bad.length} von ${second.length} falsch, z. B. ${bad[0] && bad[0].dataset.tlKey}: `
     + `${bad[0] && bad[0].getAttribute('style')} statt ${bad[0] && want.get(bad[0].dataset.tlKey)}px `
     + '— ohne sie fällt alles über dem Bildschirm auf die Schätzung zurück, und die '
     + 'Ansicht springt beim Nachladen');

  // Eine Gruppe, die nie Layout hatte (Höhe 0), bekommt keinen Platzhalter
  // von null — sie stünde sonst als Strich da, bis sie ins Bild rollt.
  second.forEach(g => { g.getBoundingClientRect = () => ({ height: 0 }); });
  w.eval('renderTimeline();');
  ok('Ohne gemessene Höhe bleibt die Schätzung aus dem CSS',
     groups().every(g => !/contain-intrinsic-size/.test(g.getAttribute('style') || '')),
     groups().map(g => g.getAttribute('style')).join(' | '));

  // (3) Die Regel im CSS. Aus dem Quelltext gelesen: jsdom rechnet kein Layout,
  // und `getComputedStyle` kennt `content-visibility` dort nicht.
  const rule = (html.match(/\n\s*\.tl-year\s*\{([^}]*)\}/) || [])[1] || '';
  ok('Die Gruppe trägt content-visibility: auto', /content-visibility:\s*auto/.test(rule), rule);
  ok('…mit einer gemerkten Höhe (`auto` vor der Schätzung)',
     /contain-intrinsic-size:\s*auto\s+\d+px/.test(rule), rule);
  // Der Rand der Zeitlinie (`.timeline { padding-left: 32px }`) gehört der
  // Gruppe: sie rückt um genau so viel nach links und polstert es wieder auf.
  const gutter = +((html.match(/\.timeline\s*\{[^}]*padding-left:\s*(\d+)px/) || [])[1] || NaN);
  const inset = /margin:\s*0\s+0\s+\d+px\s+-(\d+)px/.exec(rule);
  const pad = /padding-left:\s*(\d+)px/.exec(rule);
  ok('…und der Rand der Zeitlinie liegt IN der Gruppe',
     inset && pad && +inset[1] === gutter && +pad[1] === gutter,
     `Rand ${gutter}px, Gruppe ${inset && inset[1]}/${pad && pad[1]} — sonst schneidet `
     + 'content-visibility die Punkte der Zeitlinie (left:-30px) ab');

  console.log(fail ? `\n${fail} Zusage(n) gebrochen` : '\nZeitstrahl-Höhen: alles grün');
  process.exit(fail ? 1 : 0);
}, 0);
