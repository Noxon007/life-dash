// F1 (zweite Hälfte) — der KI-Vorschlag fürs Tagebuch.
//
// Seit 0.15.0 steht im Dialog der Satz „die KI fasst den Text nie an". Ein
// Knopf, der die KI in denselben Dialog holt, kann diesen Satz auf drei Arten
// still brechen, und keine davon fällt beim Ausprobieren auf, solange man den
// Vorschlag ohnehin übernehmen wollte:
//   * er schreibt direkt ins Textfeld (dann ist unklar, was von wem ist),
//   * er überschreibt, was schon dasteht (dann ist eigener Text weg),
//   * er speichert gleich mit (dann steht ungeprüfte KI-Prosa in der
//     Lebensdatenbank — die eine Schicht, die Maschinen nie ändern dürfen).
//
// Geprüft wird deshalb die GRENZE, nicht die Formulierung.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-f1-journal-ai.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

const calls = [];                     // jede Anfrage: [Methode, Pfad]
let suggestion = { day: '2026-07-12', text: 'Ich war in Detmold und sah einen Adler.',
                   used_events: 2, skipped_unconfirmed: 1 };

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: () => w.L, apply: () => w.L });
    w.fetch = (u, opt) => {
      const path = String(u);
      calls.push([(opt && opt.method) || 'GET', path]);
      let body = [];
      if (/\/api\/journal\/suggest/.test(path)) body = suggestion;
      else if (/\/api\/events\?/.test(path)) body = [];
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    };
  },
});

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};
const wait = ms => new Promise(r => setTimeout(r, ms));
const writes = () => calls.filter(([m]) => m && m !== 'GET');

setTimeout(async () => {
  const w = dom.window, d = w.document;
  const ta = d.getElementById('jr-text');
  const box = d.getElementById('jr-suggestion');

  w.openJournal('2026-07-12');
  await wait(30);
  calls.length = 0;

  // --- 1. Der Vorschlag wird geholt und NICHT gespeichert ----------------- //
  ta.value = 'Eigener Satz, von Hand geschrieben.';
  d.getElementById('jr-suggest').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);

  ok('Der Vorschlag wird beim Server geholt',
     calls.some(([, p]) => /\/api\/journal\/suggest\?day=2026-07-12/.test(p)),
     JSON.stringify(calls));
  ok('…und zwar lesend (GET) — ein Vorschlag schreibt nichts',
     writes().length === 0, JSON.stringify(writes()));

  // --- 2. Er steht NEBEN dem Text, nicht darin --------------------------- //
  ok('Der Vorschlag ist sichtbar', box.style.display !== 'none');
  ok('Er steht in seinem eigenen Kasten',
     /Adler/.test(d.getElementById('jr-sug-text').textContent));
  ok('Das Textfeld bleibt unangetastet',
     ta.value === 'Eigener Satz, von Hand geschrieben.',
     `Feld: "${ta.value}" — die KI hat selbst geschrieben`);
  ok('Der Kasten sagt, dass nichts gespeichert ist',
     /nicht gespeichert|not saved/i.test(box.textContent));
  ok('Er nennt seine Grundlage (2 eingeflossen, 1 übergangen)',
     /2/.test(d.getElementById('jr-sug-meta').textContent)
     && /1/.test(d.getElementById('jr-sug-meta').textContent),
     d.getElementById('jr-sug-meta').textContent);

  // --- 3. Übernehmen hängt an, überschreibt nicht ------------------------ //
  d.getElementById('jr-sug-take').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(20);
  ok('Übernehmen behält den eigenen Text',
     /Eigener Satz, von Hand geschrieben\./.test(ta.value),
     `Feld: "${ta.value}"`);
  ok('…und hängt den Vorschlag an', /Adler/.test(ta.value), `Feld: "${ta.value}"`);
  ok('Der Kasten schließt sich danach', box.style.display === 'none');
  ok('Übernehmen speichert NICHT', writes().length === 0,
     'der Mensch drückt Speichern, nicht die KI');

  // --- 4. Ein leerer Tag sagt es, statt still nichts zu tun -------------- //
  suggestion = { day: '2026-07-13', text: null, used_events: 0, skipped_unconfirmed: 3 };
  w.openJournal('2026-07-13');
  await wait(30);
  d.getElementById('jr-suggest').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  ok('Ohne Material bleibt der Kasten zu', box.style.display === 'none');
  ok('…und der Grund wird gesagt',
     /unbestätigt|unconfirmed/i.test(d.getElementById('toast-wrap').textContent),
     `Meldungen: "${d.getElementById('toast-wrap').textContent}"`);

  // --- 4b. Kein Text TROTZ Ereignissen ist ein ANDERER Grund ------------- //
  // Sonst meldet die App „für diesen Tag ist nichts erfasst", während der Tag
  // voll ist und nur das Modell nichts geliefert hat — und schickt den Nutzer
  // damit in die falsche Richtung.
  d.getElementById('toast-wrap').innerHTML = '';
  suggestion = { day: '2026-07-13', text: null, used_events: 4, skipped_unconfirmed: 0 };
  d.getElementById('jr-suggest').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  const said = d.getElementById('toast-wrap').textContent;
  ok('Liefert die KI nichts, wird DAS gesagt — nicht „nichts erfasst"',
     /KI|AI/.test(said) && !/nichts erfasst|nothing is recorded/i.test(said),
     `Meldung: "${said}"`);

  // --- 5. Ein Vorschlag gehört zu EINEM Tag ------------------------------ //
  suggestion = { day: '2026-07-14', text: 'Ein Vorschlag für den 14.',
                 used_events: 1, skipped_unconfirmed: 0 };
  w.openJournal('2026-07-14');
  await wait(30);
  d.getElementById('jr-suggest').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  ok('Der Vorschlag des 14. ist da', box.style.display !== 'none');
  d.getElementById('jr-date').value = '2026-07-15';
  d.getElementById('jr-date').dispatchEvent(new w.Event('change', { bubbles: true }));
  await wait(40);
  ok('Beim Tageswechsel verschwindet er wieder', box.style.display === 'none',
     'der Vorschlag von gestern stünde unter dem Datum von heute');

  console.log(fail ? `\nF1: ${fail} Prüfung(en) fehlgeschlagen` : '\nF1: alles grün');
  process.exit(fail ? 1 : 0);
}, 60);
