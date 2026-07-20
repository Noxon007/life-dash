const fs=require('fs'); const {JSDOM}=require('jsdom');
const html=fs.readFileSync(process.argv[2] || 'frontend/index.html','utf8');
const jobs=[{id:'j1',type:'immich',status:'running',done:3,remaining:7,unit:'Fotos',
             result:null,started_at:'2026-07-20T10:00:00',started_by:'Test'}];
const dom=new JSDOM(html,{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost:8000/',
  beforeParse(w){
    w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
    w.L=new Proxy(function(){return w.L;},{get:()=>w.L,apply:()=>w.L});
    w.fetch=(url)=>{
      if(String(url).includes('/api/jobs')) return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(jobs)});
      return Promise.reject(new Error('offline'));
    };
  }});
setTimeout(async ()=>{
  const w=dom.window;
  try {
    await w.loadJobs();
    const tbl=w.document.getElementById('jobs-table');
    console.log('Tabelleninhalt:', tbl.innerHTML.slice(0,90) || '(LEER)');
    console.log(/immich|Immich/.test(tbl.innerHTML) ? 'Job sichtbar' : 'JOB NICHT SICHTBAR');
  } catch(e){ console.log('loadJobs wirft:', e.constructor.name + ': ' + e.message); }
  process.exit(0);
},2500);
