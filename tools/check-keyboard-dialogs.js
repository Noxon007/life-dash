// Bedienung ohne Maus, und Dialoge, die sich schließen lassen.
//
// Der Name nennt die AUFGABE und nicht den Anlass: hier steht, was gelten muss,
// damit die Oberfläche mit der Tastatur bedienbar ist und jeder Dialog einen
// Weg hinaus hat. Wer den nächsten Dialog baut, sucht nach „dialog" oder
// „keyboard" — nicht nach der Nummer der Runde, in der es einmal auffiel.
//
// Vorgefunden (2026-08-11), vier stille Defekte:
//  • Die neun Navigationspunkte waren `<div>` mit einem Klick-Horcher. Mit der
//    Maus tadellos, mit der Tastatur GAR NICHT erreichbar — kein `tabindex`,
//    keine Rolle, kein Enter. Ein Defekt, den man beim Benutzen nie sieht.
//  • Escape schloss genau EINEN von sechs Dialogen, Klick daneben drei von
//    sechs. Welche Geste half, hing davon ab, welcher Dialog offen war.
//  • `data-i18n-label` sah aus wie eine Übersetzungsbindung und war keine —
//    das Attribut las niemand. Fünf `aria-label` standen deutsch da, auch in
//    der englischen Oberfläche.
//  • `.tl-day-wx` färbte sich mit `var(--muted)`; die Variable gibt es nicht,
//    und eine unbekannte Custom Property ERBT, statt auf einen Standardwert zu
//    fallen. Der Entwurf („bewusst leise") galt still nicht.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-keyboard-dialogs.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const file = process.argv[2] || 'frontend/index.html';
const html = fs.readFileSync(file, 'utf8');
const fails = [];
const ok = [];
const check = (name, cond, detail = '') =>
  (cond ? ok : fails).push(name + (cond ? '' : ` — ${detail}`));

// ---- Teil 1: am Quelltext ---------------------------------------------------

// Eine Custom Property, die nie definiert wird, ist kein Fehler und keine
// Warnung — die Eigenschaft erbt einfach. Deshalb hier: benutzte gegen
// definierte, beide Richtungen wären zu streng (ein `var(--x, fallback)` wäre
// erlaubt), also nur die ohne Ersatzwert.
{
  const css = html.slice(html.indexOf('<style>'), html.indexOf('</style>'));
  const defined = new Set([...css.matchAll(/^\s*(--[\w-]+)\s*:/gm)].map(m => m[1]));
  const used = [...css.matchAll(/var\(\s*(--[\w-]+)\s*\)/g)].map(m => m[1]);
  const orphan = [...new Set(used.filter(v => !defined.has(v)))];
  check('jede benutzte CSS-Variable ist definiert', orphan.length === 0,
        `ohne Definition (erbt still): ${orphan.join(', ')}`);
}

// Ein Übersetzungs-Attribut, das `applyLang` nicht liest, ist Markup, das
// aussieht wie eine Bindung. Genau das war `data-i18n-label`. Geprüft wird in
// BEIDE Richtungen: jede im Markup benutzte Variante muss ein `swap()` haben,
// und jedes `swap()` sollte auch benutzt werden.
{
  const variants = new Set([...html.matchAll(/(data-i18n(?:-[a-z]+)?)="[\w.]+"/g)].map(m => m[1]));
  const swapped = new Set([...html.matchAll(/swap\('(data-i18n(?:-[a-z]+)?)'/g)].map(m => m[1]));
  const unread = [...variants].filter(v => !swapped.has(v));
  const unused = [...swapped].filter(v => !variants.has(v));
  check('jede i18n-Variante im Markup wird auch angewandt', unread.length === 0,
        `im Markup, aber ohne swap(): ${unread.join(', ')}`);
  check('kein swap() ohne Fundstelle', unused.length === 0,
        `swap() ohne Markup: ${unused.join(', ')}`);
}

// Ein Knopf, dessen sichtbare Beschriftung ein Zeichen ist, trägt seinen Namen
// nur im aria-label — dann muss der übersetzt werden.
{
  const bad = [...html.matchAll(/<[a-z]+\b[^>]*aria-label="([^"]*)"[^>]*>/g)]
    .filter(m => !/data-i18n-aria/.test(m[0]))
    .filter(m => /[äöüßÄÖÜ]|^(zurück|weiter|Vollbild|schließen)$/i.test(m[1]))
    .map(m => m[1]);
  check('kein deutsches aria-label ohne Übersetzung', bad.length === 0,
        `fest verdrahtet: ${bad.join(', ')}`);
}

// ---- Teil 2: im geladenen DOM ----------------------------------------------
const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('offline'));
    w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, addListener() {} }));
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.addEventListener('error', e => errors.push('ERROR: ' + (e.error && e.error.stack || e.message)));
  },
});

setTimeout(() => {
  const w = dom.window, d = w.document;
  const fatal = errors.filter(e => !/offline|Not implemented|fetch/i.test(e));
  check('lädt ohne Fehler', fatal.length === 0, fatal.join(' | '));

  const key = (el, k) => el.dispatchEvent(new w.KeyboardEvent('keydown',
    { key: k, bubbles: true, cancelable: true }));

  // ---- Navigation mit der Tastatur ----
  const navs = [...d.querySelectorAll('.sidebar > .nav-item[data-view]')];
  check('Navigationspunkte gefunden', navs.length >= 4, `${navs.length}`);
  check('jeder Navigationspunkt ist mit Tab erreichbar',
        navs.every(n => n.getAttribute('tabindex') === '0'),
        `ohne tabindex: ${navs.filter(n => n.getAttribute('tabindex') !== '0').map(n => n.dataset.view).join(', ')}`);
  check('…und wird als Bedienelement angesagt',
        navs.every(n => n.getAttribute('role') === 'button'),
        `ohne role=button: ${navs.filter(n => n.getAttribute('role') !== 'button').map(n => n.dataset.view).join(', ')}`);

  // Der eigentliche Punkt: nicht dass die Attribute DASTEHEN, sondern dass ein
  // Tastendruck die Ansicht wirklich wechselt. Ein `tabindex` ohne Horcher ist
  // ein Fokusrahmen, der nichts tut — die schlimmere Hälfte des Defekts.
  const goTo = d.querySelector('.sidebar > .nav-item[data-view="world"]');
  if (goTo && typeof w.gotoView === 'function') {
    w.gotoView('timeline');
    key(goTo, 'Enter');
    check('Enter wechselt die Ansicht',
          d.getElementById('view-world').classList.contains('active'),
          'Enter auf „Welt" hat nichts bewirkt');
    w.gotoView('timeline');
    key(goTo, ' ');
    check('…die Leertaste ebenso',
          d.getElementById('view-world').classList.contains('active'),
          'Leertaste auf „Welt" hat nichts bewirkt');
  } else {
    check('Navigationspunkt „Welt" vorhanden', false, 'nicht gefunden');
  }

  // `.active` ist eine Farbe. Welche Ansicht offen ist, muss auch ansagbar sein.
  if (typeof w.gotoView === 'function') {
    w.gotoView('stats');
    const cur = [...d.querySelectorAll('.nav-item[aria-current]')];
    check('die offene Ansicht trägt aria-current',
          cur.length === 1 && cur[0].dataset.view === 'stats',
          `aria-current auf: ${cur.map(c => c.dataset.view).join(', ') || 'nichts'}`);
    w.gotoView('timeline');
    check('…und gibt es beim Wechsel wieder ab',
          [...d.querySelectorAll('.nav-item[aria-current]')].every(c => c.dataset.view === 'timeline'),
          'ein alter Punkt behält aria-current');
  }

  // Das Sheet wird geklont — `cloneNode` bringt Attribute mit, aber keine
  // Horcher. Mobil liegt dort die Hälfte aller Ziele.
  if (typeof w.buildNavSheet === 'function') {
    w.buildNavSheet();
    const rows = [...d.querySelectorAll('#nav-sheet-items .nav-item')];
    check('Sheet-Zeilen sind ebenfalls erreichbar',
          rows.length > 0 && rows.every(r => r.getAttribute('tabindex') === '0'),
          `${rows.length} Zeilen, davon ohne tabindex: ${rows.filter(r => r.getAttribute('tabindex') !== '0').length}`);
    const target = rows.find(r => r.dataset.view === 'achievements');
    if (target) {
      w.gotoView('timeline');
      key(target, 'Enter');
      check('…und reagieren auf Enter',
            d.getElementById('view-achievements').classList.contains('active'),
            'Enter im Sheet hat nichts bewirkt');
    }
  }

  // ---- Dialoge ----
  // Beide Richtungen: kein Dialog ohne Ausweg, und kein Eintrag ins Leere.
  const overlays = [...d.querySelectorAll('.modal-overlay')].map(el => el.id);
  // Aus dem Quelltext gelesen, nicht aus `window`: `const` auf oberster Ebene
  // eines Skripts landet im Skript-Bereich und NICHT am Fenster (anders als
  // eine `function`-Deklaration). Die Liste dafür extra global zu machen hieße,
  // die App für ihren Test umzubauen — dann lieber hier lesen.
  const listSrc = (html.match(/const MODAL_CLOSERS = \[([\s\S]*?)\];/) || [, ''])[1];
  const closers = [...listSrc.matchAll(/id:\s*'([\w-]+)'/g)].map(m => m[1]);
  // Zwei sind mit Begründung draußen — sie stehen hier NAMENTLICH, damit ein
  // dritter nicht unbemerkt dazukommt.
  const EXEMPT = ['confirm-modal', 'track-modal'];
  const orphanDialogs = overlays.filter(id => !closers.includes(id) && !EXEMPT.includes(id));
  const ghosts = closers.filter(id => !overlays.includes(id));
  check('MODAL_CLOSERS existiert', closers.length > 0, 'Liste nicht gefunden');
  check('jeder Dialog hat einen Weg hinaus', orphanDialogs.length === 0,
        `ohne Eintrag und ohne Ausnahme: ${orphanDialogs.join(', ')}`);
  check('kein Eintrag ohne Dialog', ghosts.length === 0, `zeigt ins Leere: ${ghosts.join(', ')}`);

  // Und jetzt: tut es das auch? Ein Eintrag in einer Liste ist noch kein
  // geschlossener Dialog.
  for (const id of closers) {
    const el = d.getElementById(id);
    if (!el) continue;
    el.classList.add('show');
    key(d.body, 'Escape');
    check(`Escape schließt ${id}`, !el.classList.contains('show'), 'bleibt offen');

    el.classList.add('show');
    el.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    check(`Klick daneben schließt ${id}`, !el.classList.contains('show'), 'bleibt offen');

    // Gegenprobe: ein Klick IN den Kasten darf nicht schließen. Ohne die wäre
    // der Test auch mit einem Horcher grün, der auf jeden Klick zumacht.
    el.classList.add('show');
    const box = el.querySelector('.modal-box');
    if (box) {
      box.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
      check(`…aber ein Klick im Kasten von ${id} nicht`, el.classList.contains('show'),
            'schließt beim Bedienen');
    }
    el.classList.remove('show');
  }

  // Der Begrüßungsdialog ist bewusst ohne Ausweg — er hat keinen
  // Abbrechen-Knopf, weil die Auswahl getroffen werden MUSS. Das ist eine
  // Entscheidung, kein Versehen, und steht deshalb als Prüfung da.
  {
    const tm = d.getElementById('track-modal');
    if (tm) {
      tm.classList.add('show');
      key(d.body, 'Escape');
      check('der Begrüßungsdialog bleibt bei Escape stehen', tm.classList.contains('show'),
            'lässt sich wegdrücken, ohne dass etwas gewählt wurde');
      tm.classList.remove('show');
    }
  }

  // Der Ortswähler öffnet ÜBER dem Bearbeiten-Dialog. Escape muss ihn treffen
  // und nicht den darunter — sonst steht der Wähler auf einem Dialog, den es
  // nicht mehr gibt.
  {
    const edit = d.getElementById('edit-modal'), pick = d.getElementById('pick-modal');
    if (edit && pick) {
      edit.classList.add('show'); pick.classList.add('show');
      key(d.body, 'Escape');
      check('Escape trifft den obersten Dialog',
            !pick.classList.contains('show') && edit.classList.contains('show'),
            `pick offen: ${pick.classList.contains('show')}, edit offen: ${edit.classList.contains('show')}`);
      edit.classList.remove('show'); pick.classList.remove('show');
    }
  }

  // ---- Übersetzte aria-labels ----
  // Nicht „der Schlüssel steht im Katalog" (das prüft check-i18n-coverage),
  // sondern „das Attribut ändert sich beim Umschalten".
  // Geschaltet wird über den KNOPF, nicht über `LANG`: die Variable steht als
  // `let` im Skript und ist keine Fenster-Eigenschaft — `w.LANG = 'de'` legte
  // stumm eine zweite, nie gelesene an, und die Prüfung wäre eine über nichts.
  // Und: unter jsdom startet die Seite ENGLISCH, der vorgefundene Wert ist
  // also schon der übersetzte. Geprüft wird deshalb gegen den deutschen
  // QUELLTEXT und den englischen KATALOG, nicht gegen „hat sich geändert".
  {
    const el = d.querySelector('[data-i18n-aria]');
    const btn = d.getElementById('lang-btn');
    if (!el || !btn) {
      check('data-i18n-aria und Sprachknopf vorhanden', false, 'nicht gefunden');
    } else {
      const k = el.getAttribute('data-i18n-aria');
      const srcDe = (html.match(new RegExp(`data-i18n-aria="${k}"\\s+aria-label="([^"]*)"`)) || [])[1];
      const catEn = (html.match(new RegExp(`'${k.replace(/\./g, '\\.')}':\\s*"([^"]*)"`)) || [])[1];
      const click = () => btn.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
      const lang = () => { try { return w.eval('LANG'); } catch { return '?'; } };

      check('die Seite startet englisch (jsdom)', lang() === 'en', `LANG = ${lang()}`);
      check('aria-label steht englisch da', el.getAttribute('aria-label') === catEn,
            `„${el.getAttribute('aria-label')}" statt „${catEn}"`);
      click();
      check('der Sprachknopf schaltet um', lang() === 'de', `LANG = ${lang()}`);
      check('…und das aria-label wechselt mit', el.getAttribute('aria-label') === srcDe,
            `„${el.getAttribute('aria-label')}" statt „${srcDe}"`);
      click();
      check('…und wieder zurück', el.getAttribute('aria-label') === catEn,
            `kommt als „${el.getAttribute('aria-label')}" zurück`);
    }
  }

  ok.forEach(n => console.log('  ok  ' + n));
  fails.forEach(n => console.log('  XX  ' + n));
  console.log(`\nTastatur & Dialoge: ${fails.length ? `${fails.length} Prüfung(en) fehlgeschlagen` : 'alles grün'}`);
  process.exit(fails.length ? 1 : 0);
}, 700);
