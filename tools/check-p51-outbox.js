// P5.1 — Offline erfassen: der Wächter gegen die stille Sorte Datenverlust.
//
// Was hier geprüft wird, sieht man einem laufenden Bildschirm NICHT an, weil
// der Fehlerfall am Entwicklungsrechner nie eintritt: dort ist immer Netz.
// Genau deshalb muss der Zustand HERGESTELLT werden (`navigator.onLine`
// abschalten, fetch scheitern lassen) — `check-a41-cities.js` hat ein Jahr
// lang den Auslieferungszustand gelesen und war deshalb grün, ohne etwas zu
// prüfen.
//
// Die fünf Eigenschaften, ohne die P5.1 nur so AUSSIEHT, als würde es puffern:
//   1. Ohne Netz landet der Text in der Warteschlange — und das Feld ist leer,
//      damit niemand denkt, er müsse ihn selbst aufheben.
//   2. Die Warteschlange ist SICHTBAR (Text, Zähler). Eine unsichtbare
//      Warteschlange ist von Datenverlust nicht zu unterscheiden.
//   3. Kommt das Netz zurück, geht der Eintrag raus — mit `client_id`, sonst
//      erzeugt jeder Wiederholungsversuch ein zweites Fragment.
//   4. Ein vom Server ABGELEHNTER Eintrag wird nicht endlos neu gesendet,
//      sondern sichtbar liegen gelassen — 401 dagegen bleibt wiederholbar.
//   5. Ein Eintrag verschwindet NIE, weil eine Anfrage scheiterte.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-p51-outbox.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');

// --- Netz-Attrappe: sie kann offline, kann antworten und kann ablehnen ----- //
const net = { online: true, mode: 'ok', posts: [] };

function makeDom(url) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url,
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w.L = new Proxy(function () { return w.L; }, { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
      Object.defineProperty(w.navigator, 'onLine', { get: () => net.online, configurable: true });
      w.fetch = (u, opt) => {
        const path = String(u);
        if (opt && opt.method === 'POST' && /\/api\/ingest/.test(path)) {
          if (!net.online) return Promise.reject(new TypeError('Failed to fetch'));
          net.posts.push(JSON.parse(opt.body));
          if (net.mode === 'reject')
            return Promise.resolve({ ok: false, status: 422, statusText: 'Unprocessable',
                                     json: () => Promise.resolve({ detail: 'Text zu lang' }) });
          if (net.mode === 'auth')
            return Promise.resolve({ ok: false, status: 401, statusText: 'Unauthorized',
                                     json: () => Promise.resolve({}) });
          return Promise.resolve({ ok: true, status: 200,
                                   json: () => Promise.resolve({ fragment: { id: 'f1' }, events: [] }) });
        }
        if (!net.online) return Promise.reject(new TypeError('Failed to fetch'));
        let body = [];
        if (/\/api\/auth\/config/.test(path)) body = { mode: 'dev' };
        else if (/\/api\/auth\/me$/.test(path)) body = { id: 'u1', display_name: 'Test', role: 'admin' };
        else if (/\/api\/auth\/me\/settings/.test(path)) body = { tracked_modules: null };
        else if (/\/api\/modules/.test(path)) body = [];
        else if (/\/health/.test(path)) body = { version: '0.36.0', display_version: '0.36.0', channel: 'dev' };
        else if (/\/api\/events\/index/.test(path)) body = { total: 0, dated: 0, undated: 0, unconfirmed: 0, years: [] };
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      };
    },
  });
}

let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c && !detail ? '' : c ? '' : ` — ${detail}`));
  if (!c) fail++;
};
const wait = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const dom = makeDom('http://localhost:8000/');
  await wait(60);
  const w = dom.window, d = w.document;
  const outbox = () => JSON.parse(w.localStorage.getItem('lifedash.outbox') || '[]');

  // --- 1. Ohne Netz wird gepuffert statt verloren ------------------------- //
  net.online = false;
  w.dispatchEvent(new w.Event('offline'));
  d.getElementById('input-text').value = 'Adler in Detmold gesehen';
  await w.analyze();
  await wait(20);

  ok('Ohne Netz landet die Erfassung in der Warteschlange', outbox().length === 1,
     `${outbox().length} Einträge — der Text ist weg`);
  ok('Der Text steht vollständig darin',
     (outbox()[0] || {}).raw_text === 'Adler in Detmold gesehen');
  ok('Das Eingabefeld ist danach leer',
     d.getElementById('input-text').value === '',
     'der Text steht doppelt da: im Feld und in der Warteschlange');
  ok('Ohne Netz wird gar nicht erst gesendet', net.posts.length === 0);

  // --- 2. Sichtbarkeit: die stille Warteschlange ist der eigentliche Defekt //
  const panel = d.getElementById('outbox-panel');
  ok('Die Warteschlange ist sichtbar', panel && panel.style.display !== 'none',
     'gepuffert, aber nirgends zu sehen — nicht von Verlust zu unterscheiden');
  ok('Sie zeigt den gepufferten Text', /Adler in Detmold/.test(panel.textContent));
  ok('Sie sagt, worauf sie wartet', /Netz|Verbindung|network|connection/i.test(panel.textContent));
  const badge = d.getElementById('nav-outbox-badge');
  ok('Der Zähler an „Eingabe" steht auf 1',
     badge && badge.style.display !== 'none' && badge.textContent === '1');
  ok('Der manuelle Reiter zeigt sich als außer Kraft (A40-Regel)',
     d.getElementById('input-mode-manual').classList.contains('inert'),
     'ein Formular, das man ausfüllen darf und nicht abschicken kann');

  // --- 2b. Der Kasten wird im JS gebaut, also muss der Sprachwechsel ihn
  //     ANFASSEN. `data-i18n` allein setzte den Titel auf die Fassung ohne
  //     Zähler zurück und ließe die Liste in der alten Sprache stehen (F10).
  //     Die Ausgangssprache wird HERGESTELLT: jsdom meldet `en-US`, die App
  //     folgt beim ersten Besuch dem Browser — ein Wächter, der Deutsch
  //     annimmt, prüft sonst die Rückrichtung und merkt es nicht.
  w.eval("LANG = 'de'; applyLang();");
  await wait(40);
  ok('Auf Deutsch steht der deutsche Titel da',
     /Wartet auf Verbindung/.test(panel.textContent), panel.textContent.slice(0, 90));
  d.getElementById('lang-btn').dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(40);
  ok('Sprachwechsel übersetzt die Warteschlange',
     /Waiting for a connection/.test(panel.textContent), panel.textContent.slice(0, 90));
  ok('…und behält den Zähler', /\(1\)/.test(panel.textContent),
     panel.textContent.slice(0, 90));
  ok('…und den gepufferten Text (Nutzertext wird nie übersetzt)',
     /Adler in Detmold/.test(panel.textContent));
  ok('…auch die Zustandszeile', /No network|connection/i.test(panel.textContent),
     panel.textContent.slice(0, 120));

  // --- 3. Netz zurück: raus damit, mit Kennung --------------------------- //
  net.online = true;
  const queuedId = outbox()[0].id;
  w.dispatchEvent(new w.Event('online'));
  await wait(60);

  ok('Mit Netz geht die Erfassung raus', net.posts.length === 1,
     `${net.posts.length} Sendungen`);
  ok('Sie trägt eine client_id (sonst verdoppelt jeder Wiederholversuch)',
     net.posts[0] && net.posts[0].client_id === queuedId,
     JSON.stringify(net.posts[0]));
  ok('Danach ist die Warteschlange leer', outbox().length === 0);
  ok('Und der Kasten verschwindet',
     d.getElementById('outbox-panel').style.display === 'none');
  ok('Der Zähler verschwindet mit',
     d.getElementById('nav-outbox-badge').style.display === 'none');

  // --- 4. Abgelehnt ist nicht dasselbe wie „kein Netz" ------------------- //
  net.posts.length = 0;
  net.mode = 'reject';
  d.getElementById('input-text').value = 'Ein abgelehnter Text';
  await w.analyze();
  await wait(20);
  ok('Eine echte Server-Antwort wird NICHT gepuffert', outbox().length === 0,
     'ein 422 im Puffer wird für immer wiederholt');

  // Derselbe Fall aus der Warteschlange heraus: der Eintrag war schon drin,
  // als der Server ihn ablehnte.
  w.localStorage.setItem('lifedash.outbox', JSON.stringify(
    [{ id: 'x1', raw_text: 'Abgelehnt', at: new Date().toISOString() }]));
  await w.flushOutbox(true);
  await wait(20);
  ok('Der abgelehnte Eintrag bleibt erhalten', outbox().length === 1,
     'stillschweigend verworfen — genau das darf nie passieren');
  ok('Er trägt den Grund', !!(outbox()[0] || {}).error, JSON.stringify(outbox()[0]));
  ok('Der Kasten zeigt den Grund an',
     /Text zu lang/.test(d.getElementById('outbox-panel').textContent));

  net.posts.length = 0;
  await w.flushOutbox(true);
  await wait(20);
  ok('Und er wird nicht endlos neu gesendet', net.posts.length === 0,
     `${net.posts.length} Wiederholungen trotz Ablehnung`);

  // 401 ist die Ausnahme: nicht abgelehnt, nur abgemeldet.
  w.localStorage.setItem('lifedash.outbox', JSON.stringify(
    [{ id: 'x2', raw_text: 'Sitzung abgelaufen', at: new Date().toISOString() }]));
  net.mode = 'auth';
  net.posts.length = 0;
  await w.flushOutbox(true);
  await wait(20);
  ok('Nach 401 bleibt der Eintrag WIEDERHOLBAR (kein Fehlerstempel)',
     outbox().length === 1 && !outbox()[0].error,
     'nach dem Anmelden ginge derselbe Eintrag durch — abgestempelt nie wieder');

  // --- 4b. Der Speicher ist voll ----------------------------------------- //
  // Der eine Weg, auf dem dieses Paket selbst Daten vernichten könnte: das
  // Eingabefeld leeren, obwohl das Puffern scheiterte. Dann steht der Text
  // nirgends mehr.
  net.online = false;
  net.mode = 'ok';
  w.localStorage.setItem('lifedash.outbox', '[]');
  // Am Prototyp, nicht am Objekt: `localStorage` ist in jsdom (wie im Browser)
  // ein Proxy, der unbekannte Zuweisungen als EINTRAG ablegt — ein
  // `localStorage.setItem = …` legte also stillschweigend einen Schlüssel
  // namens „setItem" an und überschriebe nichts.
  const realSet = w.Storage.prototype.setItem;
  w.Storage.prototype.setItem = function (k, v) {
    if (k === 'lifedash.outbox') throw new Error('QuotaExceededError');
    return realSet.call(this, k, v);
  };
  d.getElementById('input-text').value = 'Darf nicht verschwinden';
  await w.analyze();
  await wait(20);
  ok('Scheitert das Puffern, bleibt der Text im Feld stehen',
     d.getElementById('input-text').value === 'Darf nicht verschwinden',
     'Feld geleert, obwohl nichts gespeichert wurde — der Text ist weg');
  ok('…und es wird gesagt',
     /voll|full/i.test(d.getElementById('toast-wrap').textContent),
     d.getElementById('toast-wrap').textContent);
  w.Storage.prototype.setItem = realSet;

  // --- 5. Nichts geht verloren, wenn das Netz mittendrin abreißt --------- //
  w.localStorage.setItem('lifedash.outbox', JSON.stringify([
    { id: 'y1', raw_text: 'Erster', at: new Date().toISOString() },
    { id: 'y2', raw_text: 'Zweiter', at: new Date().toISOString() },
  ]));
  net.mode = 'ok';
  net.online = false;
  net.posts.length = 0;
  await w.flushOutbox(true);
  await wait(20);
  ok('Netzabriss verliert keinen Eintrag', outbox().length === 2,
     `${outbox().length} übrig`);

  net.online = true;
  await w.flushOutbox(true);
  await wait(30);
  ok('Nach der Rückkehr gehen beide raus, in der Reihenfolge der Erfassung',
     outbox().length === 0 && net.posts.length === 2
     && net.posts[0].raw_text === 'Erster' && net.posts[1].raw_text === 'Zweiter',
     JSON.stringify(net.posts.map(p => p.raw_text)));

  // --- 5b. Zwei Auslöser auf einmal ------------------------------------- //
  // Beim „online"-Ereignis feuern zwei Stellen: der allgemeine Zuhörer und
  // (nach einem Offline-Start) der, der danach neu lädt. Ein blosses
  // `if (busy) return;` gäbe dem zweiten ein SOFORT erfülltes Versprechen —
  // `await flushOutbox(); location.reload()` lüde dann mitten im Senden neu.
  w.localStorage.setItem('lifedash.outbox', JSON.stringify([
    { id: 'z1', raw_text: 'Nur einmal', at: new Date().toISOString() },
  ]));
  net.posts.length = 0;
  const first = w.flushOutbox();
  const second = w.flushOutbox();          // parallel, während der erste läuft
  await second;                            // muss auf den LAUFENDEN warten
  ok('Ein zweiter Aufruf wartet auf den laufenden Sendelauf',
     outbox().length === 0,
     'kehrte sofort zurück — ein Neuladen danach träfe mitten ins Senden');
  await first;
  ok('…und sendet nichts doppelt', net.posts.length === 1,
     `${net.posts.length} Sendungen für einen Eintrag`);

  dom.window.close();

  // --- 6. Teilen aus einer anderen App ----------------------------------- //
  // Eigenes Fenster, denn die Adresse steht beim Start fest — genau so kommt
  // die Freigabe aus dem Betriebssystem an.
  net.posts.length = 0;
  const shared = makeDom('http://localhost:8000/share?title=Artikel&text=Sehr%20guter%20Text&url=https://example.org/a');
  await wait(120);
  const sw = shared.window, sd = sw.document;
  const ta = sd.getElementById('input-text').value;
  ok('Geteiltes landet im Eingabefeld', /Sehr guter Text/.test(ta), `Feld: "${ta}"`);
  ok('Titel und Link gehen nicht verloren',
     /Artikel/.test(ta) && /example\.org/.test(ta), `Feld: "${ta}"`);
  ok('Die Eingabe-Ansicht ist offen',
     sd.getElementById('view-input').classList.contains('active'));
  ok('Nichts wird ungefragt gespeichert', net.posts.length === 0,
     'ein geteilter Halbsatz wäre ungeprüft im Roh-Eingang');
  ok('Die Adresse ist zurückgesetzt (Neuladen trägt nicht doppelt ein)',
     sw.location.pathname === '/' && !sw.location.search,
     `${sw.location.pathname}${sw.location.search}`);
  shared.window.close();

  console.log(fail ? `\nP5.1: ${fail} Prüfung(en) fehlgeschlagen` : '\nP5.1: alles grün');
  process.exit(fail ? 1 : 0);
})();
