// A38 (Anmerkung 82): Wacht über den Mobil-Durchgang.
//
// Der Audit fand vier Defekte, die alle still waren — nichts an ihnen wirft
// einen Fehler, sie sind nur unbenutzbar. Genau deshalb ein Skript: eine
// spätere Änderung, die einen davon zurückbringt, fällt sonst erst dem
// nächsten auf, der die App auf dem Handy benutzt.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-a38-mobile.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const fails = [];
const ok = [];
const check = (name, cond, detail = '') =>
  (cond ? ok : fails).push(name + (cond ? '' : ` — ${detail}`));

// ---- Teil 1: statische Prüfungen am Quelltext -------------------------------
// Die Beschriftungsspalten der Einstellungen standen inline und waren damit
// aus keinem Media Query erreichbar (Inline schlägt Stylesheet). Geprüft wird
// nur, was in einem style="…"-Attribut steht — dieselbe Regel im Stylesheet
// ist in Ordnung, denn dort kann der Mobilblock sie aufheben.
const inlineWidths = [...html.matchAll(/style="[^"]*min-width:\s*\d+px[^"]*"/g)]
  .filter(m => !/max-width/.test(m[0]));
check('keine Inline-Breitenspalten mehr', inlineWidths.length === 0,
      `noch inline: ${inlineWidths.map(m => m[0].slice(0, 60)).join(' | ')}`);

// vh rechnet mit ausgeblendeter Adressleiste — was in vh gedeckelt ist, ragt
// auf dem Handy darunter. Betrifft nicht nur den Dialog aus der Audit-Liste,
// sondern jeden Höhendeckel; deshalb wird über die ganze Datei geprüft.
const vhHits = [...html.matchAll(/max-height:\s*\d+vh/g)].map(m => m[0]);
check('Höhendeckel in dvh statt vh', vhHits.length === 0, `noch vh: ${vhHits.join(', ')}`);

const mediaBlocks = (html.match(/@media \(max-width: 860px\)/g) || []).length;
check('Mobilblock existiert', mediaBlocks >= 1, 'kein 860px-Block gefunden');

// ---- Teil 2: im geladenen DOM ----------------------------------------------
const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('offline'));
    w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, addListener() {} }));
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
    w.addEventListener('error', e => errors.push('ERROR: ' + (e.error && e.error.stack || e.message)));
  },
});

setTimeout(() => {
  const w = dom.window, d = w.document;
  const fatal = errors.filter(e => !/offline|Not implemented|fetch/i.test(e));
  check('lädt ohne Fehler', fatal.length === 0, fatal.join(' | '));

  // Die untere Leiste trägt höchstens fünf Ziele; neun ergaben je ~40 px.
  const primary = d.querySelectorAll('.sidebar > .nav-item.nav-primary');
  const secondary = d.querySelectorAll('.sidebar > .nav-item[data-view]:not(.nav-primary)');
  check('vier Hauptziele in der Leiste', primary.length === 4, `sind ${primary.length}`);
  check('„Mehr“-Knopf vorhanden', !!d.getElementById('nav-more'));
  check('Sheet-Container vorhanden', !!d.getElementById('nav-sheet'));

  // Das Sheet wird aus der Sidebar geklont — kein zweites Menü zum Pflegen.
  if (typeof w.buildNavSheet === 'function') {
    w.buildNavSheet();
    const rows = d.querySelectorAll('#nav-sheet-items .nav-item');
    check('Sheet enthält alle übrigen Ziele', rows.length === secondary.length,
          `${rows.length} statt ${secondary.length}`);
    check('Sheet-Zeilen behalten ihre Übersetzung',
          [...rows].every(r => r.querySelector('[data-i18n]')),
          'ein Eintrag hat kein data-i18n mehr');
  } else {
    check('buildNavSheet existiert', false, 'Funktion nicht gefunden');
  }

  // Steckt die offene Ansicht hinter „Mehr“, muss „Mehr“ markiert sein —
  // sonst zeigt die Leiste gar keinen aktiven Punkt.
  if (typeof w.gotoView === 'function') {
    try {
      w.gotoView('world');
      check('„Mehr“ ist aktiv bei versteckter Ansicht',
            d.getElementById('nav-more').classList.contains('active'));
      w.gotoView('timeline');
      check('„Mehr“ ist inaktiv bei Hauptansicht',
            !d.getElementById('nav-more').classList.contains('active'));
    } catch (e) {
      check('gotoView läuft durch', false, e.message);
    }
  }

  // Der Zähler der Verwaltung muss auf „Mehr“ gespiegelt werden.
  check('Zähler auch auf „Mehr“', !!d.getElementById('nav-more-badge'));

  // Die Sidebar-Fußzeile ist mobil ausgeblendet — ohne Spiegelung ins Sheet
  // ist auf dem Handy nirgends ablesbar, welcher Stand läuft.
  if (typeof w.openNavSheet === 'function') {
    const fv = d.getElementById('foot-version');
    fv.textContent = 'v9.9.9-dev';
    fv.classList.add('is-dev');
    fv.title = 'main @ abc1234';
    try {
      w.openNavSheet();
      const sv = d.getElementById('sheet-version');
      check('Version im „Mehr“-Sheet', !!sv && sv.textContent === 'v9.9.9-dev',
            sv ? `steht dort „${sv.textContent}“` : 'kein #sheet-version');
      check('Testgleis auch im Sheet erkennbar',
            !!sv && sv.classList.contains('is-dev') && sv.title === 'main @ abc1234',
            'is-dev/Tooltip nicht gespiegelt');
      w.closeNavSheet();
    } catch (e) {
      check('openNavSheet läuft durch', false, e.message);
    }
  } else {
    check('openNavSheet existiert', false, 'Funktion nicht gefunden');
  }

  // Karte: Filter wegklappbar, Zeitraum bleibt am Knopf ablesbar.
  check('Karten-Filter klappbar', !!d.getElementById('mp-filter-toggle'));
  check('Zeitraum am Klapp-Knopf', !!d.getElementById('mp-filter-toggle-label'));

  ok.forEach(n => console.log('  ok  ' + n));
  fails.forEach(n => console.log('  XX  ' + n));
  console.log(fails.length ? `\n${fails.length} Prüfung(en) fehlgeschlagen` : '\nA38: alles grün');
  process.exit(fails.length ? 1 : 0);
}, 2500);
