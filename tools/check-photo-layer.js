// A45 — die Foto-Ebene sagt, was sie tut, und tut nichts Stilles.
//
// Vier Eigenschaften, und drei davon sind die Sorte, die beim Bauen aus
// Versehen verschwindet, ohne dass etwas kaputt aussieht:
//
//   1. **Ohne verortete Fotos ist der Schalter sichtbar außer Kraft** (A40).
//      Ein Schalter, der aussieht wie ein Angebot und nichts tut, schickt den
//      Nutzer auf Fehlersuche bei der Karte statt beim fehlenden Lauf.
//   2. **Aus ist der Standard.** Zwanzig Jahre Bibliothek sind zehntausende
//      Marker; wer die Karte öffnet, will zuerst seine Ereignisse sehen.
//   3. **Deckelt die Antwort, sagt die Karte es** (Anmerkung 110) — und zwar
//      auf der Karte, nicht in der Liste daneben.
//   4. **Die Ebene doppelt die F18-Fotoleiste nicht** — aber HOCHGELADENE
//      Bilder bleiben trotzdem stehen. Sie sind Lebensdatenbank (Anm. 57);
//      sie durch eine Ableitung verschwinden zu lassen wäre die schlimmere
//      Doppelung, nämlich eine Auslassung.
//   5. **Das Zeitfenster ist der angezeigte Zeitraum** — nicht die Spanne
//      seiner Ereignisse. Gemeldet aus dem Betrieb: 8.120 verortete Fotos,
//      und auf Mallorca 2018 kein einziger Punkt. Das Fenster endete am
//      letzten Google-Besuch des Jahres, und im Jahrzehnt umfasste es ein
//      einziges Jahr. Ein Fenster prüft kein Test von selbst: die Anfrage
//      geht raus, die Antwort kommt, die Karte sieht bedient aus.
//
// Geprüft wird der Zustand, den es GEBEN MUSS (Regel aus check-a41-cities.js):
// die Seite, nachdem jemand die Karte geöffnet und den Schalter gedrückt hat.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-photo-layer.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
// Absichtlich unverwechselbare Zahlen: ein Test, der auf „4" prüft, ist auch
// dann grün, wenn die 4 aus einem Datum stammt (beim Schreiben von
// check-a46-visit-split.js genau so passiert).
const state = {
  index: { total: 8123, first: '2004-07-12T10:00:00', last: '2024-08-01T18:00:00',
           years_scanned: [2004, 2024], max_points: 5000 },
  map: { total: 8123, shown: 5000, points: [
    { id: 'a1', lat: 51.93, lng: 8.87, at: '2024-07-12T10:00:00', place: 'Detmold' },
    { id: 'a2', lat: 51.50, lng: -0.12, at: '2024-07-12T18:00:00', place: 'London' },
  ] },
  days: { days: { '2024-07-12': 42 } },
  groups: { level: 'city', total: 42, shown: 42, groups: [
    { day: '2024-07-12', place: 'Detmold', count: 42,
      first: '2024-07-12T09:10:00', last: '2024-07-12T19:40:00',
      lat: 51.93, lng: 8.87, assets: ['a1', 'a2', 'a3'] },
  ] },
};
const EVENT = {
  id: 'e1', title: 'Konzert', date_start: '2024-07-12T20:00:00',
  date_end: '2024-07-12T22:00:00', date_precision: 'exact', category: 'event',
  confirmed: 'confirmed', source: 'manual',
  location: { id: 'l1', name: 'Detmold', lat: 51.93, lng: 8.87, city: 'Detmold' },
};

function makeDom(withPhotos) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      // `getZoom` liefert eine ZAHL, und zwar eine steuerbare: die Punktgröße
      // hängt daran (Anmerkung 120). Ein Doppel, das hier den Alles-Proxy
      // zurückgibt, beantwortet eine andere Frage als Leaflet — und jeder
      // Vergleich `z >= 14` stürzt darüber ab.
      w.__zoom = 6;
      w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => w.__zoom : w.L), apply: () => w.L });
      w.fetch = (u, opt) => {
        const p = String(u);
        calls.push([(opt && opt.method) || 'GET', p]);
        let body = [];
        if (/photos\/index/.test(p)) body = withPhotos ? state.index
          : { total: 0, first: null, last: null, years_scanned: [], max_points: 5000 };
        else if (/photos\/days/.test(p)) body = state.days;
        else if (/photos\/groups/.test(p)) body = state.groups;
        else if (/photos\/map/.test(p)) body = state.map;
        else if (/events\/map/.test(p)) body = [EVENT];
        else if (/days\/media/.test(p)) body = {
          '2024-07-12': [
            { id: 'm1', provider: 'immich', thumb_url: '/api/media/m1/thumb',
              url: '/api/media/m1/file', captured_at: '2024-07-12T10:00:00', sort_order: 0 },
            { id: 'm2', provider: 'local', thumb_url: '/api/media/m2/thumb',
              url: '/api/media/m2/file', captured_at: '2024-07-12T11:00:00', sort_order: 1 },
          ] };
        else if (/api\/events\?/.test(p) || /api\/events$/.test(p)) body = [EVENT];
        else if (/events\/index/.test(p)) body = { total: 1, dated: 1, undated: 0, unconfirmed: 0, fuzzy: 0, years: [2024], visits: 0 };
        else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, tracked_modules: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev', channel: 'dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      };
    },
  });
}

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};
const wait = ms => new Promise(r => setTimeout(r, ms));

setTimeout(async () => {
  // --- 1. Ohne verortete Fotos: sichtbar außer Kraft ---------------------- //
  const empty = makeDom(false);
  {
    const w = empty.window, d = w.document;
    await wait(160);
    const mapChip = d.getElementById('mp-photos-toggle');
    const tlChip = d.getElementById('tl-photos-toggle');
    ok('Beide Foto-Schalter existieren', !!mapChip && !!tlChip);
    await w.openMapView();
    await wait(120);
    ok('Ohne Fotos ist der Karten-Schalter durchgestrichen',
       mapChip.classList.contains('inert'),
       'ein Schalter, der nichts kann, muss das zeigen (A40)');
    ok('…und nennt den Grund', /verortet|located/i.test(mapChip.title),
       mapChip.title);
    ok('Der Zeitstrahl-Schalter ebenso', tlChip.classList.contains('inert'),
       'zwei Antworten auf dieselbe Frage laufen still auseinander');
    calls.length = 0;
    mapChip.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(40);
    ok('Ein Klick darauf holt keine Punkte',
       !calls.some(([, p]) => /photos\/map/.test(p)),
       JSON.stringify(calls));
    w.close();
  }

  // --- 2. Mit Fotos: aus als Standard, an auf Wunsch ---------------------- //
  const dom = makeDom(true);
  const w = dom.window, d = w.document;
  await wait(160);
  const mapChip = d.getElementById('mp-photos-toggle');
  const tlChip = d.getElementById('tl-photos-toggle');

  await w.openMapView();
  await wait(140);
  ok('Mit Fotos ist der Schalter benutzbar', !mapChip.classList.contains('inert'));
  ok('…und steht auf AUS', mapChip.classList.contains('off') && !w.eval('mp.showPhotos'),
     'zehntausende Marker sind nicht das, was jemand beim Öffnen sehen will');

  calls.length = 0;
  mapChip.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(140);
  ok('Eingeschaltet werden die Punkte geholt',
     calls.some(([, p]) => /photos\/map/.test(p)),
     JSON.stringify(calls.slice(-4)));
  ok('…mit einem Zeitfenster', calls.some(([, p]) => /photos\/map\?.*from=/.test(p)),
     'ohne Fenster käme die ganze Bibliothek in eine Antwort (A37)');

  // --- 3. Die Deckelung steht AUF der Karte ------------------------------- //
  const note = d.getElementById('mp-photo-note');
  ok('Die Deckelung wird genannt', note && note.style.display !== 'none',
     'sonst sieht ein Ausschnitt aus wie die ganze Bibliothek (Anm. 110)');
  ok('…mit beiden Zahlen', /8[.,]123/.test(note.textContent) && /5[.,]000/.test(note.textContent),
     note.textContent);
  ok('…und zwar im Kartenbereich',
     !!note.closest('.map-wrap'),
     'wer auf die Karte sieht, liest die Liste daneben nicht');

  // --- 3b. Das Fenster ist der Zeitraum, nicht seine Ereignisse ----------- //
  // Der Bestand hat GENAU EIN Ereignis (12.07.2024). Käme das Fenster wie
  // früher aus den Ereignissen, endete das Jahr 2024 am 12. Juli und das
  // Jahrzehnt umfasste allein das Jahr 2020 — beides fällt hier auf.
  const windowFor = async mode => {
    calls.length = 0;
    w.eval(`mp.mode = '${mode}'; rebuildPeriods(); renderPeriod();`);
    await wait(60);
    const hit = calls.map(([, p]) => p).reverse().find(p => /photos\/map/.test(p));
    return hit ? decodeURIComponent(hit.split('?')[1] || '') : '';
  };
  const yearQs = await windowFor('year');
  ok('Das Jahr fragt das ganze Jahr ab',
     /from=2024-01-01T00:00:00/.test(yearQs) && /to=2024-12-31T23:59:59/.test(yearQs),
     yearQs || 'keine Anfrage');
  const decadeQs = await windowFor('decade');
  ok('Das Jahrzehnt fragt zehn Jahre ab',
     /from=2020-01-01T00:00:00/.test(decadeQs) && /to=2029-12-31T23:59:59/.test(decadeQs),
     decadeQs || 'keine Anfrage');
  const allQs = await windowFor('all');
  ok('„Alle" grenzt gar nicht ein', allQs === '',
     `„from=undefined" wäre ein Datum, das der Server zu lesen versucht: ${allQs}`);
  w.eval("mp.mode = 'day'; rebuildPeriods(); renderPeriod();");
  await wait(60);

  // --- 3c. Ein Punkt muss zu sehen sein (Anmerkung 120) ------------------- //
  // Gemeldet aus dem Betrieb: „Fotopunkte zu unauffällig und klein, gehen im
  // Cluster und unter den Pins unter." Sie lagen bei festen 4 px mit 1 px
  // Rand — in der Weltansicht ein Staubkorn, im Stadtplan genauso groß. Die
  // REIHENFOLGE bleibt bewusst (Fotos unter den Pins, Ereignisse sind die
  // Lebensdatenbank); sichtbar wird der Punkt über Größe und Rand.
  // Fehlt die Funktion ganz, ist das ein FEHLSCHLAG, kein Absturz: ein
  // Wächter, der stirbt, sagt nicht, WAS fehlt (Anmerkung 108).
  const rAt = z => { try { return w.eval(`__zoom = ${z}; mpPhotoRadius()`); } catch (_) { return 0; } };
  ok('Ein Fotopunkt ist größer als die alten 4 px', rAt(6) > 4, `${rAt(6)} px`);
  ok('…und wächst beim Hineinzoomen', rAt(15) > rAt(6),
     `Zoom 6: ${rAt(6)} px, Zoom 15: ${rAt(15)} px — sonst ist er im Stadtplan derselbe Fleck`);
  ok('…in Stufen, nicht sprunghaft', rAt(9) >= rAt(6) && rAt(12) >= rAt(9),
     `${rAt(6)}/${rAt(9)}/${rAt(12)}/${rAt(15)}`);
  w.eval('__zoom = 6');

  // --- 4. Zeitstrahl: Gruppen statt doppelter Leisten --------------------- //
  calls.length = 0;
  tlChip.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(220);
  ok('Der Zeitstrahl holt verdichtete Gruppen',
     calls.some(([, p]) => /photos\/groups/.test(p)),
     JSON.stringify(calls.slice(-5)));
  ok('…verdichtet vom SERVER, mit Stufe',
     calls.some(([, p]) => /photos\/groups\?.*level=/.test(p)),
     'im Browser gruppiert zerschneidet die Seitengrenze die Gruppe (A39/A37)');

  const list = d.getElementById('timeline-list');
  ok('Die Gruppe steht im Zeitstrahl', /42/.test(list.textContent),
     list.textContent.slice(0, 200));
  ok('…mit ihrem Ort', /Detmold/.test(list.textContent));
  ok('Sie sagt, dass sie auswählt', /3.*42|42.*3/.test(list.textContent),
     '„3 Bilder" über einer Gruppe von 42 behauptet Vollständigkeit');

  // Die Immich-Leiste desselben Tages ist weg — die Gruppe zeigt dieselben
  // Bilder, nur vollständig gezählt.
  ok('Die doppelte Immich-Leiste ist weg',
     !list.innerHTML.includes('/api/media/m1/thumb'),
     'dieselben Bilder zweimal, einmal mit falscher Zahl');
  // …aber das HOCHGELADENE Bild bleibt. Es steckt in keinem Fotopunkt.
  ok('Das hochgeladene Bild bleibt stehen',
     list.innerHTML.includes('/api/media/m2/thumb'),
     'Anmerkung 57: eine Ableitung darf Lebensdatenbank nicht verdecken');

  console.log(fail ? `\nFoto-Ebene: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nFoto-Ebene: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
