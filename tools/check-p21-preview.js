// P2.1 Stufe 2 — die Vorschau ist Pflicht, nicht Empfehlung.
//
// Anmerkung 107 begründet die jahresweisen Läufe mit einer Zahl: eine zwanzig
// Jahre alte Bibliothek ergibt vierstellig viele Ereignisse in einem Rutsch.
// Der Schutz davor ist ein einziges Verhalten der Oberfläche — **anlegen geht
// erst nach ansehen** —, und das ist genau die Sorte Eigenschaft, die beim
// Bauen aus Versehen verschwindet: der Knopf funktioniert ja, er tut nur zu
// viel. Anmerkung 138: seit dem Wegfall der Moderation (Fotocluster werden
// direkt bestätigt, wie ein Google-Besuch) ist die Vorschau die EINZIGE Bremse
// — wichtiger, nicht unwichtiger, als vorher. Alben (vormals Stufe 3) sind
// komplett raus.
//
// Geprüft wird deshalb der Zustand, den es GEBEN MUSS (die Regel aus
// `check-a41-cities.js`): der Knopf ist anfangs gesperrt, geht erst nach einer
// Vorschau auf, und schließt wieder, sobald das Jahr gewechselt wird — sonst
// legt er Ereignisse für ein Jahr an, das niemand gesehen hat.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-p21-preview.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
// Anmerkung 139: Die Vorschau verdichtet auf ORTE — ein Foto ist ein Ereignis,
// und zwanzigtausend Zeilen aufzuzaehlen ist selbst keine
// Entscheidungsgrundlage mehr. Genannt wird die Ebene, auf der man „ja, das
// war so" oder „nein, das sind fremde Bilder" sagen kann.
let preview = {
  year: 2024, total: 24, days: 2, seen: 40, truncated: false, skipped: [],
  places: [{ place: 'Detmold', photos: 15 }, { place: 'Chania', photos: 9 }],
  sample: [{ slot: 'immich:photo:a1', title: 'Foto in Detmold',
             at: '2024-07-12T10:00:00', place: 'Detmold' }],
};

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.fetch = (u, opt) => {
      const path = String(u);
      calls.push([(opt && opt.method) || 'GET', path, opt && opt.body]);
      let body = [];
      // Form wie der Endpunkt sie liefert: Jahr PLUS Fotozahl. Die Zahl ist
      // der Grund, warum die Liste aus Immich kommt und nicht aus dem eigenen
      // Bestand — 2004 hat 412 Fotos und sonst nichts (Anmerkung 107).
      if (/\/api\/immich\/years/.test(path)) {
        body = { current: 2024, source: 'immich', years: [
          { year: 2024, photos: 61 }, { year: 2023, photos: 240 },
          { year: 2004, photos: 412 }] };
      }
      else if (/\/api\/immich\/preview/.test(path)) body = preview;
      else if (/\/api\/jobs\/start/.test(path)) body = { id: 'j1', type: 'photo_points', status: 'running', done: 0, started_at: '2026-07-22T10:00:00', updated_at: '2026-07-22T10:00:00' };
      else if (/\/api\/jobs/.test(path)) body = [];
      // Der ECHTE Startweg — ohne ihn kommt die Seite nie bis zu der Zeile,
      // die die Jahre lädt (Anmerkung 112).
      else if (/auth\/config/.test(path)) body = { mode: 'dev' };
      else if (/auth\/me\/settings/.test(path)) body = { immich: { url: 'http://immich.local', has_key: true }, tracked_modules: null, place_name_parts: ['road', 'city', 'country'] };
      else if (/auth\/me$/.test(path)) body = { id: 'u1', display_name: 'T', role: 'admin' };
      else if (/\/api\/modules/.test(path)) body = [];
      else if (/\/health/.test(path)) body = { version: '0.39.0', display_version: '0.39.0-dev', channel: 'dev' };
      else if (/events\/index/.test(path)) body = { total: 0, dated: 0, undated: 0, unconfirmed: 0, fuzzy: 0, years: [] };
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
const started = () => calls.filter(([m, p]) => m === 'POST' && /\/api\/jobs\/start/.test(p));

setTimeout(async () => {
  const w = dom.window, d = w.document;
  const run = d.getElementById('ims-run');
  const sel = d.getElementById('ims-year');
  const box = d.getElementById('ims-result');

  ok('Die Zeile für „Immich als Quelle" existiert', !!run && !!sel && !!box);

  // --- 1. Ohne Vorschau geht nichts -------------------------------------- //
  ok('Der Anlegen-Knopf ist von Anfang an gesperrt', run.disabled,
     'ein Klick ohne Vorschau legt hunderte Ereignisse direkt bestätigt an');

  // Anmerkung 112: Hier stand `await w.loadImmichYears()` — der Wächter hat
  // sich die Jahre SELBST geholt und damit genau den Schritt übersprungen, an
  // dem es im Betrieb scheiterte. Er war grün, während der Knopf beim Nutzer
  // nichts tat. Also den Weg gehen, den ein Mensch geht: Verwaltung öffnen,
  // Reiter „Meine Daten" — den Rest muss die Seite selbst tun.
  w.gotoView('admin');
  w.showAdminTab('daten');
  await wait(120);
  // Drei Jahre vom Server plus der Sammeleintrag „Alle Jahre" (Anmerkung 120).
  ok('Die Jahresauswahl kommt vom Server', sel.options.length === 4,
     `${sel.options.length} Einträge`);
  ok('…und bietet „Alle Jahre" an',
     [...sel.options].some(o => o.value === 'all'),
     [...sel.options].map(o => o.value).join(','));
  ok('Das laufende Jahr ist vorgewählt', sel.value === '2024', sel.value);
  // Ein Jahr ohne eigene Daten muss wählbar sein — das ist der Fall, für den
  // das Paket überhaupt existiert („die Erinnerungen von vor dem Smartphone").
  ok('Alte Jahre stehen zur Wahl',
     [...sel.options].some(o => o.value === '2004'),
     [...sel.options].map(o => o.value).join(','));
  ok('…und sagen, wie viel dort liegt',
     /412/.test([...sel.options].map(o => o.textContent).join(' ')),
     'ohne die Zahl ist die Liste eine Aufzählung statt einer Empfehlung');

  // Auch wenn jemand die Sperre umgeht (Konsole, kaputtes CSS): der Klick
  // darf keinen Lauf starten.
  run.disabled = false;
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(20);
  ok('Selbst ein erzwungener Klick startet ohne Vorschau nichts',
     started().length === 0,
     'die Sperre am Knopf ist Bequemlichkeit — die Regel muss im Code stehen');

  // --- 2. Die Vorschau zeigt, was entstehen würde ------------------------ //
  d.getElementById('ims-preview').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);

  const prev = calls.filter(([, p]) => /\/api\/immich\/preview/.test(p));
  ok('Die Vorschau fragt ihr Jahr ab', prev.some(([, p]) => /year=2024/.test(p)),
     JSON.stringify(prev));
  ok('Die Vorschau legt nichts an', started().length === 0);
  ok('Der Kasten ist sichtbar', box.style.display !== 'none');

  const text = box.textContent;
  ok('Sie nennt die Gesamtzahl', /24/.test(text), text.slice(0, 200));
  ok('Sie NENNT die Orte, statt nur zu zählen',
     /Detmold/.test(text) && /Chania/.test(text),
     'eine Zahl ist keine Entscheidungsgrundlage (P2.5) — hier erst recht nicht, weil direkt bestätigt wird');

  // --- 3. Erst jetzt darf angelegt werden -------------------------------- //
  ok('Nach der Vorschau ist der Knopf offen', !run.disabled);
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(30);
  ok('Der Lauf startet als Job', started().length === 1, `${started().length} Starts`);
  const body = JSON.parse(started()[0][2] || '{}');
  // Anmerkung 139: Der Lauf heisst jetzt `photo_points` — der frueher getrennte
  // Verorten-Lauf und das Anlegen sind EIN Lauf geworden.
  ok('…vom Typ photo_points', body.type === 'photo_points', JSON.stringify(body));
  // Anmerkung 120: Der Lauf bekommt die Jahre der VORSCHAU, nicht die der
  // Auswahl — bei einem Jahr ist das dasselbe, bei „Alle Jahre" nicht.
  ok('…und mit dem Jahr im Gepäck',
     body.params && Array.isArray(body.params.years)
       && body.params.years.length === 1 && body.params.years[0] === 2024,
     JSON.stringify(body.params));

  // --- 4. Jahreswechsel entwertet die Vorschau --------------------------- //
  // Der teuerste stille Fehler dieser Oberfläche: Vorschau für 2024 ansehen,
  // auf 2019 umschalten, anlegen — und 2019 hat nie jemand gesehen. Jetzt
  // schreibt das direkt bestätigte Ereignisse an, die niemand kontrolliert hat.
  calls.length = 0;
  preview = { year: 2024, total: 9, days: 1, seen: 12, truncated: false,
              skipped: [], places: [{ place: 'Chania', photos: 9 }], sample: [] };
  d.getElementById('ims-preview').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  ok('Vorschau erneut gelaufen', !run.disabled);

  sel.value = '2022';
  sel.dispatchEvent(new w.Event('change', { bubbles: true }));
  await wait(20);
  ok('Jahreswechsel sperrt den Knopf wieder', run.disabled,
     'die Vorschau von 2024 hätte den Lauf für 2022 freigegeben');
  ok('…und räumt die alte Vorschau weg', box.style.display === 'none',
     'die Zahlen von 2024 stünden unter dem Jahr 2022');

  // --- 5. Immich fällt aus: der Grund muss ANKOMMEN ---------------------- //
  // Anmerkung 113, dritte Runde. Der Endpunkt hat einen Immich-Ausfall als
  // `502` gemeldet — semantisch passend, im Betrieb fatal: ein umgekehrter
  // Vertreter (hier Cloudflare) ersetzt den Rumpf einer 502 durch seine eigene
  // HTML-Fehlerseite. Der Satz, der genau sagt, was mit Immich los ist, kam
  // damit nie an; die Seite bekam HTML statt JSON und zeigte „502 Bad
  // Gateway". Deshalb: 200 mit `error` im Rumpf — und der Wächter stellt genau
  // diesen Zustand her.
  sel.value = '2022';
  sel.dispatchEvent(new w.Event('change', { bubbles: true }));
  preview = { year: 2022, error: 'Immich lehnt den API-Schlüssel ab (401/403)',
              total: 0, days: 0, seconds: 0.2, places: [], sample: [], skipped: [] };
  d.getElementById('ims-preview').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  ok('Ein Immich-Ausfall wird im Klartext gezeigt',
     /401|Schlüssel/.test(box.textContent),
     `stattdessen: ${box.textContent.slice(0, 120)}`);
  ok('…und der Anlegen-Knopf bleibt gesperrt', run.disabled,
     'ohne echte Vorschau darf nichts angelegt werden');

  // --- 5b. „Alle Jahre" hebt den Riegel NICHT auf (Anmerkung 120) -------- //
  // Der Riegel war nie „ein Jahr", sondern „nichts anlegen, was niemand
  // gesehen hat". Ein Sammellauf darf deshalb existieren — aber nur, wenn die
  // Vorschau wirklich JEDES Jahr einzeln ansieht und der Lauf genau diese
  // Jahre bekommt. Die naheliegende Abkürzung (eine Anfrage ohne Jahr, der
  // Server nimmt sich 25 Sekunden und antwortet mit einem Ausschnitt) wäre
  // „ein Zwanzigstel sehen, alles anlegen".
  preview = { year: 2024, total: 9, days: 1, seen: 9, truncated: false,
              skipped: [], places: [{ place: 'Kiel', photos: 9 }], sample: [] };
  sel.value = 'all';
  sel.dispatchEvent(new w.Event('change', { bubbles: true }));
  await wait(20);
  ok('„Alle Jahre" gewählt sperrt den Knopf zuerst', run.disabled,
     'die Vorschau des Einzeljahres gilt nicht für alle');
  calls.length = 0;
  d.getElementById('ims-preview').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(200);
  const asked = calls.filter(([m, p]) => m === 'POST' && /immich\/preview\?year=/.test(p))
                     .map(([, p]) => p.match(/year=(\d{4})/)[1]).sort();
  ok('Die Vorschau fragt JEDES Jahr einzeln',
     asked.join(',') === '2004,2023,2024', asked.join(',') || 'keine Anfrage');
  ok('…und keine Sammel-Anfrage ohne Jahr',
     !calls.some(([m, p]) => m === 'POST' && /immich\/preview(?!.*year=)/.test(p)),
     JSON.stringify(calls.map(c => c[1])));
  ok('Nach der Vorschau über alle Jahre ist der Knopf offen', !run.disabled);
  ok('Die Überschrift nennt die Spanne, nicht ein Jahr',
     /2004/.test(box.textContent) && /2024/.test(box.textContent),
     box.textContent.slice(0, 120));
  calls.length = 0;
  run.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(30);
  ok('Der Sammellauf startet überhaupt', started().length === 1,
     `${started().length} Starts — ohne Start gibt es auch keine Jahre zu prüfen`);
  const allRun = JSON.parse((started().slice(-1)[0] || [])[2] || '{}');
  ok('Der Lauf bekommt ALLE gesehenen Jahre',
     allRun.params && Array.isArray(allRun.params.years)
       && allRun.params.years.slice().sort().join(',') === '2004,2023,2024',
     JSON.stringify(allRun.params));

  // --- 6. Und wenn davor etwas schiefgeht? ------------------------------- //
  // Anmerkung 112: Genau hier lag der gemeldete Fehler. Die Jahresliste kam
  // nur vom Server, und ihr Aufruf hing hinter einem stummen `catch`. Ging
  // irgendetwas davor schief — ein fehlendes Feld in den Einstellungen, ein
  // nicht erreichbares Immich —, blieb das Auswahlfeld leer, der Knopf sagte
  // „bitte zuerst ein Jahr wählen" über einer leeren Liste und schickte
  // NICHTS los. Im Server-Log stand folgerichtig nichts.
  //
  // Die Jahre aus Immich sind eine Empfehlung, keine Voraussetzung: der Lauf
  // muss auch dann möglich sein, wenn sie fehlen.
  for (const [name, broken] of [['Jahresabruf scheitert', 'years'],
                                ['Einstellungen unvollständig', 'settings']]) {
    const sub = await scenario(broken);
    const sw = sub.window, sd = sw.document;
    sw.gotoView('admin');
    sw.showAdminTab('daten');
    await wait(140);
    const ssel = sd.getElementById('ims-year');
    ok(`${name}: das Auswahlfeld hat trotzdem Jahre`, ssel.options.length > 0,
       'leeres Feld = Sackgasse, genau der gemeldete Fehler');
    sub.calls.length = 0;
    sd.getElementById('ims-preview').dispatchEvent(new sw.MouseEvent('click', { bubbles: true }));
    await wait(60);
    ok(`${name}: die Vorschau geht trotzdem raus`,
       sub.calls.some(([m, p]) => m === 'POST' && /immich\/preview\?year=\d{4}/.test(p)),
       `Anfragen: ${JSON.stringify(sub.calls)}`);
    sw.close();
  }

  console.log(fail ? `\nP2.1/2: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nP2.1/2: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);

// Eine zweite Seite mit gezielt kaputter Vorgeschichte.
function scenario(broken) {
  const calls = [];
  const dom2 = new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
      w.fetch = (u, o) => {
        const p = String(u);
        calls.push([(o && o.method) || 'GET', p]);
        let body = [], ok2 = true, status = 200;
        if (/immich\/years/.test(p)) {
          if (broken === 'years') { ok2 = false; status = 502; body = { detail: 'Immich nicht erreichbar' }; }
          else body = { current: 2024, source: 'immich', years: [{ year: 2024, photos: 61 }] };
        } else if (/immich\/preview/.test(p)) body = { year: 2024, total: 0, days: 0, places: [], sample: [], skipped: [] };
        else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) {
          // `place_name_parts` fehlt: der ursprüngliche Auslöser — ein
          // TypeError vor `renderImmichState`, verschluckt vom catch.
          body = broken === 'settings'
            ? { immich: { url: 'http://immich.local', has_key: true } }
            : { immich: { url: 'http://immich.local', has_key: true }, tracked_modules: null, place_name_parts: ['city'] };
        } else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev', channel: 'dev' };
        else if (/events\/index/.test(p)) body = { total: 0, dated: 0, undated: 0, unconfirmed: 0, fuzzy: 0, years: [] };
        return Promise.resolve({ ok: ok2, status, json: () => Promise.resolve(body) });
      };
    },
  });
  dom2.calls = calls;
  return new Promise(r => setTimeout(() => r(dom2), 80));
}
