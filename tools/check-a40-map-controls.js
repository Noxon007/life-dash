// Die Kartenschalter — A40 (Anmerkung 92), fortgeschrieben mit Anmerkung 160.
//
// Der Auslöser war 2026-07, dass der Autor selbst nicht mehr sagen konnte, was
// die vier Schalter tun — und die Untersuchung fand den Grund: zwei von ihnen
// taten unter üblichen Umständen gar nichts und sahen dabei eingeschaltet aus.
// Anmerkung 154 hat die Reihe dann ganz auseinandergenommen und vier Befunde
// benannt; Anmerkung 160 baut den Entwurf „Zwei Fragen" daraus.
//
// **Die Regel, die dieser Wächter durchsetzt, ist über alle drei Runden
// dieselbe: kein Bedienelement darf still wirkungslos sein.** Was dazugekommen
// ist, ist die Form, in der die Leiste das einlöst:
//
//   1. **Zwei beschriftete Gruppen.** „Ebenen" = woher kommt, was hier liegt.
//      „Wie dicht" = wie es zusammengefasst wird. Vorher stand beides plus
//      eine Fensterfunktion in einer Reihe gleich aussehender Chips.
//   2. **Vollbild ist keine Darstellung** und steht deshalb nicht mehr in der
//      Leiste, sondern in der Kartenecke.
//   3. **Vier benannte Stufen statt eines Ein/Aus**, dessen BEDEUTUNG die
//      Zoomstufe entschied — und dessen Aus-Zustand zusätzlich den 300er-
//      Deckel scharf schaltete, was auf ihm nirgends stand (Befund d).
//   4. **Der Deckel hängt an der Stufe „Jeder Punkt"**, nicht an einem
//      anderen Schalter, und jede Stufe sagt, was sie tut.
//   5. **🛰️ gehört dem Zeitstrahl.** Auf der Karte hieß es „zurückgelegte
//      Wege", im Zeitstrahl „automatisch erfasst" — dasselbe Zeichen für zwei
//      Dinge in zwei Reitern derselben App (Befund c).
//   6. **Fotos und Google-Besuche haben verschiedene Farben.** Sie waren
//      `#f5921b` und `#f5a623`: zwei Orangetöne für die zwei Ebenen, die man
//      am ehesten auseinanderhalten will.
//
// Geprüft wird über `renderPeriod()` mit PUNKTEN auf der Karte — nicht durch
// Direktaufruf der Sync-Funktionen und nicht auf der leeren Karte, die einen
// eigenen Zweig hat. Beides war im ersten Anlauf grün, ohne etwas zu prüfen
// (Anmerkung 108, und `check-a41-cities.js` hat denselben Fehler ein Jahr lang
// gemacht).
//
// Aufruf aus dem Repo-Wurzelverzeichnis: node tools/check-a40-map-controls.js
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'frontend/index.html', 'utf8');
const fails = [], ok = [];
const check = (name, cond, detail = '') =>
  (cond ? ok : fails).push(name + (cond ? '' : ` — ${detail}`));

const errors = [];
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost:8000/',
  beforeParse(w) {
    w.fetch = () => Promise.reject(new Error('offline'));
    w.matchMedia = w.matchMedia || (() => ({ matches: false, addEventListener() {}, addListener() {} }));
    w.L = new Proxy(function () { return w.L; }, {
      get: (_t, k) => (k === 'getZoom' ? () => 6 : w.L), apply: () => w.L,
    });
    w.addEventListener('error', e => errors.push('ERROR: ' + (e.error && e.error.stack || e.message)));
  },
});

const EV = (id, cat, city) => ({
  id, title: 'Eintrag ' + id, category: cat, date_start: '2024-07-12T20:00:00',
  date_precision: 'exact', source: 'manual',
  location: { id: 'l' + id, name: 'Ort ' + id, lat: 50.9, lng: 6.9, city },
});

setTimeout(async () => {
  const w = dom.window, d = w.document;
  try { await w.openMapView(); } catch (_) { /* offline: die Punkte fehlen, die Karte steht */ }
  check('lädt ohne Fehler',
        errors.filter(e => !/offline|Not implemented|fetch/i.test(e)).length === 0,
        errors[0]);

  // Punkte herstellen — der Zustand, aus dem die Beschwerde kam.
  w.eval(`mp.located = ${JSON.stringify([EV('a', 'trip', 'Köln'), EV('b', 'concert', 'Köln'),
                                         EV('c', 'event', null)])};`);
  const render = (extra = '') =>
    w.eval(`${extra} rebuildPeriods(); renderPeriod();`);
  render("mp.mode = 'month';");
  check('Die Karte hat für diese Prüfungen wirklich Punkte',
        w.eval('mp.periods.length') > 0, 'sonst läuft alles durch den Leer-Zweig');

  // --- 1. EINE Reihe für das WAS, eine zweite fürs WIE --------------------- //
  //
  // Anmerkung 191: Hier standen bis dahin zwei beschriftete Gruppen — „Ebenen"
  // und „Kategorien" —, und das las sich als zwei nebeneinanderstehende
  // Fragen. Es war eine Frage und ihre Unterfrage: die Kategorie-Chips
  // filterten ausschließlich das, was der Chip „Von Hand" als Ganzes
  // abschaltete. Also teilen sie sich jetzt eine Reihe, und der Sammelchip ist
  // weg. „Wie dicht" bleibt getrennt — das ist wirklich eine zweite Frage.
  const groupOf = id => {
    const el = d.getElementById(id);
    const g = el && el.closest('.filter-group');
    return g ? (g.querySelector('label') || {}).textContent : null;
  };
  const sorts = ['mp-filters', 'mp-visits-toggle', 'mp-photos-toggle',
                 'mp-tracks-toggle', 'mp-baseline-toggle'].map(groupOf);
  check('Alles, was auf der Karte liegen kann, steht in EINER Gruppe',
        sorts.every(g => g && g === sorts[0]), JSON.stringify(sorts));
  check('Den Sammelchip „Von Hand" gibt es nicht mehr',
        !d.getElementById('mp-manual-toggle'),
        'zwei Wege zu demselben Zustand — alle Kategorien aus = von Hand aus');
  check('…dafür die Sammelbefehle für die ganze Reihe',
        !!d.getElementById('mp-all') && !!d.getElementById('mp-none'),
        'ohne sie wäre das Abschalten aller eigenen Einträge zwölf Klicks');
  check('…und die Verdichtung in einer ANDEREN',
        groupOf('mp-density') && groupOf('mp-density') !== sorts[0],
        `${groupOf('mp-density')} / ${sorts[0]}`);
  check('Die Gruppen sind beschriftet', !!sorts[0] && !!groupOf('mp-density'));

  // --- 2. Vollbild ist keine Darstellung ---------------------------------- //
  const fs_ = d.getElementById('mp-fullscreen');
  check('Vollbild existiert weiterhin', !!fs_);
  check('…steht aber NICHT mehr in der Filterleiste',
        fs_ && !fs_.closest('.filter-group'),
        'eine Fensterfunktion zwischen Datenebenen liest sich als eine davon');
  check('…sondern an der Karte', fs_ && !!fs_.closest('.map-wrap'));

  // --- 3. Vier benannte Stufen, genau eine gewählt ------------------------ //
  const dens = [...d.querySelectorAll('#mp-density button')];
  check('Vier benannte Verdichtungsstufen', dens.length === 4,
        dens.map(b => b.textContent.trim()).join(' / '));
  const LEVELS = ['point', 'near', 'place', 'city'];
  const haveAll = LEVELS.every(l => dens.some(b => b.dataset.level === l));
  check('…und zwar genau diese vier', haveAll,
        dens.map(b => b.dataset.level).join(', '));
  // Fehlt eine Stufe, sind alle folgenden Prüfungen sinnlos — und ein Wächter,
  // der beim kaputten Stand ABSTÜRZT, sagt zwar „nicht grün", aber nicht warum
  // (Anmerkung 108). Also hier sauber aussteigen.
  if (dens.length !== 4 || !haveAll) {
    ok.forEach(n => console.log('  ok  ' + n));
    fails.forEach(n => console.log('  XX  ' + n));
    console.log(`\n${fails.length} Prüfung(en) fehlgeschlagen`);
    process.exit(1);
  }
  check('…jede mit einem Namen, nicht mit einer Zahl',
        dens.every(b => /[a-zäöü]/i.test(b.textContent)),
        'eine unbeschriftete Stufe muss man ausprobieren statt lesen');
  check('…jede erklärt sich', dens.every(b => b.title && b.title.length > 30),
        dens.map(b => (b.title || '').length).join('/'));
  const pressed = () => dens.filter(b => b.getAttribute('aria-pressed') === 'true');
  check('Genau eine Stufe ist gewählt', pressed().length === 1,
        `${pressed().length} — eine Reihe Chips las sich als „mehrere dürfen an sein"`);

  // Und die Wahl wirkt: umschalten ändert, was gezeichnet wird.
  const level = () => w.eval('mp.density');
  dens.find(b => b.dataset.level === 'near')
      .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  check('Ein Klick auf eine Stufe wählt sie', level() === 'near', level());
  check('…und die Leiste zeigt das', pressed().length === 1
        && pressed()[0].dataset.level === 'near');

  // --- 4. Der Deckel hängt an der Stufe, nicht an einem anderen Schalter -- //
  //
  // **Befund (d), der teuerste.** Bis 0.39 aktivierte AUSschalten von „Punkte
  // zusammenfassen" zusätzlich den 300er-Deckel — der Schalter mit der
  // Aufschrift „zusammenfassen" war also auch der, der entschied, ob die Karte
  // alles zeigt. Die Zusicherung dagegen ist nicht „es gibt keinen Deckel",
  // sondern: **die Stufe „Jeder Punkt" sagt in ihrem eigenen Titel, dass sie
  // deckelt.**
  //
  // Geprüft in BEIDEN Sprachen: unter jsdom startet die Seite englisch, also
  // steht im `title` der Katalogeintrag und nicht der deutsche Quelltext. Ein
  // Defekt, der nur ins Markup geschrieben wird, erreicht die Zusicherung
  // sonst nie — beim Gegenfahren war das hier zum zweiten Mal der Fall.
  const allTexts = b => [b.title, w.eval(`(I18N_EN['${b.dataset.level
      ? 'map.dens.' + b.dataset.level + '.tip' : ''}'] || '')`),
      (html.match(new RegExp(`data-level="${b.dataset.level}"[^>]*`)) || [''])[0]];
  // **Anmerkung 161: es gibt gar keinen Deckel mehr.** Bis dahin nannte die
  // Stufe „Jeder Punkt" ihre eigene Grenze von 300 — richtig, solange je
  // Eintrag zwei Leaflet-Objekte entstanden. Seit die Einzelpunkte auf
  // derselben Leinwand liegen wie die Fotos (die dort seit Anmerkung 153
  // zwanzigtausend ohne ein Objekt zeichnet), ist die Grenze weg. Geprüft wird
  // deshalb die Umkehrung: **keine Stufe darf eine Punkt-Grenze behaupten**,
  // sonst steht auf der Karte eine Einschränkung, die es nicht gibt.
  const point = dens.find(b => b.dataset.level === 'point');
  check('Keine Stufe behauptet eine Punkt-Grenze',
        dens.every(b => allTexts(b).every(x => !/\b(300|1\.?000)\b/.test(x))),
        dens.filter(b => allTexts(b).some(x => /\b(300|1\.?000)\b/.test(x)))
            .map(b => b.dataset.level).join('/'));
  check('„Jeder Punkt" sagt stattdessen, wovon die Nummern abhängen',
        allTexts(point).slice(0, 2).every(x => /Reihenfolge|order/i.test(x)),
        JSON.stringify(allTexts(point).slice(0, 2)));

  // --- 5. Reihenfolge: außer Kraft, sobald verdichtet wird ---------------- //
  const routeChip = d.getElementById('mp-route-toggle');
  render("mp.density = 'place';");
  check('Reihenfolge-Schalter zeigt sich außer Kraft',
        routeChip.classList.contains('inert'),
        'zusammengefasste Punkte haben keine Reihenfolge');
  const blockedTitle = routeChip.title;
  render("mp.density = 'point';");
  check('…und bei „Jeder Punkt" ist er normal',
        !routeChip.classList.contains('inert'));
  check('Begründung unterscheidet sich je Lage',
        blockedTitle && blockedTitle !== routeChip.title,
        'derselbe Titel in beiden Zuständen');

  // --- 6. Wege: außer Kraft, wo nicht gezeichnet wird (Anm. 154 b) -------- //
  const trackChip = d.getElementById('mp-tracks-toggle');
  render("mp.mode = 'year';");
  check('Wege-Schalter zeigt sich außer Kraft, wo nicht gezeichnet wird',
        trackChip.classList.contains('inert'),
        'in Jahr/Jahrzehnt/Alles zeichnet drawTracks nichts');
  const tBlocked = trackChip.title;
  check('…und nennt den Grund', /Monat|month/i.test(tBlocked), tBlocked);
  render("mp.mode = 'month';");
  check('Bis Monat ist er normal', !trackChip.classList.contains('inert'));
  check('…mit anderer Begründung', tBlocked && tBlocked !== trackChip.title);
  // Ausgeschaltet ist etwas anderes als außer Kraft — sonst sähen zwei
  // verschiedene Aussagen gleich aus (A40).
  render("mp.showTracks = false;");
  check('Ausgeschaltet bleibt ausgeschaltet, nicht außer Kraft',
        trackChip.classList.contains('off') && !trackChip.classList.contains('inert'));
  render("mp.mode = 'year';");
  check('…und in der Jahresansicht gilt wieder außer Kraft',
        trackChip.classList.contains('inert') && !trackChip.classList.contains('off'));
  render("mp.showTracks = true; mp.mode = 'month';");

  // --- 7. „Je Stadt" ohne eine einzige Stadt ------------------------------ //
  w.eval(`mp.located = ${JSON.stringify([EV('x', 'trip', null), EV('y', 'event', null)])};`);
  render();
  const cityBtn = dens.find(b => b.dataset.level === 'city');
  check('„Je Stadt" tritt außer Kraft, wenn keine Stadt bekannt ist',
        cityBtn.classList.contains('inert'),
        'sonst fällt alles in einen Klumpen „ohne Stadt" und sieht aus wie ein Fehler');
  check('…mit Begründung und Weg hinaus', /Ortsnamen|place names/i.test(cityBtn.title),
        cityBtn.title);
  w.eval(`mp.located = ${JSON.stringify([EV('a', 'trip', 'Köln')])};`);
  render();
  check('…und ist wieder da, sobald eine Stadt bekannt ist',
        !cityBtn.classList.contains('inert'));

  // --- 8. 🛰️ gehört dem Zeitstrahl (Befund c) ----------------------------- //
  const txt = id => ((d.getElementById(id) || {}).textContent || '').trim();
  // **In BEIDEN Sprachen prüfen.** Unter jsdom startet die Seite englisch, also
  // ersetzt `applyI18n` den deutschen Quelltext durch den Katalogeintrag —
  // eine Prüfung nur auf das Gerenderte war grün, obwohl das Zeichen im
  // deutschen Markup stand. Genau der Fall, den Anmerkung 116 schon einmal
  // festgehalten hat („der Defekt erreichte die Zusicherung nie"), und beim
  // Gegenfahren dieses Wächters ist er zum zweiten Mal passiert.
  const sourceOf = id => {
    const m = html.match(new RegExp(`id="${id}"[\\s\\S]{0,400}?</span>\\s*</span>`));
    return m ? m[0] : '';
  };
  const cat = key => w.eval(`(I18N_EN['${key}'] || '')`);
  const SAT = /🛰/;
  check('Der Wege-Schalter trägt NICHT mehr 🛰️ — angezeigt',
        !SAT.test(txt('mp-tracks-toggle')),
        `${txt('mp-tracks-toggle')} — im Zeitstrahl heißt 🛰️ „automatisch erfasst"`);
  check('…auch nicht im deutschen Quelltext', !SAT.test(sourceOf('mp-tracks-toggle')),
        sourceOf('mp-tracks-toggle').slice(-90));
  check('…auch nicht im englischen Katalog', !SAT.test(cat('map.tracks')),
        cat('map.tracks'));
  check('…dafür der Besuchs-Schalter, wie im Zeitstrahl',
        SAT.test(txt('mp-visits-toggle')) && SAT.test(txt('tl-visits-toggle')),
        `Karte: ${txt('mp-visits-toggle')} · Zeitstrahl: ${txt('tl-visits-toggle')}`);
  check('…und zwar in beiden Sprachen dasselbe Zeichen',
        SAT.test(cat('tl.visits.chip')) && SAT.test(sourceOf('mp-visits-toggle')),
        `${cat('tl.visits.chip')} / ${sourceOf('mp-visits-toggle').slice(-90)}`);
  check('Die Karte hat überhaupt einen Besuchs-Schalter',
        !!d.getElementById('mp-visits-toggle'),
        'von zwei maschinellen Quellen ließ sich nur eine abschalten');

  // Die beiden Linien dürfen nicht wieder gleich heißen: die eine ist
  // gemessen, die andere gezeichnet.
  check('gemessene und gedachte Linie heißen verschieden',
        !/route/i.test(txt('mp-tracks-toggle')) || !/route/i.test(txt('mp-route-toggle')),
        `${txt('mp-tracks-toggle')} / ${txt('mp-route-toggle')}`);

  // --- 9. Fotos sehen anders aus als Google-Besuche ----------------------- //
  //
  // Gemeldet beim Durchsehen der Entwürfe: „im Mockup sind beide orange".
  // Sie waren es auch in der App — `#f5921b` gegen `#f5a623`.
  const photoC = w.eval("photoDotColor()").toLowerCase();
  const visitC = w.eval("catColor('event')").toLowerCase();
  check('Die Foto-Ebene hat eine eigene Farbe', photoC && photoC !== visitC,
        `Foto ${photoC} / Besuch ${visitC}`);
  const hex = c => c.replace('#', '').match(/../g).map(x => parseInt(x, 16));
  const dist = (a, b) => Math.hypot(...hex(a).map((v, i) => v - hex(b)[i]));
  check('…und zwar eine deutlich andere, nicht einen Farbwert daneben',
        dist(photoC, visitC) > 120,
        `Abstand ${Math.round(dist(photoC, visitC))} — zwei Orangetöne sind bei `
        + 'einem Punkt von 5 px dasselbe Orange');
  const fdot = d.querySelector('#mp-photos-toggle .fdot');
  check('Der Schalter trägt die Farbe seiner Ebene',
        fdot && /--photo-dot/.test(fdot.getAttribute('style') || ''),
        'zwei gepflegte Farbwerte für dieselbe Ebene laufen auseinander');

  // --- 10. Jeder Schalter erklärt sich selbst ----------------------------- //
  ['mp-tracks-toggle', 'mp-route-toggle', 'mp-baseline-toggle', 'mp-visits-toggle',
   'mp-photos-toggle'].forEach(id => {
    const el = d.getElementById(id);
    check(`${id} hat eine Erklärung`, el && el.title && el.title.length > 40,
          'kein oder zu knapper Titel');
  });

  ok.forEach(n => console.log('  ok  ' + n));
  fails.forEach(n => console.log('  XX  ' + n));
  console.log(fails.length ? `\n${fails.length} Prüfung(en) fehlgeschlagen` : '\nKartenschalter: alles grün');
  process.exit(fails.length ? 1 : 0);
}, 2500);
