// F10-Wächter: JEDER Schlüssel, den die Oberfläche benutzt, steht auch im
// englischen Katalog (Anmerkung 114).
//
// Warum es diesen Wächter braucht: Ein fehlender Schlüssel wirft nichts. `t()`
// fällt auf den deutschen Text zurück, `data-i18n` ebenso — die App läuft
// weiter und zeigt Deutsch. Das ist als Rückfall genau richtig (nie ein leeres
// Label) und als Zustand genau falsch, und man sieht es nur, wenn man die
// Oberfläche tatsächlich auf Englisch benutzt. Über drei Jahre sind so knapp
// hundert Stellen aufgelaufen: die Moderations-Warteschlange, die
// Nutzerverwaltung, die Abzeichen, die Welt-Checkliste, die Jobs-Tabelle.
//
// Geprüft werden drei Dinge:
//   1. Jeder benutzte Schlüssel steht im Katalog.
//   2. Kein Katalog-Schlüssel ist verwaist (Tippfehler fallen so auf).
//   3. Kein englischer Eintrag ist noch deutsch (Umlaute, typische Wörter) —
//      ein kopierter deutscher Text im Katalog ist schlimmer als ein
//      fehlender Schlüssel, weil der Rückfall ihn nicht mehr erwischt.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-i18n-coverage.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const file = process.argv[2] || 'frontend/index.html';
const html = fs.readFileSync(file, 'utf8');

// --- benutzte Schlüssel einsammeln ------------------------------------------
const used = new Map();          // key -> Beispiel-Fundstelle
const add = (key, where) => { if (!used.has(key)) used.set(key, where); };

// t('key', 'Deutsch') — auch über Zeilenumbrüche hinweg
for (const m of html.matchAll(/\bt\(\s*['"]([\w.]+)['"]\s*,/g)) add(m[1], 't()');
// data-i18n / -title / -ph
for (const m of html.matchAll(/data-i18n(?:-title|-ph)?="([\w.]+)"/g)) add(m[1], 'data-i18n');
// Zusammengesetzte Schlüssel: t('job.' + type, …) — die Präfixe kennt nur der
// Code, die Werte stehen in den Maps daneben. Deshalb werden sie aus dem
// GELADENEN DOM geholt statt geraten (dieselbe Lehre wie check-a41-cities:
// ein Wächter muss den Zustand herstellen, nicht den Quelltext lesen).
const dynamic = [
  ['cat.', 'catLabels'], ['job.', 'JOB_LABELS'], ['jobstatus.', 'JOB_STATUS_DE'],
  ['ent.type.', 'ENT_TYPES'], ['track.', 'TRACK_LABELS'], ['prec.', 'PRECISION_LABELS'],
  ['theme.', 'THEME_LABELS'],
];
// Schlüssel, deren Präfix aus einer Struktur mit anderem Bau kommt.
const fromStructure = w => {
  const out = [];
  // titles: { view: [Titel, Untertitel] }
  Object.keys(w.eval('titles') || {}).forEach(v => {
    out.push('view.' + v + '.title', 'view.' + v + '.sub');
  });
  // BASEMAPS tragen ihren Schlüssel selbst
  Object.values(w.eval('BASEMAPS') || {}).forEach(b => b && b.key && out.push(b.key));
  return out;
};
// Module kommen zur Laufzeit aus /api/modules — offline gibt es sie nicht.
// Ihre Katalog-Einträge sind deshalb NICHT verwaist, nur unbeweisbar.
const RUNTIME_PREFIXES = ['module.'];

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('offline'));
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
  },
});

let fail = 0;
const ok = (name, cond, detail = '') => {
  console.log((cond ? '  ok  ' : '  XX  ') + name + (cond ? '' : ` — ${detail}`));
  if (!cond) fail++;
};

setTimeout(() => {
  const w = dom.window;
  // `const` im Script-Scope landet nicht auf `window` — über eval holen.
  let catalog = null;
  try { catalog = w.eval('I18N_EN'); } catch (_) {}
  ok('Katalog geladen', catalog && Object.keys(catalog).length > 50,
     'I18N_EN nicht erreichbar');
  if (!catalog) { process.exit(1); }

  dynamic.forEach(([prefix, mapName]) => {
    let keys = [];
    try { keys = Object.keys(w.eval(mapName) || {}); } catch (_) {}
    ok(`${mapName} lesbar`, keys.length > 0, `${mapName} ist leer oder fehlt`);
    keys.forEach(k => add(prefix + k, mapName));
  });
  // Monate und Jahreszeiten sind Zahlen-Schlüssel — sie stehen in keiner Map.
  for (let i = 0; i < 12; i++) { add('mon.s.' + i, 'MONTHS_SHORT'); add('mon.l.' + i, 'MONTHS_LONG'); }
  fromStructure(w).forEach(k => add(k, 'Struktur'));
  // Zusammengesetzte Schlüssel aus Inline-Maps, die keinen Namen haben
  // (`t('prov.' + e.confirmed_by, …)`, `t('tier.' + k, …)`).
  ['prov.manual', 'prov.bulk', 'prov.import',
   'tier.bronze', 'tier.silber', 'tier.gold', 'tier.platin'].forEach(k => add(k, 'inline'));

  const missing = [...used.keys()].filter(k => catalog[k] === undefined).sort();
  ok('jeder benutzte Schlüssel steht im Katalog', missing.length === 0,
     `${missing.length} fehlen: ${missing.slice(0, 40).join(', ')}${missing.length > 40 ? ' …' : ''}`);

  const orphans = Object.keys(catalog)
    .filter(k => !used.has(k) && !RUNTIME_PREFIXES.some(p => k.startsWith(p)))
    .sort();
  ok('kein verwaister Katalog-Eintrag', orphans.length === 0,
     `${orphans.length} ohne Fundstelle (Tippfehler?): ${orphans.slice(0, 30).join(', ')}`);

  // Ein deutscher Text IM Katalog ist unsichtbar: der Rückfall greift nicht
  // mehr, weil der Schlüssel ja existiert.
  const germanish = /[äöüÄÖÜß]|\b(und|oder|nicht|keine|werden|wurde|Ereignisse?|Einträge?|löschen|gelöscht|Nutzer|Orte)\b/;
  const stillGerman = Object.entries(catalog)
    .filter(([, v]) => typeof v === 'string' && germanish.test(v))
    .map(([k]) => k);
  ok('kein deutscher Text im englischen Katalog', stillGerman.length === 0,
     stillGerman.join(', '));

  console.log(`\n${used.size} Schlüssel benutzt, ${Object.keys(catalog).length} im Katalog`);
  console.log(fail ? `\nF10: ${fail} Prüfung(en) fehlgeschlagen` : '\nF10: alles grün');
  process.exit(fail ? 1 : 0);
}, 2500);
