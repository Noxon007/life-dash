const fs=require('fs'); const {JSDOM}=require('jsdom');
const html=fs.readFileSync(process.argv[2] || 'frontend/index.html','utf8');
const dom=new JSDOM(html,{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost:8000/',
  beforeParse(w){ w.fetch=()=>Promise.reject(new Error('x'));
    w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
    w.L=new Proxy(function(){return w.L;},{get:()=>w.L,apply:()=>w.L}); }});
setTimeout(()=>{
  const w=dom.window,d=w.document; let fail=0;
  const ok=(n,c)=>{console.log((c?'  ok   ':'  FAIL ')+n); if(!c)fail++;};
  const metricOf=(e,...ks)=>{for(const k of ks){const m=(e.metrics||[]).find(x=>x.key===k); if(m&&m.value!=null)return m.value;}return null;};
  const m=(k,v)=>({key:k,value:v,source:'weather'});
  const tiles=()=>d.getElementById('weather-tiles').textContent.replace(/\s+/g,' ');

  // Ein Importtag: 20 Besuche, alle mit DEMSELBEN Wetter (so sehen echte
  // Timeline-Daten aus — genau das hat der Fehler übersehen)
  const visits = Array.from({length:20},(_,i)=>({
    id:'v'+i, title:'Besuch '+i, category:'event',
    date_start:`2024-06-15T${String(8+Math.floor(i/3)).padStart(2,'0')}:00:00`,
    date_precision:'exact',
    metrics:[m('temperature_c',18),m('rain_mm',5),m('sunshine_h',4)]}));
  w.renderWeatherSummary(visits, metricOf, ()=>'Ort');
  ok('20 Besuche an EINEM Tag = 1 Tag mit Wetter', /(^| )1 /.test(tiles()));
  ok('Sonnenstunden nicht vervielfacht (4 h statt 80 h)', /4 h/.test(tiles()) && !/80 h/.test(tiles()));
  ok('1 Regentag statt 20', /(^| )1 /.test(tiles()) && !/(^| )20 /.test(tiles()));

  // Ein ganzes Jahr Importdaten: darf nie mehr als 365 Regentage ergeben
  const year=[]; 
  for(let day=1; day<=300; day++){
    const dt=new Date(2024,0,day).toISOString().slice(0,10);
    for(let k=0;k<12;k++) year.push({id:`e${day}_${k}`,title:'x',category:'event',
      date_start:`${dt}T${String(6+k).padStart(2,'0')}:00:00`,date_precision:'exact',
      metrics:[m('temperature_c',10),m('rain_mm',3),m('sunshine_h',2)]});
  }
  w.renderWeatherSummary(year, metricOf, ()=>'Ort');
  const num = parseInt(tiles().trim().split(' ')[0],10);
  ok('3600 Einträge an 300 Tagen = 300 Tage mit Wetter', num===300);
  const vals=[...d.querySelectorAll('#chart-raindays *')].map(x=>parseInt(x.textContent,10)).filter(n=>Number.isFinite(n)&&n<1900);
  ok('Regentage pro Jahr bleiben unter 366 ('+vals.join(", ")+")", vals.length>0 && vals.every(n=>n<=366));

  // Wärmste Reise: über TAGE mitteln, nicht über Einträge
  const trip=[
    ...Array.from({length:10},(_,i)=>({id:'t1_'+i,title:'Reise',category:'trip',parent_event_id:'P',
      date_start:'2024-07-01T09:00:00',date_precision:'exact',metrics:[m('temperature_c',30)]})),
    {id:'t2',title:'Reise',category:'trip',parent_event_id:'P',
      date_start:'2024-07-02T09:00:00',date_precision:'exact',metrics:[m('temperature_c',20)]},
  ];
  w.renderWeatherSummary(trip, metricOf, ()=>'Ort');
  ok('Reisetemperatur mittelt über Tage (25.0 statt 29.1)', /25\.0 °C/.test(tiles()));

  console.log(fail?`\n${fail} FEHLER`:'\nA31: alle Prüfungen bestanden');
  process.exit(fail?1:0);
},2500);
