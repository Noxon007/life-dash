// Prüft, dass `data-i18n` niemals auf einem Element sitzt, das Bedienelemente
// oder benannte Kinder enthält.
//
// Warum: `data-i18n` ersetzt den GESAMTEN Inhalt des Elements durch den
// übersetzten Text. Sitzt es auf einem Container, in dem ein <input> oder ein
// Element mit id steckt, verschwindet dieses beim Sprachwechsel spurlos.
// Genau das passierte von 0.20.0 bis 0.26.1: auf Englisch fehlten die
// Export-Optionen, die Import-Schwelle, die Ortsnamen-Bausteine und die
// Tracking-Auswahl — die App war einsprachig benutzbar (KONZEPT Anmerkung 71).
//
// Regel: `data-i18n` gehört auf einen <span>, der NUR Text umschließt;
// Bedienelemente stehen daneben, nicht darin.
const fs = require('fs');
const { JSDOM } = require('jsdom');

const file = process.argv[2] || 'frontend/index.html';
const dom = new JSDOM(fs.readFileSync(file, 'utf8'));
const bad = [];

for (const el of dom.window.document.querySelectorAll('[data-i18n]')) {
  const controls = el.querySelectorAll('input, select, textarea, button');
  const ids = [...el.querySelectorAll('[id]')].map(n => n.id);
  if (controls.length || ids.length) {
    bad.push(`${el.getAttribute('data-i18n')} → enthält ${
      [...new Set([...[...controls].map(c => '<' + c.tagName.toLowerCase() + '>'), ...ids])].join(', ')}`);
  }
}

if (bad.length) {
  console.log('data-i18n überschreibt Bedienelemente:');
  bad.forEach(b => console.log('  ' + b));
  console.log('\nAbhilfe: data-i18n auf einen <span> setzen, der nur Text enthält.');
  process.exit(1);
}
console.log('ok — kein data-i18n über Bedienelementen');
