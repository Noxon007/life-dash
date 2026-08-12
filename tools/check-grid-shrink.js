// Rückmeldung 2026-08-12 — **`1fr` ist keine Anteilsangabe, sondern
// `minmax(min-content, 1fr)`.**
//
// Gemeldet als „auf mobil habe ich beim Statistik-Reiter ein Links-Rechts-
// Scrollen, weil nicht alles passt". Die Ursache ist eine Zeile CSS, die
// überall richtig aussieht: `grid-template-columns: repeat(2, 1fr)`.
//
// Eine `fr`-Spalte hat ein **automatisches Minimum**, und das ist die
// min-content-Breite ihres Inhalts. Steht darin ein Wort, das der Browser
// nicht teilen darf — im Alters-Block ist das „1.135.849.203", 150 px am
// Stück —, dann kann die Spalte nicht schmaler werden als dieses Wort. Zwei
// solche Spalten plus Abstände sind breiter als ein Telefon; das Raster wächst
// über seinen Kasten hinaus, und weil `.content` wegen `overflow-y: auto` auch
// waagerecht zum Rollbereich wird, scrollt die ganze SEITE seitwärts.
//
// **Warum das ein Wächter sein muss und keine Anmerkung:** der Defekt ist
// unsichtbar, solange niemand ein schmales Gerät benutzt, er entsteht durch
// eine völlig normal aussehende Zeile, und er wandert — die Zahl, die als
// nächstes zu lang wird, steht in einem anderen Raster. Geprüft wird deshalb
// die REGEL und nicht der Fall: jede `fr`-Spur muss schrumpfen dürfen.
//
// Zwei Formen sind erlaubt:
//   * `minmax(0, 1fr)`      — die Spur darf beliebig schmal werden
//   * `minmax(min(X, 100%), 1fr)` — X nur, solange X überhaupt hineinpasst
// Und eine ist es nicht: `minmax(260px, 1fr)`. Eine feste Untergrenze ist
// dieselbe Falle noch einmal, nur mit einer selbstgewählten Zahl.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-grid-shrink.js
const fs = require('fs');

const file = process.argv[2] || 'frontend/index.html';
const html = fs.readFileSync(file, 'utf8');
let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};

// --- Werte einsammeln: Stylesheet UND Inline-Stile ------------------------- //
// Der Inline-Stil zählt mit: er ist genau der Ort, an dem eine Regel entsteht,
// die keine Media Query je wieder erreicht (A38 hat das für `.action-key`
// schon einmal gelernt).
const found = [];                       // { value, where }
const css = html.slice(html.indexOf('<style>') + 7, html.indexOf('</style>'));
for (const m of css.matchAll(/grid-template-columns\s*:\s*([^;}]+)/g))
  found.push({ value: m[1].trim(), where: 'Stylesheet' });
for (const m of html.matchAll(/style="[^"]*grid-template-columns\s*:\s*([^;"]+)/g))
  found.push({ value: m[1].trim(), where: 'Inline-Stil' });

ok('Raster-Definitionen gefunden', found.length > 0,
   'ohne Fundstellen prüft dieser Wächter nichts — dann stimmt der Selektor '
   + 'nicht mehr, nicht der Code');

// --- `minmax(...)` als BALANCIERTE Klammer herausschneiden ----------------- //
// Ein Regex über `minmax\([^)]*\)` scheitert an `minmax(min(260px, 100%), 1fr)`
// und ließe die innere Klammer stehen — die Prüfung fände dort ein „nacktes"
// fr, das keines ist. Ein Wächter, der aus dem falschen Grund rot wird, kostet
// dasselbe wie einer, der aus dem falschen Grund grün ist.
function cutCalls(value, name) {
  const out = [];                       // die Argumentlisten der Aufrufe
  let rest = '', i = 0;
  while (i < value.length) {
    const at = value.indexOf(name + '(', i);
    if (at < 0) { rest += value.slice(i); break; }
    rest += value.slice(i, at);
    let depth = 0, j = at + name.length;
    for (; j < value.length; j++) {
      if (value[j] === '(') depth++;
      else if (value[j] === ')') { depth--; if (!depth) break; }
    }
    out.push(value.slice(at + name.length + 1, j));
    i = j + 1;
  }
  return { calls: out, rest };
}
// Argumente einer Liste auf oberster Ebene trennen — `min(260px, 100%)` ist
// EIN Argument, nicht zwei.
function splitTop(args) {
  const out = []; let depth = 0, cur = '';
  for (const c of args) {
    if (c === '(') depth++;
    if (c === ')') depth--;
    if (c === ',' && !depth) { out.push(cur.trim()); cur = ''; continue; }
    cur += c;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

const bare = [];        // fr-Spur ganz ohne minmax
const rigid = [];       // minmax mit fester Untergrenze
for (const { value, where } of found) {
  const { calls, rest } = cutCalls(value, 'minmax');
  // (1) Was nach dem Herausschneiden aller minmax() noch ein `fr` trägt, ist
  //     eine Spur mit automatischem Minimum.
  if (/(^|[\s,(])[\d.]*fr\b/.test(rest)) bare.push(`${where}: ${value}`);
  // (2) Und in den minmax() selbst: trägt die OBERgrenze ein `fr`, muss die
  //     Untergrenze schrumpfen dürfen.
  for (const call of calls) {
    const [lo, hi] = splitTop(call);
    if (!hi || !/fr\b/.test(hi)) continue;
    const shrinkable = /^0(px|%|em|rem)?$/.test(lo) || /^min\(/.test(lo);
    if (!shrinkable) rigid.push(`${where}: minmax(${lo}, ${hi})`);
  }
}

ok('keine fr-Spur ohne minmax', bare.length === 0,
   `${bare.length} Stelle(n): ${bare.join(' | ')}\n        `
   + '`1fr` bedeutet `minmax(min-content, 1fr)` — die Spalte kann nicht '
   + 'schmaler werden als ihr längstes unteilbares Wort, und die Seite '
   + 'scrollt dann seitwärts. Richtig: `minmax(0, 1fr)`.');
ok('keine feste Untergrenze vor einer fr-Spur', rigid.length === 0,
   `${rigid.length} Stelle(n): ${rigid.join(' | ')}\n        `
   + '`minmax(260px, 1fr)` ist dieselbe Falle mit einer selbstgewählten Zahl. '
   + 'Richtig: `minmax(min(260px, 100%), 1fr)` — die Grenze gilt nur, solange '
   + 'sie hineinpasst.');

// --- Und die andere Hälfte: der Inhalt muss den Umbruch KÖNNEN ------------- //
// `minmax(0, 1fr)` erlaubt der Spalte, schmaler zu werden als ihr Inhalt.
// Damit die Zahl dann umbricht statt aus der Kachel zu laufen, braucht sie
// `overflow-wrap: anywhere` — und zwar `anywhere` und nicht `break-word`: nur
// `anywhere` senkt auch die min-content-Breite, also genau die Größe, um die
// es hier geht. Die beiden Hälften gehören zusammen; einzeln ist jede die
// Verschiebung des Problems.
ok('die große Zahl darf umbrechen',
   /\.stat-num\s*\{[^}]*overflow-wrap:\s*anywhere/.test(css),
   '`minmax(0, 1fr)` lässt die Spalte schmaler werden als die Zahl — ohne '
   + '`overflow-wrap: anywhere` an `.stat-num` läuft sie dann aus der Kachel');

console.log(fail ? `\nRaster: ${fail} Prüfung(en) fehlgeschlagen`
                 : '\nRaster: alles grün');
process.exit(fail ? 1 : 0);
