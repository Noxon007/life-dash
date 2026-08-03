// Anmerkung 139 — ein Foto ist ein Ereignis, und die beiden Ansichten zeigen
// zwei verschiedene Dinge davon.
//
// Diese Datei löst `check-photo-layer.js` (A45) ab. Die alte Ebene hatte einen
// eigenen Abruf und eine eigene Tabelle; beides ist weg. Was bleibt, sind
// **fünf Zusagen, die man dem Ergebnis nicht ansieht**:
//
//   1. **Die Karte bekommt das BILD, der Zeitstrahl die TATSACHE.** Ein
//      Foto-Ereignis zeigt im Zeitstrahl ausdrücklich kein Vorschaubild — das
//      ist eine bewusste Unterdrückung und sieht beim Lesen wie ein Fehler
//      aus, also wird sie festgenagelt. Auf der Karte hängt dasselbe Ereignis
//      sein Bild ins Popup.
//   2. **Ein Foto ist kein Pin.** Zehntausend nummerierte Marker mit
//      Stopp-Listen-Einträgen wären eine unbedienbare Karte und eine Liste,
//      in der kein von Hand erfasster Eintrag mehr zu finden ist. Fotos gehen
//      auf die Leinwand, unter die Pins.
//   3. **Zwei getrennte Schalter.** 🛰️ Google und 📷 Immich sind zwei Sorten
//      Beleg mit zwei Größenordnungen; ein gemeinsamer Schalter blendete
//      hunderte Besuche mit zehntausenden Fotos zusammen aus.
//   4. **Der Schalter filtert im SERVER.** Ein ausgeschalteter Schalter soll
//      zehntausende Punkte gar nicht erst über die Leitung schicken — und ein
//      eingeschalteter muss sie deshalb anfordern. Ein Filter, der nur in eine
//      Richtung wirkt, macht aus dem Einschalten eine Aktion ohne Wirkung.
//   5. **Ohne Foto-Ereignisse ist der Schalter sichtbar außer Kraft** (A40) —
//      sonst sucht der Nutzer den Fehler bei der Karte statt beim fehlenden
//      Lauf.
//
// Geprüft wird der Zustand, den es GEBEN MUSS (Regel aus check-a41-cities.js):
// die Seite, nachdem jemand die Karte geöffnet und den Schalter gedrückt hat.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-photo-events.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
// Gezeichnete Formen: `marker` = Pin, `circleMarker` = Punkt auf der Leinwand.
// Der Unterschied IST die zweite Zusage, also wird er gemessen.
const drawn = { marker: 0, circle: 0, popups: [] };

// Absichtlich unverwechselbare Zahlen (Regel aus check-a46-visit-split.js: ein
// Test auf „4" ist auch grün, wenn die 4 aus einem Datum stammt).
const ASSET = 'asset-77713';
const PHOTO_EVENT = {
  id: 'pe1', title: 'Foto in Detmold', category: 'event',
  date_start: '2024-07-12T10:00:00', date_precision: 'exact',
  confirmed: 'confirmed', source: 'immich', photo: ASSET,
  location: { id: 'lp', name: 'Detmold', lat: 51.93, lng: 8.87, city: 'Detmold' },
  entities: [], metrics: [],
  // Ein Foto-Ereignis trägt normalerweise gar keinen MediaRef. Hier bekommt es
  // trotzdem einen: die Unterdrückung im Zeitstrahl muss auch dann greifen,
  // wenn Medien DA sind — sonst prüft der Wächter nur, dass eine leere Liste
  // leer bleibt (dieselbe Falle wie `every` auf einer leeren Liste, Anm. 108).
  media: [{ id: 'mp', provider: 'immich', thumb_url: '/api/media/mp/thumb',
            url: '/api/media/mp/file', sort_order: 0 }],
};
// Wie ein Fotopunkt im Speicher aussieht, nachdem `expandPhotoPoints` die
// kompakte Form entpackt hat (Anmerkung 157) — keine Ereigniskennung.
const PHOTO_EVENT_POINT = {
  source: 'immich', category: 'event', date_start: '2024-07-12T10:00:00',
  photo: ASSET, location: { name: 'Detmold', lat: 51.93, lng: 8.87 },
};
const HAND_EVENT = {
  id: 'he1', title: 'Konzert', category: 'concert',
  date_start: '2024-07-12T20:00:00', date_precision: 'exact',
  confirmed: 'confirmed', source: 'manual',
  location: { id: 'lh', name: 'Köln', lat: 50.94, lng: 6.96, city: 'Köln' },
  entities: [], metrics: [],
  media: [{ id: 'mh', provider: 'local', thumb_url: '/api/media/mh/thumb',
            url: '/api/media/mh/file', sort_order: 0 }],
};

function makeDom(photoCount) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      // `getZoom` liefert eine ZAHL, und zwar eine steuerbare: die Punktgröße
      // hängt daran (Anmerkung 120). Ein Doppel, das hier den Alles-Proxy
      // zurückgibt, beantwortet eine andere Frage als Leaflet — und jeder
      // Vergleich `z >= 14` stürzt darüber ab.
      w.__zoom = 6;
      const shape = kind => (...args) => {
        if (kind === 'marker') drawn.marker++;
        if (kind === 'circle') drawn.circle++;
        const self = {
          addTo: () => self,
          bindPopup: (c) => { if (kind === 'circle') drawn.popups.push(String(c)); return self; },
          bindTooltip: () => self, setRadius: () => self, on: () => self,
        };
        return self;
      };
      const base = new Proxy(function () { return base; }, {
        get: (_t, k) => {
          if (k === 'getZoom') return () => w.__zoom;
          if (k === 'marker') return shape('marker');
          if (k === 'circleMarker') return shape('circle');
          if (k === 'canvas') return () => ({ _n: 'canvas' });
          return base;
        },
        apply: () => base,
      });
      w.L = base;
      w.fetch = (u, opt) => {
        const p = String(u);
        calls.push([(opt && opt.method) || 'GET', p]);
        let body = [];
        const wantsPhotos = !/[?&]photos=0/.test(p);
        if (/events\/map/.test(p)) {
          // **Anmerkung 157: die echte Antwortform.** Fotos kommen kompakt
          // (`[lat, lng, Zeit, Asset, Ort-Index, Kategorie-Index]`), Pins als
          // Ereignisse. Vorher legte dieses Doppel das Foto-EREIGNIS in
          // `events` — die Form, die der Server bis Anmerkung 157 schickte.
          // Damit hätte der Wächter die Umstellung nicht bemerkt und
          // stattdessen weiter einen Weg geprüft, den es nicht mehr gibt: ein
          // Doppel, das eine Form nachbaut, die der Server nicht mehr spricht,
          // ist keine Vereinfachung, sondern eine andere Funktion (Anm. 116).
          const evs = [HAND_EVENT];
          const photos = wantsPhotos && photoCount
            ? { places: ['Detmold'], cats: ['event'],
                points: [[51.93, 8.87, '2024-07-12T10:00:00', ASSET, 0, 0]] }
            : { places: [], cats: [], points: [] };
          body = { total: photoCount ? photoCount + 1 : 1,
                   shown: evs.length + photos.points.length,
                   events: evs, photos };
        } else if (/events\/index/.test(p)) {
          body = { total: 2, dated: 2, undated: 0, unconfirmed: 0, fuzzy: 0,
                   years: [{ year: 2024, count: 2 }], visits: 3,
                   photo_events: photoCount, machine_proposals: 0 };
        } else if (/days\/media/.test(p)) {
          body = { '2024-07-12': [
            { id: 'ds', provider: 'immich', thumb_url: '/api/media/ds/thumb',
              url: '/api/media/ds/file', captured_at: '2024-07-12T10:00:00', sort_order: 0 }] };
        } else if (/api\/events\?/.test(p)) {
          body = /[?&]photos=0/.test(p) ? [HAND_EVENT] : [PHOTO_EVENT, HAND_EVENT];
        } else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
        else if (/api\/tracks/.test(p)) body = { total: 0, shown: 0, tracks: [] };
        else if (/immich\/day-clusters/.test(p)) body = { total: 0, sample: [] };
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
// Ein Wächter, der beim kaputten Stand ABSTÜRZT statt zu berichten, sagt zwar
// „nicht grün", aber nicht warum — und Anmerkung 108 verlangt, ihn genau dort
// laufen zu lassen.
const inPage = (w, code) => { try { return w.eval(code); } catch (e) { return `FEHLER: ${e.message}`; } };

setTimeout(async () => {
  // --- 1. Ohne Foto-Ereignisse: sichtbar außer Kraft ---------------------- //
  {
    const w = makeDom(0).window, d = w.document;
    await wait(160);
    const mapChip = d.getElementById('mp-photos-toggle');
    const tlChip = d.getElementById('tl-photos-toggle');
    ok('Beide Foto-Schalter existieren', !!mapChip && !!tlChip);
    await w.openMapView();
    await wait(120);
    ok('Ohne Foto-Ereignisse ist der Karten-Schalter durchgestrichen',
       mapChip.classList.contains('inert'),
       'ein Schalter, der nichts kann, muss das zeigen (A40)');
    ok('…und nennt den Grund', /Ereignis|event/i.test(mapChip.title), mapChip.title);
    ok('Der Zeitstrahl-Schalter ebenso', tlChip.classList.contains('inert'),
       'zwei Antworten auf dieselbe Frage laufen still auseinander');
    w.close();
  }

  // --- 2. Mit Foto-Ereignissen -------------------------------------------- //
  const dom = makeDom(12481);
  const w = dom.window, d = w.document;
  await wait(160);
  const mapChip = d.getElementById('mp-photos-toggle');
  const tlChip = d.getElementById('tl-photos-toggle');

  await w.openMapView();
  await wait(140);
  ok('Mit Foto-Ereignissen ist der Schalter benutzbar',
     !mapChip.classList.contains('inert'));
  ok('…und steht auf AUS', mapChip.classList.contains('off') && !w.eval('mp.showPhotos'),
     'zehntausende Punkte sind nicht das, was jemand beim Öffnen sehen will');
  ok('…und nennt SEINE Zahl', /12[.,]481/.test(mapChip.textContent),
     `${mapChip.textContent} — ein gemeinsamer Zähler mit den Google-Besuchen `
     + 'passte zu keinem der beiden Schalter');

  // --- 3. Der Schalter filtert im SERVER ---------------------------------- //
  calls.length = 0;
  mapChip.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(160);
  const mapCalls = calls.filter(([, p]) => /events\/map/.test(p)).map(c => c[1]);
  ok('Einschalten holt die Punkte NEU', mapCalls.length > 0,
     'ein Filter, der nur ausblendet, macht aus dem Einschalten eine Aktion '
     + 'ohne Wirkung');
  ok('…ohne photos=0 im Gepäck', mapCalls.length > 0
     && mapCalls.every(p => !/photos=0/.test(p)), JSON.stringify(mapCalls));

  // --- 4. Ein Foto ist kein Pin ------------------------------------------- //
  drawn.marker = 0; drawn.circle = 0; drawn.popups.length = 0;
  w.eval("mp.mode = 'all'; rebuildPeriods(); renderPeriod();");
  await wait(80);
  ok('Das Foto-Ereignis geht auf die Foto-Ebene', inPage(w, 'mpPhotoPoints.length') === 1,
     `${inPage(w, 'mpPhotoPoints.length')} Punkte, ${drawn.marker} Pins — zehntausend `
     + 'nummerierte Marker wären eine unbedienbare Karte');
  // **Anmerkung 153.** Bis dahin war jeder Fotopunkt ein eigener
  // `L.circleMarker`: ein Objekt mit Ereignis-Abonnement und Popup, das bei
  // jedem Kartenschritt einzeln projiziert wird. Bei zwanzigtausend Fotos
  // stürzte der Tab damit ab, sobald eine Vektorkarte darunter lag. Die Zusage
  // ist deshalb nicht mehr „es wird ein Kreis gezeichnet", sondern **„es
  // entsteht KEIN Objekt je Foto"** — und das ist die Zusicherung, die beim
  // nächsten bequemen `L.circleMarker(...)` sofort umfällt.
  //
  // **Anmerkung 160 schärft die Zusicherung.** Bis dahin lautete sie „es
  // entsteht KEIN `circleMarker`" — das war richtig, solange nur Fotos Kreise
  // waren. Seit die Ortsgruppen Flächen sind (Fläche statt Ziffer), gibt es
  // Kreise, die mit Fotos nichts zu tun haben, und die alte Fassung wäre rot
  // geworden, ohne dass etwas kaputt ist.
  //
  // Was wirklich gemeint war und jetzt dasteht: **die Zahl der Leaflet-Objekte
  // wächst nicht mit der Zahl der Fotos.** Gemessen wird mit einem Foto und
  // mit fünfhundert; bleibt die Zahl gleich, ist die Ebene eine Leinwand.
  // Genau diese Zusicherung fällt beim nächsten bequemen `L.circleMarker(...)`
  // je Punkt sofort um.
  const objectsWith = n => {
    const many = Array.from({ length: n }, (_, i) => ({
      source: 'immich', category: 'event', date_start: '2024-07-12T10:00:00',
      photo: 'a' + i,
      location: { name: 'Detmold', lat: 51.93 + i * 0.0001, lng: 8.87 },
    }));
    drawn.marker = 0; drawn.circle = 0;
    inPage(w, `mp.located = mp.located.filter(e => e.source !== 'immich')
                 .concat(${JSON.stringify(many)});
               rebuildPeriods(); renderPeriod();`);
    return drawn.marker + drawn.circle;
  };
  const few = objectsWith(1), lots = objectsWith(500);
  ok('…und die Objektlast wächst NICHT mit der Zahl der Fotos', few === lots,
     `${few} Objekte bei 1 Foto, ${lots} bei 500 — genau die Last, die den Tab umbrachte`);
  ok('…die Punkte sind trotzdem alle da', inPage(w, 'mpPhotoPoints.length') === 500,
     `${inPage(w, 'mpPhotoPoints.length')} — eine Leinwand, die nichts zeichnet, ist auch sparsam`);
  // Zurück auf den Stand, den die folgenden Prüfungen erwarten.
  inPage(w, "mp.located = mp.located.filter(e => e.source !== 'immich')"
          + `.concat([${JSON.stringify(PHOTO_EVENT_POINT)}]); rebuildPeriods(); renderPeriod();`);
  // **Anmerkung 157.** Der Punkt kommt kompakt an und wird hier wieder zu
  // einem Punkt mit Ort, Zeit und Bild — aber ohne Ereigniskennung. Beides
  // wird geprüft: dass die Entpackung stimmt (sonst zeichnete die Ebene
  // `undefined`-Koordinaten und wäre trotzdem „ein Punkt lang"), und dass
  // niemand die Kennung der Vollständigkeit halber zurücklegt.
  ok('…der kompakte Punkt trägt Ort, Zeit und Asset',
     inPage(w, "mpPhotoPoints[0] && mpPhotoPoints[0].location.name") === 'Detmold'
     && inPage(w, "mpPhotoPoints[0] && mpPhotoPoints[0].location.lat") === 51.93
     && inPage(w, "mpPhotoPoints[0] && mpPhotoPoints[0].photo") === ASSET,
     JSON.stringify(inPage(w, 'JSON.stringify(mpPhotoPoints[0])')));
  ok('…und KEINE Ereigniskennung',
     inPage(w, "mpPhotoPoints[0] && mpPhotoPoints[0].id") === undefined,
     '36 Zeichen je Punkt für etwas, das die Karte nie öffnet (Anm. 139)');
  const popup = typeof w.photoPopupHtml === 'function'
    ? String(w.photoPopupHtml(PHOTO_EVENT)) : '(photoPopupHtml fehlt)';
  ok('…und das Bild hängt im Popup', popup.includes(`/api/photos/${ASSET}/thumb`),
     `${popup.slice(0, 200)} — die Karte ist der Ort für das Bild`);
  // Gegenprobe: die Ebene folgt dem Schalter, nicht der Liste. Ohne diese
  // Prüfung wäre „geht auf die Foto-Ebene" auch dann grün, wenn der Schalter
  // gar nichts mehr bewirkt.
  inPage(w, "mp.showPhotos = false; renderPeriod();");
  await wait(60);
  ok('Ausgeschaltet ist die Ebene leer', inPage(w, 'mpPhotoPoints.length') === 0,
     `${inPage(w, 'mpPhotoPoints.length')} Punkte trotz ausgeschaltetem Schalter`);
  inPage(w, "mp.showPhotos = true; renderPeriod();");
  await wait(60);
  const stops = d.getElementById('mp-stops');
  ok('…und steht NICHT in der Stopp-Liste', !/Foto in Detmold/.test(stops.textContent),
     `${stops.textContent.slice(0, 160)} — sonst findet niemand mehr einen von `
     + 'Hand erfassten Eintrag darin');
  ok('Das handerfasste Ereignis steht sehr wohl drin',
     /Konzert/.test(stops.textContent), stops.textContent.slice(0, 160));

  // --- 5. Die Deckelung steht AUF der Karte ------------------------------- //
  const note = d.getElementById('mp-photo-note');
  ok('Die Deckelung wird genannt', note && note.style.display !== 'none',
     'sonst sieht ein Ausschnitt aus wie der ganze Bestand (Anm. 110)');
  if (note) {
    ok('…mit beiden Zahlen', /12[.,]482/.test(note.textContent)
       && /\b2\b/.test(note.textContent), note.textContent);
    ok('…und zwar im Kartenbereich', !!note.closest('.map-wrap'),
       'wer auf die Karte sieht, liest die Liste daneben nicht');
  }

  // --- 6. Der Zeitstrahl bekommt die TATSACHE, nicht das Bild ------------- //
  w.eval("tl.zoom = 'month';");
  calls.length = 0;
  tlChip.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(300);
  const evCalls = calls.filter(([, p]) => /api\/events\?/.test(p)).map(c => c[1]);
  ok('Der Zeitstrahl fragt die Foto-Ereignisse beim Server an',
     evCalls.some(p => /photos=1/.test(p)),
     `${JSON.stringify(evCalls.slice(-2))} — im Browser gefiltert bestünde eine `
     + 'Seite fast nur aus Ausgeblendetem (A37)');

  const list = d.getElementById('timeline-list');
  ok('Das Foto-Ereignis steht im Zeitstrahl', /Foto in Detmold/.test(list.textContent),
     list.textContent.slice(0, 200));
  // **Die Kernzusage.** Sie sieht beim Lesen wie ein Fehler aus, deshalb steht
  // sie hier ausgeschrieben: dasselbe Ereignis, dessen Bild auf der Karte im
  // Popup hängt, zeigt im Zeitstrahl KEINS.
  ok('…aber OHNE sein Vorschaubild',
     !list.innerHTML.includes('/api/media/mp/thumb'),
     'zwölf Vorschaubilder je Zeile über zwanzig Jahre sind eine Wand, keine '
     + 'Erinnerung — und die Bilder des Tages stehen schon in der Tagesleiste');
  // Die Gegenprobe: die Unterdrückung darf nicht ALLE Bilder treffen.
  ok('Das handerfasste Ereignis behält seins',
     list.innerHTML.includes('/api/media/mh/thumb'),
     'die Unterdrückung hängt an der QUELLE, nicht am Vorhandensein von Medien');
  ok('Und die Tagesleiste bleibt', list.innerHTML.includes('/api/media/ds/thumb'),
     'Job 2 aus Anmerkung 139 ist unverändert — sie ist jetzt sogar die '
     + 'einzige Stelle, an der die Bilder eines Tages stehen');

  console.log(fail ? `\nFoto-Ereignisse: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nFoto-Ereignisse: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
