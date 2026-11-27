"""
Home-Seite der App als eigene Komponente (Streamlit components v2): Kacheln, SVG-Charts, Klicks gehen an Python
zurueck (Navigation, Kurse aktualisieren). Keine externen Bibliotheken, kein pyarrow.
Alle Texte aus den Daten werden im JavaScript escaped (Agenten- und News-Texte sind nicht vertrauenswuerdig).
"""
import streamlit as st

CSS = r"""
:host{display:block}
.fr{--tx:var(--st-text-color,#1f2328);--bg:var(--st-background-color,#fff);
 --mut:color-mix(in srgb,var(--tx) 58%,transparent);--faint:color-mix(in srgb,var(--tx) 40%,transparent);
 --line:color-mix(in srgb,var(--tx) 11%,transparent);--line2:color-mix(in srgb,var(--tx) 20%,transparent);
 --soft:color-mix(in srgb,var(--tx) 4%,transparent);--hov:color-mix(in srgb,var(--tx) 7%,transparent);
 --acc:#185FA5;--acc2:#378ADD;--accbg:rgba(55,138,221,.12);
 --dec:#A32D2D;--decbg:rgba(226,75,74,.13);--rd:#8a5208;--rdbg:rgba(239,159,39,.18);--ok:#0F6E56;--okbg:rgba(29,158,117,.13);
 --pos:#1a7f4b;--neg:#b42318;
 color:var(--tx);font-family:inherit;font-size:calc(17px*var(--bfs,1));line-height:1.45;font-variant-numeric:tabular-nums}
.fr.dark{--acc:#85B7EB;--acc2:#85B7EB;--accbg:rgba(55,138,221,.16);--dec:#F7A1A1;--decbg:rgba(226,75,74,.24);--rd:#FAC775;--rdbg:rgba(239,159,39,.22);--ok:#7FD9B8;--okbg:rgba(29,158,117,.22);--pos:#5DCAA5;--neg:#F09595}
.fr *{box-sizing:border-box}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 14px}
.top h1{font-size:calc(25px*var(--bfs,1));font-weight:600;margin:0;letter-spacing:-.01em}
.top .sub{color:var(--mut);font-size:calc(16px*var(--bfs,1))}
.search{flex:1;min-width:220px;max-width:460px;display:flex;align-items:center;gap:8px;border:1px solid var(--line2);
 border-radius:10px;padding:0 12px;height:36px;background:var(--bg)}
.search:focus-within{border-color:var(--acc2);box-shadow:0 0 0 3px var(--accbg)}
.search input{flex:1;border:0;outline:0;background:transparent;color:var(--tx);font:inherit;font-size:calc(16px*var(--bfs,1))}
.search kbd{font-size:calc(14px*var(--bfs,1));color:var(--faint);border:1px solid var(--line);border-radius:5px;padding:1px 5px}
.btn{height:36px;border:1px solid var(--line2);background:var(--bg);color:var(--tx);border-radius:10px;padding:0 14px;
 font:inherit;font-size:calc(16px*var(--bfs,1));cursor:pointer;display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.btn:hover{background:var(--hov)} .btn.pri{background:var(--tx);color:var(--bg);border-color:var(--tx)}
.btn.pri:hover{opacity:.88}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}
.c3{grid-column:span 3}.c4{grid-column:span 4}.c5{grid-column:span 5}.c6{grid-column:span 6}.c7{grid-column:span 7}.c8{grid-column:span 8}.c12{grid-column:span 12}
@media (max-width:1100px){.c3{grid-column:span 6}.c4,.c5,.c6,.c7,.c8{grid-column:span 12}}
@media (max-width:640px){.c3{grid-column:span 12}}
.k5{grid-column:span 12;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}
@media (max-width:1100px){.k5{grid-template-columns:repeat(2,minmax(0,1fr))}}
.card{border:1px solid var(--line);border-radius:14px;padding:16px 18px;background:var(--bg);min-width:0}
.card.click{cursor:pointer;transition:border-color .15s}.card.click:hover{border-color:var(--line2)}
.ch{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 12px}
.ch h3{font-size:calc(18px*var(--bfs,1));font-weight:600;margin:0}.ch .meta{font-size:calc(15px*var(--bfs,1));color:var(--mut)}
.kpi{background:var(--soft);border:1px solid transparent;border-radius:14px;padding:14px 16px;min-width:0}
.kpi .l{font-size:calc(15.5px*var(--bfs,1));color:var(--mut);display:flex;align-items:center;gap:6px}
.kpi .v{font-size:calc(30px*var(--bfs,1));font-weight:600;letter-spacing:-.02em;margin:4px 0 2px;white-space:nowrap}
.kpi .s{font-size:calc(15.5px*var(--bfs,1));color:var(--mut)}
.kpi.sm .v{font-size:calc(22px*var(--bfs,1))}
.pos{color:var(--pos)}.neg{color:var(--neg)}
.pill{display:inline-block;font-size:calc(14.5px*var(--bfs,1));font-weight:500;padding:2px 9px;border-radius:999px;white-space:nowrap}
.p-decide{background:var(--decbg);color:var(--dec)}.p-read{background:var(--rdbg);color:var(--rd)}.p-none{background:var(--okbg);color:var(--ok)}
.row{display:flex;gap:12px;align-items:flex-start;padding:10px 6px;border-top:1px solid var(--line);border-radius:8px}
.row:first-of-type{border-top:0}
.row.click{cursor:pointer}.row.click:hover{background:var(--hov)}
.tk{font-family:var(--st-code-font,ui-monospace,Menlo,monospace);font-weight:600;font-size:calc(16px*var(--bfs,1))}
.mut{color:var(--mut)}.sm{font-size:calc(15.5px*var(--bfs,1))}
.grow{flex:1;min-width:0}
.dt{min-width:52px;color:var(--mut);font-size:calc(15.5px*var(--bfs,1));padding-top:1px}
.ico{width:28px;height:28px;border-radius:8px;background:var(--soft);display:flex;align-items:center;justify-content:center;flex:none;color:var(--mut)}
.brief{display:flex;gap:14px;align-items:flex-start;border:1px solid var(--line);border-left:3px solid var(--acc2);border-radius:0 12px 12px 0;padding:12px 16px}
.brief b{font-weight:600}
.seg{display:inline-flex;background:var(--soft);border-radius:9px;padding:2px}
.seg button{border:0;background:transparent;color:var(--mut);font:inherit;font-size:calc(15px*var(--bfs,1));padding:4px 9px;border-radius:7px;cursor:pointer}
.seg button.on{background:var(--bg);color:var(--tx);box-shadow:0 0 0 1px var(--line)}
.chart{position:relative}
.tip{position:absolute;pointer-events:none;background:var(--bg);border:1px solid var(--line2);border-radius:10px;padding:8px 10px;
 font-size:calc(15px*var(--bfs,1));box-shadow:0 6px 20px rgba(0,0,0,.10);white-space:nowrap;z-index:5;display:none}
.legend{display:flex;gap:14px;font-size:calc(15px*var(--bfs,1));color:var(--mut);flex-wrap:wrap;margin-top:6px}
.sw{display:inline-block;width:10px;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.chip{border:1px solid var(--line);border-radius:10px;padding:6px 10px;font-size:calc(15px*var(--bfs,1));min-width:92px}
.chip b{display:block;font-size:calc(17px*var(--bfs,1));font-weight:600}
.bar{height:8px;border-radius:4px;background:var(--soft);overflow:hidden}.bar i{display:block;height:100%;border-radius:4px}
.tm{position:relative;height:300px}
.tile{position:absolute;border-radius:8px;padding:8px 10px;overflow:hidden;cursor:pointer;border:2px solid var(--bg);transition:filter .12s}
.tile:hover{filter:brightness(.95)}
.tile .n{font-weight:600;font-size:calc(16px*var(--bfs,1))}.tile .x{font-size:calc(15px*var(--bfs,1));opacity:.85}
.tile .n,.tile .x{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lg{display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:7px;cursor:pointer;font-size:calc(16px*var(--bfs,1))}
.lg:hover{background:var(--hov)}.lg .d{width:10px;height:10px;border-radius:3px;flex:none}
.empty{color:var(--mut);font-size:calc(16px*var(--bfs,1));padding:8px 0}
.stack{display:flex;flex-direction:column;gap:14px;min-width:0}
.rgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:36px}
@media (max-width:900px){.rgrid{grid-template-columns:1fr}}
.clamp{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.lgg{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:6px}
.card{display:flex;flex-direction:column}
.foot{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;color:var(--faint);font-size:calc(15px*var(--bfs,1));margin-top:14px}
a{color:inherit;text-decoration:none}
svg text{fill:var(--mut);font-size:calc(14px*var(--bfs,1))}
.ii{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;border:1px solid var(--line2);
color:var(--mut);font:italic 600 11px/1 Georgia,serif;margin-left:7px;cursor:help;position:relative;vertical-align:2px;text-transform:none;letter-spacing:0}
.ii:hover{color:var(--tx);border-color:var(--mut)}
.ii:hover::after{content:attr(data-tip);position:absolute;left:50%;top:calc(100% + 7px);transform:translateX(-50%);width:max-content;max-width:320px;
white-space:normal;background:#1d2329;color:#fff;font:400 calc(14px*var(--bfs,1))/1.45 system-ui,-apple-system,Segoe UI,sans-serif;padding:8px 11px;
border-radius:8px;z-index:60;box-shadow:0 6px 20px rgba(0,0,0,.2);text-align:left}
"""

JS = r"""
const PAL=['#185FA5','#1D9E75','#7F77DD','#D85A30','#BA7517','#D4537E','#378ADD','#5DCAA5','#888780','#993C1D','#AFA9EC','#639922'];
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const NF=(d)=>new Intl.NumberFormat('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const eur=v=>v==null?'–':(v<0?'−€':'€')+NF(0).format(Math.abs(v));
const pct=(v,d=1,sign=true)=>v==null?'–':(sign&&v>0?'+':'')+NF(d).format(v*100)+'%';
const cls=v=>v==null?'':(v>=0?'pos':'neg');
const LV={decide:'Decide',read:'Read up',none:'Calm'};
const TH={broken:'broken',weakened:'weakened',intact:'intact',strengthened:'strengthened'};
const ii=t=>`<span class="ii" data-tip="${esc(t)}">i</span>`;
const ICON={'Earnings':'M4 19V9m5 10V5m5 14v-7m5 7V8','Ex-dividend':'M12 3v18m4-14H10a3 3 0 000 6h4a3 3 0 010 6H7','Dividend payment':'M12 3v18m4-14H10a3 3 0 000 6h4a3 3 0 010 6H7','Announced':'M4 5h16v11H8l-4 4z'};
const svgIco=p=>`<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${p}"/></svg>`;
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const fmtDate=s=>{if(!s)return '';const [y,m,d]=s.slice(0,10).split('-');return m?`${+d} ${MON[+m-1]}`:s};
const daysTo=s=>Math.round((new Date(s+'T12:00:00')-new Date(new Date().toISOString().slice(0,10)+'T12:00:00'))/864e5);

export default function(component){
 const {data,parentElement,setTriggerValue}=component;
 const D=data||{};
 let root=parentElement.querySelector('.fr');
 if(!root){root=document.createElement('div');root.className='fr';parentElement.appendChild(root)}
 const host=parentElement.host||parentElement;
 const lum=c=>{const m=String(c||'').match(/\d+(\.\d+)?/g);return m&&m.length>=3&&!(m.length>3&&+m[3]===0)?(+m[0]*.299+ +m[1]*.587+ +m[2]*.114):null};
 const app=document.querySelector('.stApp')||document.body;
 let L=lum(getComputedStyle(app).backgroundColor); if(L==null)L=lum(getComputedStyle(document.body).backgroundColor);
 if(L==null){const hx=(getComputedStyle(host).getPropertyValue('--st-background-color')||'').trim().match(/^#([0-9a-f]{6})$/i);if(hx){const n=parseInt(hx[1],16);L=((n>>16)&255)*.299+((n>>8)&255)*.587+(n&255)*.114}}
 root.classList.toggle('dark',L!=null&&L<110);
 const go=(page,t)=>setTriggerValue('open',{page,t:t||null,n:Date.now()});
 const K=D.kpi||{}; const C=K.counts||{decide:0,read:0,none:0};
 const known=new Set((D.positions||[]).map(p=>p.t));
 const PART=D.part||'full';

 // ---------- Kopf, Kennzahlen, Brief
 const T=K.theses||{}; const tt=(T.intact||0)+(T.strengthened||0)+(T.weakened||0)+(T.broken||0);
 const ne=K.next_earn, NW=K.news||{};
 let h='';
 if(PART!=='side'){
 h+=`<div class="top"><div><h1>${esc(D.name||'Portfolio')}</h1><div class="sub">As of ${esc(D.asof||'–')}${D.quotes_asof?' · quotes '+esc(fmtDate(D.quotes_asof)):''}</div></div>
 <label class="search"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
 <input id="q" placeholder="Ticker or command: GOOG · news · portfolio · brief" autocomplete="off"><kbd>Enter</kbd></label>
 <button class="btn" id="rf">${svgIco('M20 11a8 8 0 10-2.3 5.7M20 4v7h-7')} Refresh</button>
 <button class="btn pri" id="run">${svgIco('M7 4v16l13-8z')} Start analysis</button></div>`;

 h+=`<div class="grid">`;
 const seg=(n,c)=>tt?`<i style="width:${n/tt*100}%;background:${c};display:inline-block;height:100%"></i>`:'';
 h+=`<div class="kpi c3"><div class="l">${K.value!=null?'Portfolio value':'Model portfolio'}${ii('Current market value of your holdings in EUR, from your transactions and live quotes (Yahoo, refreshed every 15 minutes).')}</div><div class="v">${K.value!=null?eur(K.value):'weights only'}</div>
   <div class="s">today <span class="${cls(K.day_pct)}">${pct(K.day_pct,2)}</span>${K.day_eur!=null?` (<span class="${cls(K.day_eur)}">${(K.day_eur>0?'+':'')+eur(K.day_eur)}</span>)`:''} · live quotes</div></div>`;
 const OPEN=C.open??(C.decide+C.read);
 h+=`<div class="kpi c3 click" id="kact" style="cursor:pointer"><div class="l">Action needed${ii('Positions the Brief agent rated Decide or Read up that you have not yet marked as done or seen.')}</div><div class="v">${OPEN} <span style="font-size:calc(17px*var(--bfs,1));font-weight:500;color:${OPEN?'var(--dec)':'var(--mut)'}">open</span></div>
   <div class="s">${C.decide} decide · ${C.read} read up${C.handled?` · ${C.handled} done/seen`:''}</div></div>`;
 h+=`<div class="kpi c3"><div class="l">Thesis scorecard${ii('Each researched holding has 3–4 investment theses from the Annual Report agent; every Earnings Review rates them strengthened, intact, weakened or broken. A holding counts as intact if none of its theses is weakened or broken.')}</div><div class="v">${T.firms?`${T.firms_ok||0} / ${T.firms} <span style="font-size:calc(17px*var(--bfs,1));font-weight:500" class="mut">holdings intact</span>`:tt?`${(T.intact||0)+(T.strengthened||0)} / ${tt} <span style="font-size:calc(17px*var(--bfs,1));font-weight:500" class="mut">intact</span>`:'–'}</div>
   <div class="bar" style="display:flex;margin:6px 0 4px">${seg(T.strengthened||0,'#1D9E75')}${seg(T.intact||0,'#5DCAA5')}${seg(T.weakened||0,'#EF9F27')}${seg(T.broken||0,'#E24B4A')}</div>
   <div class="s" title="A holding counts as intact if none of its theses is weakened or broken.">${tt?`${(T.intact||0)+(T.strengthened||0)} of ${tt} theses intact · `:''}${T.weakened||0} weakened · ${T.broken||0} broken</div></div>`;
 h+=`<div class="kpi c3 ${ne?'click':''}" id="kne" style="${ne?'cursor:pointer':''}"><div class="l">Next earnings${ii('Next quarterly results date of your holdings from the Yahoo calendar; +n means more holdings report the same day.')}</div><div class="v">${ne?`<span class="tk" style="font-size:calc(25px*var(--bfs,1))">${esc(ne.t)}</span>${ne.more?` <span style="font-size:calc(17px*var(--bfs,1));font-weight:500" class="mut">+${ne.more}</span>`:''} <span style="font-size:calc(17px*var(--bfs,1));font-weight:500" class="mut">${fmtDate(ne.date)}</span>`:'–'}</div>
   <div class="s">${ne?(daysTo(ne.date)<=0?'today':'in '+daysTo(ne.date)+' days'):'no date in the calendar'}${K.events_week!=null?' · '+K.events_week+' events in 7 days':''}</div></div>`;

 if(D.brief_text_missing){h+=`<div class="c12" style="border:1px solid var(--line);border-left:3px solid #EF9F27;border-radius:0 12px 12px 0;padding:10px 14px" class="sm"><b>Brief text missing.</b> <span class="mut">The writing step of the Brief agent stopped during the last run. Ratings and triggers below are current; explanations and the summary follow with the next run.</span></div>`}
 if(D.headline||D.summary){h+=`<div class="brief c12"><div class="ico" style="background:var(--accbg);color:var(--acc)">${svgIco('M4 5h16v14H4zM8 9h8M8 13h5')}</div>
   <div class="grow"><b>${esc(D.headline)}</b><div class="sm mut" style="margin-top:2px">${esc(D.summary||'')}</div></div>
   <div style="display:flex;gap:8px;flex:none"><button class="btn" id="bpdf">${svgIco('M12 4v11M7 10l5 5 5-5M5 20h14')} PDF</button><button class="btn" id="bdoc">${svgIco('M9 12l2 2 4-4M4 5h16v14H4z')} With fact check</button></div></div>`}
 }

 // ---------- Handlungsbedarf + Termine
 if(PART==='full'){
 h+=`<div class="card c7"><div class="ch"><h3>Action needed</h3><span class="meta">rule-based from all agents · click opens research</span></div>`;
 if(!(D.actions||[]).length) h+=`<div class="empty">No position needs action.</div>`;
 (D.actions||[]).slice(0,6).forEach(a=>{h+=`<div class="row click" data-t="${esc(a.t)}"><span class="pill p-${a.level}" style="min-width:84px;text-align:center">${LV[a.level]}</span>
   <div class="grow"><div><span class="tk">${esc(a.t)}</span>${a.w!=null?` <span class="mut sm">· ${pct(a.w,1,false)}</span>`:''}</div>
   <div class="sm mut clamp" title="${esc(a.why)}">${esc(a.why)}</div>${a.next?`<div class="sm" style="margin-top:3px">→ ${esc(a.next)}</div>`:''}</div></div>`});
 h+=`</div>`;
 }
 if(PART!=='top'){
 h+=`<div class="${PART==='side'?'c12':'c5'} stack"><div class="card"><div class="ch"><h3>Calendar${ii('Earnings dates, ex-dividend and payment dates of your holdings from Yahoo (estimated dates are marked), plus events announced in the news.')}</h3><span class="meta">next 45 days</span></div>`;
 const ups=D.upcoming||[];
 if(!ups.length) h+=`<div class="empty">No dates in the Yahoo calendar. “Refresh” reloads.</div>`;
 ups.forEach(e=>{const dd=daysTo(e.date);h+=`<div class="row click" data-t="${esc(e.t)}"><div class="dt">${fmtDate(e.date)}</div><div class="ico">${svgIco(ICON[e.type]||ICON['Announced'])}</div>
   <div class="grow"><span class="tk">${esc(e.t)}</span> ${esc(e.type)}${e.detail==='estimated'?' <span class="mut sm">(estimated)</span>':''}</div><span class="sm mut">${dd<=0?'today':'in '+dd+' d'}</span></div>`});
 if((D.announced||[]).length){h+=`<div class="sm mut" style="margin:10px 0 2px">Announced in the news</div>`;
  D.announced.slice(0,3).forEach(e=>{h+=`<div class="row click" data-url="${esc(e.url)}"><div class="dt">${fmtDate(e.date)}</div><div class="grow sm"><span class="tk">${esc(e.t)}</span> ${esc(e.title)}</div></div>`})}
 h+=`</div>`;

 h+=`<div class="card"><div class="ch"><h3>Top headlines${ii('Most material headlines of the last 10 days as rated by the News Tracker; the number is the stock reaction vs. the index on day 0–1.')}</h3><span class="meta">${NW.notable!=null?`${NW.notable} material in 7 days · `:''}reaction day 0–1</span></div>`;
 if(!(D.news||[]).length) h+=`<div class="empty">No material headlines in the news store.</div>`;
 (D.news||[]).slice(0,5).forEach(n=>{const dc=n.dir==='positive'?'var(--pos)':n.dir==='negative'?'var(--neg)':'var(--faint)';
  h+=`<div class="row click" data-url="${esc(n.url)}"><div class="dt">${fmtDate(n.date)}</div><i style="width:7px;height:7px;border-radius:50%;background:${dc};margin-top:7px;flex:none"></i>
   <div class="grow"><div class="clamp"><span class="tk">${esc(n.t)}</span> ${esc((n.title||'').slice(0,150))}</div>${n.pub?`<div class="sm mut">${esc(n.pub)}</div>`:''}</div><span class="sm ${cls(n.car)}" style="white-space:nowrap">${n.car!=null?pct(n.car):''}</span></div>`});
 h+=`<div class="sm" style="color:var(--acc);cursor:pointer;margin-top:8px" id="allnews">All news →</div></div></div>`;
 }
 h+=`</div>`;
 const run=D.run;
 if(PART==='full')h+=`<div class="foot"><span>${run?`Last run ${esc(String(run.stamp||'').replace('_',' '))} · ${run.ok}/${run.steps} steps succeeded${run.cost!=null?' · $'+NF(2).format(run.cost):''}`:'No run yet'}${(D.gaps||[]).length?' · '+D.gaps.length+' data gaps':''}</span>
   <span>Sources: SEC EDGAR, Yahoo Finance, Finnhub · numbers fact-checked · not investment advice</span></div>`;
 root.innerHTML=h;

 // ---------- Interaktion
 const $=s=>root.querySelector(s), $$=s=>[...root.querySelectorAll(s)];
 $$('.row.click').forEach(r=>r.onclick=()=>{if(r.dataset.url){window.open(r.dataset.url,'_blank','noopener')}else if(r.dataset.t){go('research',r.dataset.t)}});
 if($('#run'))$('#run').onclick=()=>go('run'); if($('#rf'))$('#rf').onclick=()=>setTriggerValue('refresh',Date.now());
 if($('#kact'))$('#kact').onclick=()=>setTriggerValue('jump',Date.now());
 if($('#kne')&&ne) $('#kne').onclick=()=>go('research',ne.t);
 if($('#bpdf')) $('#bpdf').onclick=()=>setTriggerValue('pdf',Date.now());
 if($('#bdoc')) $('#bdoc').onclick=()=>setTriggerValue('doc',Date.now());
 if($('#allnews')) $('#allnews').onclick=()=>go('news');
 if($('#q'))$('#q').onkeydown=e=>{if(e.key!=='Enter')return;const v=e.target.value.trim();if(!v)return;const w=v.split(/\s+/);const t=w[0].toUpperCase();const cmd=(w[1]||w[0]).toLowerCase();
  if(known.has(t)&&w[1]&&cmd.startsWith('news')){go('news',t)}else if(known.has(t)){go('research',t)}
  else if(cmd.startsWith('news')){go('news')}else if(cmd.startsWith('port')){go('portfolio')}else if(cmd.startsWith('brief')){setTriggerValue('pdf',Date.now())}
  else if(cmd.startsWith('run')||cmd.startsWith('analy')){go('run')}else if(cmd.startsWith('proto')||cmd.startsWith('log')){go('log')}
  else{e.target.value='';e.target.placeholder=`“${v}” not in the portfolio – ticker or news, portfolio, brief`}};

 // ---------- Depotwert-Chart
 const S=D.series; const vc=$('#vc'), vtip=$('#vtip');
 function drawValue(r){
  [...vc.querySelectorAll('svg')].forEach(x=>x.remove());
  if(!S||!S.value){vc.insertAdjacentHTML('afterbegin','<div class="empty">No price history yet – run the Portfolio Manager.</div>');return}
  const dts=S.value.d, last=new Date(dts[dts.length-1]); let from=new Date(last);
  ({'1M':()=>from.setMonth(from.getMonth()-1),'3M':()=>from.setMonth(from.getMonth()-3),'6M':()=>from.setMonth(from.getMonth()-6),
    'YTD':()=>{from=new Date(last.getFullYear(),0,1)},'1J':()=>from.setFullYear(from.getFullYear()-1),'3J':()=>from.setFullYear(from.getFullYear()-3),'5J':()=>from.setFullYear(from.getFullYear()-5),'Max':()=>{from=new Date(dts[0])}})[r]();
  const fi=Math.max(0,dts.findIndex(d=>new Date(d)>=from)); const idx=[];for(let i=fi;i<dts.length;i++)if(S.value.v[i]!=null)idx.push(i);
  if(idx.length<2){vc.insertAdjacentHTML('afterbegin','<div class="empty">Too few data points for this period.</div>');return}
  const bmap=S.bench?Object.fromEntries(S.bench.d.map((d,i)=>[d,S.bench.v[i]])):{}; const imap=S.invested?Object.fromEntries(S.invested.d.map((d,i)=>[d,S.invested.v[i]])):{};
  let v=idx.map(i=>S.value.v[i]); let b=idx.map(i=>bmap[dts[i]]??null); const inv=idx.map(i=>imap[dts[i]]??null);
  if(S.kind==='index'){const v0=v[0];v=v.map(x=>x/v0*100)}
  if(S.kind==='index'||!S.invested){const b0=b.find(x=>x!=null);if(b0)b=b.map(x=>x==null?null:x/b0*v[0])}
  const W=Math.max(320,vc.clientWidth),H=270,pl=8,pr=58,pt=10,pb=24;
  const all=[...v,...b,...inv].filter(x=>x!=null); let lo=Math.min(...all),hi=Math.max(...all); const pad=(hi-lo)*.08||1; lo-=pad;hi+=pad;
  const X=i=>pl+i/(idx.length-1)*(W-pl-pr), Y=y=>pt+(1-(y-lo)/(hi-lo))*(H-pt-pb);
  const path=a=>a.map((y,i)=>y==null?'':`${i&&a[i-1]!=null?'L':'M'}${X(i).toFixed(1)},${Y(y).toFixed(1)}`).join('');
  const kind=S.kind==='eur'; const big=hi>=1e5;const fmt=y=>kind?(big?NF(0).format(y/1000)+' T€':NF(0).format(y)+' €'):NF(0).format(y);
  let grid='';for(let g=0;g<=4;g++){const y=lo+(hi-lo)*g/4;grid+=`<line x1="${pl}" x2="${W-pr}" y1="${Y(y)}" y2="${Y(y)}" stroke="var(--line)"/><text x="${W-pr+6}" y="${Y(y)+4}">${fmt(y)}</text>`}
  const nt=Math.min(6,idx.length);let xl='';for(let k=0;k<nt;k++){const i=Math.round(k*(idx.length-1)/(nt-1||1));const d=dts[idx[i]];xl+=`<text x="${X(i)}" y="${H-6}" text-anchor="${k===0?'start':k===nt-1?'end':'middle'}">${fmtDate(d)}${d.slice(2,4)}</text>`}
  const area=path(v)+`L${X(v.length-1)},${H-pb}L${X(0)},${H-pb}Z`;
  vc.insertAdjacentHTML('afterbegin',`<svg width="${W}" height="${H}" style="display:block">${grid}${xl}
   <path d="${area}" fill="var(--accbg)"/>${S.invested?`<path d="${path(inv)}" fill="none" stroke="#BA7517" stroke-width="1.4" stroke-dasharray="2 3"/>`:''}
   <path d="${path(b)}" fill="none" stroke="var(--faint)" stroke-width="1.5" stroke-dasharray="5 4"/><path d="${path(v)}" fill="none" stroke="var(--acc2)" stroke-width="2.2" stroke-linejoin="round"/>
   <line id="vx" y1="${pt}" y2="${H-pb}" stroke="var(--line2)" style="display:none"/><circle id="vd" r="4.5" fill="var(--acc2)" stroke="var(--bg)" stroke-width="2" style="display:none"/>
   <rect x="${pl}" y="0" width="${W-pl-pr}" height="${H}" fill="transparent" id="vh"/></svg>`);
  const chg=v[v.length-1]-v[0], dinv=(inv[inv.length-1]!=null&&inv[0]!=null)?inv[inv.length-1]-inv[0]:null;
  $('#vt').textContent=kind?'Depotwert':'Depotentwicklung (Start = 100)';
  $('#vs').innerHTML=`${kind?eur(v[v.length-1]):NF(1).format(v[v.length-1])} · <span class="${cls(chg)}">${chg>=0?'+':''}${kind?eur(chg):NF(1).format(chg)} (${pct(chg/v[0])})</span> im Zeitraum${dinv!=null&&Math.abs(dinv)>1?` · davon Netto-Einzahlungen ${eur(dinv)}`:''}`;
  const sv=vc.querySelector('svg'),vx=sv.querySelector('#vx'),vd=sv.querySelector('#vd');
  sv.querySelector('#vh').onmousemove=e=>{const bx=sv.getBoundingClientRect();const i=Math.max(0,Math.min(idx.length-1,Math.round((e.clientX-bx.left-pl)/(W-pl-pr)*(idx.length-1))));
   vx.setAttribute('x1',X(i));vx.setAttribute('x2',X(i));vx.style.display='';vd.setAttribute('cx',X(i));vd.setAttribute('cy',Y(v[i]));vd.style.display='';
   const d=dts[idx[i]];vtip.innerHTML=`<div class="mut">${d.slice(8,10)}.${d.slice(5,7)}.${d.slice(0,4)}</div><div><b>${kind?eur(v[i]):NF(1).format(v[i])}</b> portfolio</div>${b[i]!=null?`<div class="mut">${kind?eur(b[i]):NF(1).format(b[i])} Benchmark</div>`:''}${inv[i]!=null?`<div class="mut">${eur(inv[i])} invested</div>`:''}<div class="${cls(v[i]/v[0]-1)}">${pct(v[i]/v[0]-1)} since start</div>`;
   vtip.style.display='block';const tx=X(i)+14;vtip.style.left=(tx+vtip.offsetWidth>W?X(i)-vtip.offsetWidth-14:tx)+'px';vtip.style.top='12px'};
  sv.querySelector('#vh').onmouseleave=()=>{vx.style.display='none';vd.style.display='none';vtip.style.display='none'};
 }
 let range='1J'; $$('#rng button').forEach(bt=>bt.onclick=()=>{range=bt.dataset.r;$$('#rng button').forEach(x=>x.classList.toggle('on',x===bt));drawValue(range)});

 // ---------- Donut
 function drawDonut(){
  const A=(D.alloc||[]).filter(a=>a.v>0); const dn=$('#dn'); if(!A.length){dn.innerHTML='<div class="empty">Keine Gewichte.</div>';return}
  const tot=A.reduce((s,a)=>s+a.v,0), R=78, r=52, cx=90, cy=90; let a0=-Math.PI/2, arcs='';
  A.forEach((a,i)=>{const a1=a0+a.v/tot*2*Math.PI, big=a1-a0>Math.PI?1:0, p=(rr,t)=>[cx+rr*Math.cos(t),cy+rr*Math.sin(t)];
   const [x0,y0]=p(R,a0),[x1,y1]=p(R,a1),[x2,y2]=p(r,a1),[x3,y3]=p(r,a0);
   arcs+=`<path data-i="${i}" d="M${x0},${y0}A${R},${R} 0 ${big} 1 ${x1},${y1}L${x2},${y2}A${r},${r} 0 ${big} 0 ${x3},${y3}Z" fill="${PAL[i%PAL.length]}" stroke="var(--bg)" stroke-width="1.5" style="cursor:pointer;transition:opacity .12s"/>`;a0=a1});
  dn.innerHTML=`<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"><svg width="180" height="180" viewBox="0 0 180 180" style="flex:none">${arcs}
   <text id="dc1" x="90" y="86" text-anchor="middle" style="font-size:calc(16px*var(--bfs,1));fill:var(--mut)">Largest position</text><text id="dc2" x="90" y="106" text-anchor="middle" style="font-size:calc(20px*var(--bfs,1));font-weight:600;fill:var(--tx)"></text></svg>
   <div class="grow lgg" style="min-width:150px">${A.map((a,i)=>`<div class="lg" data-i="${i}" data-t="${esc(a.k)}"><span class="d" style="background:${PAL[i%PAL.length]}"></span><span class="tk grow">${esc(a.k)}</span><span>${pct(a.v,1,false)}</span></div>`).join('')}</div></div>`;
  const c1=dn.querySelector('#dc1'),c2=dn.querySelector('#dc2'); const reset=()=>{c1.textContent='Largest position';c2.textContent=`${A[0].k} ${pct(A[0].v,0,false)}`;dn.querySelectorAll('path').forEach(p=>p.style.opacity=1)};
  const hl=i=>{c1.textContent=A[i].k;c2.textContent=pct(A[i].v,1,false);dn.querySelectorAll('path').forEach(p=>p.style.opacity=(+p.dataset.i===i)?1:.35)};
  dn.querySelectorAll('path,.lg').forEach(el=>{el.onmouseenter=()=>hl(+el.dataset.i);el.onmouseleave=reset;el.onclick=()=>known.has(A[+el.dataset.i].k)&&go('research',A[+el.dataset.i].k)});reset();
 }

 // ---------- Treemap
 function squarify(items,x,y,w,h){const out=[];let row=[],rect={x,y,w,h};
  const worst=(rw,len)=>{const s=rw.reduce((a,b)=>a+b.a,0),mx=Math.max(...rw.map(q=>q.a)),mn=Math.min(...rw.map(q=>q.a));return Math.max(len*len*mx/(s*s),s*s/(len*len*mn))};
  const place=(rw,rc)=>{const s=rw.reduce((a,b)=>a+b.a,0);if(rc.w>=rc.h){const cw=s/rc.h;let yy=rc.y;rw.forEach(q=>{const hh=q.a/cw;out.push({...q,rx:rc.x,ry:yy,rw:cw,rh:hh});yy+=hh});return{x:rc.x+cw,y:rc.y,w:rc.w-cw,h:rc.h}}
   const rh=s/rc.w;let xx=rc.x;rw.forEach(q=>{const ww=q.a/rh;out.push({...q,rx:xx,ry:rc.y,rw:ww,rh:rh});xx+=ww});return{x:rc.x,y:rc.y+rh,w:rc.w,h:rc.h-rh}};
  let i=0;while(i<items.length){const len=Math.min(rect.w,rect.h),it=items[i];if(!row.length||worst([...row,it],len)<=worst(row,len)){row.push(it);i++}else{rect=place(row,rect);row=[]}}
  if(row.length)place(row,rect);return out}
 const tm=$('#tm'), ttip=$('#ttip'); let tmode='level';
 const divColor=(v,s)=>{if(v==null)return['var(--soft)','var(--mut)'];const k=Math.min(1,Math.abs(v)/s);const a=(.12+.5*k).toFixed(2);return v>=0?[`rgba(29,158,117,${a})`,k>.6?'#04342C':'var(--ok)']:[`rgba(226,75,74,${a})`,k>.6?'#501313':'var(--dec)']};
 // kleine Positionen (< 1 %) zu einer Kachel zusammenfassen, groesste zuerst (sonst entstehen beim Squarify schmale Streifen)
 function treeItems(src){const P=(src||[]).filter(p=>p.w>0).sort((a,b)=>b.w-a.w);const tot=P.reduce((s,p)=>s+p.w,0);
  const big=P.filter(p=>p.w/tot>=.01),sm=P.filter(p=>p.w/tot<.01);
  if(sm.length<2)return P;return[...big,{t:'Other',others:sm,w:sm.reduce((s,p)=>s+p.w,0)}]}
 function drawTree(){
  const P=treeItems(D.positions); if(!P.length){tm.innerHTML='<div class="empty">No positions.</div>';return}
  const W=tm.clientWidth||600,H=300,tot=P.reduce((s,p)=>s+p.w,0); const rects=squarify(P.map(p=>({...p,a:p.w/tot*W*H})),0,0,W,H);
  tm.innerHTML=rects.map((q,i)=>{let bg,fg,sub;
   if(q.others){bg='var(--soft)';fg='var(--mut)';sub=q.others.length+' holdings < 1%'}
   else if(tmode==='level'){bg=q.level==='decide'?'var(--decbg)':q.level==='read'?'var(--rdbg)':'var(--okbg)';fg=q.level==='decide'?'var(--dec)':q.level==='read'?'var(--rd)':'var(--ok)';sub=q.thesis?'Thesis '+TH[q.thesis]:LV[q.level]}
   else if(tmode==='chg'){[bg,fg]=divColor(q.chg,.03);sub=q.chg==null?'no quote':pct(q.chg,2)}else{[bg,fg]=divColor(q.ret1y,.5);sub=q.ret1y==null?'–':pct(q.ret1y,0)+' 1Y'}
   const tiny=q.rw<40||q.rh<24,small=q.rw<72||q.rh<52;
   return `<div class="tile" data-i="${i}" style="left:${q.rx}px;top:${q.ry}px;width:${q.rw}px;height:${q.rh}px;background:${bg};color:${fg};${small?'padding:5px 6px':''}">
    ${tiny?'':`<div class="n tk" style="${small?'font-size:calc(14px*var(--bfs,1))':''}">${esc(q.others?'Other':q.t)}</div>`}${small?'':`<div class="x">${pct(q.w,1,false)}</div><div class="x">${esc(sub)}</div>`}</div>`}).join('');
  $('#tml').innerHTML=tmode==='level'?'<span><span class="pill p-decide">Decide</span></span><span><span class="pill p-read">Read up</span></span><span><span class="pill p-none">Calm</span></span>':
   `<span>Green = up, red = down · full intensity at ${tmode==='chg'?'±3%':'±50%'}</span>`;
  tm.querySelectorAll('.tile').forEach(el=>{const q=rects[+el.dataset.i];
   if(q.others){el.style.cursor='default';el.onmousemove=e=>{const card=tm.parentElement.getBoundingClientRect();
     ttip.innerHTML=`<div><b>${q.others.length} small positions</b> · together ${pct(q.w,1,false)}</div>`+q.others.map(o=>`<div><span class="tk">${esc(o.t)}</span> <span class="mut">${pct(o.w,1,false)}</span></div>`).join('');
     ttip.style.display='block';let lx=e.clientX-card.left+14;if(lx+ttip.offsetWidth>card.width)lx=e.clientX-card.left-ttip.offsetWidth-14;ttip.style.left=lx+'px';ttip.style.top=(e.clientY-card.top+14)+'px'};
    el.onmouseleave=()=>{ttip.style.display='none'};return}
   el.onclick=()=>go('research',q.t);
   el.onmousemove=e=>{const card=tm.parentElement.getBoundingClientRect();ttip.innerHTML=`<div><span class="tk">${esc(q.t)}</span> <span class="mut">${esc(q.name&&q.name!==q.t?q.name:'')}</span></div>
    <div>Weight ${pct(q.w,1,false)}${q.value!=null?' · '+eur(q.value):''}</div><div>${LV[q.level]}${q.thesis?' · thesis '+TH[q.thesis]:''}</div>
    <div class="mut">Today ${pct(q.chg,2)} · 1 year ${pct(q.ret1y,0)}${q.rc!=null?' · risk share '+pct(q.rc,1,false):''}</div>${q.sector?`<div class="mut">${esc(q.sector)}</div>`:''}`;
    ttip.style.display='block';let lx=e.clientX-card.left+14;if(lx+ttip.offsetWidth>card.width)lx=e.clientX-card.left-ttip.offsetWidth-14;ttip.style.left=lx+'px';ttip.style.top=(e.clientY-card.top+14)+'px'};
   el.onmouseleave=()=>{ttip.style.display='none'}});
 }
 $$('#tmode button').forEach(bt=>bt.onclick=()=>{tmode=bt.dataset.m;$$('#tmode button').forEach(x=>x.classList.toggle('on',x===bt));drawTree()});

 // ---------- Diversifikation
 function drawDiv(k){const L=(D.struct||{})[k]||[];const dv=$('#dv');if(!L.length){dv.innerHTML='<div class="empty">Keine Strukturdaten – Portfolio Manager laufen lassen.</div>';return}
  const mx=Math.max(...L.map(x=>x.v));dv.innerHTML=L.map((x,i)=>`<div style="margin:9px 0"><div style="display:flex;justify-content:space-between" class="sm"><span>${esc(x.k)}</span><span>${pct(x.v,1,false)}</span></div>
   <div class="bar" style="margin-top:4px"><i style="width:${x.v/mx*100}%;background:${x.k==='Sonstige'?'var(--line2)':PAL[i%PAL.length]}"></i></div></div>`).join('')+
   `<div class="sm mut" style="margin-top:12px">Effective ${K.eff_n!=null?NF(1).format(K.eff_n):'–'} positions · top 3 ${pct(K.top3,0,false)}</div><div class="sm mut" style="margin-top:4px">${L[0].v>.5?`More than half in ${esc(L[0].k)} – concentration risk.`:`Largest block: ${esc(L[0].k)} at ${pct(L[0].v,0,false)}.`}</div>`}
 $$('#dmode button').forEach(bt=>bt.onclick=()=>{$$('#dmode button').forEach(x=>x.classList.toggle('on',x===bt));drawDiv(bt.dataset.k)});

 if(root._ro)root._ro.disconnect();  // Charts liegen jetzt auf der Portfolio-Seite
}
"""

_home = st.components.v2.component("finrobot_home", css=CSS, js=JS)


def render_home(payload, key="home"):
    """Zeigt die Home-Seite; Rueckgabe hat .open ({page, t}) und .refresh als einmalige Trigger."""
    return _home(data=payload, key=key, on_open_change=lambda: None, on_refresh_change=lambda: None,
                 on_pdf_change=lambda: None, on_doc_change=lambda: None, on_jump_change=lambda: None)
