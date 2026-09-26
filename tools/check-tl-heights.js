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
// Anmerkung 230 kam eine vierte dazu: **unveränderte Gruppen bleiben stehen**
// (dieselben Knoten), veränderte und aufgeklappte werden neu gebaut, und
// „N weitere anzeigen" läuft auf einem wiederverwendeten Knoten genau einmal.
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
const ev = (id, at) => ({
  id, title: 'Eintrag ' + id, category: 'event', source: 'manual',
  date_start: at, date_precision: 'exact', confirmed: 'confirmed',
  entities: [], metrics: [], media: [],
});
const EVENTS = Array.from({ length: 40 }, (_, n) =>
  ev('e' + n, new Date(START - n * 6 * 3600e3).toISOString().slice(0, 19)))
  // Anmerkung 230: ein Tag mit mehr als TL_GROUP_CAP (25) Einträgen, damit
  // „N weitere anzeigen" überhaupt erscheint.
  .concat(Array.from({ length: 30 }, (_, n) =>
    ev('v' + n, `2024-12-01T${String(8 + Math.floor(n / 4)).padStart(2, '0')}:${
      String((n % 4) * 15).padStart(2, '0')}:00`)));
// Eine „nachgeladene Seite": fünf ältere Tage.
const OLDER = Array.from({ length: 5 }, (_, n) =>
  ev('o' + n, `2024-11-${String(20 - n).padStart(2, '0')}T12:00:00`));

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
  // Seit Anmerkung 230 bleiben unveränderte Gruppen stehen — die Höhen-Mitnahme
  // betrifft nur NEU eingesetzte. Also hier jede Gruppe als verändert markieren.
  w.eval('TL_GROUP_HTML.clear(); renderTimeline();');
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
  w.eval('TL_GROUP_HTML.clear(); renderTimeline();');
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

  // (4) Anmerkung 230: was sich nicht geändert hat, bleibt stehen.
  const errors = [];
  w.addEventListener('error', e => errors.push(e.message || String(e.error)));
  const keyOf = n => n.dataset.tlKey;
  w.eval('renderTimeline();');
  const a = groups();
  w.eval('renderTimeline();');
  const b = groups();
  ok('Ohne Änderung bleibt jeder Knoten derselbe',
     a.length === b.length && a.every((n, i) => n === b[i]),
     `${a.filter((n, i) => n !== b[i]).length} von ${a.length} neu gebaut — dann wird wieder `
     + 'alles geparst, und genau das war der teure Teil');
  ok('…und in derselben Reihenfolge', a.map(keyOf).join() === b.map(keyOf).join());

  // Eine Gruppe, die NACH dem Einsetzen verändert wird (Aufklappen), wird neu
  // gebaut — ihre nachträglich geschriebenen Register-Einträge stimmen beim
  // nächsten Durchgang nicht mehr.
  const touched = b[1];
  touched.appendChild(d.createElement('div'));
  w.eval('renderTimeline();');
  const c = groups();
  ok('Eine nachträglich veränderte Gruppe wird neu gebaut',
     c[1] !== touched && c[1].dataset.tlKey === touched.dataset.tlKey,
     'ein aufgeklappter Knoten mit Indizes eines alten Durchgangs zeigte beim Klick auf falsche Einträge');
  ok('…und nur sie', c.every((n, i) => i === 1 || n === b[i]),
     `${c.filter((n, i) => i !== 1 && n !== b[i]).length} weitere neu gebaut`);

  // Nachladen: ältere Tage kommen HINTEN dazu, die vorderen bleiben stehen.
  w.eval(`tl.events = tl.events.concat(${JSON.stringify(OLDER)}); renderTimeline();`);
  const e = groups();
  ok('Nachladen hängt an und lässt die vorderen Gruppen stehen',
     e.length === c.length + OLDER.length && c.every((n, i) => n === e[i]),
     `${e.length} Gruppen, ${c.filter((n, i) => n !== e[i]).length} der alten neu gebaut`);
  ok('…und die neuen stehen hinten, in der Reihenfolge der Zeit',
     e.slice(c.length).map(keyOf).join() === '2024-11-20,2024-11-19,2024-11-18,2024-11-17,2024-11-16',
     e.slice(c.length).map(keyOf).join());
  const list = d.getElementById('timeline-list');
  ok('…und der Fuß steht darunter, genau einmal',
     list.querySelectorAll('#tl-load-more, #tl-more-baseline').length <= 1
     && !list.lastElementChild.classList.contains('tl-year')
     && [...list.children].filter(n => !n.classList.contains('tl-year')).length === 1,
     [...list.children].filter(n => !n.classList.contains('tl-year')).map(n => n.outerHTML.slice(0, 60)).join(' | '));

  // „N weitere anzeigen" auf einem WIEDERVERWENDETEN Knoten: genau ein Lauf.
  // Mit einem Horcher je Knopf bekäme der Knoten bei jedem Durchgang einen
  // weiteren, und der zweite schriebe auf einen schon ersetzten Knopf.
  const big = groups().find(n => n.dataset.tlKey === '2024-12-01');
  const more = big && big.querySelector('[data-tl-more]');
  ok('Der volle Tag bietet „weitere anzeigen" an', !!more);
  // Gezählt wird die ARBEIT, nicht das Bild: der zweite Horcher schriebe
  // `outerHTML` auf einen schon ersetzten Knopf, und das ist laut Spezifikation
  // still wirkungslos — das Bild stimmt, und jeder Klick baut die Karten doppelt.
  w.eval(`window.__items = 0; const __ri = renderItem;
          renderItem = x => { window.__items++; return __ri(x); };`);
  if (more) more.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(20);
  ok('…und ein Klick zeigt alle, ohne Fehler',
     big && big.querySelectorAll('.event-card').length === 30 && errors.length === 0,
     `${big && big.querySelectorAll('.event-card').length} Karten, Fehler: ${errors.join(' | ')}`);
  ok('…und baut die fünf fehlenden Karten genau einmal', w.__items === 5,
     `${w.__items} Karten gebaut — ein Horcher je Knopf sammelt sich auf einem `
     + 'wiederverwendeten Knoten mit jedem Durchgang an');
  w.eval('renderTimeline();');
  ok('…und danach wird der Tag wieder zugeklappt gebaut',
     groups().find(n => n.dataset.tlKey === '2024-12-01') !== big,
     'der Beobachter hat das Aufklappen nicht bemerkt');

  console.log(fail ? `\n${fail} Zusage(n) gebrochen` : '\nZeitstrahl-Höhen: alles grün');
  process.exit(fail ? 1 : 0);
}, 0);
