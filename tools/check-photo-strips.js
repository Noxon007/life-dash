// Fotoleisten im Zeitstrahl: eine je Zoomstufe, und die Beschriftung sagt die
// Wahrheit (Anmerkung 110).
//
// Gemeldet wurde: „Fotos dieses Tages wird bei Woche/Monat für die Tage
// untereinander gepackt". Stimmt — es gab nur eine Regel (eine Leiste je Tag),
// und im Monatszoom wurden daraus dreißig Leisten mit hunderten Vorschaubildern.
// Entschieden wurde: Woche bündeln, ab Monat **zwölf Bilder als Auswahl**.
//
// Eine Auswahl, die sich nicht als Auswahl zu erkennen gibt, ist eine
// Behauptung — deshalb prüft dieser Wächter vor allem die BESCHRIFTUNG. Und er
// prüft den Betrachter: solange eine Leiste genau einen Tag umfasste, konnte
// man die Bilder über das Datum nachschlagen; sobald sie eine Woche umfasst,
// wäre das der Satz des ersten Tages — falsche Bilder hinter dem Klick.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-photo-strips.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

// Drei Tage einer Woche, zusammen 40 Bilder.
const DAYS = { '2024-05-06': 20, '2024-05-07': 15, '2024-05-08': 5 };
const media = {};
Object.entries(DAYS).forEach(([d, n]) => {
  media[d] = Array.from({ length: n }, (_, i) => ({
    id: `${d}-${i}`, thumb_url: `/api/media/${d}-${i}/thumb`,
    url: `/api/media/${d}-${i}/file`, caption: '', provider: 'local',
  }));
});
const events = Object.keys(DAYS).map((d, i) => ({
  id: 'e' + i, title: 'Ereignis ' + i, category: 'event', confidence: 1,
  date_start: `${d}T12:00:00`, date_precision: 'day', confirmed: 'confirmed',
  source: 'manual', entities: [], metrics: [], media: [],
}));

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
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
  const render = zoom => {
    w.eval(`
      TL_DAY_MEDIA.clear();
      ${Object.entries(media).map(([k, v]) =>
        `TL_DAY_MEDIA.set(${JSON.stringify(k)}, ${JSON.stringify(v)});`).join('\n')}
      tl.events = ${JSON.stringify(events)};
      tl.zoom = ${JSON.stringify(zoom)};
      tl.catFilter = new Set(FILTER_CATS_BASE.concat(['event']));
      tl.query = ''; tl.done = true;
      renderTimelineList();`);
    return [...d.querySelectorAll('[data-day-media]')];
  };

  // --- 1. Tag: je Tag eine Leiste, wie bisher ---------------------------- //
  let strips = render('day');
  ok('Tageszoom: eine Leiste je Tag', strips.length === 3, `${strips.length} Leisten`);
  ok('…und sie heißt nach dem Tag',
     /dieses Tages|this day/i.test(strips[0].textContent), strips[0].textContent.trim());

  // --- 2. Woche: EINE Leiste, alle Bilder --------------------------------- //
  strips = render('week');
  ok('Wochenzoom: nur noch eine Leiste', strips.length === 1,
     `${strips.length} Leisten — die Tage stapeln sich wieder`);
  if (strips.length === 1) {
    const imgs = strips[0].querySelectorAll('img').length;
    ok('…mit allen 40 Bildern der Woche', imgs === 40, `${imgs} Bilder`);
    ok('…und sie heißt nach der Woche',
       /Woche|week/i.test(strips[0].textContent), strips[0].textContent.trim());
  }

  // --- 3. Monat: Auswahl, und sie sagt es -------------------------------- //
  strips = render('month');
  ok('Monatszoom: eine Leiste', strips.length === 1, `${strips.length} Leisten`);
  if (strips.length === 1) {
    const imgs = strips[0].querySelectorAll('img').length;
    ok('…gedeckelt auf zwölf Bilder', imgs === 12, `${imgs} Bilder`);
    const label = strips[0].textContent;
    ok('…und die Beschriftung nennt beide Zahlen', /12/.test(label) && /40/.test(label),
       `"${label.trim()}" — eine Auswahl, die sich nicht als solche zeigt, behauptet Vollständigkeit`);
  }

  // --- 4. Der Betrachter zeigt die Bilder DIESER Leiste ------------------- //
  // Der Fehler, der beim Bauen entstand: die Bilder über das Datum
  // nachzuschlagen ergab bei einer Wochenleiste den Satz des ersten Tages.
  render('week');
  let opened = null;
  w.eval('window.__origLb = openLightbox; openLightbox = (m, i) => { window.__lb = { n: m.length, i }; };');
  const img = d.querySelectorAll('[data-day-media] img')[25];
  if (img) {
    img.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    opened = w.__lb;
  }
  ok('Klick öffnet den Betrachter mit der ganzen Wochenleiste',
     opened && opened.n === 40, JSON.stringify(opened));
  ok('…und beim angeklickten Bild', opened && opened.i === 25, JSON.stringify(opened));

  console.log(fail ? `\nFotoleisten: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nFotoleisten: alles grün');
  process.exit(fail ? 1 : 0);
}, 100);
