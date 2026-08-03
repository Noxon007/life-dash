// Anmerkungen 155/156 — drei Statistik-Ansichten und die Ranglisten.
//
// Vier Zusagen, jede einzeln still brechbar:
//
//   1. **Es sind wirklich drei Ansichten.** Wenn das Umschalten nur die
//      Reiterleiste einfärbt und alle Kacheln weiter untereinander stehen,
//      sieht das Ergebnis fast genauso aus wie vorher — nur mit einer Leiste
//      darüber. Geprüft wird deshalb, WAS sichtbar ist, nicht was aktiv heißt.
//   2. **Die Ranglisten kommen erst beim Ansehen** (A37). Ein Endpunkt, der
//      schon beim Öffnen des Reiters mitgeholt wird, ist keine dritte Ansicht,
//      sondern ein größerer Überblick.
//   3. **Die gemerkte Ansicht ist die gezeigte** — dieselbe Falle wie bei der
//      Sammlungs-Sortierung (Anmerkung 149): der Zustand nach dem ersten
//      Laden ist der, den niemand prüft, weil jeder Test vorher klickt.
//   4. **Tage führen, Einträge stehen daneben** (Anmerkung 143/148), und eine
//      Wetter-Zeile führt zu ihrem TAG (Anmerkung 142) — nicht in den
//      Bearbeiten-Dialog des Eintrags, der zufällig den Messwert trägt.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-stats-panes.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};
const wait = ms => new Promise(r => setTimeout(r, ms));
const inPage = (w, code) => { try { return w.eval(code); } catch (e) { return `FEHLER: ${e.message}`; } };

// Absichtlich unverwechselbare Zahlen (Regel aus check-a46-visit-split.js).
const TOPLISTS = {
  weather: {
    hot: [{ value: 38.4, id: 'e1', title: 'Andalusien', date_start: '2019-06-26T14:00:00',
            date_precision: 'day', place: 'Sevilla' },
          { value: 31.5, id: 'e2', title: 'Balkon', date_start: '2022-07-19T15:00:00',
            date_precision: 'day', place: 'Detmold' }],
    cold: [], sunny: [], rainy: [], windy: [], snowy: [], gust: [],
    felt_hot: [], felt_cold: [], longest_day: [], shortest_day: [],
  },
  places: [{ name: 'Kaiserstraße 5', days: 4711, events: 8123 }],
  cities: [{ name: 'Schwerin', days: 317, events: 902 }],
  countries: [{ name: 'Portugal', days: 129, events: 431 }],
  years: [{ name: '2019', days: 288, events: 640 }],
  categories: [{ name: 'meal', days: 205, events: 519 }],
  streaks: {
    longest_run: { from: '2019-01-01', to: '2019-03-12', days: 71 },
    longest_gap: { from: '2003-02-01', to: '2003-04-30', days: 89 },
    longest_trip: { id: 't1', title: 'Interrail', from: '2011-07-01',
                    to: '2011-07-24', days: 24 },
  },
};
const OVERVIEW = {
  counts: { events: 2, unconfirmed: 0, places: 1, cities: 1, concerts: 0,
            milestones: 0, meals: 0, moves: 0 },
  birth: null, age: null, per_year: [[2019, 2]], per_category: [['event', 2]],
  top_places: [['Kaiserstraße 5', 4711]], top_cities: [['Schwerin', 317]],
  top_animals: [], extremes: {}, weather: { days: 0 },
};

function makeDom(stored) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w.L = new Proxy(function () { return w.L; },
        { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
      // Eine gemerkte Ansicht, die NICHT die Voreinstellung ist — sonst prüft
      // dieser Wächter nur den frisch geklickten Zustand, und der ist immer
      // stimmig (die Lehre aus check-comp-sort.js).
      if (stored) w.localStorage.setItem('ld_stats_pane', stored);
      w.fetch = (u, opt) => {
        const p = String(u);
        calls.push([(opt && opt.method) || 'GET', p]);
        let body = [];
        if (/stats\/toplists/.test(p)) body = TOPLISTS;
        else if (/stats\/overview/.test(p)) body = OVERVIEW;
        else if (/stats\/widgets/.test(p)) body = [];
        else if (/events\/index/.test(p)) body = { revision: 'r1', total: 2, dated: 2,
          undated: 0, unconfirmed: 0, years: [{ year: 2019, count: 2 }] };
        else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
        else if (/api\/compendium\//.test(p)) body = [];
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      };
    },
  });
}

// Sichtbar heißt: der Kasten selbst steht nicht auf display:none.
const visiblePanes = d => [...d.querySelectorAll('#view-stats .stats-pane')]
  .filter(p => p.style.display !== 'none').map(p => p.dataset.statsPane);

setTimeout(async () => {
  // --- 1. Der erste Blick: gemerkt ist „Diagramme" ------------------------ //
  {
    const w = makeDom('charts').window, d = w.document;
    await wait(160);
    calls.length = 0;
    await w.loadStats();
    await wait(120);
    ok('Es gibt drei Ansichten',
       d.querySelectorAll('#view-stats .stats-pane').length === 3,
       `${d.querySelectorAll('#view-stats .stats-pane').length} Bereiche`);
    ok('Die gemerkte Ansicht ist die gezeigte',
       visiblePanes(d).join(',') === 'charts',
       `sichtbar: ${visiblePanes(d).join(', ') || '(nichts)'}`);
    const active = d.querySelector('#stats-tabs .zoom-btn.active');
    ok('…und die Leiste sagt dasselbe', active && active.dataset.stats === 'charts',
       `aktiv: ${active && active.dataset.stats}`);
    // A37: die teure Antwort erst beim Ansehen.
    ok('Die Ranglisten werden dabei NICHT geholt',
       !calls.some(([, p]) => /toplists/.test(p)),
       'ein Endpunkt, der immer mitkommt, ist keine eigene Ansicht');
    // Gegenprobe: die Kacheln sind nicht weg, nur nicht dran.
    ok('Die Kacheln sind gefüllt, auch wenn sie gerade nicht dran sind',
       d.getElementById('stat-events').textContent === '2',
       d.getElementById('stat-events').textContent);
    w.close();
  }

  // --- 2. Umschalten auf die Ranglisten ----------------------------------- //
  const dom = makeDom('tiles');
  const w = dom.window, d = w.document;
  await wait(160);
  await w.loadStats();
  await wait(120);
  ok('Voreingestellt sind die Zahlen', visiblePanes(d).join(',') === 'tiles',
     `sichtbar: ${visiblePanes(d).join(', ')}`);

  calls.length = 0;
  const topsTab = d.querySelector('#stats-tabs [data-stats="tops"]');
  ok('Es gibt einen Reiter für die Ranglisten', !!topsTab);
  if (topsTab) topsTab.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(200);
  ok('Der Klick zeigt die Ranglisten', visiblePanes(d).join(',') === 'tops',
     `sichtbar: ${visiblePanes(d).join(', ')}`);
  ok('…und holt sie erst jetzt', calls.some(([, p]) => /toplists/.test(p)),
     JSON.stringify(calls.map(c => c[1])));
  ok('…und merkt sich die Wahl',
     inPage(w, "localStorage.getItem('ld_stats_pane')") === 'tops',
     'ohne localStorage ist es keine Einstellung, sondern eine Wiederholung');

  const tops = d.getElementById('stats-tops');
  ok('Es gibt einen Kasten für die Ranglisten', !!tops);
  const txt = (tops ? tops.textContent : '').replace(/\s+/g, ' ');

  // --- 3. Tage führen, Einträge stehen daneben ---------------------------- //
  ok('Die Ortsliste nennt die Tage', /4[.,]711/.test(txt), txt.slice(0, 200));
  ok('…und die Einträge daneben', /8[.,]123/.test(txt), txt.slice(0, 200));
  ok('Städte, Länder, Jahre und Kategorien stehen da',
     /Schwerin/.test(txt) && /Portugal/.test(txt) && /2019/.test(txt)
     && /317/.test(txt) && /129/.test(txt),
     txt.slice(0, 300));
  ok('Die Serien stehen da', /71/.test(txt) && /89/.test(txt) && /Interrail/.test(txt),
     txt.slice(0, 300));

  // --- 4. Die Wetterliste ist die Kachel, nur ganz ------------------------ //
  ok('Die Wetter-Rangliste zeigt alle Plätze', /38[.,]4/.test(txt) && /31[.,]5/.test(txt),
     txt.slice(0, 300));
  ok('…mit Ort und Anlass', /Sevilla/.test(txt) && /Andalusien/.test(txt),
     txt.slice(0, 300));
  // Anmerkung 142: der Klick führt zum TAG.
  const row = tops && tops.querySelector('[data-top-day]');
  ok('Eine Wetter-Zeile trägt ihren Tag', !!row && row.dataset.topDay === '2019-06-26',
     `${row && row.dataset.topDay}`);
  if (row) {
    row.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(120);
    ok('…und der Klick führt in den Zeitstrahl DIESES Tages',
       inPage(w, 'tl.day') === '2019-06-26',
       `tl.day = ${inPage(w, 'tl.day')} — nicht in den Bearbeiten-Dialog eines `
       + 'Eintrags, der zufällig den Messwert trägt (Anmerkung 142)');
  }

  console.log(fail ? `\nAnm. 155/156: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nAnm. 155/156: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
