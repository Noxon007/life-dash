// Das Losungswort vor dem Datenverlust — an beiden Löschwegen dasselbe, und
// vom Server auch akzeptiert.
//
// Der gemeldete Fehler war klein und von der teuren Sorte: „Meine Daten
// löschen" verlangte `LOESCHEN`, „Alle Daten löschen" verlangte `LÖSCHEN`.
// Zwei Stellen, dieselbe Frage, zwei Antworten — genau das Muster aus
// CLAUDE.md („Eine Regel an zwei Orten läuft auseinander, und zwar still").
// Dahinter lag der schwerere Fall: das eine Wort wurde vom SERVER geprüft,
// das andere nur vom Browser. Wer die Wörter vereinheitlicht, ohne diese
// Naht zu prüfen, hat eine Oberfläche, die ein Wort verlangt, das der Server
// zurückweist — und der Nutzer sieht einen 400er ohne Erklärung.
//
// Geprüft wird deshalb über drei Dateien hinweg:
//   index.html (beide Dialoge)  →  I18N_EN['wipe.word']  →  app/wipe.py
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-wipe-word.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const py = fs.readFileSync(process.argv[3] || 'backend/app/wipe.py', 'utf8');

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};

// Was der Server durchgehen lässt.
const wordsBlock = py.match(/DELETE_WORDS\s*=\s*frozenset\(\{([\s\S]*?)\}\)/);
const accepted = wordsBlock
  ? [...wordsBlock[1].matchAll(/"([^"]+)"/g)].map(m => m[1].toUpperCase())
  : [];
ok('Der Server hat eine Wortliste', accepted.length >= 2,
   'DELETE_WORDS in app/wipe.py nicht gefunden — Regex und Quelltext passen nicht mehr zusammen');

// Beide Aufrufer: der Konto-Weg und der System-Weg. Beide müssen das Wort aus
// dem Katalog holen (nicht hart schreiben) UND es mitschicken.
const handlers = [
  ['Meine Daten löschen', /btn-wipe-mine[\s\S]{0,2200}?\n\}\);/],
  ['Alle Daten löschen', /btn-wipe'\)[\s\S]{0,1800}?\n\}\);/],
];
const bodies = {};
for (const [name, re] of handlers) {
  const m = html.match(re);
  ok(`Der Knopf „${name}" ist auffindbar`, !!m,
     'der Wächter prüft sonst nichts — Handler umbenannt?');
  const body = m ? m[0] : '';
  bodies[name] = body;
  ok(`„${name}" holt das Wort aus dem Katalog`,
     /t\('wipe\.word'/.test(body),
     'ein hart geschriebenes Losungswort ist auf einer fremden Tastatur eine Sackgasse');
  ok(`„${name}" schickt die Bestätigung zum Server`,
     /confirm:\s*typed/.test(body),
     'sonst prüft nur der Browser — und ein blankes POST leert die Datenbank');
}

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
  },
});

setTimeout(() => {
  const w = dom.window;
  let en = null;
  try { en = w.eval('I18N_EN'); } catch (_) { /* siehe nächste Prüfung */ }
  ok('Der englische Katalog ist erreichbar', !!en, 'lädt die Seite überhaupt?');

  // Das deutsche Wort steht im Quelltext (F10: Deutsch ist die Wahrheit), das
  // englische im Katalog. BEIDE müssen beim Server durchkommen.
  const de = (html.match(/t\('wipe\.word',\s*'([^']+)'\)/) || [])[1];
  ok('Das deutsche Losungswort steht im Quelltext', !!de,
     "t('wipe.word', '…') nicht gefunden");
  ok(`Der Server akzeptiert das deutsche Wort „${de}"`,
     accepted.includes((de || '').toUpperCase()),
     `DELETE_WORDS kennt nur ${accepted.join(', ')} — die Oberfläche verlangt etwas anderes`);

  const enWord = (en || {})['wipe.word'];
  ok('Der englische Katalog hat ein Losungswort', !!enWord,
     "I18N_EN['wipe.word'] fehlt — englisch stünde dann ein Umlaut auf einer Tastatur ohne Umlaut");
  ok(`Der Server akzeptiert das englische Wort „${enWord}"`,
     accepted.includes((enWord || '').toUpperCase()),
     `DELETE_WORDS kennt nur ${accepted.join(', ')}`);

  // Und der Fragetext darf das Wort nicht selbst noch einmal buchstabieren —
  // sonst steht im Dialog ein anderes Wort als im Eingabefeld.
  for (const key of ['wipemine.ask', 'wipe.ask']) {
    const s = (en || {})[key] || '';
    ok(`„${key}" setzt das Wort ein statt es zu wiederholen`,
       s.includes('{w}'),
       `steht: „${s}" — beim nächsten Wortwechsel bleibt dieser Satz stehen`);
  }
  // Dasselbe für den deutschen Quelltext.
  ok('Der deutsche Fragetext setzt das Wort ein',
     /wipemine\.ask'[\s\S]{0,400}\{w\}/.test(html),
     'im deutschen Dialogtext steht das Wort ausgeschrieben');

  console.log(fail ? `\nLosungswort: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nLosungswort: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
