// Ort auf der Karte wählen — und ob der gewählte Punkt wirklich ankommt.
//
// **Der Defekt, um den es hier geht, sieht nach Erfolg aus.** Wer auf der
// Karte auf ein Haus klickt, bekommt eine Adresse ins Feld, drückt Speichern,
// und der Eintrag steht da — mit einem Ort, einem Namen, einer Koordinate. Nur
// ist es nicht die geklickte: fehlt `location_lat`/`location_lng` im Absenden,
// geocodiert der Server den NAMEN vorwärts und legt den Punkt dorthin, wo
// Nominatim den Ort sieht (meist der Ortsmittelpunkt). Nichts daran meldet
// sich; die Karte zeigt danach einen Punkt, nur einen anderen. Genau die
// Sorte Stille, die in diesem Projekt der wiederkehrende Fehler ist.
//
// Fünf Zusagen:
//
//   1. **Alle drei Felder haben den Knopf, und er öffnet den Dialog.** Ein
//      Feld ohne ihn ist kein Fehler, den man sieht — man tippt eben weiter.
//   2. **Erst ein Punkt, dann „Übernehmen".** Der Knopf ist bis dahin gesperrt;
//      ein Übernehmen ohne Punkt schriebe eine Adresse ohne Bezug ins Feld.
//   3. **Die Adresse wird nachgeschlagen und steht im Feld** — sie ist die
//      Beschriftung, nicht die Angabe.
//   4. **Der Punkt reist in ALLEN DREI Absendungen mit** (Eingabe,
//      Bearbeiten-Dialog, Wohnort). Drei Formulare, drei Stellen, an denen
//      dasselbe vergessen werden kann.
//   5. **Wer den Namen danach ändert, meint den Namen** — dann darf die alte
//      Koordinate NICHT mitfahren. Zwei Angaben über dieselbe Sache laufen
//      sonst auseinander (Anmerkung 106): das Feld sagt „Berlin", der Punkt
//      zeigt aufs Elternhaus, und der Server nimmt den Punkt.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-place-picker.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

// Unverwechselbare Werte: aus keinem Datum, keiner Zählung und keiner anderen
// Koordinate der Testdaten abzuleiten.
const PICK_LAT = 53.93412;
const PICK_LNG = 10.30871;
const PICK_NAME = 'Musterweg 1, Mözen, Deutschland';
// Was ein Vorwärts-Geocoding aus dem NAMEN machen würde. Steht hier, damit
// klar ist, dass die beiden Wege verschiedene Antworten geben — sonst wäre
// jede Zusicherung hier grün, egal welcher genommen wird.
const EVENT_PLACE = { id: 'l1', name: 'Alter Ort', lat: 50.0, lng: 8.0 };

function makeDom(state) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w.confirm = () => true;

      // **Das Leaflet-Doppel muss `map()` und `marker()` WIRKLICH können.**
      // Ein Auffang-Proxy gibt für jede Eigenschaft sich selbst zurück — dann
      // schluckt `map.on('click', fn)` den Handler, und ein Kartenklick lässt
      // sich gar nicht auslösen. Die Zusicherung wäre dann eine über den
      // Dialog und keine über das Wählen (dieselbe Falle wie beim
      // `getZoom()`- und beim `getLayers()`-Doppel, Anmerkungen 120/163).
      let base;
      const mkMap = (id) => {
        const t = { _h: {}, _id: id };
        const p = new Proxy(t, {
          get: (o, k) => {
            if (k === 'on') return (ev, fn) => { (o._h[ev] = o._h[ev] || []).push(fn); return p; };
            if (k === 'setView') return (c, z) => { o._view = [c, z]; return p; };
            if (k === 'getZoom') return () => 14;
            if (k === 'invalidateSize' || k === 'removeLayer' || k === 'addLayer'
                || k === 'fitBounds' || k === 'remove' || k === 'addControl') return () => p;
            if (k in o) return o[k];
            return base;
          },
        });
        if (id === 'pick-map') state.pickMap = p;
        return p;
      };
      const mkMarker = (ll) => {
        const mk = {
          _ll: ll, setLatLng: (x) => { mk._ll = x; return mk; },
          addTo: () => mk, bindPopup: () => mk, bindTooltip: () => mk,
          on: () => mk, remove: () => mk, setIcon: () => mk,
        };
        state.marker = mk;
        return mk;
      };
      const group = () => {
        const layers = [];
        const g = { addTo: () => g, clearLayers: () => { layers.length = 0; return g; },
                    getLayers: () => layers, addLayer: (x) => { layers.push(x); return g; },
                    _push: (x) => layers.push(x) };
        return g;
      };
      base = new Proxy(function () { return base; }, {
        get: (_t, k) => {
          if (k === 'map') return mkMap;
          if (k === 'marker') return mkMarker;
          if (k === 'layerGroup' || k === 'featureGroup') return group;
          if (k === 'getZoom') return () => 6;
          return base;
        },
        apply: () => base,
      });
      w.L = base;

      w.fetch = (u, opt) => {
        const p = String(u);
        const method = (opt && opt.method) || 'GET';
        state.calls.push([method, p, opt && opt.body]);
        let body = [];
        if (/reverse-location/.test(p)) {
          state.reverseAsked = p;
          if (state.reverseFails) {
            return Promise.resolve({ ok: false, status: 404,
                                     text: () => Promise.resolve('nix') });
          }
          body = { name: PICK_NAME };
        } else if (/\/api\/events\/e1$/.test(p)) {
          body = { id: 'e1', title: 'Konzert', category: 'concert',
                   date_start: '2026-05-01T00:00:00', date_precision: 'day',
                   confidence: 1, confirmed: 'confirmed', source: 'manual',
                   location: EVENT_PLACE, entities: [], metrics: [], media: [] };
        } else if (/\/api\/events$/.test(p) && method === 'POST') {
          body = { id: 'new', title: 'X' };
        } else if (/\/api\/baselines$/.test(p) && method === 'POST') {
          body = { id: 'b9', day_count: 7298 };
        } else if (/\/api\/baselines$/.test(p)) body = [];
        else if (/\/api\/moderation\//.test(p)) body = { id: 'e1', title: 'Konzert' };
        else if (/events\/index/.test(p)) {
          body = { total: 0, dated: 0, undated: 0, unconfirmed: 0, fuzzy: 0, years: [],
                   visits: 0, photo_events: 0, machine_proposals: 0, revision: 'r1',
                   baseline_days: 0, baseline_years: [] };
        } else if (/api\/events\?/.test(p)) body = [];
        else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
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
const inPage = (w, code) => { try { return w.eval(code); } catch (e) { return `FEHLER: ${e.message}`; } };

// Den Dialog öffnen, auf die Karte klicken, übernehmen — der ganze Weg, den
// ein Nutzer geht. Bewusst über die KNÖPFE und nicht über `openPlacePicker()`
// direkt: ein Wächter, der die Funktion selbst ruft, ist grün, sobald es sie
// gibt (der `check-a41-cities.js`-Fall, Anmerkung 108).
async function pickOn(w, d, field, lat = PICK_LAT, lng = PICK_LNG) {
  // Fehlt der Knopf, fällt die Zusicherung des Aufrufers — der Wächter darf
  // daran nicht ABSTÜRZEN, sonst bleiben alle folgenden Prüfungen ungefahren
  // und der Lauf sieht aus wie ein Lauf mit einem Befund statt mit fünf.
  const btn = d.querySelector(`[data-pick-for="${field}"]`);
  if (!btn) return false;
  btn.dispatchEvent(new w.Event('click', { bubbles: true }));
  await wait(40);
  const handlers = inPage(w, 'pickMap && pickMap._h && pickMap._h.click');
  if (!handlers || !handlers.length) return false;
  handlers[0]({ latlng: { lat, lng } });
  await wait(20);
  d.getElementById('pick-ok').dispatchEvent(new w.Event('click', { bubbles: true }));
  await wait(120);
  return true;
}
const bodyOf = (state, re, method) => {
  const hit = [...state.calls].reverse().find(
    ([m, u]) => m === method && re.test(u));
  if (!hit || !hit[2]) return null;
  try { return JSON.parse(hit[2]); } catch (_) { return null; }
};

setTimeout(async () => {
  // --- 1. Der Knopf steht an allen drei Feldern und öffnet den Dialog -------
  {
    const state = { calls: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(250);

    for (const field of ['mf-location', 'ed-location', 'bl-place']) {
      ok(`„${field}" hat einen Kartenknopf`,
         !!d.querySelector(`[data-pick-for="${field}"]`),
         'ohne ihn tippt man weiter und merkt nie, dass es die Wahl gibt');
    }

    d.querySelector('[data-pick-for="mf-location"]').dispatchEvent(
      new w.Event('click', { bubbles: true }));
    await wait(40);
    ok('Der Klick öffnet den Kartendialog',
       d.getElementById('pick-modal').classList.contains('show'));

    // (2) Ohne Punkt bleibt „Übernehmen" zu.
    ok('„Übernehmen" ist ohne gewählten Punkt gesperrt',
       d.getElementById('pick-ok').disabled,
       'sonst landete eine Adresse im Feld, auf die niemand gezeigt hat');

    const handlers = inPage(w, 'pickMap && pickMap._h && pickMap._h.click');
    ok('Ein Klick auf die Karte ist verdrahtet',
       Array.isArray(handlers) && handlers.length > 0,
       'ohne den Handler gibt es keine Wahl, nur einen Dialog');
    if (Array.isArray(handlers) && handlers.length) {
      handlers[0]({ latlng: { lat: PICK_LAT, lng: PICK_LNG } });
      await wait(20);
      ok('…und öffnet damit „Übernehmen"', !d.getElementById('pick-ok').disabled);
      ok('…und die Zeile darunter nennt den Punkt',
         d.getElementById('pick-state').textContent.includes(String(PICK_LAT)),
         d.getElementById('pick-state').textContent);
    }

    // (3) Übernehmen schlägt die Adresse nach und füllt das Feld.
    d.getElementById('pick-ok').dispatchEvent(new w.Event('click', { bubbles: true }));
    await wait(150);
    ok('„Übernehmen" schlägt die Adresse zum PUNKT nach',
       /reverse-location/.test(state.reverseAsked || '')
       && new RegExp(`lat=${PICK_LAT}`).test(state.reverseAsked || ''),
       state.reverseAsked || 'kein Abruf');
    ok('…und schreibt sie ins Feld',
       d.getElementById('mf-location').value === PICK_NAME,
       d.getElementById('mf-location').value);
    ok('…und schließt den Dialog',
       !d.getElementById('pick-modal').classList.contains('show'));
  }

  // --- 2. Der Punkt reist mit: manuelle Eingabe ----------------------------
  {
    const state = { calls: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(250);
    d.getElementById('mf-title').value = 'Grillen im Garten';
    d.getElementById('mf-date-start').value = '2026-07-01';
    ok('Kartenklick im Eingabeformular angekommen', await pickOn(w, d, 'mf-location'));
    d.getElementById('mf-save').dispatchEvent(new w.Event('click', { bubbles: true }));
    await wait(150);

    const sent = bodyOf(state, /\/api\/events$/, 'POST');
    ok('Die Erfassung schickt den gewählten Punkt mit',
       !!sent && sent.location_lat === PICK_LAT && sent.location_lng === PICK_LNG,
       `${JSON.stringify(sent && { n: sent.location_name, lat: sent.location_lat,
                                   lng: sent.location_lng })} — ohne die beiden `
       + 'Werte geocodiert der Server den NAMEN vorwärts und legt den Ort auf '
       + 'Nominatims Punkt, nicht auf den geklickten');
  }

  // --- 3. Der Punkt reist mit: Bearbeiten-Dialog ---------------------------
  {
    const state = { calls: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(250);
    await w.openEventEdit('e1');
    await wait(60);
    ok('Kartenklick im Bearbeiten-Dialog angekommen', await pickOn(w, d, 'ed-location'));
    d.getElementById('ed-save').dispatchEvent(new w.Event('click', { bubbles: true }));
    await wait(150);

    const sent = bodyOf(state, /\/api\/moderation\//, 'PATCH');
    ok('Die Korrektur schickt den gewählten Punkt mit',
       !!sent && sent.location_lat === PICK_LAT && sent.location_lng === PICK_LNG,
       JSON.stringify(sent));
    ok('…und den Namen dazu',
       !!sent && sent.location_name === PICK_NAME,
       'der Endpunkt legt den Ort nur an, wenn er weiß, wie er heißen soll');
  }

  // --- 4. Der Punkt reist mit: Wohnort -----------------------------------
  {
    const state = { calls: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(250);
    d.getElementById('bl-from').value = '1991-09-25';
    ok('Kartenklick im Wohnort-Formular angekommen', await pickOn(w, d, 'bl-place'));
    d.getElementById('bl-add').dispatchEvent(new w.Event('click', { bubbles: true }));
    await wait(150);

    const sent = bodyOf(state, /\/api\/baselines$/, 'POST');
    ok('Der Wohnort schickt den gewählten Punkt mit',
       !!sent && sent.lat === PICK_LAT && sent.lng === PICK_LNG,
       `${JSON.stringify(sent)} — ohne Koordinate bekommen die abgeleiteten `
       + 'Tage nie ein Wetter, und genau dafür gibt es den Wohnort');
  }

  // --- 5. Wer den Namen ändert, meint den Namen ----------------------------
  {
    const state = { calls: [] };
    const w = makeDom(state).window, d = w.document;
    await wait(250);
    d.getElementById('mf-title').value = 'Etwas anderes';
    await pickOn(w, d, 'mf-location');
    // Von Hand überschrieben — jetzt ist der Text die Aussage, nicht der Punkt.
    d.getElementById('mf-location').value = 'Berlin';
    d.getElementById('mf-save').dispatchEvent(new w.Event('click', { bubbles: true }));
    await wait(150);

    const sent = bodyOf(state, /\/api\/events$/, 'POST');
    ok('Ein von Hand geänderter Name löst den Punkt',
       !!sent && sent.location_name === 'Berlin'
       && sent.location_lat == null && sent.location_lng == null,
       `${JSON.stringify(sent && { n: sent.location_name, lat: sent.location_lat })} `
       + '— sonst sagt das Feld „Berlin" und der gespeicherte Punkt zeigt aufs '
       + 'Elternhaus (Anmerkung 106)');
  }

  // --- 6. Ohne Adresse bleibt der Punkt trotzdem gültig --------------------
  {
    const state = { calls: [], reverseFails: true };
    const w = makeDom(state).window, d = w.document;
    await wait(250);
    d.getElementById('mf-title').value = 'Hütte im Wald';
    await pickOn(w, d, 'mf-location');
    ok('Ohne Adresse bekommt das Feld die Platzhalter-Schreibweise',
       /^Ort \(/.test(d.getElementById('mf-location').value),
       `„${d.getElementById('mf-location').value}" — leer zu bleiben verschwiege `
       + 'den Fehlschlag, und „Ort (…)" ist die Marke, an der der '
       + 'Ortsnamen-Lauf ihn später wiederfindet');

    d.getElementById('mf-save').dispatchEvent(new w.Event('click', { bubbles: true }));
    await wait(150);
    const sent = bodyOf(state, /\/api\/events$/, 'POST');
    ok('…und der Punkt geht trotzdem mit',
       !!sent && sent.location_lat === PICK_LAT,
       'der Punkt ist die Aussage — ob es eine Adresse dazu gibt, ändert daran nichts');
  }

  console.log(fail ? `\nOrtswahl: ${fail} Zusicherung(en) gerissen`
                   : '\nOrtswahl: alles grün');
  process.exit(fail ? 1 : 0);
}, 400);
