"""
Research-Reiter: Firmen-Kacheln und Firmen-Dashboard (Streamlit components v2, gleiches Design wie die Home-Seite).
Klicks gehen an Python zurueck (Firma oeffnen, Report oeffnen, neue Zahlen pruefen). Alle Texte werden escaped.
"""
import streamlit as st

from home_view import CSS as HOME_CSS

CSS = HOME_CSS + r"""
.ctile{border:1px solid var(--line);border-radius:14px;padding:14px 16px;background:var(--bg);cursor:pointer;display:flex;
 flex-direction:column;gap:6px;min-width:0;transition:border-color .15s,transform .15s}
.ctile:hover{border-color:var(--line2);transform:translateY(-1px)}
.ctile .tt{display:flex;align-items:center;justify-content:space-between;gap:8px}
.ctile .big{font-size:calc(21px*var(--bfs,1));font-weight:600;font-family:var(--st-code-font,ui-monospace,Menlo,monospace)}
.cgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.th-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;padding:12px 6px;border-top:1px solid var(--line);cursor:pointer;border-radius:8px}
.th-row:hover{background:var(--hov)}.th-row:first-of-type{border-top:0}
.qchips{display:flex;gap:4px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.qc{font-size:calc(14px*var(--bfs,1));padding:3px 7px;border-radius:6px;white-space:nowrap}
.s-strengthened{background:rgba(29,158,117,.22);color:var(--ok)}.s-intact{background:var(--okbg);color:var(--ok)}
.s-weakened{background:var(--rdbg);color:var(--rd)}.s-broken{background:var(--decbg);color:var(--dec)}.s-baseline{background:var(--soft);color:var(--mut)}
.th-det{grid-column:1/-1;display:none;font-size:calc(16px*var(--bfs,1));color:var(--mut);padding:4px 0 2px}
.th-row.open .th-det{display:block}
.kgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}
.kcard{border:1px solid var(--line);border-radius:14px;padding:12px 14px;min-width:0}
.kcard .kn{font-size:calc(15.5px*var(--bfs,1));color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kcard .kv{font-size:calc(23px*var(--bfs,1));font-weight:600;margin:2px 0}
.rtile{border:1px solid var(--line);border-radius:12px;padding:12px 14px;min-width:0;display:flex;flex-direction:column;gap:6px}
.rtile.sel{border-color:var(--acc2);box-shadow:0 0 0 3px var(--accbg)}
.rgrid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.cmp{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
.cmp table{width:100%;border-collapse:collapse;font-size:calc(16px*var(--bfs,1))}.cmp td,.cmp th{padding:6px 4px;border-top:1px solid var(--line);text-align:left;vertical-align:top}
.cmp th{color:var(--mut);font-weight:500}
.chk{display:inline-flex;align-items:center;gap:6px;font-size:calc(15.5px*var(--bfs,1));color:var(--mut);cursor:pointer}
.back{border:0;background:transparent;color:var(--mut);font:inherit;font-size:calc(16px*var(--bfs,1));cursor:pointer;padding:0;display:inline-flex;align-items:center;gap:4px}
.back:hover{color:var(--tx)}
.c2{grid-column:span 2}@media (max-width:1100px){.c2{grid-column:span 4}}@media (max-width:640px){.c2{grid-column:span 6}}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 14px}
"""

COMMON_JS = r"""
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const NF=(d)=>new Intl.NumberFormat('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const pct=(v,d=1,sign=true)=>v==null?'–':(sign&&v>0?'+':'')+NF(d).format(v*100)+'%';
const cls=v=>v==null?'':(v>=0?'pos':'neg');
const LV={decide:'Decide',read:'Read up',none:'Calm'};
const TH={broken:'broken',weakened:'weakened',intact:'intact',strengthened:'strengthened',baseline:'baseline'};
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const fmtDate=s=>{if(!s)return '–';const [y,m,d]=s.slice(0,10).split('-');return m?`${d} ${MON[+m-1]} ${y}`:s};
const ii=t=>`<span class="ii" data-tip="${esc(t)}">i</span>`;
const svgIco=p=>`<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${p}"/></svg>`;
function darkMode(root,parentElement){const lum=c=>{const m=String(c||'').match(/\d+(\.\d+)?/g);return m&&m.length>=3&&!(m.length>3&&+m[3]===0)?(+m[0]*.299+ +m[1]*.587+ +m[2]*.114):null};
 const app=document.querySelector('.stApp')||document.body;let L=lum(getComputedStyle(app).backgroundColor);if(L==null)L=lum(getComputedStyle(document.body).backgroundColor);root.classList.toggle('dark',L!=null&&L<110)}
function mount(parentElement){let root=parentElement.querySelector('.fr');if(!root){root=document.createElement('div');root.className='fr';parentElement.appendChild(root)}return root}
const tallyBar=t=>{const n=(t.strengthened||0)+(t.intact||0)+(t.weakened||0)+(t.broken||0);if(!n)return '<div class="bar" style="opacity:.5"></div>';
 const seg=(k,c)=>t[k]?`<i style="width:${t[k]/n*100}%;background:${c};display:inline-block;height:100%"></i>`:'';
 return `<div class="bar" style="display:flex">${seg('strengthened','#1D9E75')}${seg('intact','#5DCAA5')}${seg('weakened','#EF9F27')}${seg('broken','#E24B4A')}</div>`};
"""

GRID_JS = COMMON_JS + r"""
export default function(component){
 const {data,parentElement,setTriggerValue}=component; const D=data||{}; const root=mount(parentElement); darkMode(root,parentElement);
 const C=D.companies||[];
 let h=`<div class="top"><div><h1>Company research</h1><div class="sub">${C.filter(c=>c.n_reports).length} companies with reports · click opens the company dashboard</div></div>
  <label class="search"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
  <input id="f" placeholder="Filter companies or enter a new ticker, e.g. NVDA" autocomplete="off"><kbd>Enter</kbd></label>
  <div class="seg" id="sc"><button data-s="pf">Portfolio</button><button data-s="all">All</button><button data-s="rep">With reports</button></div></div><div class="cgrid" id="g"></div>`;
 root.innerHTML=h; const g=root.querySelector('#g'); let scope=C.some(c=>c.in_portfolio)?'pf':'all', q='';
 root.querySelectorAll('#sc button').forEach(b=>b.classList.toggle('on',b.dataset.s===scope));
 function draw(){const L=C.filter(c=>(scope==='all'||(scope==='pf'&&c.in_portfolio)||(scope==='rep'&&c.n_reports))&&(!q||(c.t+' '+c.name).toLowerCase().includes(q)));
  g.innerHTML=L.map(c=>{const fc=c.fc&&c.fc[1]?c.fc[0]/c.fc[1]:null;
   return `<div class="ctile" data-t="${esc(c.t)}"><div class="tt"><span class="big">${esc(c.t)}</span>${c.level?`<span class="pill p-${c.level}">${LV[c.level]}</span>`:(c.in_portfolio?'':'<span class="pill" style="background:var(--soft);color:var(--mut)">Watchlist</span>')}</div>
    <div class="sm mut" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(c.name)}${c.w!=null?' · '+pct(c.w,1,false):''}</div>
    ${c.n_reports?`${tallyBar(c.tally)}<div class="sm clamp" style="min-height:38px">${esc(c.headline)}</div>
    <div class="sm mut" style="display:flex;justify-content:space-between"><span>${c.n_reports} Report${c.n_reports>1?'s':''} · ${fmtDate(c.last)}</span>${fc!=null?`<span title="Fact check">${NF(0).format(fc*100)}% verified</span>`:''}</div>`:
    `<div class="sm mut" style="min-height:38px">No research report yet${/\.(TO|DE|AS|PA|CO|L|SW|MI)$/.test(c.t)?' – no SEC 10-K for this stock, only news and key figures':''}.</div>
    ${/\.(TO|DE|AS|PA|CO|L|SW|MI)$/.test(c.t)?'':`<button class="btn" data-mk="${esc(c.t)}" style="height:30px;font-size:calc(15px*var(--bfs,1));align-self:flex-start">Create report</button>`}`}</div>`}).join('')||'<div class="empty">No company found. Enter a ticker and press Enter to create a report.</div>';
  g.querySelectorAll('.ctile').forEach(el=>el.onclick=e=>{if(e.target.closest('[data-mk]'))return;setTriggerValue('open',{t:el.dataset.t,n:Date.now()})});
  g.querySelectorAll('[data-mk]').forEach(b=>b.onclick=()=>setTriggerValue('make',{t:b.dataset.mk,n:Date.now()}));}
 root.querySelectorAll('#sc button').forEach(b=>b.onclick=()=>{scope=b.dataset.s;root.querySelectorAll('#sc button').forEach(x=>x.classList.toggle('on',x===b));draw()});
 const f=root.querySelector('#f'); f.oninput=()=>{q=f.value.trim().toLowerCase();draw()};
 f.onkeydown=e=>{if(e.key!=='Enter')return;const v=f.value.trim().toUpperCase();if(!v)return;const hit=C.find(c=>c.t===v);
  if(hit){setTriggerValue('open',{t:v,n:Date.now()})}else if(/^[A-Z][A-Z0-9.\-]{0,9}$/.test(v)){setTriggerValue('make',{t:v,n:Date.now()})}};
 draw();
}
"""

COMPANY_JS = COMMON_JS + r"""
export default function(component){
 const {data,parentElement,setTriggerValue}=component; const D=data||{}; const root=mount(parentElement); darkMode(root,parentElement);
 const go=(name,v)=>setTriggerValue(name,{v:v||null,n:Date.now()});
 const PART=D.part||'full', TOP=PART!=='main', MAIN=PART!=='top';
 const KH=(D.kpi_hist||[]).length?D.kpi_hist:null;
 let h='';
 if(TOP){h+=`<div class="toolbar"><button class="back" id="bk">${svgIco('M15 18l-6-6 6-6')} All companies</button></div>
 <div class="top"><div><h1><span class="tk" style="font-size:calc(25px*var(--bfs,1))">${esc(D.t)}</span> <span style="font-weight:500">${esc(D.name&&D.name!==D.t?D.name:'')}</span></h1>
  <div class="sub">${[D.sector,D.w!=null?'Weight '+pct(D.w,1,false):'Not in portfolio',D.earnings_date?'Earnings Review '+fmtDate(D.earnings_date):null,D.annual_fy?'Annual Report FY'+D.annual_fy:null].filter(Boolean).map(esc).join(' · ')}</div></div>
  <div style="flex:1"></div>${D.level?`<span class="pill p-${D.level}" style="font-size:calc(15.5px*var(--bfs,1));padding:4px 12px">${LV[D.level]}</span>`:''}
  <button class="btn" id="upd">${svgIco('M20 11a8 8 0 10-2.3 5.7M20 4v7h-7')} Check for new results</button>
  ${D.annual_fy?`<button class="btn" id="com" title="Investment Committee: a CIO and three analyst groups debate and vote. Takes up to 60 minutes and costs about $1–2.">${svgIco('M17 20h5v-2a3 3 0 00-5.4-1.8M9 20H2v-2a3 3 0 015.4-1.8M15 7a3 3 0 11-6 0 3 3 0 016 0z')} Start committee<span style="display:inline-block;font-size:calc(13px*var(--bfs,1));font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:#B9770E;background:rgba(239,159,39,.15);border:1px solid rgba(239,159,39,.35);border-radius:6px;padding:0 5px;margin-left:6px;line-height:15px" title="Beta: results not yet validated">Beta</span></button>`:''}
  ${(D.reports||[]).length?`<button class="btn pri" id="ord">${svgIco('M4 5h16v14H4zM8 9h8M8 13h5')} Open latest report</button>`:''}</div>`;
 h+=`<div class="grid">`;
 const k=(l,v,s,c='')=>`<div class="kpi sm c2"><div class="l">${l}</div><div class="v ${c}">${v}</div><div class="s">${s}</div></div>`;
 h+=k('Today',pct(D.chg,2),'price move',cls(D.chg))+k('1 year',pct(D.ret1y,0),'price return',cls(D.ret1y))+k('Risk share',D.rc!=null?pct(D.rc,1,false):'–',D.w!=null?'at '+pct(D.w,1,false)+' weight':'–')
   +k('Forward P/E',D.pe!=null?NF(1).format(D.pe):'–','next 12 months')+k('Analyst upside',pct(D.upside,0),'to price target',cls(D.upside))+k('Revenue growth',pct(D.growth,0),'expected',cls(D.growth));
 h+=REPORTS_HTML();
 h+=`</div>`}
 if(MAIN){h+=`<div class="grid">`;

 // Neueste Zahlen + Kernaussagen (links), Handlungsbedarf + Termine + News (rechts)
 h+=`<div class="c8 stack"><div class="card"><div class="ch"><h3>Latest results${ii('From the Earnings Review agent: all quarters since the last 10-K, read from the 8-K press releases and 10-Q filings at SEC EDGAR, with results vs. consensus.')}</h3><span class="meta">${D.quarters&&D.quarters.length?esc(D.quarters[0]+' to '+D.quarters[D.quarters.length-1]):''}${D.earnings_date?' · review from '+fmtDate(D.earnings_date):''}</span></div>
  ${D.headline?`<div style="font-weight:600;margin-bottom:6px">${esc(D.headline)}</div><div class="sm mut clamp" id="sum" style="-webkit-line-clamp:4">${esc(D.summary)}</div>
  ${D.outlook||D.risk_update?`<details style="margin-top:8px"><summary class="sm" style="cursor:pointer;color:var(--acc)">Outlook and risks</summary>${D.outlook?`<p class="sm"><b>Outlook:</b> ${esc(D.outlook)}</p>`:''}${D.risk_update?`<p class="sm"><b>Risks:</b> ${esc(D.risk_update)}</p>`:''}</details>`:''}`
  :`<div class="empty">No earnings review yet. “Check for new results” starts the Earnings Reviewer.</div>`}</div>`;
 // Thesen
 const allQ=[...new Set((D.theses||[]).flatMap(t=>Object.keys(t.statuses||{})))].sort((a,b)=>{const p=x=>{const m=x.match(/Q(\d)\s*FY(\d{4})/);return m?+m[2]*10+ +m[1]:0};return p(a)-p(b)});
 h+=`<div class="card"><div class="ch"><div><h3>Investment theses${ii('Written by the Annual Report agent from the 10-K (3–4 theses, each with a signpost to watch). Every Earnings Review rates each thesis per quarter: strengthened, intact, weakened or broken.')}</h3><div class="meta">status per quarter from the earnings reviews · click shows evidence and signpost</div></div>
  <div class="legend" style="margin:0">${['strengthened','intact','weakened','broken'].map(s=>`<span class="qc s-${s}">${TH[s]}</span>`).join('')}</div></div>`;
 if(!(D.theses||[]).length) h+=`<div class="empty">No theses yet – run the Annual Report agent first.</div>`;
 (D.theses||[]).forEach((t,i)=>{h+=`<div class="th-row" data-i="${i}"><div><div style="font-weight:500">${esc(t.thesis)}</div>${t.signpost?`<div class="sm mut clamp" style="-webkit-line-clamp:1">Signpost: ${esc(t.signpost)}</div>`:''}</div>
   <div class="qchips">${allQ.map(q=>{const s=(t.statuses||{})[q];return s?`<span class="qc s-${s}" title="${esc(q)}: ${esc(TH[s]||s)}">${esc(q.replace(' FY',' '))}</span>`:`<span class="qc" style="background:var(--soft);color:var(--faint)">${esc(q.replace(' FY',' '))}</span>`}).join('')}
    <span class="pill s-${t.status||'baseline'}" style="min-width:86px;text-align:center;margin-left:6px">${esc(TH[t.status]||t.status||'–')}</span></div>
   <div class="th-det">${t.evidence?`<p><b>Current evidence:</b> ${esc(t.evidence)}</p>`:''}${t.baseline?`<p><b>Starting point (annual report):</b> ${esc(t.baseline)}</p>`:''}${t.signpost?`<p><b>Signpost:</b> ${esc(t.signpost)}</p>`:''}</div></div>`});
 h+=`</div>`;

 h+=`<div class="card"><div class="ch"><h3>Key takeaways${ii('The main conclusions of the latest Annual Report written by the agent; every number in it is fact-checked against the 10-K and market data.')}</h3><span class="meta">${D.annual_fy?'Annual Report FY'+esc(D.annual_fy):''}</span></div>
  ${(D.takeaways||[]).length?D.takeaways.map(x=>`<div class="row" style="padding:8px 0"><i style="width:6px;height:6px;border-radius:50%;background:var(--acc2);margin-top:8px;flex:none"></i><div class="grow sm">${esc(x)}</div></div>`).join(''):'<div class="empty">No annual report yet.</div>'}</div></div>`;

 h+=`<div class="c4 stack"><div class="card"><div class="ch"><h3>${D.level==='none'||!D.level?'Why no action':'Why '+LV[D.level].toLowerCase()}${ii('Rule-based triggers from the Weekly Brief, e.g. a broken thesis, weight above the position limit, analyst revisions or unusual news.')}</h3><span class="meta">Weekly Brief</span></div>
  ${(D.triggers||[]).length?D.triggers.map(x=>`<div class="row" style="padding:8px 0"><span class="pill p-${x.level}" style="min-width:76px;text-align:center">${LV[x.level]||esc(x.level)}</span><div class="grow sm">${esc(x.text)}<div class="mut" style="font-size:calc(14.5px*var(--bfs,1))">${esc(x.source)}</div></div></div>`).join(''):'<div class="empty">No rule-based triggers.</div>'}</div>
  <div class="card"><div class="ch"><h3>Calendar</h3></div>${(D.events||[]).length?D.events.map(e=>`<div class="row" style="padding:7px 0"><div class="dt">${esc(fmtDate(e.date).slice(0,6))}</div><div class="grow sm">${esc({'Quarterly results':'Earnings','Ex-dividend':'Ex-dividend','Dividend payment':'Dividend payment'}[e.type]||e.type)}${e.detail==='estimated'?' <span class="mut">(estimated)</span>':''}</div></div>`).join(''):'<div class="empty">No dates in the calendar.</div>'}
  ${D.forecast?`<div class="sm mut" style="margin-top:8px">Weekly forecast ${esc(D.forecast.date||'')}: ${esc(D.forecast.direction||'')} ${esc(D.forecast.low??'')}–${esc(D.forecast.high??'')}%<span style="display:inline-block;font-size:calc(13px*var(--bfs,1));font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:#B9770E;background:rgba(239,159,39,.15);border:1px solid rgba(239,159,39,.35);border-radius:6px;padding:0 5px;margin-left:6px;line-height:15px" title="Beta: short-term forecast from news and key figures, hit rate not yet evaluated">Beta</span></div>`:''}</div><div class="card"><div class="ch"><h3>News</h3><span class="meta">30 days</span></div>
  ${(D.stories||[]).length?`<div class="sm mut" style="margin-bottom:4px">Laufende Storylines: ${D.stories.map(s=>esc(s.title)+' ('+esc(s.status)+')').join(' · ')}</div>`:''}
  ${(D.news||[]).length?D.news.slice(0,6).map(n=>{const dc=n.dir==='positive'?'var(--pos)':n.dir==='negative'?'var(--neg)':'var(--faint)';return `<div class="row click" data-url="${esc(n.url)}"><div class="dt">${esc(fmtDate(n.date).slice(0,6))}</div><i style="width:7px;height:7px;border-radius:50%;background:${dc};margin-top:7px;flex:none"></i><div class="grow sm clamp">${esc(n.title)}</div><span class="sm ${cls(n.car)}">${n.car!=null?pct(n.car):''}</span></div>`}).join(''):'<div class="empty">No material headlines.</div>'}</div></div>`;

 // KPIs je Quartal
 h+=`<div class="card c12"><div class="ch"><div><h3>KPIs by quarter${ii('Company-specific KPIs (e.g. payment volume, cloud revenue, subscribers) that the Earnings Review agent extracts each quarter; merged across all reviews into a time series. The change is vs. the same quarter last year.')}</h3><div class="meta">${KH?'company-specific KPIs from all earnings reviews · last 8 quarters · growth vs. prior-year quarter (YoY) and prior quarter (QoQ)':'from the earnings review · dark bar = this year, light = prior-year quarter · growth YoY and QoQ'}</div></div><div class="seg" id="kmode"><button data-km="bars" class="on">Bars</button><button data-km="line">Line</button><button data-km="yoy">YoY growth</button></div></div>`;
 if(!(KH||D.kpis||[]).length) h+=`<div class="empty">No quarterly KPIs yet.</div>`; else h+=`<div class="kgrid" id="kg"></div>`;
 h+=`</div>`;
 // Thesis Tracker
 {const TR=D.tracker||{};const Q=TR.quarters||[];
  const stc=s=>s?`<span class="qc s-${s}">${esc(TH[s]||s)}</span>`:'<span class="qc s-baseline">no record</span>';
  const dot=s=>({strengthened:'#1D9E75',intact:'#5DCAA5',weakened:'#EF9F27',broken:'#E24B4A'})[s]||'var(--line2)';
  h+=`<div class="card c12"><div class="ch"><div><h3>Thesis tracker${ii('Each thesis from the annual report gets 1–3 measurable milestones (the thesis book). Every quarter – including Q4 – is reviewed separately from its own 8-K press release and 10-Q: KPIs with the same names each quarter, guidance, management messages and a status per thesis, all fact-checked. Python checks the milestones; a note appears when the model’s status and the milestones disagree. Early warnings are negative news since the last quarter.')}</h3>
   <div class="meta">${TR.book?`thesis book FY${esc(TR.fyear||'')} · ${Q.length} quarter record${Q.length===1?'':'s'}${Q.length?' ('+esc(Q[0])+' → '+esc(Q[Q.length-1])+')':''}`:'no thesis book yet'}</div></div>
   <div style="display:flex;gap:8px;flex-wrap:wrap">${TR.book?'':'<button class="btn" id="trb">Create thesis book</button>'}<button class="btn" id="trr">Review missing quarters</button></div></div>`;
  if(!TR.book) h+=`<div class="empty">The thesis book turns the annual report’s theses into measurable milestones (one model call, about 0.3 cents). After that, every quarter since the 10-K is reviewed separately.</div>`;
  else{
   if(!Q.length) h+=`<div class="sm mut" style="margin-bottom:10px">No quarter records yet – “Review missing quarters” reviews every quarter since the 10-K separately (about 1–2 minutes and 2–4 cents per quarter, runs in the background).</div>`;
   (TR.theses||[]).forEach(T=>{
    h+=`<div class="trth" style="border-top:1px solid var(--line);padding:12px 2px">
     <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"><b style="font-weight:600">${esc(T.id)} · ${esc(T.short)}</b>${stc(T.status)}
      ${T.met_share!=null?`<span class="sm mut">milestones met last quarter: ${Math.round(T.met_share*100)}%</span>`:''}</div>
     <div class="sm mut" style="margin:3px 0 8px" title="${esc(T.thesis)}">${esc(T.thesis.length>220?T.thesis.slice(0,220)+'…':T.thesis)}</div>`;
    if(Q.length){h+=`<div style="overflow-x:auto"><table class="vtab" style="min-width:${260+Q.length*110}px"><tr><th style="width:260px">Status / milestone</th>${Q.map(q=>`<th>${esc(q)}</th>`).join('')}</tr>`;
     h+=`<tr><td>Status</td>${T.timeline.map(c=>`<td title="${esc(c.evidence||'')}"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${dot(c.status)};margin-right:6px;vertical-align:-1px"></span>${esc(c.status?TH[c.status]||c.status:'–')}</td>`).join('')}</tr>`;
     T.milestones.forEach(m=>{h+=`<tr><td>${esc(m.text)}</td>${m.cells.map(c=>`<td style="color:${c.met==null?'var(--mut)':c.met?'var(--pos)':'var(--neg)'}">${c.v==null?'–':NF(Math.abs(c.v)<100?1:0).format(c.v)+(c.u==='%'||c.u==='% YoY'?'%':c.u==='pp'?' pp':'')+' '+(c.met==null?'':c.met?'✓':'✗')}</td>`).join('')}</tr>`});
     if(!T.milestones.length)h+=`<tr><td colspan="${Q.length+1}" class="mut">No measurable milestone for this thesis – judged from the evidence only.</td></tr>`;
     h+=`</table></div>`;
     const lastEv=[...T.timeline].reverse().find(c=>c.evidence);
     if(lastEv)h+=`<div class="sm" style="margin-top:6px"><span class="mut">${esc(lastEv.q)}:</span> ${esc(lastEv.evidence)}</div>`}
    if(T.check)h+=`<div class="sm" style="margin-top:6px;color:#B9770E">⚠ ${esc(T.check)}</div>`;
    h+=`</div>`});
   if((TR.records||[]).length){h+=`<div style="border-top:1px solid var(--line);padding-top:12px;margin-top:4px"><div class="sm mut" style="margin-bottom:6px">Quarter by quarter (newest first; click to open)</div>`;
    [...TR.records].reverse().forEach((r,i)=>{const fc=r.fc||{};
     h+=`<details class="trq" ${i===0?'open':''} style="border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:6px 0"><summary style="cursor:pointer"><b style="font-weight:600">${esc(r.label)}</b> <span class="sm mut">quarter ended ${esc(fmtDate(r.end))}${fc.total?` · fact check ${fc.matched}/${fc.total}`:''}</span> · ${esc(r.headline||'')}</summary>
      <div class="sm" style="margin-top:8px;line-height:1.55">${esc(r.summary||'')}</div>
      ${r.guidance?`<div class="sm" style="margin-top:6px"><b style="font-weight:600">Guidance:</b> ${esc(r.guidance)}</div>`:''}
      ${(r.narrative||[]).length?`<div class="sm" style="margin-top:6px"><b style="font-weight:600">Management:</b><ul style="margin:4px 0 0 18px;padding:0">${r.narrative.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
      ${(r.risks||[]).length?`<div class="sm" style="margin-top:6px"><b style="font-weight:600">Risks:</b> ${r.risks.map(esc).join(' · ')}</div>`:''}
      ${r.release?`<div class="sm" style="margin-top:6px"><a href="${esc(r.release)}" target="_blank" rel="noopener">Earnings release (SEC)</a></div>`:''}</details>`});
    h+=`</div>`}
   if((TR.warnings||[]).length)h+=`<div class="vnote" style="margin-top:10px"><b>Early warnings since the last quarter:</b>${TR.warnings.slice(0,5).map(w=>`<div class="sm" style="margin-top:4px">${esc(fmtDate(String(w.date||'').slice(0,10)))} · ${w.url?`<a href="${esc(w.url)}" target="_blank" rel="noopener">${esc(w.text)}</a>`:esc(w.text)}</div>`).join('')}</div>`;
  }
  h+=`</div>`}
 h+=`</div>`}
 function REPORTS_HTML(){return `<div class="card c12"><div class="ch"><div><h3>Reports${ii('Every Annual Report and Earnings Review run is archived with its date. Open shows the PDF or the text with fact-check colours; tick two reports of the same kind to compare theses and KPIs.')}</h3><div class="meta">every run is archived with its date · tick two reports of the same kind to compare</div></div></div>
  <div class="rgrid2">${(D.reports||[]).map((r,i)=>{const fc=r.fc_total?r.fc_matched/r.fc_total:null;return `<div class="rtile" data-i="${i}">
   <div style="display:flex;justify-content:space-between;align-items:center"><span class="pill" style="background:${r.kind==='annual'?'var(--accbg)':'var(--soft)'};color:${r.kind==='annual'?'var(--acc)':'var(--mut)'}">${r.kind==='annual'?'Annual Report':'Earnings Review'}</span><span class="sm mut">${fmtDate(r.date)}</span></div>
   <div style="font-weight:500">${esc(r.title)}</div><div class="sm mut clamp">${esc(r.headline)}</div>
   ${fc!=null?`<div class="sm mut" style="display:flex;align-items:center;gap:8px"><div class="bar" style="width:80px;height:6px"><i style="width:${fc*100}%;background:var(--ok)"></i></div>${r.fc_matched}/${r.fc_total} numbers found in sources</div>`:''}
   <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px"><label class="chk"><input type="checkbox" data-c="${i}"> compare</label><button class="btn" data-o="${esc(r.id)}" style="height:30px;font-size:calc(15px*var(--bfs,1))">Open</button></div></div>`}).join('')||'<div class="empty">No reports yet.</div>'}</div>
  <div id="cmp" style="margin-top:14px"></div></div>`}
 root.innerHTML=h;
 const $=s=>root.querySelector(s),$$=s=>[...root.querySelectorAll(s)];
 if($('#bk'))$('#bk').onclick=()=>go('back'); if($('#upd'))$('#upd').onclick=()=>go('check',D.t); if($('#com'))$('#com').onclick=()=>go('committee',D.t); if($('#ord'))$('#ord').onclick=()=>go('report',D.reports[0].id);
 $$('.th-row').forEach(r=>r.onclick=()=>r.classList.toggle('open'));
 $$('.row.click').forEach(r=>r.onclick=()=>r.dataset.url&&window.open(r.dataset.url,'_blank','noopener'));
 $$('[data-o]').forEach(b=>b.onclick=()=>go('report',b.dataset.o));
 if($('#trb'))$('#trb').onclick=()=>{$('#trb').textContent='Creating …';go('tracker','book')};
 if($('#trr'))$('#trr').onclick=()=>go('tracker','review');

 // KPI-Karten: Verlauf je Quartal; die letzte Karte fuellt die Reihe auf, damit kein Leerraum bleibt
 const kg=$('#kg');
 const unitDe=u=>String(u||'').replace('USD bn','$bn').replace('USD per share','$ per share').replace('USD mn','$m').replace(/^mn$/,'m').replace(/^bn$/,'bn');
 const sq=q=>String(q).replace(/^Q(\d)\s*FY\d{2}(\d{2})$/,'Q$1 $2').replace(/\s*FY\d{2}(\d{2})/,' $1');
 const CARDS=KH?KH.map(K=>({name:K.name,unit:K.unit,good:K.good,q:K.points.map(p=>p[0]),v:K.points.map(p=>p[1]),p:null,yoy:K.latest_yoy,src:'Earnings Reviews'}))
   :(D.kpis||[]).map(K=>{const n=K.v.length;const last=K.v[n-1],prev=K.p[n-1];return {...K,yoy:(last!=null&&prev!=null&&prev!==0)?(last-prev)/Math.abs(prev):null}});
 const qk=x=>{const m=String(x).match(/Q(\d)\D*?(\d{4}|\d{2})\b/);return m?[+(m[2].length===2?'20'+m[2]:m[2]),+m[1]]:null};
 const nice=(lo,hi)=>{if(lo===hi){hi=lo+(Math.abs(lo)||1)}const raw=(hi-lo)/4,p=Math.pow(10,Math.floor(Math.log10(raw)));const st=[1,2,2.5,5,10].map(x=>x*p).find(x=>x>=raw)||10*p;
  const a=Math.floor(lo/st)*st,t=[];for(let v=a;v<=hi+st*0.999;v+=st)t.push(+v.toFixed(10));return t};
 const fax=v=>{const a=Math.abs(v);return NF(Number.isInteger(v)||a>=10?0:a>=1?1:2).format(v)};
 const gp=v=>v==null?'–':(v>=0?'+':'')+NF(1).format(v*100)+'%';
 const isGood=(K,g)=>g==null?null:(K.good==='down'?g<=0:g>=0);
 CARDS.forEach(K=>{const keys=K.q.map(qk), M={};keys.forEach((k,i)=>{if(k&&K.v[i]!=null)M[k[0]*10+k[1]]=K.v[i]});
  K.yoyA=K.q.map((q,i)=>{const pv=K.p&&K.p[i]!=null?K.p[i]:(keys[i]?M[(keys[i][0]-1)*10+keys[i][1]]:null);return (K.v[i]!=null&&pv!=null&&pv!==0)?K.v[i]/Math.abs(pv)-Math.sign(pv):null});
  K.qoqA=K.q.map((q,i)=>{const k=keys[i];if(!k||K.v[i]==null)return null;const pk=k[1]===1?(k[0]-1)*10+4:k[0]*10+k[1]-1;const pv=M[pk];return (pv!=null&&pv!==0)?K.v[i]/Math.abs(pv)-Math.sign(pv):null});
  K.yoy=K.yoyA[K.yoyA.length-1]; K.qoq=K.qoqA[K.qoqA.length-1]});
 let KMODE='bars';
 function drawKpis(){if(!kg)return;
  const n=CARDS.length, maxc=Math.max(1,Math.min(n,Math.floor((kg.clientWidth+14)/340)));
  let cols=maxc,best=99;for(let c=maxc;c>=Math.max(1,maxc-1);c--){const e=(c-n%c)%c;if(e<best){best=e;cols=c}}
  const spans=CARDS.map(()=>1), r=n%cols; if(r){for(let k=0;k<cols-r;k++)spans[n-1-(k%r)]++}
  kg.style.gridTemplateColumns=`repeat(${cols},minmax(0,1fr))`;
  kg.innerHTML=CARDS.map((K,i)=>{const last=K.v[K.v.length-1], gy=isGood(K,K.yoy), gq=isGood(K,K.qoq);
   return `<div class="kcard" style="grid-column:span ${spans[i]}" title="${esc(K.name)}${K.src?' ('+esc(K.src)+')':''}"><div class="kn">${esc(K.name)}</div>
    <div class="kv">${last!=null?NF(Math.abs(last)<10?2:1).format(last):'–'} <span class="sm mut" style="font-weight:400">${esc(unitDe(K.unit))}</span></div>
    <div class="sm"><span class="${gy==null?'mut':gy?'pos':'neg'}">${gp(K.yoy)} YoY</span> <span class="mut">·</span> <span class="${gq==null?'mut':gq?'pos':'neg'}">${gp(K.qoq)} QoQ</span> <span class="mut">· ${esc(sq(K.q[K.q.length-1]||''))}</span></div>
    <div class="kb" data-i="${i}"></div></div>`}).join('');
  kg.querySelectorAll('.kb').forEach(el=>{const K0=CARDS[+el.dataset.i];const off=Math.max(0,K0.q.length-8);
   const K={...K0,q:K0.q.slice(off),v:K0.v.slice(off),p:K0.p?K0.p.slice(off):null,yoyA:K0.yoyA.slice(off),qoqA:K0.qoqA.slice(off)};
   const W=Math.max(260,el.clientWidth),n=K.q.length,L=44,R=W-6,T=8,PH=118,B=T+PH, growth=KMODE==='yoy';
   const ser=growth?K.yoyA.map(x=>x==null?null:x*100):K.v, two=!growth&&KMODE==='bars'&&!!K.p&&K.p.some(x=>x!=null);
   const vals=[...ser,...(two?K.p:[])].filter(x=>x!=null); if(!vals.length){el.innerHTML='<div class="sm mut" style="margin-top:8px">No values to chart.</div>';return}
   let lo=Math.min(...vals),hi=Math.max(...vals); if(KMODE!=='line'||growth){lo=Math.min(lo,0);hi=Math.max(hi,0)} else {const pad=(hi-lo)*0.15||Math.abs(hi)*0.1||1;lo-=pad;hi+=pad}
   const ticks=nice(lo,hi), t0=ticks[0], t1=ticks[ticks.length-1], Y=v=>B-(v-t0)/((t1-t0)||1)*PH;
   const slot=(R-L)/n, bw=Math.max(5,Math.min(22,slot/(two?2.7:1.7))), every=Math.ceil(n/Math.max(1,Math.floor((R-L)/46)));
   const unit=growth?'% YoY':unitDe(K.unit); let s='';
   ticks.forEach(t=>{s+=`<line x1="${L}" x2="${R}" y1="${Y(t)}" y2="${Y(t)}" stroke="var(--line)" stroke-width="1"/><text x="${L-6}" y="${Y(t)+4}" text-anchor="end" fill="var(--mut)" style="font-size:calc(11.5px*var(--bfs,1))">${fax(t)}${growth?'%':''}</text>`});
   const y0=Y(Math.max(t0,Math.min(0,t1)));
   if(KMODE==='line'&&!growth){const pts=ser.map((v,i)=>v==null?null:[L+slot*(i+.5),Y(v)]);let d='',pen=false;pts.forEach(p=>{if(!p){pen=false;return}d+=(pen?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1);pen=true});
    s+=`<path d="${d}" fill="none" stroke="var(--acc)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    pts.forEach((p,i)=>{if(p)s+=`<circle cx="${p[0]}" cy="${p[1]}" r="${i===n-1?4.5:3.2}" fill="var(--acc)" stroke="var(--bg)" stroke-width="2"><title>${esc(K.q[i])}: ${NF(2).format(ser[i])} ${esc(unit)}</title></circle>`})}
   else K.q.forEach((q,i)=>{const cx=L+slot*(i+.5);
    const bars=growth?[[ser[i],isGood(K,K.yoyA[i])?'var(--pos)':'var(--neg)',-bw/2]]:two?[[K.p[i],'var(--line2)',-bw-1],[ser[i],'var(--acc)',1]]:[[ser[i],i===n-1?'var(--acc)':'var(--acc2)',-bw/2]];
    bars.forEach(([v,c,o],j)=>{if(v==null)return;const y=Y(v);const lab=growth?NF(1).format(v)+'% YoY':NF(2).format(v)+' '+unit;
     s+=`<rect x="${(cx+o).toFixed(1)}" y="${Math.min(y,y0).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1.5,Math.abs(y0-y)).toFixed(1)}" rx="3" fill="${c}"><title>${esc(q)}${two&&j===0?' prior year':''}: ${esc(lab)}</title></rect>`})});
   s+=`<line x1="${L}" x2="${R}" y1="${y0}" y2="${y0}" stroke="var(--mut)" stroke-width="1"/>`;
   const fs='style="font-size:calc(11.5px*var(--bfs,1))"';
   K.q.forEach((q,i)=>{const cx=L+slot*(i+.5),show=(n-1-i)%every===0;
    if(show)s+=`<text x="${cx}" y="${B+15}" text-anchor="middle" fill="var(--tx)" ${fs}>${esc(sq(q))}</text>`;
    if(!growth&&show){const g1=K.yoyA[i],g2=K.qoqA[i],c1=isGood(K,g1),c2=isGood(K,g2);
     s+=`<text x="${cx}" y="${B+33}" text-anchor="middle" style="fill:var(${c1==null?'--mut':c1?'--pos':'--neg'});font-size:calc(11.5px*var(--bfs,1))">${gp(g1)}</text>`;
     s+=`<text x="${cx}" y="${B+50}" text-anchor="middle" style="fill:var(${c2==null?'--mut':c2?'--pos':'--neg'});font-size:calc(11.5px*var(--bfs,1))">${gp(g2)}</text>`}});
   if(!growth)s+=`<text x="${L-6}" y="${B+33}" text-anchor="end" fill="var(--mut)" ${fs}>YoY</text><text x="${L-6}" y="${B+50}" text-anchor="end" fill="var(--mut)" ${fs}>QoQ</text>`;
   const H=B+(growth?22:58);
   el.innerHTML=`<div class="sm mut" style="margin-top:8px">${esc(unit)}</div><svg width="${W}" height="${H}" style="display:block;margin-top:2px;overflow:visible">${s}</svg>`});
 }
 root.querySelectorAll('#kmode button').forEach(b=>b.onclick=()=>{KMODE=b.dataset.km;root.querySelectorAll('#kmode button').forEach(x=>x.classList.toggle('on',x===b));drawKpis()});
 drawKpis();
 if(kg){if(root._kro)root._kro.disconnect();let lw=kg.clientWidth;root._kro=new ResizeObserver(()=>{if(Math.abs(kg.clientWidth-lw)>8){lw=kg.clientWidth;drawKpis()}});root._kro.observe(kg)}

 // Vergleich
 const sel=new Set(); const cmp=$('#cmp');
 $$('[data-c]').forEach(c=>c.onchange=()=>{const i=+c.dataset.c;c.checked?sel.add(i):sel.delete(i);if(sel.size>2){const f=[...sel][0];sel.delete(f);const el=root.querySelector(`[data-c="${f}"]`);if(el)el.checked=false}
  $$('.rtile').forEach(t=>t.classList.toggle('sel',sel.has(+t.dataset.i)));drawCmp()});
 function drawCmp(){if(!cmp)return;const R=[...sel].map(i=>D.reports[i]).sort((a,b)=>a.date<b.date?-1:1);
  if(R.length<2){cmp.innerHTML=(D.reports||[]).length<2?'<div class="sm mut">Comparison available once a second report exists – every run is archived automatically.</div>':'';return}
  if(R[0].kind!==R[1].kind){cmp.innerHTML='<div class="sm" style="color:var(--rd)">Please pick two reports of the same kind (annual with annual, earnings review with earnings review).</div>';return}
  const [a,b]=R; const fa=a.fc_total?a.fc_matched/a.fc_total:null, fb=b.fc_total?b.fc_matched/b.fc_total:null;
  const thA=Object.fromEntries((a.theses||[]).map(t=>[t.thesis.replace(/^T\d+:\s*/,'').slice(0,60),t]));
  let rows=(b.theses||[]).map(t=>{const o=thA[t.thesis.replace(/^T\d+:\s*/,'').slice(0,60)];const ch=o&&o.status!==t.status;
   return `<tr><td>${esc(t.thesis)}</td><td>${o?`<span class="qc s-${o.status||'baseline'}">${esc(TH[o.status]||o.status||'–')}</span>`:'<span class="mut">new</span>'}</td><td><span class="qc s-${t.status||'baseline'}">${esc(TH[t.status]||t.status||'–')}</span>${ch?' <b style="color:var(--rd)">changed</b>':''}</td></tr>`}).join('');
  const lastQ=v=>{const qs=Object.keys(v||{}).sort((x,y)=>{const p=z=>{const m=z.match(/Q(\d)\s*FY(\d{4})/);return m?+m[2]*10+ +m[1]:0};return p(x)-p(y)});return qs[qs.length-1]};
  const sq=q=>String(q||'').replace(/\s*FY\d{2}(\d{2})/,' $1');
  let krows='';if(a.kind==='earnings'){const KA=Object.fromEntries((a.kpis||[]).map(k=>[k.name,k]));(b.kpis||[]).forEach(k=>{const o=KA[k.name];const qb=lastQ(k.values),qa=o?lastQ(o.values):null;
   const vb=qb?k.values[qb]:null, va=qa?o.values[qa]:null; const d=(va!=null&&vb!=null&&va!==0)?(vb-va)/Math.abs(va):null;
   krows+=`<tr><td>${esc(k.name)}</td><td>${va!=null?NF(2).format(va)+' <span class="mut">'+esc(sq(qa))+'</span>':'–'}</td><td>${vb!=null?NF(2).format(vb)+' <span class="mut">'+esc(sq(qb))+'</span>':'–'}${d!=null&&qa!==qb?` <span class="${(k.good==='down'?-d:d)>=0?'pos':'neg'}">${pct(d)}</span>`:''}</td></tr>`})}
  cmp.innerHTML=`<div class="ch"><h3>Comparison: ${fmtDate(a.date)} → ${fmtDate(b.date)}</h3><span class="meta">fact check ${fa!=null?NF(0).format(fa*100)+'%':'–'} → ${fb!=null?NF(0).format(fb*100)+'%':'–'}</span></div>
   <div class="cmp"><div class="kcard"><div class="kn">${fmtDate(a.date)} · ${esc(a.title)}</div><div class="sm" style="margin-top:4px">${esc(a.headline)}</div></div><div class="kcard"><div class="kn">${fmtDate(b.date)} · ${esc(b.title)}</div><div class="sm" style="margin-top:4px">${esc(b.headline)}</div></div></div>
   <div class="cmp" style="margin-top:12px"><table><tr><th>Thesis</th><th>before</th><th>after</th></tr>${rows||'<tr><td colspan="3" class="mut">No theses</td></tr>'}</table>
   ${krows?`<table><tr><th>KPI (latest quarter)</th><th>before</th><th>after</th></tr>${krows}</table>`:'<div></div>'}</div>`}
 if(cmp)drawCmp();
}
"""

VAL_CSS = r"""
.vgrid{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:16px}
@media (max-width:1000px){.vgrid{grid-template-columns:minmax(0,1fr)}}
.vbig{font-size:calc(30px*var(--bfs,1));font-weight:600;line-height:1.1}
.vsl{display:grid;grid-template-columns:150px minmax(0,1fr) 64px;align-items:center;gap:10px;margin:7px 0}
.vsl label{font-size:calc(14.5px*var(--bfs,1));color:var(--mut)}.vsl b{font-weight:600;text-align:right;font-variant-numeric:tabular-nums}
.vsl input[type=range]{width:100%;accent-color:var(--acc)}
.vbar{display:grid;grid-template-columns:150px minmax(0,1fr) 70px;align-items:center;gap:10px;margin:5px 0;font-size:calc(14.5px*var(--bfs,1))}
.vbar .tr{height:12px;background:var(--soft);border-radius:4px;position:relative;overflow:hidden}
.vbar .tr i{position:absolute;top:0;bottom:0;border-radius:4px}
.vbar span:last-child{text-align:right;font-variant-numeric:tabular-nums}
.vtab{width:100%;border-collapse:collapse;font-size:calc(14px*var(--bfs,1));font-variant-numeric:tabular-nums}
.vtab th,.vtab td{padding:6px 7px;border-top:1px solid var(--line);text-align:right;white-space:nowrap}
.vtab th{color:var(--mut);font-weight:500;border-top:0}.vtab td:first-child,.vtab th:first-child{text-align:left}
.vtab tr.me td{background:var(--accbg);font-weight:600}.vtab tr.md td{color:var(--mut);font-style:italic}
.vtab td.cur{outline:2px solid var(--acc);outline-offset:-2px;font-weight:600}
.qrow{display:flex;gap:9px;align-items:flex-start;padding:4px 0;font-size:calc(14.5px*var(--bfs,1))}
.qi{width:18px;flex:none;text-align:center;font-weight:700}
.vbtns{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.vnote{font-size:calc(14.5px*var(--bfs,1));line-height:1.5;margin-top:10px;padding:10px 12px;border-radius:10px;background:var(--soft)}
"""

VAL_JS = r"""
export default function(component){
 const {data,parentElement,setTriggerValue}=component; const D=data||{}; const root=mount(parentElement); darkMode(root,parentElement);
 const go=(name,v)=>setTriggerValue(name,{v:v||null,n:Date.now()});
 const P=v=>v==null||typeof v==='string'?(v||'–'):NF(1).format(v*100)+'%';
 const head=(t,tip,meta)=>`<div class="ch"><div><h3>${t}${ii(tip)}</h3>${meta?`<div class="meta">${meta}</div>`:''}</div></div>`;
 if(!D.t||D.missing){root.innerHTML=`<div class="card">${head('Valuation, quality and peers','Reverse DCF, financial quality scores and peer comparison, computed from Yahoo Finance data.','')}
   <div class="sm mut">${esc(D.error||'Valuation data not loaded yet.')}</div><div class="vbtns"><button class="btn" id="vl">Load data (about 15 s)</button></div></div>`;
  const b=root.querySelector('#vl'); if(b)b.onclick=()=>go('refresh',1); return}
 const rd=D.rdcf||{}, q=D.quality||{}, mk=D.market||{}, cs=D.consensus||{}, C=D.case;
 const okR=rd&&!rd.error&&rd.ev&&rd.rev0;
 const cons=(cs.years||[]).filter(y=>typeof y.growth==='number');
 const S={w:rd.wacc||0.09,m:rd.m_target||0.15,tg:rd.tg||0.025,y:rd.years||10,g:C&&C.growth!=null?C.growth:(cons[0]?cons[0].growth:(typeof rd.implied_g==='number'?rd.implied_g:0.08))};
 const S0={...S};
 function val(g,w,m,tg,y){let pv=0,r=rd.rev0;for(let t=1;t<=y;t++){r*=1+g;const mm=rd.m0+(m-rd.m0)*t/y;pv+=r*mm/Math.pow(1+w,t)}return pv+r*m*(1+tg)/(w-tg)/Math.pow(1+w,y)}
 function solve(w,m,tg,y){if(w<=tg+0.002)return null;let lo=-0.3,hi=1.0;const f=g=>val(g,w,m,tg,y)-rd.ev;if(f(lo)>0)return -Infinity;if(f(hi)<0)return Infinity;for(let k=0;k<70;k++){const mid=(lo+hi)/2;f(mid)<0?lo=mid:hi=mid}return (lo+hi)/2}
 const G=v=>v==null?'–':v===Infinity?'> 100%':v===-Infinity?'< −30%':NF(1).format(v*100)+'%';
 const asof=D.asof?fmtDate(D.asof.slice(0,10)):'';
 let h=`<div class="vgrid"><div class="card">`;
 h+=head('Reverse DCF',`What constant revenue growth over the next years does today's enterprise value price in? Free-cash-flow margin moves linearly from the last fiscal year (${P(rd.m0)}) to the target margin; terminal value with perpetual growth. Move the assumptions to test it; the AI base case is proposed from the annual report research. Model: WACC = risk-free rate + beta × 5%.`,
  okR?`FY${esc(rd.fy)} · EV ${NF(0).format(rd.ev)}m ${esc(mk.fin_cur||'')} · revenue ${NF(0).format(rd.rev0)}m · data as of ${esc(asof)}${D.stale?' · <b style="color:var(--neg)">older than a day</b>':''}`:'');
 if(!okR){h+=`<div class="sm mut">Reverse DCF not available: ${esc(rd.error||(D.errors||{}).rdcf||'no data')}.</div>`}
 else{
  h+=`<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-end;margin:4px 0 8px">
    <div><div class="sm mut">Market-implied revenue growth p.a.</div><div class="vbig" id="vig">–</div></div>
    <div><div class="sm mut">Value at your growth</div><div class="vbig" id="vup">–</div><div class="sm mut" id="vup2"></div></div></div>`;
  const sl=(id,lab,min,max,step,v)=>`<div class="vsl"><label for="${id}">${lab}</label><input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${v}"><b id="${id}o"></b></div>`;
  h+=sl('sw','WACC',5,16,0.25,(S.w*100).toFixed(2))+sl('sm','Target FCF margin',0,50,0.5,(S.m*100).toFixed(1))+sl('st','Perpetual growth',0,4,0.25,(S.tg*100).toFixed(2))
   +sl('sy','Years of growth',5,15,1,S.y)+sl('sg','Your growth p.a.',-5,40,0.5,(S.g*100).toFixed(1));
  h+=`<div style="margin-top:12px" id="vbars"></div>`;
  if(C)h+=`<div class="vnote"><b>AI base case</b> <span class="sm mut">${esc(fmtDate((C.created||'').slice(0,10)))}</span> · growth ${P(C.growth)}, margin ${P(C.margin)}, WACC ${P(C.wacc)}, perpetual ${P(C.terminal)}<br>${esc(C.rationale||'')}</div>`;
  h+=`<div class="vbtns">${C?'<button class="btn" id="vac">Apply AI case</button>':''}<button class="btn" id="vsu">${C?'New AI case':'Suggest AI base case'}</button><button class="btn" id="vrs">Reset</button><button class="btn" id="vrf">Refresh data</button></div>`;
  h+=`<div class="sm mut" style="margin:14px 0 4px">Sensitivity: implied growth by target margin and WACC (current assumptions outlined)</div><div id="vsens"></div>`}
 h+=`</div><div class="card">`;
 // Quality
 const pi=q.piotroski, az=q.altman, bm=q.beneish;
 h+=head('Financial quality','Piotroski F-score: 9 accounting tests on profitability, leverage/liquidity and efficiency (7–9 strong, 0–3 weak). Altman Z: bankruptcy risk (> 2.99 safe, 1.81–2.99 grey, < 1.81 distress; less meaningful for banks and asset-light software). Beneish M: earnings-manipulation screen (above −1.78 = red flag). From the annual statements on Yahoo Finance.',q.fy?`fiscal year ${esc(q.fy)} vs. prior year`:'');
 if(q.error||!pi){h+=`<div class="sm mut">Quality scores not available: ${esc(q.error||(D.errors||{}).quality||'no data')}.</div>`}
 else{const sc=pi.score, col=sc>=7?'var(--pos)':sc<=3?'var(--neg)':'#B9770E';
  h+=`<div style="display:flex;gap:26px;flex-wrap:wrap;margin:4px 0 10px">
   <div><div class="sm mut">Piotroski F-score</div><div class="vbig" style="color:${col}">${sc}<span class="sm mut" style="font-weight:400"> / ${pi.available}</span></div></div>
   <div><div class="sm mut">Altman Z</div><div class="vbig">${az?NF(2).format(az.z):'–'}</div>${az?`<span class="pill" style="background:${az.zone==='safe'?'rgba(26,127,75,.12)':az.zone==='grey'?'rgba(185,119,14,.14)':'rgba(180,35,24,.12)'};color:${az.zone==='safe'?'var(--pos)':az.zone==='grey'?'#B9770E':'var(--neg)'}">${esc(az.zone)}</span>`:''}</div>
   <div><div class="sm mut">Beneish M</div><div class="vbig">${bm?NF(2).format(bm.m):'–'}</div>${bm?`<span class="pill" style="background:${bm.flag?'rgba(180,35,24,.12)':'rgba(26,127,75,.12)'};color:${bm.flag?'var(--neg)':'var(--pos)'}">${bm.flag?'red flag':'no red flag'}</span>`:''}</div></div>`;
  h+=(pi.criteria||[]).map(c=>`<div class="qrow"><span class="qi" style="color:${c.pass==null?'var(--mut)':c.pass?'var(--pos)':'var(--neg)'}">${c.pass==null?'–':c.pass?'✓':'✗'}</span><span>${esc(c.criterion)}</span></div>`).join('')}
 // implizite Rendite
 const ir=D.irr||{};
 if(ir&&!ir.error&&ir.irr!=null)h+=`<div class="vnote"><b>Implied return on the consensus path:</b> ${P(ir.irr)} p.a. vs. WACC ${P(ir.wacc)}${typeof ir.spread==='number'?` (<span class="${ir.spread>=0?'pos':'neg'}">${ir.spread>=0?'+':''}${NF(1).format(ir.spread*100)} pp</span>)`:''}. Revenue follows analyst consensus for two years, then growth fades to 2.5% by year 10.</div>`;
 h+=`</div></div>`;
 // Peers
 const PR=D.peers||[];
 h+=`<div class="card" style="margin-top:16px">${head('Peer comparison','Peers chosen and justified by the Annual Report agent (business model first, size second). Figures from Yahoo Finance, trailing twelve months; forward P/E on consensus. In the company row, green = better than the peer median, red = worse.',PR.length?`${PR.length-1} peers · data as of ${esc(asof)}`:'')}`;
 if(!PR.length)h+=`<div class="sm mut">No peers yet – they are chosen in the next annual report run.</div>`;
 else{const COLS=[['mcap','Mkt cap','bn',0],['growth','Rev. growth','%',1],['gm','Gross margin','%',1],['om','Op. margin','%',1],['fcfm','FCF margin','%',1],['roe','ROE','%',1],['evs','EV/Sales','x',-1],['eve','EV/EBITDA','x',-1],['fpe','Fwd P/E','x',-1],['nde','Net debt/EBITDA','x',-1]];
  const med=k=>{const a=PR.slice(1).map(r=>r[k]).filter(v=>typeof v==='number').sort((x,y)=>x-y);if(!a.length)return null;const m=a.length>>1;return a.length%2?a[m]:(a[m-1]+a[m])/2};
  const MED=Object.fromEntries(COLS.map(c=>[c[0],med(c[0])]));
  const fv=(v,u)=>v==null?'–':u==='%'?NF(1).format(v*100)+'%':u==='x'?NF(1).format(v)+'x':NF(v>=100?0:1).format(v);
  const row=(r,cls,me)=>`<tr class="${cls}"><td>${me?'':''}<b style="font-weight:${me?600:500}">${esc(r.t)}</b> <span class="sm mut">${esc(String(r.name||'').slice(0,26))}</span></td>${COLS.map(([k,l,u,dir])=>{let st='';if(me&&dir&&typeof r[k]==='number'&&MED[k]!=null&&!(k==='nde'&&r[k]<0&&MED[k]<0)){const better=dir>0?r[k]>MED[k]:r[k]<MED[k];st=` style="color:${better?'var(--pos)':'var(--neg)'}"`}return `<td${st}>${fv(r[k],u)}</td>`}).join('')}</tr>`;
  h+=`<div style="overflow-x:auto"><table class="vtab"><tr><th>Company</th>${COLS.map(c=>`<th>${c[1]}${c[2]==='bn'?' ($bn)':''}</th>`).join('')}</tr>${row(PR[0],'me',true)}${PR.slice(1).map(r=>row(r,'',false)).join('')}<tr class="md"><td>Peer median</td>${COLS.map(([k,l,u])=>`<td>${fv(MED[k],u)}</td>`).join('')}</tr></table></div>`;
  h+=`<div style="display:flex;align-items:center;gap:12px;margin:14px 0 6px;flex-wrap:wrap"><span class="sm mut">Chart</span><div class="seg" id="pm">${COLS.slice(1).map((c,i)=>`<button data-k="${c[0]}" class="${i===0?'on':''}">${c[1]}</button>`).join('')}</div></div><div id="pbars"></div>`;
  if(D.peer_note)h+=`<div class="vnote"><b>Competitive position (annual report):</b> ${esc(D.peer_note)}</div>`;
  root._COLS=COLS;root._fv=fv}
 h+=`</div>`;
 root.innerHTML=h;
 const $=s=>root.querySelector(s);
 // Peer-Balken
 function pbars(k){const el=$('#pbars');if(!el)return;const c=root._COLS.find(x=>x[0]===k);const rows=PR.filter(r=>typeof r[k]==='number');
  if(!rows.length){el.innerHTML='<div class="sm mut">No data for this metric.</div>';return}
  const mx=Math.max(...rows.map(r=>Math.abs(r[k])),1e-9);
  el.innerHTML=rows.sort((a,b)=>b[k]-a[k]).map(r=>`<div class="vbar"><span><b style="font-weight:${r.t===PR[0].t?600:400}">${esc(r.t)}</b></span><div class="tr"><i style="left:0;width:${Math.abs(r[k])/mx*100}%;background:${r.t===PR[0].t?'var(--acc)':r[k]<0?'var(--neg)':'var(--line2)'}"></i></div><span>${root._fv(r[k],c[2])}</span></div>`).join('')}
 if($('#pm')){root.querySelectorAll('#pm button').forEach(b=>b.onclick=()=>{root.querySelectorAll('#pm button').forEach(x=>x.classList.toggle('on',x===b));pbars(b.dataset.k)});pbars('growth')}
 if(!okR)return;
 const ids={sw:'w',sm:'m',st:'tg',sy:'y',sg:'g'};
 function draw(){const ig=solve(S.w,S.m,S.tg,S.y);
  $('#swo').textContent=NF(2).format(S.w*100)+'%';$('#smo').textContent=NF(1).format(S.m*100)+'%';$('#sto').textContent=NF(2).format(S.tg*100)+'%';$('#syo').textContent=S.y;$('#sgo').textContent=NF(1).format(S.g*100)+'%';
  $('#vig').textContent=G(ig);
  const V=S.w>S.tg+0.002?val(S.g,S.w,S.m,S.tg,S.y):null;
  if(V!=null){const nd=mk.mcap?rd.ev-mk.mcap:null; const up=nd!=null?(V-nd)/mk.mcap-1:V/rd.ev-1;
   $('#vup').innerHTML=`<span class="${up>=0?'pos':'neg'}">${up>=0?'+':''}${NF(0).format(up*100)}%</span>`;
   $('#vup2').textContent=`${nd!=null?'equity value vs. market cap':'enterprise value vs. today'} · EV ${NF(0).format(V)}m`}
  else{$('#vup').textContent='–';$('#vup2').textContent='WACC must exceed perpetual growth'}
  const bars=[['Market-implied',ig,'var(--acc)'],...cons.slice(0,2).map(y=>[`Consensus FY${y.fy}`,y.growth,'var(--acc2)']),['3-year history',rd.hist_cagr3,'var(--line2)'],...(C?[['AI base case',C.growth,'#B9770E']]:[]),['Your growth',S.g,'var(--tx)']].filter(b=>typeof b[1]==='number'&&isFinite(b[1]));
  const lo=Math.min(0,...bars.map(b=>b[1])),hi=Math.max(0.01,...bars.map(b=>b[1])),X=v=>(v-lo)/(hi-lo)*100;
  $('#vbars').innerHTML=bars.map(([l,v,c])=>`<div class="vbar"><span>${esc(l)}</span><div class="tr"><i style="left:${Math.min(X(0),X(v))}%;width:${Math.max(0.8,Math.abs(X(v)-X(0)))}%;background:${c}"></i></div><span>${NF(1).format(v*100)}%</span></div>`).join('');
  const ms=[-0.10,-0.05,0,0.05,0.10].map(d=>Math.max(0,S.m+d)), ws=[-0.02,-0.01,0,0.01,0.02].map(d=>S.w+d);
  $('#vsens').innerHTML=`<table class="vtab"><tr><th>Margin \\ WACC</th>${ws.map(w=>`<th>${NF(1).format(w*100)}%</th>`).join('')}</tr>${ms.map((m,i)=>`<tr><td>${NF(1).format(m*100)}%</td>${ws.map((w,j)=>`<td class="${i===2&&j===2?'cur':''}">${G(solve(w,m,S.tg,S.y))}</td>`).join('')}</tr>`).join('')}</table>`}
 Object.keys(ids).forEach(id=>{const el=$('#'+id);el.oninput=()=>{const k=ids[id];S[k]=k==='y'?+el.value:+el.value/100;draw()}});
 const setS=o=>{Object.assign(S,o);$('#sw').value=(S.w*100).toFixed(2);$('#sm').value=(S.m*100).toFixed(1);$('#st').value=(S.tg*100).toFixed(2);$('#sy').value=S.y;$('#sg').value=(S.g*100).toFixed(1);draw()};
 if($('#vac'))$('#vac').onclick=()=>setS({w:C.wacc??S.w,m:C.margin??S.m,tg:C.terminal??S.tg,g:C.growth??S.g});
 $('#vrs').onclick=()=>setS({...S0});
 $('#vsu').onclick=()=>{$('#vsu').textContent='Asking the model …';go('suggest',1)};
 $('#vrf').onclick=()=>{$('#vrf').textContent='Loading …';go('refresh',1)};
 draw();
}
"""

_grid = st.components.v2.component("finrobot_companies", css=CSS, js=GRID_JS)
_company = st.components.v2.component("finrobot_company", css=CSS + VAL_CSS, js=COMPANY_JS)
VAL_JS_FULL = COMMON_JS + VAL_JS
_val = st.components.v2.component("finrobot_valuation", css=CSS + VAL_CSS, js=VAL_JS_FULL)


def render_companies(companies, key="companies"):
    return _grid(data={"companies": companies}, key=key, on_open_change=lambda: None, on_make_change=lambda: None)


def render_valuation(payload, key="valuation"):
    return _val(data=payload, key=key, on_refresh_change=lambda: None, on_suggest_change=lambda: None)


def render_company(payload, key="company"):
    return _company(data=payload, key=key, on_back_change=lambda: None, on_check_change=lambda: None,
                    on_report_change=lambda: None, on_committee_change=lambda: None,
                    on_tracker_change=lambda: None)
