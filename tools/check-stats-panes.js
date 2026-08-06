// Anmerkungen 155/156 — drei Statistik-Ansichten und die Ranglisten.
//
// Vier Zusagen, jede einzeln still brechbar:
//
//   1. **Es sind wirklich drei Ansichten.** Wenn das Umschalten nur die
//      Reiterleiste einfärbt und alle Kacheln weiter untereinander stehen,
//      sieht das Ergebnis fast genauso aus wie vorher — nur mit einer Leiste
//      darüber. Geprüft wird deshalb, WAS sichtbar ist, nicht was aktiv heißt.
//   2. **Die Ranglisten kommen erst beim Ansehen** (A37). Ein Endpunkt, der
//      schon beim Öffnen des Reiters mitgeholt wird, ist keine dritte Ansicht,
//      sondern ein größerer Überblick.
//   3. **Die gemerkte Ansicht ist die gezeigte** — dieselbe Falle wie bei der
//      Sammlungs-Sortierung (Anmerkung 149): der Zustand nach dem ersten
//      Laden ist der, den niemand prüft, weil jeder Test vorher klickt.
//   4. **Tage führen, Einträge stehen daneben** (Anmerkung 143/148), und eine
//      Wetter-Zeile führt zu ihrem TAG (Anmerkung 142) — nicht in den
//      Bearbeiten-Dialog des Eintrags, der zufällig den Messwert trägt.
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-stats-panes.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const calls = [];
let fail = 0;
const ok = (n, c, detail = '') => {
  console.log((c ? '  ok  ' : '  XX  ') + n + (c ? '' : ` — ${detail}`));
  if (!c) fail++;
};
const wait = ms => new Promise(r => setTimeout(r, ms));
const inPage = (w, code) => { try { return w.eval(code); } catch (e) { return `FEHLER: ${e.message}`; } };

// Absichtlich unverwechselbare Zahlen (Regel aus check-a46-visit-split.js).
const TOPLISTS = {
  weather: {
    hot: [{ value: 38.4, id: 'e1', title: 'Andalusien', date_start: '2019-06-26T14:00:00',
            date_precision: 'day', place: 'Sevilla' },
          { value: 31.5, id: 'e2', title: 'Balkon', date_start: '2022-07-19T15:00:00',
            date_precision: 'day', place: 'Detmold' }],
    cold: [], sunny: [], rainy: [], windy: [], snowy: [], gust: [],
    felt_hot: [], felt_cold: [], longest_day: [], shortest_day: [],
    // Anmerkung 189: „am längsten geregnet" — eine andere Frage als „am
    // meisten geregnet", und der Wert lag seit F12 ungenutzt herum.
    rain_long: [{ value: 18.0, id: 'e9', title: 'Dauerregen',
                  date_start: '2024-06-21T09:00:00', date_precision: 'day',
                  place: 'Hamburg' }],
  },
  places: [{ name: 'Kaiserstraße 5', days: 4711, events: 8123 }],
  cities: [{ name: 'Schwerin', days: 317, events: 902 }],
  countries: [{ name: 'Portugal', days: 129, events: 431 }],
  years: [{ name: '2019', days: 288, events: 640 }],
  categories: [{ name: 'meal', days: 205, events: 519 }],
  streaks: {
    longest_run: { from: '2019-01-01', to: '2019-03-12', days: 71 },
    longest_gap: { from: '2003-02-01', to: '2003-04-30', days: 89 },
    longest_trip: { id: 't1', title: 'Interrail', from: '2011-07-01',
                    to: '2011-07-24', days: 24 },
  },
  // --- Anmerkung 189 ---
  photos: { total: 7412, uploads: 91, linked: 7321, events_with_photo: 812,
            events_total: 8900, first: '2004-08-03', last: '2026-07-30',
            bytes: 268435456,
            years: [{ year: 2004, count: 12 }],
            days: [{ day: '2021-09-09', count: 137 }] },
  farthest: { km: 8412.5, place: 'Kuta Beach', city: 'Denpasar',
              country: 'Indonesien', date: '2016-03-12', home: 'Elternhaus' },
  // Anmerkung 195: bewusst MEHR als zehn Jahre — der Deckel greift erst
  // darüber, und ein Wächter, der ihn nie auslöst, prüft ihn nicht.
  reach: [{ year: 2016, countries: 7, cities: 23 },
          ...Array.from({ length: 13 }, (_, i) => (
            { year: 2017 + i, countries: 2, cities: 5 }))],
};
// Wege — eigener Endpunkt, eigener Reiter, andere Herkunft.
const TRACKS = {
  total_km: 184213.4, count: 51987, first: '2013-05-02', last: '2026-07-28',
  modes: [{ mode: 'drive', count: 20114, km: 152880.2 },
          { mode: null, count: 33, km: 12.7 }],
  years: [{ year: 2013, count: 400, km: 6120.5 },
          { year: 2014, count: 900, km: 9042.1 }],
  longest: [{ date: '2015-08-14', mode: 'drive', km: 913.6 }],
};
const OVERVIEW = {
  counts: { events: 2, unconfirmed: 0, places: 1, cities: 1, concerts: 0,
            milestones: 0, meals: 0, moves: 0 },
  birth: null, age: null, per_year: [[2019, 2]], per_category: [['event', 2]],
  top_places: [['Kaiserstraße 5', 4711]], top_cities: [['Schwerin', 317]],
  top_animals: [], extremes: {}, weather: { days: 0 },
};

function makeDom(stored) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost:8000/',
    beforeParse(w) {
      w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w.L = new Proxy(function () { return w.L; },
        { get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L });
      // Eine gemerkte Ansicht, die NICHT die Voreinstellung ist — sonst prüft
      // dieser Wächter nur den frisch geklickten Zustand, und der ist immer
      // stimmig (die Lehre aus check-comp-sort.js).
      if (stored) w.localStorage.setItem('ld_stats_pane', stored);
      w.fetch = (u, opt) => {
        const p = String(u);
        calls.push([(opt && opt.method) || 'GET', p]);
        let body = [];
        if (/stats\/tracks/.test(p)) body = TRACKS;
        else if (/stats\/toplists/.test(p)) body = TOPLISTS;
        else if (/stats\/overview/.test(p)) body = OVERVIEW;
        else if (/stats\/widgets/.test(p)) body = [];
        else if (/events\/index/.test(p)) body = { revision: 'r1', total: 2, dated: 2,
          undated: 0, unconfirmed: 0, years: [{ year: 2019, count: 2 }] };
        else if (/auth\/config/.test(p)) body = { mode: 'dev' };
        else if (/auth\/me\/settings/.test(p)) body = { immich: null, place_name_parts: ['city'] };
        else if (/auth\/me$/.test(p)) body = { id: 'u1', display_name: 'T', role: 'admin' };
        else if (/\/api\/modules/.test(p)) body = [];
        else if (/\/health/.test(p)) body = { version: '0.39.0', display_version: '0.39.0-dev' };
        else if (/\/api\/jobs/.test(p)) body = [];
        else if (/api\/compendium\//.test(p)) body = [];
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
      };
    },
  });
}

// Sichtbar heißt: der Kasten selbst steht nicht auf display:none.
const visiblePanes = d => [...d.querySelectorAll('#view-stats .stats-pane')]
  .filter(p => p.style.display !== 'none').map(p => p.dataset.statsPane);

setTimeout(async () => {
  // --- 1. Der erste Blick: gemerkt ist „Diagramme" ------------------------ //
  {
    const w = makeDom('charts').window, d = w.document;
    await wait(160);
    calls.length = 0;
    await w.loadStats();
    await wait(120);
    // **Nicht „es sind drei".** Die Zahl stand hier bis F21 und war ein
    // Wächter für die Vergangenheit (Anmerkung 114): sie fiel um, als eine
    // vierte Ansicht dazukam, obwohl nichts kaputt war — und sie hätte
    // geschwiegen, wenn ein Reiter ohne Bereich (oder umgekehrt) entstanden
    // wäre, also beim einzigen Defekt, den es hier gibt. Geprüft wird
    // stattdessen, dass sich Leiste und Bereiche DECKEN, in beide Richtungen.
    const tabs = [...d.querySelectorAll('#stats-tabs .zoom-btn')].map(b => b.dataset.stats);
    const panes = [...d.querySelectorAll('#view-stats .stats-pane')].map(p => p.dataset.statsPane);
    ok('Jeder Reiter hat seinen Bereich — und jeder Bereich seinen Reiter',
       tabs.length > 0 && tabs.length === panes.length
       && tabs.every(x => panes.includes(x)) && panes.every(x => tabs.includes(x)),
       `Reiter: ${tabs.join(', ')} · Bereiche: ${panes.join(', ')}`);
    ok('Die gemerkte Ansicht ist die gezeigte',
       visiblePanes(d).join(',') === 'charts',
       `sichtbar: ${visiblePanes(d).join(', ') || '(nichts)'}`);
    const active = d.querySelector('#stats-tabs .zoom-btn.active');
    ok('…und die Leiste sagt dasselbe', active && active.dataset.stats === 'charts',
       `aktiv: ${active && active.dataset.stats}`);
    // A37: die teure Antwort erst beim Ansehen.
    ok('Die Ranglisten werden dabei NICHT geholt',
       !calls.some(([, p]) => /toplists/.test(p)),
       'ein Endpunkt, der immer mitkommt, ist keine eigene Ansicht');
    // Gegenprobe: die Kacheln sind nicht weg, nur nicht dran.
    ok('Die Kacheln sind gefüllt, auch wenn sie gerade nicht dran sind',
       d.getElementById('stat-events').textContent === '2',
       d.getElementById('stat-events').textContent);
    w.close();
  }

  // --- 2. Umschalten auf die Ranglisten ----------------------------------- //
  const dom = makeDom('tiles');
  const w = dom.window, d = w.document;
  await wait(160);
  await w.loadStats();
  await wait(120);
  ok('Voreingestellt sind die Zahlen', visiblePanes(d).join(',') === 'tiles',
     `sichtbar: ${visiblePanes(d).join(', ')}`);

  calls.length = 0;
  const topsTab = d.querySelector('#stats-tabs [data-stats="tops"]');
  ok('Es gibt einen Reiter für die Ranglisten', !!topsTab);
  if (topsTab) topsTab.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(200);
  ok('Der Klick zeigt die Ranglisten', visiblePanes(d).join(',') === 'tops',
     `sichtbar: ${visiblePanes(d).join(', ')}`);
  ok('…und holt sie erst jetzt', calls.some(([, p]) => /toplists/.test(p)),
     JSON.stringify(calls.map(c => c[1])));
  ok('…und merkt sich die Wahl',
     inPage(w, "localStorage.getItem('ld_stats_pane')") === 'tops',
     'ohne localStorage ist es keine Einstellung, sondern eine Wiederholung');

  const tops = d.getElementById('stats-tops');
  ok('Es gibt einen Kasten für die Ranglisten', !!tops);
  const txt = (tops ? tops.textContent : '').replace(/\s+/g, ' ');

  // --- 3. Tage führen, Einträge stehen daneben ---------------------------- //
  ok('Die Ortsliste nennt die Tage', /4[.,]711/.test(txt), txt.slice(0, 200));
  ok('…und die Einträge daneben', /8[.,]123/.test(txt), txt.slice(0, 200));
  ok('Städte, Länder, Jahre und Kategorien stehen da',
     /Schwerin/.test(txt) && /Portugal/.test(txt) && /2019/.test(txt)
     && /317/.test(txt) && /129/.test(txt),
     txt.slice(0, 300));
  ok('Die Serien stehen da', /71/.test(txt) && /89/.test(txt) && /Interrail/.test(txt),
     txt.slice(0, 300));

  // --- 4. Die Wetterliste ist die Kachel, nur ganz ------------------------ //
  ok('Die Wetter-Rangliste zeigt alle Plätze', /38[.,]4/.test(txt) && /31[.,]5/.test(txt),
     txt.slice(0, 300));
  ok('…mit Ort und Anlass', /Sevilla/.test(txt) && /Andalusien/.test(txt),
     txt.slice(0, 300));
  // Anmerkung 142: der Klick führt zum TAG.
  //
  // **Gezielt gesucht und nicht „die erste".** Seit Anmerkung 189 gibt es
  // mehrere Sorten anklickbarer Zeilen (der entfernteste Punkt, die Foto-Tage),
  // und `querySelector` nahm die oberste — die Prüfung hätte dann eine andere
  // Zeile geprüft als die, um die es geht, und wäre grün geblieben.
  const row = tops && [...tops.querySelectorAll('[data-top-day]')]
    .find(r => r.dataset.topDay === '2019-06-26');
  ok('Eine Wetter-Zeile trägt ihren Tag', !!row,
     [...(tops ? tops.querySelectorAll('[data-top-day]') : [])]
       .map(r => r.dataset.topDay).join(', '));
  if (row) {
    row.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await wait(120);
    ok('…und der Klick führt in den Zeitstrahl DIESES Tages',
       inPage(w, 'tl.day') === '2019-06-26',
       `tl.day = ${inPage(w, 'tl.day')} — nicht in den Bearbeiten-Dialog eines `
       + 'Eintrags, der zufällig den Messwert trägt (Anmerkung 142)');
  }

  // --- 5. Anmerkung 189: was bisher ungenutzt herumlag -------------------- //
  ok('Die Regenstunden haben eine eigene Rangliste', /18/.test(txt)
     && /Dauerregen/.test(txt),
     '„nassester Tag" misst Millimeter — wie LANGE es geregnet hat, ist eine '
     + 'andere Frage, und der Wert lag seit F12 in jeder Zeile');

  // Fotos: die Zahl steht mit ihrem Nenner da, und hochgeladen/verknüpft
  // bleiben getrennt (Anmerkung 57 — das eine ist Lebensdatenbank, das andere
  // eine Ableitung, und genau den Unterschied merkt ein Backup).
  ok('Die Foto-Tafel nennt die Gesamtzahl', /7[.,]412/.test(txt), txt.slice(0, 400));
  ok('…und trennt Hochgeladenes von Verknüpftem',
     /91/.test(txt) && /7[.,]321/.test(txt),
     'eine gemeinsame Zahl verspräche einen Bestand, von dem der größere Teil '
     + 'in einem fremden System liegt');
  ok('…und nennt den Nenner, nicht nur den Zähler',
     /812/.test(txt) && /8[.,]900/.test(txt),
     '„812 Einträge mit Bild" ist keine Auskunft, „812 von 8.900" ist eine');
  ok('Der Tag mit den meisten Fotos steht da', /137/.test(txt), txt.slice(0, 400));

  // Am weitesten weg — die Frage gibt es erst mit dem Wohnort.
  // Gerundet angezeigt (8.412,5 -> „8.413 km") — Kilometer mit Nachkommastelle
  // wären eine Genauigkeit, die eine Luftlinie über 8.000 km nicht hat.
  ok('Der entfernteste Punkt steht da mit seiner Entfernung',
     /8[.,]41[23]/.test(txt) && /Kuta Beach/.test(txt), txt.slice(0, 400));
  ok('…und sagt, WOVON gemessen wurde', /Elternhaus/.test(txt),
     'ohne den Bezugspunkt ist „8.412 km" keine Aussage — ein '
     + 'Lebensmittelpunkt wandert');
  ok('Die Reichweite je Jahr steht da', /7/.test(txt) && /23/.test(txt),
     txt.slice(0, 400));

  // --- 5b. Anmerkung 195: die Kacheln passen aufeinander ------------------- //
  //
  // Gemeldet wurde „das sieht doof aus mit großer Lücke": „Am weitesten von zu
  // Hause" (EINE Zeile) stand neben „Reichweite je Jahr" (vierzig) und wurde
  // vom Raster auf dessen Höhe gestreckt — ein weißes Feld, das zu neun
  // Zehnteln leer war. Geprüft wird deshalb die ANORDNUNG, nicht das Aussehen:
  // welche Kachel steht in welcher Reihe.
  const panelOf = re => [...(tops ? tops.querySelectorAll('.panel') : [])]
    .find(p => re.test((p.querySelector('h3') || {}).textContent || ''));
  const far = panelOf(/weitesten|Farthest/);
  const streaks = panelOf(/Längste Serien|Longest streaks/);
  const reachPanel = panelOf(/Reichweite|Reach per year/);
  const years = panelOf(/Top-Jahre|Top years/);
  ok('Die beiden kurzen Auskünfte stehen in DERSELBEN Reihe',
     !!far && !!streaks && far.parentElement === streaks.parentElement,
     'eine einzeilige Kachel neben einer vierzigzeiligen wird auf deren Höhe '
     + 'gestreckt — genau die gemeldete Lücke');
  ok('…und die Reichweite steht bei den Ranglisten',
     !!reachPanel && !!years && reachPanel.parentElement === years.parentElement,
     'dort sind alle Kacheln zehn Zeilen hoch');
  // Der Deckel selbst: gescrollt, nicht gekürzt — und er SAGT, wie viele es
  // sind. Ein Deckel, der schweigt, sieht aus wie das Ende der Daten.
  const capped = reachPanel && reachPanel.querySelector('.panel-rows.capped');
  ok('Die lange Liste wird gedeckelt statt gestreckt', !!capped,
     'ohne Deckel zieht sie die Reihe daneben auf ihre Höhe');
  ok('…zeigt aber weiterhin ALLE Zeilen',
     !!capped && capped.querySelectorAll('.top-row').length === 14,
     `Zeilen: ${capped ? capped.querySelectorAll('.top-row').length : '-'} — `
     + 'gedeckelt heißt gescrollt, nicht abgeschnitten');
  ok('…und die Überschrift nennt die Gesamtzahl',
     !!reachPanel && /\(\s*14\s*\)/.test(reachPanel.querySelector('h3').textContent),
     reachPanel ? reachPanel.querySelector('h3').textContent : '(keine Kachel)');
  const short = far && far.querySelector('.panel-rows');
  ok('Eine kurze Kachel bekommt KEINEN Deckel',
     !!short && !short.classList.contains('capped'),
     'ein Rollbalken um eine einzelne Zeile wäre die Lücke nur anders');

  // --- 6. Die Wege: eigener Reiter, eigene Herkunft ----------------------- //
  calls.length = 0;
  const trTab = d.querySelector('#stats-tabs [data-stats="tracks"]');
  ok('Es gibt einen eigenen Reiter für die Wege', !!trTab,
     'zwischen den Ranglisten stünden diese Zahlen neben erfassten Tatsachen, '
     + 'als wären sie welche');
  if (trTab) trTab.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  await wait(200);
  ok('Der Klick zeigt sie', visiblePanes(d).join(',') === 'tracks',
     `sichtbar: ${visiblePanes(d).join(', ')}`);
  ok('…und holt sie erst jetzt', calls.some(([, p]) => /stats\/tracks/.test(p)),
     JSON.stringify(calls.map(c => c[1])));
  const trPane = d.querySelector('[data-stats-pane="tracks"]');
  const trTxt = (trPane ? trPane.textContent : '').replace(/\s+/g, ' ');
  // **Die eigentliche Zusage dieses Reiters.** Die Warnung steht ÜBER den
  // Zahlen und ist ANZEIGE, nicht deutscher Quelltext — unter jsdom startet
  // die Seite englisch, und ein ins Markup gebauter Hinweis erreichte die
  // Prüfung nie (Anmerkung 116/160).
  ok('Die Herkunft steht über den Zahlen',
     /Google/.test(trTxt) && /imprecise|ungenau/i.test(trTxt),
     trTxt.slice(0, 200));
  const warnPos = trTxt.indexOf('Google');
  ok('…und zwar VOR ihnen, nicht als Fußnote',
     warnPos >= 0 && warnPos < trTxt.indexOf('184'),
     `Warnung bei ${warnPos}, erste Zahl bei ${trTxt.indexOf('184')} — wer eine `
     + 'Jahressumme liest, hat die Fußnote schon hinter sich');
  ok('Die Summe steht da', /184[.,]213|184213/.test(trTxt.replace(/\s/g, '')),
     trTxt.slice(0, 300));
  ok('…und die Fortbewegungsart in Worten',
     /car|Auto/.test(trTxt), trTxt.slice(0, 300));
  ok('Ein Weg OHNE Angabe wird nicht zu „unbekannt" gemacht',
     /export|Export/.test(trTxt),
     '`unknown` heißt „Google wusste es nicht", `null` heißt „im Export stand '
     + 'nichts" — zwei Fälle, zwei Sätze');

  // --- 7. Anmerkung 199: eine Zählung ohne Loch -------------------------- //
  //
  // Die Ränge der Serien-Kachel standen als 0/1/2 im Quelltext und wurden
  // DANACH gefiltert. Fehlt eine der drei Zeilen — und `longest_gap` fehlt bei
  // jedem lückenlos erfassten Bestand —, zeigte die Kachel „1." und „3.".
  // Eine Zählung mit Loch liest sich wie eine verschwundene Zeile.
  //
  // Der Fall wird HERGESTELLT und nicht abgewartet: die Fixtures oben haben
  // alle drei Zeilen, und mit ihnen ist die Kachel immer stimmig — genau der
  // Zustand, den jede bisherige Prüfung gesehen hat.
  {
    TOPLISTS.streaks = { ...TOPLISTS.streaks, longest_gap: null };
    const w2 = makeDom('tops').window, d2 = w2.document;
    await wait(160);
    await w2.loadStats();
    await wait(200);
    const pane = d2.getElementById('stats-tops');
    const panel = [...(pane ? pane.querySelectorAll('.panel') : [])]
      .find(p => /Längste Serien|Longest streaks/
        .test((p.querySelector('h3') || {}).textContent || ''));
    const ranks = [...(panel ? panel.querySelectorAll('.top-rank') : [])]
      .map(e => e.textContent.trim());
    ok('Ohne Lücke im Bestand fehlt die Zeile, nicht die Zahl',
       ranks.length === 2, `Zeilen: ${ranks.length}`);
    ok('…und die Ränge zählen lückenlos weiter',
       ranks.join(',') === '1,2',
       `Ränge: ${ranks.join(', ')} — „1." und „3." sieht aus, als wäre eine `
       + 'Zeile verschwunden');
    w2.close();
  }

  console.log(fail ? `\nAnm. 155/156: ${fail} Prüfung(en) fehlgeschlagen`
                   : '\nAnm. 155/156: alles grün');
  process.exit(fail ? 1 : 0);
}, 80);
