"""
News-Seite der App (Streamlit components v2, Design wie Home): Wochenueberblick, Themen, Storylines, Signale je Titel
und ein filterbarer Meldungs-Feed. Nur Titel des aktuellen Portfolios. Alle Texte werden escaped.
"""
import streamlit as st

from company_view import COMMON_JS
from home_view import CSS as HOME_CSS

CSS = HOME_CSS + r"""
.c2{grid-column:span 2}@media (max-width:1100px){.c2{grid-column:span 4}}@media (max-width:640px){.c2{grid-column:span 6}}
.chipf{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:4px 10px;font-size:calc(15.5px*var(--bfs,1));cursor:pointer;background:var(--bg);color:var(--mut);margin:0 6px 6px 0}
.tbl tr.nb td{border-bottom:0;padding-bottom:2px}.tbl tr.flr td{padding-top:0;font-size:calc(15px*var(--bfs,1));white-space:normal;line-height:1.4}
.chipf.on{border-color:var(--acc2);color:var(--tx);background:var(--accbg)}
.pips{display:inline-flex;gap:2px;vertical-align:middle}.pips i{width:5px;height:12px;border-radius:2px;background:var(--line2)}.pips i.f{background:var(--acc2)}
.story{border:1px solid var(--line);border-radius:12px;padding:10px 12px;min-width:0}
.sgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
.st-escalating{background:var(--decbg);color:var(--dec)}.st-developing{background:var(--rdbg);color:var(--rd)}.st-new{background:var(--accbg);color:var(--acc)}.st-ongoing{background:var(--okbg);color:var(--ok)}.st-resolved,.st-fading{background:var(--soft);color:var(--mut)}
.tbl{width:100%;border-collapse:collapse;font-size:calc(16px*var(--bfs,1))}.tbl th{font-weight:500;color:var(--mut);text-align:right;padding:7px 6px;border-bottom:1px solid var(--line2);white-space:nowrap}
.tbl th:first-child,.tbl td:first-child{text-align:left}.tbl td{text-align:right;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
.tbl td.l{text-align:left;white-space:normal;color:var(--mut);font-size:calc(15.5px*var(--bfs,1))}
.feed .row{align-items:flex-start}
.tgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.tile{border:1px solid var(--line);border-radius:14px;padding:12px 14px;min-width:0;background:var(--bg)}
.tile .tt{font-weight:600;font-size:calc(17px*var(--bfs,1));line-height:1.35}.tile .tx{font-size:calc(15.5px*var(--bfs,1));color:var(--mut);margin:5px 0 7px;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.feed.side .row{gap:8px;padding:8px 2px}.feed.side .dt{min-width:42px!important;font-size:calc(15px*var(--bfs,1))}
.feed.side .search{max-width:none!important;width:100%;margin-top:8px}.feed.side .ch{display:block}
"""

JS = COMMON_JS + r"""
export default function(component){
 const {data,parentElement,setTriggerValue}=component; const D=data||{}; const root=mount(parentElement); darkMode(root,parentElement);
 const K=D.kpi||{}, G=D.digest;
 const ST={escalating:'escalating',developing:'developing',new:'new',ongoing:'ongoing',resolved:'resolved',fading:'fading'};
 const CAT={'earnings':'Earnings','guidance':'Guidance','m&a':'M&A','management':'Management','legal/regulatory':'Legal/regulatory','product/business':'Product/business','analyst rating':'Analysts','capital markets':'Capital markets','macro/sector':'Macro/sector','other':'Other'};
 const PART=D.part||'full';
 let h='';
 if(PART==='top'||PART==='full'){
  h+=`<div class="top"><div><h1>News</h1><div class="sub">${D.tickers.length} holdings · signals from ${esc(fmtDate(D.date))}${G?' · news digest from '+esc(fmtDate(G.date)):''}${K.notable!=null?` · ${K.notable} material headlines in 7 days (<span class="pos">${K.pos||0} positive</span>, <span class="neg">${K.neg||0} negative</span>)${K.escalating?`, <span class="neg">${K.escalating} storylines escalating</span>`:''}`:''}</div></div>
   <div style="flex:1"></div>${G?'<button class="btn" id="dg">'+svgIco('M4 5h16v14H4zM8 9h8M8 13h5')+' Open news digest</button>':''}</div>`;
  const RISK={concentration:'Concentration risk',opportunity:'Opportunity',contagion:'Contagion'};
  h+=`<div style="display:flex;align-items:baseline;gap:10px;margin:2px 0 10px"><h3 style="margin:0;font-size:calc(19px*var(--bfs,1));font-weight:600">Themes across holdings${ii('From the weekly news digest: topics that affect several of your positions at once (e.g. AI capex, rates, regulation), flagged as concentration risk, opportunity or contagion.')}</h3><span class="meta">where your portfolio depends on a common theme · click a ticker to open the company</span></div>
   <div class="tgrid">${(D.themes||[]).length?D.themes.map(t=>`<div class="tile"><div class="tt">${esc(t.theme)}${t.risk?` <span class="pill ${t.risk==='opportunity'?'p-none':'p-read'}" style="font-size:calc(14px*var(--bfs,1));vertical-align:1px">${esc(RISK[t.risk]||t.risk)}</span>`:''}</div>
    <div class="tx" title="${esc(t.explanation)}">${esc(t.explanation)}</div>${t.tickers.map(x=>`<span class="pill tf" data-t="${esc(x)}" style="background:var(--soft);color:var(--mut);margin:0 4px 3px 0;cursor:pointer">${esc(x)}</span>`).join('')}</div>`).join('')
    :'<div class="empty">No cross-holding themes in the latest news digest.</div>'}</div>`;
 }
 if(PART==='main'||PART==='full'){
  h+=`<div class="stack">`;
  if(G){h+=`<div class="card"><div class="ch"><h3>Week in review${ii('Written by the News Tracker agent once a week: headline, summary and one note per position, based on all classified headlines of the week. Numbers are fact-checked against the collected news.')}</h3><span class="meta">news digest ${esc(fmtDate(G.date))} · covers ${G.covers.map(esc).join(', ')||'–'}</span></div>
   <div style="font-weight:600;margin-bottom:6px">${esc(G.headline)}</div><div class="sm mut clamp" style="-webkit-line-clamp:5">${esc(G.summary)}</div>
   ${G.notes.length?`<div style="margin-top:10px">${G.notes.map(n=>`<div class="row" style="padding:8px 0"><span class="tk" style="min-width:64px">${esc(n.t)}</span><div class="grow sm">${esc(n.note)}</div></div>`).join('')}</div>`:''}
   ${G.market||G.analysts?`<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--line)">${G.market?`<div class="sm" style="font-weight:600;margin-bottom:2px">Market backdrop <span class="mut" style="font-weight:400">· what moved the overall market</span></div><div class="sm mut">${esc(G.market)}</div>`:''}${G.analysts?`<div class="sm" style="font-weight:600;margin:8px 0 2px">Analyst views <span class="mut" style="font-weight:400">· ratings and price targets on your holdings</span></div><div class="sm mut">${esc(G.analysts)}</div>`:''}</div>`:''}
   ${G.covers.length<D.tickers.length?`<div class="note" style="margin-top:10px;font-size:calc(15.5px*var(--bfs,1));color:var(--mut);background:var(--soft);border-radius:10px;padding:8px 10px">The latest digest does not cover all positions yet – the next run (“Start analysis”) will add them.</div>`:''}</div>`}
 // Signale (mit Storylines je Titel)
 const RK={escalating:0,developing:1,new:2,ongoing:3}, SB={};
 [...(D.stories||[])].sort((a,b)=>(RK[a.status]??4)-(RK[b.status]??4)).forEach(x=>(SB[x.t]=SB[x.t]||[]).push(x));
 h+=`<div class="card"><div class="ch"><div><h3>Signals and storylines per holding${ii('Per holding over the last week: number of material headlines, sentiment (positive minus negative), stock move vs. the MSCI ACWI, net analyst actions and running storylines (escalating first). Anomalies such as unusual volume are listed below each row.')}</h3><div class="meta">material headlines, sentiment (positive minus negative), stock vs. MSCI ACWI this week, net analyst actions, running stories (escalating first) · click opens the company</div></div></div>
  <div style="overflow-x:auto"><table class="tbl"><tr><th>Holding</th><th>Headlines</th><th>Sentiment</th><th>Stock vs. index</th><th>Analysts</th><th style="text-align:left">Storylines</th></tr>
  ${(D.signals||[]).map(s=>`<tr class="click ${(s.flags||[]).length?'nb':''}" data-t="${esc(s.t)}" style="cursor:pointer"><td><span class="tk">${esc(s.t)}</span></td><td>${s.n??'–'}</td><td class="${s.sent>0?'pos':s.sent<0?'neg':''}">${s.sent==null?'–':(s.sent>0?'+':'')+s.sent}</td><td class="${cls(s.ar)}">${pct(s.ar)}</td><td class="${cls(s.analyst)}">${s.analyst==null?'–':(s.analyst>0?'+':'')+NF(0).format(s.analyst)}</td><td class="l" style="min-width:220px">${(SB[s.t]||[]).slice(0,2).map(x=>`<span class="pill st-${esc(x.status)}" title="since ${esc(fmtDate(x.since))}" style="display:inline-block;margin:0 4px 3px 0">${esc(ST[x.status]||x.status)}: ${esc(String(x.title).slice(0,60))}</span>`).join('')||(s.stories?s.stories:'–')}</td></tr>${(s.flags||[]).length?`<tr class="click flr" data-t="${esc(s.t)}" style="cursor:pointer"><td></td><td colspan="5" class="l"><span class="mut">Notable:</span> ${s.flags.map(esc).join('; ')}</td></tr>`:''}`).join('')}</table></div></div>`;

 h+=`</div>`;
 }
 // Feed
 if(PART==='side'||PART==='full'){
 h+=`<div class="card feed ${PART==='side'?'side':''}"><div class="ch"><div><h3>Headlines${ii('All headlines on your holdings from Finnhub, Yahoo, Google News and SEC 8-K filings, de-duplicated. The News Tracker rates each for relevance, direction and materiality (1–3 dots); the number on the right is the stock reaction vs. the index on day 0–1.')}</h3><div class="meta" id="fm"></div></div>
  <label class="search" style="max-width:300px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg><input id="fq" placeholder="Search headlines" autocomplete="off"></label></div>
  <div id="ft">${['All',...D.tickers].map((t,i)=>`<span class="chipf ${i?'':'on'}" data-t="${esc(t)}">${esc(t)}</span>`).join('')}</div>
  <div style="margin:2px 0 8px"><span class="chipf on" data-d="all">All directions</span><span class="chipf" data-d="positive">Positive</span><span class="chipf" data-d="negative">Negative</span><span class="chipf" data-m="1">incl. noise</span></div>
  <div id="fl"></div><div style="text-align:center;margin-top:8px"><button class="btn" id="more" style="height:30px;font-size:calc(15px*var(--bfs,1))">Show more</button></div></div>`;
 }
 root.innerHTML=h;
 const $=s=>root.querySelector(s),$$=s=>[...root.querySelectorAll(s)];
 if($('#dg'))$('#dg').onclick=()=>setTriggerValue('digest',Date.now());
 $$('tr.click').forEach(r=>r.onclick=()=>setTriggerValue('open',{t:r.dataset.t,n:Date.now()}));

 $$('.tf').forEach(e=>e.onclick=()=>setTriggerValue('open',{t:e.dataset.t,n:Date.now()}));
 if(!$('#fl'))return;
 const SIDE=PART==='side';
 let ft='All', fd='all', noise=false, q='', lim=SIDE?15:25;
 function drawF(){const L=(D.items||[]).filter(x=>(ft==='All'||x.t===ft)&&(fd==='all'||x.dir===fd)&&(noise||x.mat>=2)&&(!q||x.title.toLowerCase().includes(q)));
  $('#fm').textContent=`${L.length} headlines${noise?'':' (materiality 2–3)'} · last 3 weeks`;
  $('#fl').innerHTML=L.slice(0,lim).map(x=>{const dc=x.dir==='positive'?'var(--pos)':x.dir==='negative'?'var(--neg)':'var(--faint)';
   return `<div class="row click" data-url="${esc(x.url)}"><div class="dt" style="min-width:58px">${esc(fmtDate(x.date).slice(0,6))}<div style="font-size:calc(14px*var(--bfs,1))">${esc(x.date.slice(11,16))}</div></div>
    <i style="width:7px;height:7px;border-radius:50%;background:${dc};margin-top:7px;flex:none"></i>
    <div class="grow" title="${SIDE?esc((x.pub||'')+(x.sum?' · '+x.sum.slice(0,240):'')):''}"><div><span class="tk">${esc(x.t)}</span> ${esc(x.title)}</div>${SIDE?(x.pub?`<div class="sm mut">${esc(x.pub)}</div>`:''):`<div class="sm mut"><b style="font-weight:600">${esc(x.pub)}</b>${x.cat?' · '+esc(CAT[x.cat]||x.cat):''}${x.sum?' · '+esc(x.sum.slice(0,160)):''}</div>`}</div>
    <div style="text-align:right;min-width:86px"><span class="pips" title="Materiality ${x.mat} of 3">${[1,2,3].map(i=>`<i class="${i<=x.mat?'f':''}"></i>`).join('')}</span><div class="sm ${cls(x.car)}">${x.car!=null?pct(x.car):''}</div></div></div>`}).join('')||'<div class="empty">No headlines in this selection.</div>';
  $('#more').style.display=L.length>lim?'':'none';
  $$('#fl .row.click').forEach(r=>r.onclick=()=>r.dataset.url&&window.open(r.dataset.url,'_blank','noopener'))}
 $$('#ft .chipf').forEach(c=>c.onclick=()=>{ft=c.dataset.t;$$('#ft .chipf').forEach(x=>x.classList.toggle('on',x===c));lim=25;drawF()});
 $$('[data-d]').forEach(c=>c.onclick=()=>{fd=c.dataset.d;$$('[data-d]').forEach(x=>x.classList.toggle('on',x===c));drawF()});
 $$('[data-m]').forEach(c=>c.onclick=()=>{noise=!noise;c.classList.toggle('on',noise);drawF()});
 $('#fq').oninput=e=>{q=e.target.value.trim().toLowerCase();drawF()}; $('#more').onclick=()=>{lim+=25;drawF()};
 drawF();
}
"""

_news = st.components.v2.component("finrobot_news", css=CSS, js=JS)


def render_news(payload, key="news"):
    return _news(data=payload, key=key, on_open_change=lambda: None, on_digest_change=lambda: None)
