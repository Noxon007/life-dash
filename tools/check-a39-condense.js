// A39 (Anmerkung 88): Verdichtung des Zeitstrahls nach Stadt.
//
// Geprüft wird die Eigenschaft, die still falsch werden kann: eine Karte, die
// mehrere Besuche vertritt, darf nicht wie ein einzelnes Ereignis aussehen und
// erst recht nicht wie eines bearbeitet werden. Der Fehler wäre unsichtbar —
// man bearbeitet dann irgendeinen der vertretenen Besuche, ohne es zu merken.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-a39-condense.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const fails = [], ok = [];
const check = (name, cond, detail = '') =>
  (cond ? ok : fails).push(name + (cond ? '' : ` — ${detail}`));

const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('offline'));
    w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, addListener() {} }));
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.addEventListener('error', e => errors.push('ERROR: ' + (e.error && e.error.stack || e.message)));
  },
});

const GROUPED = {
  id: 'rep-1', title: 'Besuch: Kaiserstraße 5, Bilk, Düsseldorf',
  category: 'event', confirmed: 'confirmed', confidence: 1,
  date_start: '2026-07-05T08:14:00', date_precision: 'exact',
  location: { id: 'l1', name: 'Kaiserstraße 5, Bilk, Düsseldorf', city: 'Düsseldorf' },
  entities: [], metrics: [], media: [],
  group: { city: 'Düsseldorf', count: 12,
           first: '2026-07-05T08:14:00', last: '2026-07-05T19:30:00' },
};
const SINGLE = { ...GROUPED, id: 'solo-1', group: null };

setTimeout(() => {
  const w = dom.window, d = w.document;
  check('lädt ohne Fehler',
        errors.filter(e => !/offline|Not implemented|fetch/i.test(e)).length === 0);

  if (typeof w.eventCard !== 'function') {
    check('eventCard vorhanden', false);
  } else {
    const grouped = w.eventCard(GROUPED);
    const single = w.eventCard(SINGLE);

    // Der Titel eines beliebigen Einzelbesuchs wäre als Titel der Gruppe falsch.
    check('Gruppe zeigt die Stadt, nicht die Straße',
          grouped.includes('Düsseldorf') && !grouped.includes('Kaiserstraße'),
          'Straßenname steht noch im Kopf der Sammelkarte');
    check('Gruppe nennt die Anzahl', /12/.test(grouped));
    check('Gruppe nennt die Zeitspanne',
          grouped.includes('08:14') && grouped.includes('19:30'),
          'Spanne fehlt — „12 Besuche“ allein lässt offen, wann');
    check('Gruppe ist als Sammelkarte markiert', grouped.includes('is-group'));
    check('Gruppe hat einen Aufklapp-Chip', grouped.includes('data-expand-group'));

    // Einzelne Ereignisse dürfen sich durch nichts davon ändern.
    check('Einzelkarte bleibt unverändert',
          !single.includes('is-group') && !single.includes('data-expand-group')
          && single.includes('Kaiserstraße'));

    // Der Kern: eine Sammelkarte darf den Bearbeiten-Dialog nicht öffnen.
    d.querySelector('.content').insertAdjacentHTML('beforeend',
      `<div class="timeline">${grouped}</div>`);
    let opened = null;
    w.openEventEdit = id => { opened = id; };
    let expanded = false;
    const chip = d.querySelector('[data-expand-group]');
    chip.addEventListener('click', () => { expanded = true; });
    d.querySelector('.event-card.is-group').dispatchEvent(
      new w.MouseEvent('click', { bubbles: true }));
    check('Klick auf die Sammelkarte bearbeitet nichts', opened === null,
          `openEventEdit wurde mit ${opened} gerufen`);
    check('Klick auf die Sammelkarte klappt auf', expanded);
  }

  // Verdichtung muss serverseitig angefordert werden — täte der Browser sie,
  // zerschnitte die Seitengrenze die Gruppen.
  check('Zeitstrahl fordert condense beim Server an',
        /condense:\s*1/.test(html), 'kein condense-Parameter in der Abfrage');
  // Anmerkung 134: Aufgeklappt wird nach der VERDICHTUNGSSTUFE (`place` +
  // `group`), nicht mehr fest nach `city`. Bei „district" trägt group.city
  // einen Ortsteil („HafenCity"), und ein Filter auf Location.city fände ihn
  // nie — die Karte klappte ins Leere auf. Der Filter muss die Stufen-Spalte
  // prüfen, dieselbe, die die Gruppe gebildet hat.
  check('Aufklappen löst die Gruppe stufengerecht auf (place + group)',
        /fetchEvents\(\{\s*group:[^}]*place:/.test(html),
        'kein place/group-Filter beim Aufklappen — ein Ortsteil klappt ins Leere');

  ok.forEach(n => console.log('  ok  ' + n));
  fails.forEach(n => console.log('  XX  ' + n));
  console.log(fails.length ? `\n${fails.length} Prüfung(en) fehlgeschlagen` : '\nA39: alles grün');
  process.exit(fails.length ? 1 : 0);
}, 2500);
