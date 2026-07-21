// A37 — serverseitiges Zeitfenster: der Wächter gegen den stillen Rückfall.
//
// Der gefährliche Fehler dieses Pakets ist nicht „langsam", sondern „falsch":
// Eine Ansicht, die wieder die ganze Liste holt und selbst zählt, sieht
// richtig aus, zählt aber nur noch das geladene Fenster. Kein Test der Zahlen
// würde das melden — die Zahlen sind ja in sich stimmig.
//
// Deshalb wird hier der VERKEHR geprüft: Welche Anfragen stellt die App, und
// beantwortet sie ihre Gesamt-Kacheln aus dem Index statt aus einer Liste?
const fs = require('fs'); const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

const calls = [];
const page = n => Array.from({ length: n }, (_, i) => ({
  id: 'e' + i, title: 'Eintrag ' + i, category: 'event', confidence: 1,
  date_start: `2024-06-${String((i % 28) + 1).padStart(2, '0')}T10:00:00`,
  date_precision: 'day', confirmed: 'confirmed', source: 'manual',
  entities: [], metrics: [], media: [],
}));

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
    w.fetch = (url) => {
      calls.push(String(url));
      let body = [];
      if (/\/api\/events\/index/.test(url)) {
        body = { total: 12000, dated: 11900, undated: 100, unconfirmed: 7,
                 year_min: 1990, year_max: 2024, years: [{ year: 2024, count: 300 }],
                 birth: { date_start: '1990-04-12T00:00:00', date_precision: 'day' } };
      } else if (/\/api\/events\?/.test(url)) {
        const limit = +(String(url).match(/limit=(\d+)/) || [0, 0])[1];
        body = page(limit ? Math.min(limit, 300) : 5);
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    };
  },
});

setTimeout(async () => {
  const w = dom.window, d = w.document; let fail = 0;
  const ok = (n, c) => { console.log((c ? '  ok   ' : '  FAIL ') + n); if (!c) fail++; };
  const eventCalls = () => calls.filter(u => /\/api\/events\?/.test(u));

  calls.length = 0;
  await w.loadTimeline();

  // 1. Der Zeitstrahl fragt eine SEITE an — nie mehr die ganze Geschichte.
  ok('Zeitstrahl fragt mit limit an', eventCalls().some(u => /limit=\d+/.test(u)));
  ok('Zeitstrahl holt NICHT die ganze Liste',
     eventCalls().every(u => /limit=\d+/.test(u) || /(vague|parent|category|from|to)=/.test(u)));

  // 2. Nachladen blättert weiter, statt dieselbe Seite noch einmal zu holen.
  const before = eventCalls().length;
  await w.loadTimeline(true);
  const added = eventCalls().slice(before);
  ok('Nachladen verschiebt den Versatz', added.some(u => /offset=[1-9]/.test(u)));

  // 3. Die Gesamt-Kacheln kommen aus dem Index, nicht aus der geladenen Liste.
  //    (Die Antwort oben liefert 300 Einträge, aber 12.000 im Index — zeigt die
  //    Kachel 300, rechnet wieder jemand über eine Liste.)
  await w.loadToday();
  const total = d.getElementById('today-events').textContent;
  ok('„Heute" zeigt den Gesamtbestand (12.000, nicht die Seitenlänge)',
     /12[.,]?000/.test(total));
  ok('„Heute" zeigt die Spanne aus dem Index (1990 – 2024)',
     /1990/.test(d.getElementById('today-span').textContent));
  ok('Unbestätigte kommen aus dem Index (7)',
     d.getElementById('today-unconfirmed').textContent.trim() === '7');

  // 4. F17: Das Geburtsdatum stammt aus dem Index — in der geladenen Seite
  //    steht kein Meilenstein „Geburt", die Alters-Chips müssen trotzdem da
  //    sein. Geprüft wird das Sichtbare: Geburt 1990, Einträge 2024 → „mit 34".
  w.renderTimeline();
  const list = d.getElementById('timeline-list').textContent;
  ok('Alters-Chips überleben das Zeitfenster (Geburt kommt aus dem Index)',
     /🎂/.test(list) && /34/.test(list));

  console.log(fail ? `\n${fail} FEHLER` : '\nA37: alle Prüfungen bestanden');
  process.exit(fail ? 1 : 0);
}, 2500);
