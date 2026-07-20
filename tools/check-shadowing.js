// Sucht Funktionen, die die Übersetzungsfunktion t() durch eine gleichnamige
// lokale Variable verdecken UND sie im selben Gültigkeitsbereich aufrufen.
// Genau dieser Fehler machte die Job-Tabelle von 0.20.0 bis 0.26.1 unbrauchbar:
// ein Syntaxcheck sieht ihn nicht, und er schlägt erst zur Laufzeit zu.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2] || 'd:/Python/life-dash/frontend/index.html', 'utf8');
const bad = [];
const re = /(?:async\s+)?function\s+(\w+)\s*\([^)]*\)\s*\{/g;
let m;
while ((m = re.exec(src))) {
  let depth = 1, i = m.index + m[0].length;
  while (i < src.length && depth) { const c = src[i++]; if (c === '{') depth++; else if (c === '}') depth--; }
  const body = src.slice(m.index + m[0].length, i);
  // Deklaration auf oberster Ebene der Funktion (nicht in verschachtelten Blöcken)
  const decl = /(?:^|\n)\s{2,4}(?:const|let|var)\s+t\s*=/.test(body);
  const call = /\bt\(\s*['"]/.test(body);
  if (decl && call) bad.push(m[1]);
}
if (bad.length) { console.log('VERDECKTES t() in: ' + bad.join(', ')); process.exit(1); }
console.log('ok — t() wird nirgends verdeckt');
