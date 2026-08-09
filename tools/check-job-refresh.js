// Anmerkung 212: Ein Lauf, der auf dem SERVER fertig wird, aktualisiert die
// offene Ansicht — egal, welcher Reiter gerade vorn ist.
//
// Warum das ein Wächter sein muss: der gemeldete Defekt war nicht Kaputtheit,
// sondern Stille. Der Bestand änderte sich, und keine offene Ansicht erfuhr
// davon; sichtbar wurde das erst beim harten Neuladen. Ein solcher Rückfall
// sieht bei jedem einzelnen Test nach „grün" aus, weil jede Funktion für sich
// noch existiert. Geprüft wird deshalb die KETTE: läuft → fertig → Bestand
// vergessen → Lader der offenen Ansicht gerufen.
//
// Und in beide Richtungen — die zweite Hälfte ist die, die man vergisst:
// solange etwas läuft, darf NICHTS aufgefrischt werden (sonst baut sich die
// Ansicht alle vier Sekunden neu auf), und ein Lauf, den dieser Browser selbst
// im Vordergrund gefahren hat, darf keine zweite Meldung erzeugen.
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

let jobs = [];
const calls = { index: 0, today: 0 };

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
    w.fetch = (url) => {
      const u = String(url);
      const json = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
      if (u.includes('/api/jobs')) return json(jobs);
      if (u.includes('/api/events/index')) { calls.index++; return json({ revision: 'r' + calls.index, years: [] }); }
      return Promise.reject(new Error('offline'));
    };
  },
});

const wait = ms => new Promise(r => setTimeout(r, ms));

setTimeout(async () => {
  const w = dom.window;
  let fail = 0;
  const ok = (n, c) => { console.log((c ? '  ok  ' : '  FAIL ') + n); if (!c) fail++; };

  ok('Der Wächter existiert', typeof w.jobWatchTick === 'function'
     && typeof w.refreshCurrentView === 'function');
  if (typeof w.jobWatchTick !== 'function') { console.log('\n1 FEHLER'); process.exit(1); }

  // Die Ansicht, die gerade offen ist, wird beobachtbar gemacht: ihr Lader
  // wird ersetzt. Ein Auffang-Proxy täte es NICHT — der zählt jeden Zugriff
  // als Aufruf und wäre immer grün (die Falle aus CLAUDE.md).
  // `VIEW_LOADERS` und `JOB_WATCH` sind top-level `const` — die landen NICHT
  // auf `window`. Über `w.eval` liegt dieselbe Bindung vor; das Objekt zu
  // verändern reicht, weil es dieselbe Referenz ist.
  const view = w.document.querySelector('.view.active');
  ok('Es gibt eine offene Ansicht', !!view);
  const key = view.id.replace(/^view-/, '');
  w.eval('VIEW_LOADERS')[key] = () => { calls.today++; return Promise.resolve(); };

  // --- 1. Ein fremder Lauf läuft: nichts wird aufgefrischt ------------------
  jobs = [{ id: 'j1', type: 'weather', status: 'running', done: 3, remaining: 7,
            unit: 'Tage', result: null, started_at: '2026-08-09T10:00:00', started_by: 'Test' }];
  // Den Bestandsstempel einmal holen und damit in den Zwischenspeicher legen —
  // sonst prüft die Invalidierung unten gegen nichts.
  await w.fetchIndex();
  await w.fetchIndex();
  ok('Der Bestandsstempel wird zwischengespeichert', calls.index === 1);
  const before = calls.today;
  await w.jobWatchTick();
  await wait(50);
  ok('Solange er LÄUFT, wird nichts neu gebaut', calls.today === before);
  ok('…und der Wächter hat ihn gemerkt', w.eval('JOB_WATCH').live.size === 1);

  // --- 2. Er wird fertig: die offene Ansicht kommt neu ----------------------
  jobs = [{ id: 'j1', type: 'weather', status: 'done', done: 10, remaining: 0,
            unit: 'Tage', result: '10 Tage ergänzt', started_at: '2026-08-09T10:00:00',
            started_by: 'Test' }];
  const idxBefore = calls.index;
  await w.jobWatchTick();
  await wait(50);
  ok('Fertig → der Lader der offenen Ansicht läuft', calls.today > before);
  // Der Stempel wird VERWORFEN, nicht sofort neu geholt — geholt wird er von
  // dem, der ihn braucht. Geprüft wird also die Invalidierung: die nächste
  // Frage geht wieder ans Netz.
  await w.fetchIndex();
  ok('…und der gemerkte Bestandsstempel ist verworfen', calls.index > idxBefore);
  ok('…der Lauf gilt nicht mehr als laufend', w.eval('JOB_WATCH').live.size === 0);

  // --- 3. Kein zweites Mal ---------------------------------------------------
  const after = calls.today;
  await w.jobWatchTick();
  await wait(50);
  ok('Derselbe fertige Lauf frischt kein zweites Mal auf', calls.today === after);

  // --- 4. Ein EIGENER Vordergrund-Lauf meldet sich nicht doppelt -------------
  // Registrierte Vordergrund-Läufe (Backup, Timeline-Import) stehen in
  // derselben Liste, haben aber ihren Overlay und ihre eigene Meldung.
  jobs = [{ id: 'j2', type: 'data_import', status: 'running', done: 0, remaining: 5,
            unit: 'Zeilen', result: null, started_at: '2026-08-09T11:00:00', started_by: 'Test' }];
  w.eval('JOB_WATCH').mine.add('j2');
  await w.jobWatchTick();
  await wait(50);
  const own = calls.today;
  jobs = [{ id: 'j2', type: 'data_import', status: 'done', done: 5, remaining: 0,
            unit: 'Zeilen', result: 'fertig', started_at: '2026-08-09T11:00:00', started_by: 'Test' }];
  await w.jobWatchTick();
  await wait(50);
  ok('Ein eigener Vordergrund-Lauf löst KEINE zweite Auffrischung aus',
     calls.today === own);
  ok('…und wird danach vergessen', !w.eval('JOB_WATCH').mine.has('j2'));

  // --- 5. Die Tabelle fragt nicht mehr selbst --------------------------------
  // Zwei Poller nebeneinander wären zwei Antworten auf „läuft noch was?".
  ok('Die Jobs-Tabelle stellt keinen eigenen Takt mehr',
     !/jobsTimer\s*=\s*setTimeout/.test(html));
  ok('…und der Wächter hat einen', /JOB_WATCH\.timer\s*=\s*ms\s*\?\s*setTimeout/.test(html));

  console.log(fail ? `\n${fail} FEHLER` : '\nAuffrischen nach Job-Ende: alles grün');
  process.exit(fail ? 1 : 0);
}, 2500);
