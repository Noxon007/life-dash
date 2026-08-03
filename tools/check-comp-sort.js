// Anmerkungen 148/149 — die Sammlung sortiert nach TAGEN, und sie zeigt sie auch.
//
// Drei Zusagen, jede einzeln still brechbar:
//
//   1. **Die Reihenfolge ist die Antwort.** Eine Kachelwand macht von sich aus
//      genau eine Aussage: welche zuerst kommt. Kommt die Sortierung nicht an,
//      sieht die Wand aus wie vorher — der Defekt ist unsichtbar, solange man
//      nicht weiß, wer oben stehen müsste.
//   2. **Tage führen, Einträge stehen daneben** (Anmerkung 143). Beide Zahlen
//      müssen auf der Kachel stehen; „11.203 Einträge" allein ist nach einem
//      Timeline-Import eine Aussage über den Import.
//   3. **Der gemerkte Zustand wird angezeigt** (A40): steht „Tage" aktiv da,
//      muss auch nach Tagen sortiert sein — und umgekehrt.
//
// Geprüft wird am HERGESTELLTEN Zustand, nicht am Auslieferungs-Markup: die
// Reiterleiste wird beim Laden der Module ersetzt, und ein Wächter, der das
// nackte HTML liest, prüft einen Zustand, den niemand zu sehen bekommt (A42,
// `check-a41-cities.js`).
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-comp-sort.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const fails = [], ok = [];
const check = (name, cond, detail = '') =>
  (cond ? ok : fails).push(name + (cond ? '' : ` — ${detail}`));

// Die Antworten des Servers, absichtlich NICHT nach Tagen vorsortiert: der
// Server sortiert nach Namen, das Sortieren ist Sache dieser Seite. Käme die
// Prüfmenge schon richtig herein, wäre jede Zusicherung aus dem falschen Grund
// grün (Anmerkung 108).
const ENTITIES = [
  { id: 'a', name: 'Albanien', confirmed: 'confirmed', day_count: 2, event_count: 90, attributes: {} },
  { id: 'b', name: 'Belgien', confirmed: 'confirmed', day_count: 40, event_count: 41, attributes: {} },
  { id: 'c', name: 'Chile', confirmed: 'unconfirmed', day_count: 9, event_count: 9, attributes: {} },
];
const CITIES = [
  { name: 'Aachen', country: 'Deutschland', day_count: 3, event_count: 300, place_count: 1,
    first_visit: '2020-01-01T00:00:00', last_visit: '2020-01-03T00:00:00' },
  { name: 'Bremen', country: 'Deutschland', day_count: 60, event_count: 61, place_count: 2,
    first_visit: '2019-01-01T00:00:00', last_visit: '2024-01-01T00:00:00' },
];

const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = (url) => {
      const u = String(url);
      const body = /\/api\/cities(\?|$)/.test(u) ? CITIES
        : /\/api\/compendium\//.test(u) ? ENTITIES
        : null;
      if (body === null) return Promise.reject(new Error('offline'));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    };
    w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, addListener() {} }));
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.addEventListener('error', e => errors.push('ERROR: ' + (e.error && e.error.stack || e.message)));
    // Eine gemerkte Wahl, die NICHT die Voreinstellung ist. Ohne sie prüft
    // dieser Wächter nur den frisch geklickten Zustand — und der ist immer
    // stimmig. Der Fall, der auffällt, ist der ERSTE Blick nach dem Laden:
    // Leiste sagt „Tage", Kacheln stehen alphabetisch (A40).
    w.localStorage.setItem('ld_comp_sort', 'name');
  },
});

const wait = ms => new Promise(r => setTimeout(r, ms));

setTimeout(async () => {
  const w = dom.window, d = w.document;
  check('lädt ohne Fehler',
        errors.filter(e => !/offline|Not implemented|fetch/i.test(e)).length === 0,
        errors[0] || '');

  const names = () => [...d.querySelectorAll('#compendium-grid .comp-name')]
    .map(x => x.textContent.trim());
  const setSort = async s => {
    const chip = d.querySelector(`#comp-sort [data-sort="${s}"]`);
    if (!chip) return false;
    chip.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(60);
    return true;
  };

  check('es gibt eine Sortierleiste', !!d.getElementById('comp-sort'),
        'ohne sie ist die Reihenfolge nicht wählbar');
  check('beide Sortierungen sind da',
        !!d.querySelector('#comp-sort [data-sort="days"]')
        && !!d.querySelector('#comp-sort [data-sort="name"]'));

  // --- 0. Der erste Blick nach dem Laden ---------------------------------- //
  // Gemerkt ist „Name" (siehe beforeParse). Die Leiste muss das SOFORT zeigen,
  // ohne dass jemand klickt, und die Kacheln müssen dazu passen.
  const activeNow = () => {
    const a = d.querySelector('#comp-sort .filter-chip.active');
    return a ? a.dataset.sort : null;
  };
  check('die gemerkte Wahl steht schon beim Laden in der Leiste',
        activeNow() === 'name',
        `aktiv: ${activeNow()} — die Leiste sagt etwas anderes als sie tut`);
  if (typeof w.loadCompendium === 'function') {
    await w.loadCompendium('country');
    await wait(60);
    const shown = [...d.querySelectorAll('#compendium-grid .comp-name')]
      .map(x => x.textContent.trim()).join(',');
    check('und die Kacheln stehen von Anfang an so da',
          shown === 'Albanien,Belgien,Chile', `Reihenfolge: ${shown}`);
  }

  // --- 1. Entities: Tage führen ------------------------------------------- //
  if (typeof w.loadCompendium !== 'function') {
    check('loadCompendium vorhanden', false);
  } else {
    check('„nach Tagen" ist wählbar', await setSort('days'));
    await w.loadCompendium('country');
    await wait(60);
    check('Länder stehen nach Tagen, die meisten zuerst',
          names().join(',') === 'Belgien,Chile,Albanien',
          `Reihenfolge: ${names().join(', ')}`);

    const first = d.querySelector('#compendium-grid .comp-count');
    const txt = first ? first.textContent.replace(/\s+/g, ' ') : '';
    // 40 Tage / 41 Einträge sind absichtlich fast gleich: eine Kachel, die
    // versehentlich zweimal dieselbe Zahl zeigt, fällt bei „12 / 3400" nicht
    // auf, hier schon.
    check('die Kachel nennt die Tage', /40\D/.test(txt), `Kachel: „${txt}"`);
    check('die Kachel nennt die Einträge daneben', /41\D/.test(txt), `Kachel: „${txt}"`);

    check('„nach Namen" ist wählbar', await setSort('name'));
    await w.loadCompendium('country');
    await wait(60);
    check('nach Namen steht es alphabetisch',
          names().join(',') === 'Albanien,Belgien,Chile',
          `Reihenfolge: ${names().join(', ')}`);
  }

  // --- 2. Städte folgen derselben Wahl ------------------------------------ //
  // Der Städte-Reiter ist der einzige, der nicht aus einem Modul kommt (A42) —
  // und war deshalb schon einmal der, der eine Neuerung nicht mitbekam.
  if (typeof w.loadCities === 'function') {
    await setSort('days');
    await w.loadCities();
    await wait(60);
    check('Städte folgen derselben Sortierung',
          names().join(',') === 'Bremen,Aachen',
          `Reihenfolge: ${names().join(', ')}`);
  }

  // --- 3. Der angezeigte Zustand ist der wirksame ------------------------- //
  const bar = () => d.getElementById('comp-sort');
  const active = () => {
    const a = d.querySelector('#comp-sort .filter-chip.active');
    return a ? a.dataset.sort : null;
  };
  await setSort('name');
  check('die Leiste zeigt die gewählte Sortierung', active() === 'name',
        `aktiv: ${active()}`);
  await setSort('days');
  check('und wechselt mit ihr', active() === 'days', `aktiv: ${active()}`);
  check('die Wahl wird gemerkt',
        (() => { try { return w.localStorage.getItem('ld_comp_sort') === 'days'; }
                 catch (_) { return false; } })(),
        'ohne localStorage ist es keine Einstellung, sondern eine Wiederholung');

  // --- 4. Eine Detailseite hat nichts zu sortieren ------------------------- //
  if (typeof w.openEntityDetail === 'function') {
    await w.openEntityDetail('country', 'a', 'Albanien');
    await wait(60);
    check('auf der Detailseite ist die Leiste weg',
          !!bar() && bar().style.display === 'none',
          'eine Sortierleiste über einer einzelnen Seite bedient nichts (A40)');
  }

  ok.forEach(n => console.log('  ok  ' + n));
  fails.forEach(n => console.log('  XX  ' + n));
  console.log(fails.length ? `\n${fails.length} Prüfung(en) fehlgeschlagen`
                           : '\nAnm. 148/149: alles grün');
  process.exit(fails.length ? 1 : 0);
}, 2500);
