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
// Nachgereicht (2026-08-11, Anmerkung 218), zwei weitere:
//  • Tab führte aus dem offenen Dialog HINAUS. Ein Dialog, den die Tastatur
//    verlassen kann, ist mit der Tastatur keiner — man tabbt in Knöpfe hinter
//    der Verdunklung und drückt sie, ohne sie zu sehen.
//  • Beim Schließen fiel der Fokus an den Anfang des Dokuments statt zurück auf
//    den Knopf, der geöffnet hat. Mit der Maus fällt beides NIE auf; deshalb
//    stehen hier Prüfungen und keine Absichtserklärungen.
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

  const key = (el, k, opts = {}) => el.dispatchEvent(new w.KeyboardEvent('keydown',
    { key: k, bubbles: true, cancelable: true, ...opts }));

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
  // Beide Richtungen: kein Dialog ohne Zeile, und keine Zeile ins Leere.
  //
  // Was ein Dialog IST, wird hier über die Bauform bestimmt und nicht über eine
  // zweite Namensliste: alles, was den Rest der Seite überdeckt, ist einer —
  // die sechs `.modal-overlay`, das Sheet, der Bildbetrachter und das
  // Lade-Overlay. Ein siebter Dialog fällt damit auf, sobald er die Klasse
  // benutzt, und nicht erst, wenn jemand diesen Wächter erweitert.
  const overlays = [...d.querySelectorAll(
    '.modal-overlay, .sheet-overlay, .lightbox, .loading-overlay')].map(el => el.id);
  // Aus dem Quelltext gelesen, nicht aus `window`: `const` auf oberster Ebene
  // eines Skripts landet im Skript-Bereich und NICHT am Fenster (anders als
  // eine `function`-Deklaration). Die Liste dafür extra global zu machen hieße,
  // die App für ihren Test umzubauen — dann lieber hier lesen.
  const listSrc = (html.match(/const OVERLAYS = \[([\s\S]*?)\n\];/) || [, ''])[1];
  const entries = [...listSrc.matchAll(/\{\s*id:\s*'([\w-]+)',([^}]*)\}/g)].map(m => ({
    id: m[1],
    closes: !/close:\s*null/.test(m[2]),
    enter: !/enter:\s*false/.test(m[2]),
  }));
  const ids = entries.map(e => e.id);
  const orphanDialogs = overlays.filter(id => !ids.includes(id));
  const ghosts = ids.filter(id => !overlays.includes(id));
  check('OVERLAYS existiert', entries.length > 0, 'Liste nicht gefunden');
  check('jeder Dialog steht in der Liste', orphanDialogs.length === 0,
        `ohne Zeile: ${orphanDialogs.join(', ')}`);
  check('kein Eintrag ohne Dialog', ghosts.length === 0, `zeigt ins Leere: ${ghosts.join(', ')}`);

  // Kein zweiter Weg auf. `openOverlay`/`closeOverlay` sind der einzige Ort, an
  // dem `.show` an einem Overlay wandert — wer das selbst schreibt, bekommt
  // Fokusfalle und Rückweg nicht, und zwar ohne dass irgendetwas rot wird.
  // `#ai-preview` ist kein Overlay, sondern ein Kasten im Fluss der
  // Erfassungs-Ansicht; er steht deshalb namentlich hier.
  {
    const owner = html.slice(html.indexOf('const OVERLAYS = ['));
    const stray = [...html.matchAll(/getElementById\('([\w-]+)'\)\.classList\.(?:add|remove)\('show'\)/g)]
      .filter(m => m[1] !== 'ai-preview')
      .filter(m => !owner.includes(m[0]))
      .map(m => m[1]);
    check('nur ein Weg, ein Overlay zu zeigen', stray.length === 0,
          `setzt .show an OVERLAYS vorbei: ${[...new Set(stray)].join(', ')}`);
  }

  // Und jetzt: tut es das auch? Ein Eintrag in einer Liste ist noch kein
  // geschlossener Dialog.
  for (const { id, closes } of entries) {
    const el = d.getElementById(id);
    if (!el) continue;
    el.classList.add('show');
    key(d.body, 'Escape');
    // Beide Richtungen: die Einträge ohne `close` sind mit Grund ohne Ausweg,
    // und dieser Grund ist selbst eine Zusicherung. Ein Escape, das sie
    // trotzdem schlösse, wäre genauso ein Defekt wie eins, das fehlt.
    check(closes ? `Escape schließt ${id}` : `Escape lässt ${id} stehen`,
          closes !== el.classList.contains('show'), 'unerwarteter Zustand');
    el.classList.remove('show');

    if (!closes) continue;
    el.classList.add('show');
    el.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    check(`Klick daneben schließt ${id}`, !el.classList.contains('show'), 'bleibt offen');

    // Gegenprobe: ein Klick IN den Kasten darf nicht schließen. Ohne die wäre
    // der Test auch mit einem Horcher grün, der auf jeden Klick zumacht.
    el.classList.add('show');
    const box = el.querySelector('.modal-box, .sheet');
    if (box) {
      box.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
      check(`…aber ein Klick im Kasten von ${id} nicht`, el.classList.contains('show'),
            'schließt beim Bedienen');
    }
    el.classList.remove('show');
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

  // ---- Der Fokus (Anmerkung 218) ----
  // Ein Dialog, aus dem Tab hinausführt, ist mit der Tastatur keiner. Und einer,
  // der den Fokus beim Schließen nicht zurückgibt, kostet nach JEDER Benutzung
  // denselben Weg durch die halbe Seite. Beides sieht man mit der Maus nie —
  // deshalb steht es hier und nicht in der Absicht.
  const inside = (el) => el.contains(d.activeElement) && d.activeElement !== d.body;
  const trigger = d.querySelector('.sidebar > .nav-item[data-view="world"]');

  if (typeof w.openOverlay !== 'function' || typeof w.closeOverlay !== 'function') {
    check('openOverlay/closeOverlay sind erreichbar', false, 'nicht am Fenster gefunden');
  } else {
    // 1. Beim Öffnen wandert der Fokus in den Dialog — auf den KASTEN, damit
    //    Rolle und Überschrift angesagt werden und nicht das erste Feld.
    trigger.focus();
    w.openOverlay('edit-modal');
    const edit = d.getElementById('edit-modal');
    check('Öffnen setzt den Fokus in den Dialog', inside(edit),
          `Fokus auf: ${d.activeElement && d.activeElement.id || d.activeElement.tagName}`);
    check('…und zwar auf den Kasten mit der Rolle',
          d.activeElement === edit.querySelector('[role="dialog"]'),
          `statt auf ${d.activeElement && d.activeElement.tagName}`);

    // 2. Tab bleibt drin — in beide Richtungen und auch von außen zurück.
    const ring = w.focusablesIn(edit);
    check('der Dialog hat Bedienelemente zum Fangen', ring.length >= 2, `${ring.length}`);
    // Der Ring ist nicht „alles, was im Kasten steht": ein verstecktes
    // Bedienelement im Ring ist ein Fokusrahmen auf einem unsichtbaren Knopf.
    // `ed-days-row` ist im Markup `display:none` — genau der Fall, und der
    // Grund, warum `offsetParent` hier nicht taugt (unter jsdom immer null).
    check('versteckte Bedienelemente stehen nicht im Ring',
          !ring.includes(d.getElementById('ed-days-btn')),
          '„Tages-Einträge anlegen" ist fokussierbar, obwohl seine Zeile aus ist');
    const first = ring[0], last = ring[ring.length - 1];
    last.focus();
    key(last, 'Tab');
    check('Tab am Ende springt an den Anfang des Dialogs', d.activeElement === first,
          `landet auf ${d.activeElement && (d.activeElement.id || d.activeElement.tagName)}`);
    first.focus();
    key(first, 'Tab', { shiftKey: true });
    check('Shift+Tab am Anfang springt ans Ende', d.activeElement === last,
          `landet auf ${d.activeElement && (d.activeElement.id || d.activeElement.tagName)}`);
    // Der eigentliche Defekt: der Fokus steht HINTER dem Dialog (z. B. weil ein
    // Klick ihn dorthin gesetzt hat) und Tab läuft dort weiter.
    trigger.focus();
    key(trigger, 'Tab');
    check('Tab von hinter dem Dialog holt zurück', inside(edit),
          `bleibt auf ${d.activeElement && (d.activeElement.id || d.activeElement.tagName)}`);

    // 3. Beim Schließen zurück auf den Auslöser.
    trigger.focus();
    w.openOverlay('journal-modal');
    w.closeOverlay('journal-modal');
    check('Schließen gibt den Fokus an den Auslöser zurück', d.activeElement === trigger,
          `landet auf ${d.activeElement && (d.activeElement.id || d.activeElement.tagName)}`);

    // 4. Der zweite Dialog über dem ersten gibt an den ERSTEN zurück, nicht an
    //    das, was vor beiden dran war. Genau hier reicht ein einzelnes
    //    gemerktes Element nicht.
    trigger.focus();
    w.openOverlay('edit-modal');
    const innerBtn = d.getElementById('ed-save') || ring[0];
    innerBtn.focus();
    w.openOverlay('pick-modal');
    check('der zweite Dialog liegt über dem ersten', inside(d.getElementById('pick-modal')),
          'Fokus nicht im Ortswähler');
    w.closeOverlay('pick-modal');
    check('…und gibt den Fokus in den ersten zurück', d.activeElement === innerBtn,
          `landet auf ${d.activeElement && (d.activeElement.id || d.activeElement.tagName)}`);
    w.closeOverlay('edit-modal');
    check('…erst der letzte gibt ihn nach draußen', d.activeElement === trigger,
          `landet auf ${d.activeElement && (d.activeElement.id || d.activeElement.tagName)}`);

    // 5. Das Lade-Overlay ist `role="status"`: es wird angesagt, nicht betreten.
    //    Sperren muss es trotzdem — sonst tabbt man in eine Seite, deren eigenes
    //    CSS zusagt, sie sei gerade nicht bedienbar.
    trigger.focus();
    w.openOverlay('loading-overlay');
    check('das Lade-Overlay zieht den Fokus NICHT zu sich',
          d.activeElement === trigger, 'unterbricht die aria-live-Ansage');
    // Hier NICHT gegen `activeElement` prüfen: jsdom bewegt den Fokus bei Tab
    // nicht von selbst, „steht noch auf dem Auslöser" wäre also auch ohne jede
    // Sperre wahr — eine Prüfung über nichts. Gemessen wird, ob der Tastendruck
    // abgefangen wurde (der Abbrechen-Knopf ist `hidden`, es gibt im Overlay
    // also gar nichts zu fokussieren: dann ist „nirgendwohin" die Antwort).
    const ranThrough = key(trigger, 'Tab');
    check('…sperrt den Weg dahinter aber trotzdem',
          !ranThrough || inside(d.getElementById('loading-overlay')),
          'Tab läuft ungebremst in die Seite dahinter');
    w.closeOverlay('loading-overlay');

    // 6. `uiDialog` setzt den Fokus selbst weiter ins Eingabefeld. Der Rückweg
    //    darf davon nicht abhängen — das ist der Fall, an dem „zuletzt
    //    fokussiert" die falsche Antwort gibt.
    trigger.focus();
    // `uiPrompt` ist ein `const` und damit KEINE Fenster-Eigenschaft — über
    // `w.eval` in den globalen Bereich hinein, wie beim Sprachschalter unten.
    const answer = w.eval('uiPrompt("Frage?")');
    check('die Eingabe-Frage fokussiert ihr Feld',
          d.activeElement === d.getElementById('cf-input'),
          `Fokus auf ${d.activeElement && (d.activeElement.id || d.activeElement.tagName)}`);
    key(d.getElementById('cf-input'), 'Escape');
    answer.then(() => {});
    check('…und gibt den Fokus danach an den Auslöser zurück', d.activeElement === trigger,
          `landet auf ${d.activeElement && (d.activeElement.id || d.activeElement.tagName)}`);
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
