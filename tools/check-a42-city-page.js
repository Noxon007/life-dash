// A42 (Anmerkung 102): Die Stadt ist ein Sammlungs-EINTRAG, keine Kachel mit
// Sprungziel.
//
// Geprüft wird die Eigenschaft, die A41 fehlte und die man einer Kachel nicht
// ansieht: ein Klick im Kompendium muss IM Kompendium landen — mit
// Beschreibung, Karte und Ereignissen —, so wie bei Tieren und Ländern. Führt
// er stattdessen in den Zeitstrahl, sieht das aus wie eine Funktion und ist
// eine Ausleitung; genau die Sorte Halbheit, die Anmerkung 94 schon einmal
// beschrieben hat.
//
// Dazu zwei Dinge, die im Betrieb teuer wären und beim Ansehen nicht auffallen:
//   * die Beschreibung darf nur geholt werden, wenn keine da ist (sonst fragt
//     jedes Öffnen erneut bei Wikipedia an — der Endlos-Abruf aus F12/A39),
//   * die Seite darf nicht alle Ereignisse der Stadt rendern wollen; nach einem
//     Import sind das tausende (A37).
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-a42-city-page.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
let cached = false;          // hat der Server schon eine Beschreibung?

const detail = () => ({
  name: 'Düsseldorf', country: 'Deutschland', event_count: 342, place_count: 3,
  first_visit: '2019-03-02T10:00:00', last_visit: '2024-08-11T18:00:00',
  places: [
    { id: 'l1', name: 'Kaiserstraße', lat: 51.23, lng: 6.78, event_count: 300 },
    { id: 'l2', name: 'Hofgarten', lat: 51.24, lng: 6.77, event_count: 42 },
  ],
  events: [{ id: 'e1', title: 'Besuch: Hofgarten', category: 'event', confidence: 1,
             date_start: '2024-08-11T18:00:00', date_precision: 'day',
             confirmed: 'confirmed', source: 'google_timeline',
             entities: [], metrics: [], media: [] }],
  events_shown: 1,
  // cached: false = noch nie nachgesehen · 'leer' = nachgesehen, kein Artikel
  info: cached === 'leer' ? { name: 'Düsseldorf', lang: 'de', description: null }
        : cached ? { name: 'Düsseldorf', lang: 'de', description: 'Landeshauptstadt.' }
        : null,
});

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
  beforeParse(w) {
    w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
    w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
    w.fetch = (url, opt) => {
      calls.push(String(url));
      let body = [];
      if (/\/api\/cities\/detail/.test(url)) body = detail();
      else if (/\/api\/cities\/describe/.test(url)) {
        cached = true;
        body = { name: 'Düsseldorf', lang: 'de', description: 'Landeshauptstadt.' };
      } else if (/\/api\/cities/.test(url)) {
        body = [{ name: 'Düsseldorf', country: 'Deutschland', event_count: 342,
                  place_count: 3, first_visit: '2019-03-02T10:00:00',
                  last_visit: '2024-08-11T18:00:00' }];
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    };
  },
});

setTimeout(async () => {
  const w = dom.window, d = w.document; let fail = 0;
  const ok = (n, c, detailText = '') => {
    console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detailText}`));
    if (!c) fail++;
  };

  // --- 1. Der Klick bleibt in der Sammlung -------------------------------- //
  let wentToTimeline = false;
  w.eval('window.__origFilter = tlFilterCity; tlFilterCity = c => { window.__timeline = c; };');
  await w.loadCities();
  const card = d.querySelector('#compendium-grid .comp-card[data-city]');
  ok('Städte-Kachel vorhanden', !!card, 'loadCities rendert keine Karten');
  if (card) {
    card.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await new Promise(r => setTimeout(r, 30));
  }
  wentToTimeline = w.__timeline !== undefined;
  ok('Klick öffnet die Stadtseite, nicht den Zeitstrahl', !wentToTimeline,
     'die Sammlung leitet aus sich heraus statt eine Seite zu zeigen');

  const detailEl = d.getElementById('compendium-detail');
  ok('Detailbereich ist sichtbar', detailEl.style.display !== 'none');
  ok('Stadtseite fragt ihren Endpunkt',
     calls.some(u => /\/api\/cities\/detail\?name=/.test(u)),
     'keine Detail-Abfrage — woher kämen Orte und Ereignisse?');

  // --- 2. Was auf der Seite steht ---------------------------------------- //
  const text = detailEl.textContent;
  ok('Name steht auf der Seite', /Düsseldorf/.test(text));
  ok('Zahlen stehen auf der Seite', /342/.test(text), text.slice(0, 120));
  ok('Beschreibung wird gezeigt', /Landeshauptstadt/.test(text),
     'die Beschreibung wurde geholt und nicht gerendert');
  ok('Karte der Orte wird angelegt', !!d.getElementById('comp-map'),
     'ohne Karte ist die Seite eine Liste');
  ok('Zurück-Knopf vorhanden', !!d.getElementById('comp-back'),
     'eine Seite ohne Rückweg ist eine Sackgasse');
  ok('Zeitstrahl bleibt als Knopf erreichbar', !!d.getElementById('city-timeline'),
     'für alle Besuche ist der Zeitstrahl der richtige Ort — der Weg muss bleiben');

  // Die Vorschau sagt, dass sie eine ist. Ohne den Hinweis behauptet eine
  // Seite mit einem Eintrag, die Stadt hätte einen.
  ok('Vorschau nennt den Rest', /341/.test(text),
     'zeigt 1 von 342 und sagt es nicht');

  // --- 3. Der Zeitstrahl-Knopf tut, was er verspricht --------------------- //
  d.getElementById('city-timeline').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await new Promise(r => setTimeout(r, 10));
  ok('Zeitstrahl-Knopf filtert auf die Stadt', w.__timeline === 'Düsseldorf',
     `filterte auf "${w.__timeline}"`);

  // --- 4. Kein Abruf-Sturm bei Wikipedia --------------------------------- //
  const first = calls.filter(u => /describe/.test(u)).length;
  ok('Beschreibung wird beim ersten Mal geholt', first === 1,
     `${first} Abrufe beim ersten Öffnen`);
  calls.length = 0;
  await w.openCityDetail('Düsseldorf');
  await new Promise(r => setTimeout(r, 30));
  ok('zwischengespeicherte Beschreibung wird nicht erneut geholt',
     calls.filter(u => /describe/.test(u)).length === 0,
     'jedes Öffnen fragt erneut bei Wikipedia an');

  // Und derselbe Verzicht für den Fall, den man leicht übersieht: eine Stadt
  // OHNE Wikipedia-Artikel. Der Server hat dafür eine Zeile ohne Text — das ist
  // eine Antwort. Wer auf den Text statt auf die Zeile prüft, fragt für jede
  // artikellose Stadt bei jedem Öffnen erneut nach.
  cached = 'leer';
  calls.length = 0;
  await w.openCityDetail('Düsseldorf');
  await new Promise(r => setTimeout(r, 30));
  ok('„kein Artikel" gilt als Antwort, nicht als Lücke',
     calls.filter(u => /describe/.test(u)).length === 0,
     'artikellose Städte fragen bei jedem Öffnen erneut');

  // --- 5. Die Seite lädt nicht die ganze Stadt ---------------------------- //
  ok('Stadtseite holt keine unbegrenzte Ereignisliste',
     !calls.some(u => /\/api\/events\?/.test(u) && !/limit=/.test(u)),
     'greift an der Vorschau vorbei auf die volle Liste');

  console.log(fail ? `\n${fail} Prüfung(en) fehlgeschlagen` : '\nA42: alles grün');
  process.exit(fail ? 1 : 0);
}, 300);
