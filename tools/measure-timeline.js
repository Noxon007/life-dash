// Was kostet der Zeitstrahl beim Nachladen? Messen statt raten.
//
// Gemeldet: „ältere Einträge laden finde ich schwierig umgesetzt. man kann
// nicht einfach runterscrollen und es dauert alles lange."
//
// Diese Messung beantwortet die zweite Hälfte davon. Sie läuft in jsdom, misst
// also die JavaScript-Seite (Zeichenketten bauen, HTML parsen, Knoten anlegen)
// und NICHT Layout und Malen des echten Browsers — die kommen obendrauf. Was
// sie zeigt, ist deshalb eine Untergrenze und trotzdem aussagekräftig: wenn
// schon der Aufbau ohne Bildschirm mit jeder Seite länger dauert, ist die Form
// des Problems gefunden.
//
// **Was sie ergeben hat (2026-08-04, Anmerkung 179).** Im Jahres-Zoom — der
// Voreinstellung — besteht die ganze Liste aus 24 Knoten und ist in 4 ms
// gebaut. Nicht das Zeichnen war die Bremse, sondern das Gegenteil: eine Seite
// von 300 Ereignissen ergibt dort EINE Überschrift, die Seite ist zu kurz zum
// Scrollen, und der Weg in die Vergangenheit sind hundert Klicks. Daraus wurde
// das Gerüst aus dem Index (siehe `tools/check-tl-index.js`).
//
// **Was sie NICHT behoben hat und was hier weiter zu messen ist:** im
// Tages-Zoom baut jede nachgeladene Seite die GANZE Liste neu — 26 ms bei 300
// Karten, 172 ms bei 1.800, also mit jeder Seite mehr. Diese Zahlen stehen
// hier, damit der nächste Umbau daran gemessen wird und nicht an einem Gefühl.
//
// **Und was kosten die abgeleiteten Grundort-Tage?** (Anmerkung 182) Der
// zweite Zahlenwert ist ihre Menge in JAHREN; ohne ihn läuft die Messung wie
// bisher. Gemessen am 2026-08-04, `renderTimeline()` auf vollem Stand:
//
//     Jahre  Zoom    mit Fenster   ohne jedes Fenster
//        20  Jahr         50 ms       49 ms  (dort GIBT es keins)
//        20  Monat        52 ms      923 ms
//        20  Tag         206 ms   10.196 ms
//        40  Jahr        103 ms      101 ms
//        40  Monat        51 ms    1.925 ms
//        40  Tag         210 ms   43.402 ms
//
// Das ist der ganze Grund, warum Jahr und Jahrzehnt alle Tage nehmen und Tag,
// Woche und Monat ein wachsendes Fenster: in den Sammel-Zoomstufen begrenzt
// `TL_GROUP_CAP` die Zeilen je Gruppe ohnehin, im Tages-Zoom ist jeder Tag
// eine eigene Gruppe.
//
// Aufruf aus dem Repo-Wurzelverzeichnis:
//   node tools/measure-timeline.js [Seiten] [Grundort-Jahre]
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync('frontend/index.html', 'utf8');
const PAGES = Number(process.argv[2] || 6);
const BL_YEARS = Number(process.argv[3] || 0);
const PAGE = 300;               // TL_PAGE
const START = new Date('2024-12-31T12:00:00Z').getTime();

// Grundort-Tage in den Jahren VOR den Ereignissen — dort, wo sie in echt auch
// liegen: in der Zeit, aus der nichts erfasst ist.
const BL_DAYS = {};
{
  const first = new Date('2022-12-31T00:00:00Z');
  for (let i = 0; i < BL_YEARS * 365; i++) {
    BL_DAYS[new Date(first.getTime() - i * 86400e3).toISOString().slice(0, 10)] = 0;
  }
}
const BL_TOTAL = Object.keys(BL_DAYS).length;
const BL_INDEX_YEARS = BL_TOTAL
  ? [...new Set(Object.keys(BL_DAYS).map(d => +d.slice(0, 4)))]
      .sort().map(year => ({ year, count: 365 }))
  : [];

// Ereignisse absteigend nach Datum, wie der Server sie liefert: einer je
// Stunde, damit ein Jahrgang mehrere Monate umspannt und die Gruppierung
// wirklich etwas zu tun bekommt.
function page(offset) {
  return Array.from({ length: PAGE }, (_, i) => {
    const n = offset + i;
    const at = new Date(START - n * 3600e3).toISOString().slice(0, 19);
    return {
      id: 'e' + n, title: 'Eintrag ' + n, category: n % 3 ? 'event' : 'trip',
      source: n % 2 ? 'manual' : 'google_timeline',
      date_start: at, date_precision: 'exact', confirmed: 'confirmed',
      entities: [], metrics: [], media: [],
      location: { id: 'l' + (n % 40), name: 'Ort ' + (n % 40),
                  lat: 51 + (n % 40) / 100, lng: 8 + (n % 40) / 100, city: 'Stadt ' + (n % 7) },
    };
  });
}

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.__zoom = 6;
    const base = new Proxy(function () { return base; }, {
      get: (_t, k) => (k === 'getZoom' ? () => w.__zoom : base), apply: () => base,
    });
    w.L = base;
    w.fetch = u => {
      const p = String(u);
      let body = [];
      if (/api\/events\?/.test(p)) {
        const off = Number((p.match(/offset=(\d+)/) || [])[1] || 0);
        body = page(off);
      } else if (/events\/index/.test(p)) {
        body = { total: PAGE * PAGES, dated: PAGE * PAGES, undated: 0, unconfirmed: 0,
                 fuzzy: 0, visits: 0, photo_events: 0, machine_proposals: 0,
                 years: [{ year: 2024, count: PAGE * PAGES }],
                 baseline_days: BL_TOTAL, baseline_years: BL_INDEX_YEARS };
      } else if (/days\/baseline/.test(p)) {
        body = BL_TOTAL
          ? { periods: [{ id: 'b1', label: 'Elternhaus', place: 'Musterweg 1',
                          city: 'Musterstadt', country: 'DE' }], days: BL_DAYS }
          : {};
      } else if (/days\/media|days\/weather/.test(p)) body = {};
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

const wait = ms => new Promise(r => setTimeout(r, ms));

setTimeout(async () => {
  const w = dom.window, d = w.document;
  await wait(200);
  // Der Jahres-Zoom ist die Voreinstellung — und die teuerste Gruppierung,
  // weil alles in EINEN Eimer fällt und der Deckel je Gruppe erst danach greift.
  for (const zoom of ['year', 'month', 'day']) {
    w.eval(`tl.zoom = '${zoom}'; tl.events = []; tl.offset = 0; tl.done = false;
            tl.autoPages = 99;`);   // Auto-Nachladen aus: hier wird von Hand geblättert
    console.log(`\n=== Zoom „${zoom}" ===`);
    console.log('  Seite   Karten   Aufbau     Knoten');
    let sum = 0;
    for (let i = 0; i < PAGES; i++) {
      const t0 = w.performance.now();
      await w.loadTimeline(i > 0);
      const dt = w.performance.now() - t0;
      sum += dt;
      const n = w.eval('tl.events.length');
      const nodes = d.getElementById('timeline-list').querySelectorAll('*').length;
      console.log(`  ${String(i + 1).padStart(5)}   ${String(n).padStart(6)}   `
                  + `${dt.toFixed(0).padStart(5)} ms   ${String(nodes).padStart(6)}`);
    }
    console.log(`  ${PAGES} Seiten zusammen: ${sum.toFixed(0)} ms`);
    if (BL_TOTAL) {
      console.log(`  Grundort-Zeilen: ${w.eval('TL_BASELINE_SHOWN')}`
                  + ` von ${w.eval('TL_BASELINE.size')} geladenen`
                  + ` (Fenster: ${w.eval("tl.zoom === 'year' || tl.zoom === 'decade'")
                      ? 'keins — Jahr/Jahrzehnt zählen alle' : w.eval('tl.blPages') + ' Schritt(e)'})`);
    }
    // Und die reine Zeichenzeit ohne Abruf, auf dem vollen Stand.
    const t1 = w.performance.now();
    w.renderTimeline();
    console.log(`  Nur renderTimeline() bei ${w.eval('tl.events.length')} Einträgen: `
                + `${(w.performance.now() - t1).toFixed(0)} ms`);
  }
  process.exit(0);
}, 80);
