// Jeder Job-Typ hat einen Namen — in beiden Sprachen (Anmerkung 120).
//
// Der gemeldete Fehler war eine Kleinigkeit mit einer unangenehmen Eigenschaft:
// im Jobs-Reiter stand `photo_points`. Nicht falsch, nicht kaputt, nur roh —
// das Backend kannte sein Label längst (`JOB_TYPES` in routers/jobs.py), die
// Oberfläche fiel auf `esc(j.type)` zurück. **Ein Fallback, der wie eine
// Anzeige aussieht, versteckt die Lücke**: nichts bricht, niemand bemerkt es,
// und beim nächsten neuen Job-Typ passiert dasselbe wieder.
//
// Geprüft wird deshalb die Naht zwischen zwei Dateien, die niemand zusammen
// liest — dort, wo die Annahme des einen Teils auf die des anderen trifft
// (Anmerkung 111). Drei Listen müssen dieselben Schlüssel tragen:
//   backend JOB_TYPES  →  JOB_LABELS (deutsch)  →  I18N_EN['job.<typ>']
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-job-labels.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const py = fs.readFileSync(process.argv[3] || 'backend/app/routers/jobs.py', 'utf8');

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};

// Die Wahrheit steht im Backend: es entscheidet, welche Typen es gibt.
const block = py.match(/JOB_TYPES\s*=\s*\{([\s\S]*?)\n\}/);
const types = block ? [...block[1].matchAll(/^\s*"([a-z_]+)":/gm)].map(m => m[1]) : [];

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    // Kein Server nötig: geprüft werden zwei Tabellen, keine Abläufe.
    w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
  },
});

setTimeout(() => {
  const w = dom.window;
  ok('Die Typenliste des Backends wurde gefunden', types.length >= 5,
     `gefunden: ${types.join(', ') || 'nichts'} — Regex und Quelltext passen nicht mehr zusammen`);
  // `const` auf oberster Ebene eines klassischen Skripts landet NICHT auf
  // `window` — `w.JOB_LABELS` wäre still `undefined`, und der Wächter hätte
  // fröhlich jedes einzelne Label vermisst, egal wie vollständig es ist.
  // Über `w.eval` sieht man die Bindung so, wie die Seite sie sieht.
  let labels = null, en = null;
  try { labels = w.eval('JOB_LABELS'); en = w.eval('I18N_EN'); } catch (_) { /* siehe nächste Prüfung */ }
  ok('Die Oberfläche hat eine Label-Tabelle', !!labels && !!en,
     'JOB_LABELS oder I18N_EN nicht erreichbar — lädt die Seite überhaupt?');

  for (const type of types) {
    ok(`„${type}" hat einen deutschen Namen`,
       !!(labels || {})[type],
       'sonst steht der nackte Schlüssel im Jobs-Reiter');
    ok(`„${type}" hat einen englischen Namen`,
       !!(en || {})[`job.${type}`],
       `I18N_EN['job.${type}'] fehlt — englisch erscheint dann deutsch`);
  }

  // Und andersherum: ein Label ohne Typ ist ein Rest von etwas Abgeschafftem.
  for (const key of Object.keys(labels || {})) {
    ok(`„${key}" gibt es im Backend noch`, types.includes(key),
       'verwaistes Label — der Typ wurde umbenannt oder entfernt');
  }

  // ---- Der Nachtplan: dieselbe Naht, eine Ebene tiefer -------------------
  // `SCHED_TYPES` (Browser) sagt, was ANGEBOTEN wird; `SCHEDULABLE_TYPES`
  // (Server) entscheidet, was tatsächlich LÄUFT. Laufen sie auseinander, ist
  // genau eine der beiden Richtungen still: ein Häkchen, das nichts auslöst,
  // oder ein nächtlicher Lauf ohne Schalter. Beides sieht im Betrieb aus wie
  // „hat wohl nichts zu tun".
  const schedBlock = py.match(/SCHEDULABLE_TYPES\s*=\s*\(([\s\S]*?)\)/);
  const serverSched = schedBlock
    ? [...schedBlock[1].matchAll(/"([a-z_]+)"/g)].map(m => m[1]) : [];
  let uiSched = null;
  try { uiSched = w.eval('SCHED_TYPES'); } catch (_) { /* siehe Prüfung */ }
  ok('Der Server hat eine Nachtplan-Liste', serverSched.length > 0,
     'SCHEDULABLE_TYPES in routers/jobs.py nicht gefunden');
  ok('Die Oberfläche hat eine Nachtplan-Liste', Array.isArray(uiSched),
     'SCHED_TYPES nicht erreichbar');
  for (const tp of serverSched) {
    ok(`Nachtplan „${tp}" wird auch angeboten`, (uiSched || []).includes(tp),
       'der Server plant ihn, die Oberfläche zeigt keinen Schalter dafür');
  }
  for (const tp of uiSched || []) {
    ok(`Nachtplan „${tp}" wird auch ausgeführt`, serverSched.includes(tp),
       'ankreuzbar, aber der Ticker überspringt ihn — ein Häkchen ohne Wirkung');
  }

  console.log(fail ? `\nJob-Namen: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nJob-Namen: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
