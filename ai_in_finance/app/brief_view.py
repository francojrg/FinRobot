"""
Brief-Seite der App (Streamlit components v2, Design wie Home): Weekly Brief mit allen neuen Meldungen je Position.
Die Brief-Texte kommen als HTML aus Python (escaped, Zahlen mit Faktencheck-Markierung und Quelle im Tooltip);
Meldungen und Storylines werden hier escaped.
"""
import streamlit as st

from company_view import COMMON_JS
from home_view import CSS as HOME_CSS
from lib.html_site import RICH_TIP_JS

CSS = HOME_CSS + r"""
.c2{grid-column:span 2}@media (max-width:1100px){.c2{grid-column:span 4}}@media (max-width:640px){.c2{grid-column:span 6}}
.txt p{margin:0 0 .45rem}.txt p:last-child{margin-bottom:0}
.num{border-radius:3px;padding:0 2px;position:relative;cursor:help}
.num.ok{background:rgba(29,158,117,.12);border-bottom:2px solid #1D9E75}.num.no{background:rgba(226,75,74,.12);border-bottom:2px solid #E24B4A}
.num.un{background:var(--soft)}.num.ctx{background:rgba(239,159,39,.16);border-bottom:2px dashed #BA7517}
.jt .num[data-tip]:hover::after,.jt .num[data-tip]:focus::after{display:none}
.rtip{position:fixed;z-index:9999;max-width:460px;background:#1d2329;color:#fff;font-size:calc(15.5px*var(--bfs,1));line-height:1.5;padding:9px 11px;
 border-radius:9px;box-shadow:0 8px 24px rgba(0,0,0,.22);pointer-events:none;display:none;font-weight:400}
.rtip .h{font-weight:600;margin-bottom:4px}.rtip .q{color:#d9dee3}.rtip mark{background:#F5C451;color:#1d2329;border-radius:3px;padding:0 2px}
.rtip u{text-decoration-color:#7FC8A9;text-underline-offset:2px}.rtip .f{color:#9aa4ad;font-size:calc(14.5px*var(--bfs,1));margin-top:5px}
.num[data-tip]:hover::after,.num[data-tip]:focus::after{content:attr(data-tip);position:absolute;left:0;top:calc(100% + 6px);z-index:30;
 width:max-content;max-width:400px;white-space:pre-line;background:#1d2329;color:#fff;font-size:calc(15px*var(--bfs,1));line-height:1.45;padding:8px 10px;
 border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,.18);pointer-events:none;font-weight:400}
.num.tr[data-tip]:hover::after,.num.tr[data-tip]:focus::after{left:auto;right:0}
.pcard{border:1px solid var(--line);border-radius:14px;padding:16px 18px;display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:22px}
@media (max-width:1000px){.pcard{grid-template-columns:1fr}}
.pcard.decide{border-left:3px solid #E24B4A;border-radius:0 14px 14px 0}.pcard.read{border-left:3px solid #EF9F27;border-radius:0 14px 14px 0}
.lab{font-size:calc(14.5px*var(--bfs,1));color:var(--mut);text-transform:none;margin:8px 0 2px;font-weight:600;letter-spacing:.01em}
.qc{font-size:calc(14px*var(--bfs,1));padding:2px 7px;border-radius:6px;white-space:nowrap;display:inline-block;margin:0 4px 4px 0}
.s-strengthened{background:rgba(29,158,117,.22);color:var(--ok)}.s-intact{background:var(--okbg);color:var(--ok)}
.s-weakened{background:var(--rdbg);color:var(--rd)}.s-broken{background:var(--decbg);color:var(--dec)}
.st-escalating{background:var(--decbg);color:var(--dec)}.st-developing{background:var(--rdbg);color:var(--rd)}.st-new{background:var(--accbg);color:var(--acc)}
.nrow{display:flex;gap:10px;align-items:flex-start;padding:7px 4px;border-top:1px solid var(--line);border-radius:6px;cursor:pointer;font-size:calc(16px*var(--bfs,1))}
.nrow:first-child{border-top:0}.nrow:hover{background:var(--hov)}
.ov .pcard{grid-template-columns:1fr;gap:0;padding:12px 16px}.ov .pcard.open{grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:22px}
@media (max-width:1000px){.ov .pcard.open{grid-template-columns:1fr}}
.phd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;cursor:pointer}.phd .chev{margin-left:auto;color:var(--mut);transition:transform .15s}
.pcard.open .phd .chev{transform:rotate(180deg)}.pcard.handled{opacity:.62}.pcard.handled:hover{opacity:.9}
.acts{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:12px;padding-top:10px;border-top:1px solid var(--line)}
.acts .btn{height:30px;font-size:calc(15.5px*var(--bfs,1));padding:0 11px}.acts input{height:30px;border:1px solid var(--line2);border-radius:8px;
 background:var(--bg);color:var(--tx);font:inherit;font-size:calc(15.5px*var(--bfs,1));padding:0 10px;min-width:200px;flex:1;max-width:340px}
.badge{font-size:calc(14.5px*var(--bfs,1));padding:2px 8px;border-radius:6px;background:var(--soft);color:var(--mut)}
.badge.done{background:var(--okbg);color:var(--ok)}
.lnk{color:var(--acc);cursor:pointer;font-size:calc(15.5px*var(--bfs,1))}
.tgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
.tl{border:1px solid var(--line);border-radius:12px;padding:10px 12px;cursor:pointer;background:var(--bg);transition:border-color .12s,box-shadow .12s}
.tl:hover{border-color:var(--line2)}.tl.decide{border-top:3px solid #E24B4A}.tl.read{border-top:3px solid #EF9F27}
.tl.on{box-shadow:0 0 0 2px #378ADD}.tl.handled{opacity:.55}.tl.handled:hover{opacity:.85}
.tlh{display:flex;justify-content:space-between;align-items:center;gap:6px}.tl i.dt{flex:none;width:9px!important;min-width:0;height:9px;border-radius:50%;display:inline-block;padding:0;margin:0}
.detail{margin-top:12px}
details.more{border:1px solid var(--line);border-radius:14px;padding:12px 16px}details.more summary{cursor:pointer;font-weight:600;font-size:calc(17px*var(--bfs,1))}
"""

JS = COMMON_JS + r"""
export default function(component){
 const {data,parentElement,setTriggerValue}=component; const D=data||{}; const root=mount(parentElement); darkMode(root,parentElement);
 const K=D.kpi||{};
 const ST={escalating:'escalating',developing:'developing',new:'new'};
 const OV=D.mode==='overview';
 let h='';
 if(!OV){h+=`<div class="top"><div><h1>Weekly Brief</h1><div class="sub">As of ${esc(fmtDate(D.date))} · portfolio snapshot ${esc(fmtDate(D.sources.snapshot))} · news ${esc(fmtDate(D.sources.news))} · headlines of the last ${D.news_days} days</div></div>
  <div style="flex:1"></div><button class="btn" id="doc">${svgIco('M4 5h16v14H4zM8 9h8M8 13h5')} As document with fact check</button></div><div class="grid">`;
 const k=(l,v,s,c='')=>`<div class="kpi sm c2"><div class="l">${l}</div><div class="v ${c}">${v}</div><div class="s">${s}</div></div>`;
 h+=k('Decide',K.decide,'positions','neg')+k('Read up',K.read,'positions')+k('Calm',K.none,'no trigger','pos')
  +k('New headlines',K.news,`material, ${D.news_days} days`)
  +k('Fact check',K.fc_t?`${K.fc_m}/${K.fc_t}`:'–',K.fc_orig_t&&K.fc_orig_m!==K.fc_m?`first draft ${K.fc_orig_m}/${K.fc_orig_t}`:'numbers found in the sources')
  +k('Data gaps',(D.gaps||[]).length,(D.gaps||[]).length?'listed below':'none');
 h+=`<div class="card c12"><div style="font-size:calc(21px*var(--bfs,1));font-weight:600;line-height:1.35" class="txt">${D.headline||''}</div><div class="txt mut" style="margin-top:8px">${D.summary||''}</div>
  <div class="sm mut" style="margin-top:10px">Numbers marked green appear in the agents' inputs – hover to see source and passage.</div></div>`;}
 else{h+=`<div class="ov"><div class="grid">`}
 h+=`<div class="c12" style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap"><h3 style="margin:6px 0 0;font-size:calc(19px*var(--bfs,1));font-weight:600">${OV?'Action needed'+ii('Rules of the Brief agent rate every position: Decide (e.g. a thesis broke or a big weight with weakening theses), Read up (e.g. weakened thesis, analyst revisions, unusual news) or Calm. Click a tile for what happened, why it matters and the next step; mark it Done, Seen or Hidden with a note the agents read next time.'):'Positions'}</h3>
  ${OV?`<div style="display:flex;gap:12px;align-items:center"><span class="lnk" id="shid"></span><div class="seg" id="lf"><button data-l="act" class="on">Action needed</button><button data-l="none">Calm</button><button data-l="all">All</button></div></div>`
   :`<div class="seg" id="lf"><button data-l="all" class="on">All</button><button data-l="decide">Decide</button><button data-l="read">Read up</button><button data-l="none">Calm</button></div>`}</div>
  <div class="c12 stack" id="pl"></div>`;
 if(OV){h+=`<div class="c12"><details class="more"><summary>Portfolio as a whole and data gaps</summary><div class="grid" style="margin-top:12px">`}
 if((D.portfolio||[]).length||D.portfolio_note||D.no_action){h+=`<div class="card c7"><div class="ch"><h3>Portfolio as a whole</h3></div>${D.portfolio_note?`<div class="txt sm">${D.portfolio_note}</div>`:''}
  ${(D.portfolio||[]).map(x=>`<div class="row" style="padding:8px 0"><span class="pill p-${esc(x.level)}" style="min-width:84px;text-align:center">${LV[x.level]||esc(x.level)}</span><div class="grow sm">${esc(x.text)}</div></div>`).join('')}
  ${D.no_action?`<div class="lab">No action needed</div><div class="txt sm mut">${D.no_action}</div>`:''}</div>`}
 h+=`<div class="card ${(D.portfolio||[]).length||D.portfolio_note||D.no_action?'c5':'c12'}"><div class="ch"><h3>Data gaps</h3><span class="meta">what the agents were missing</span></div>
  ${(D.gaps||[]).length?D.gaps.map(g=>`<div class="row" style="padding:7px 0"><div class="grow sm">${esc(g)}</div></div>`).join(''):'<div class="empty">No data gaps.</div>'}</div>`;
 if(OV){h+=`</div></details></div></div>`}
 h+=`</div>`;
 root.innerHTML=h;
 const $=s=>root.querySelector(s),$$=s=>[...root.querySelectorAll(s)];
 if($('#doc'))$('#doc').onclick=()=>setTriggerValue('doc',Date.now());
 let lf=OV?'act':'all', showHid=false; const opened=new Set();
 let sel=globalThis.__blumSel||null;   // Ueberblick: ausgewaehlte Kachel, deren Details unter den Kacheln stehen
 const DOT={strengthened:'#1D9E75',intact:'#5DCAA5',weakened:'#EF9F27',broken:'#E24B4A'};
 const tile=p=>{const a=p.act;const trig=(p.triggers||[])[0]?.text||'';const th=p.theses||[];
  return `<div class="tl ${esc(p.level)} ${a?'handled':''} ${p.t===sel?'on':''}" data-sel="${esc(p.t)}">
   <div class="tlh"><span class="tk" style="font-size:calc(19px*var(--bfs,1))">${esc(p.t)}</span>${a?`<span class="badge ${a.state==='done'?'done':''}">${ACT[a.state]}</span>`:`<span class="pill p-${esc(p.level)}">${LV[p.level]||esc(p.level)}</span>`}</div>
   <div class="sm mut" style="margin-top:2px">${p.w!=null?pct(p.w,1,false):''}${p.chg!=null?` · today <span class="${cls(p.chg)}">${pct(p.chg,2)}</span>`:''}</div>
   <div class="sm clamp" style="margin-top:6px;min-height:2.7em">${esc(a&&a.note?'Note: '+a.note:trig)}</div>
   <div class="sm mut" style="margin-top:6px;display:flex;align-items:center;gap:3px">${th.map(x=>`<i class="dt" style="background:${DOT[x.status]||'var(--line2)'}" title="${esc(x.thesis||'')}: ${esc(TH[x.status]||x.status)}"></i>`).join('')}<span style="margin-left:${th.length?6:0}px">${p.n_news||0} news</span></div></div>`};
 const ACT={done:'done',seen:'seen',hidden:'hidden'};
 function draw(){const nHid=(D.positions||[]).filter(p=>p.act&&p.act.state==='hidden').length;
  if($('#shid'))$('#shid').textContent=nHid?(showHid?`hide ${nHid} hidden`:`${nHid} hidden · show`):'';
  const P=(D.positions||[]).filter(p=>(lf==='all'||(lf==='act'?p.level!=='none':p.level===lf))&&(!OV||showHid||!(p.act&&p.act.state==='hidden')));
  if(OV){opened.clear();if(sel)opened.add(sel)}
  const cards=L=>L.map(p=>{const op=!OV||opened.has(p.t); const a=p.act;
   const hd=`<div class="phd" data-tog="${esc(p.t)}"><span class="tk" style="font-size:calc(19px*var(--bfs,1));cursor:pointer" data-t="${esc(p.t)}">${esc(p.t)}</span><span class="mut sm">${esc(p.name||'')}</span>
    <span class="pill p-${esc(p.level)}">${LV[p.level]||esc(p.level)}</span><span class="sm mut">${p.w!=null?'Weight '+pct(p.w,1,false):''}</span>
    ${a?`<span class="badge ${a.state==='done'?'done':''}">${ACT[a.state]} ${esc(fmtDate(a.date))}${a.note?' · '+esc(a.note):''}</span>`:''}
    ${op?'':`<span class="sm mut clamp" style="flex:1;min-width:160px">${esc((p.triggers||[])[0]?.text||'')}</span>`}<span class="chev">▾</span></div>`;
   if(OV&&!op)return `<div class="pcard ${esc(p.level)} ${a?'handled':''}">${hd}</div>`;
   const acts=OV&&p.level!=='none'?`<div class="acts" data-a="${esc(p.t)}">${a?`<span class="sm mut">${ACT[a.state]} on ${esc(fmtDate(a.date))}</span><button class="btn" data-st="open">Undo</button>`
     :`<button class="btn" data-st="done">✓ Done</button><button class="btn" data-st="seen">◉ Seen</button><button class="btn" data-st="hidden">✕ Hide</button>`}
     <input placeholder="Note for you and the agents, e.g. holding on purpose" value="${esc(a&&a.note||'')}" maxlength="300"></div>`:'';
   return `<div class="pcard ${esc(p.level)} ${OV?'open':''} ${a?'handled':''}"><div>${OV?hd:''}
   <div style="display:${OV?'none':'flex'};align-items:center;gap:10px;flex-wrap:wrap"><span class="tk" style="font-size:calc(19px*var(--bfs,1));cursor:pointer" data-t="${esc(p.t)}">${esc(p.t)}</span><span class="mut sm">${esc(p.name||'')}</span>
    <span class="pill p-${esc(p.level)}">${LV[p.level]||esc(p.level)}</span><span class="sm mut">${p.w!=null?'Weight '+pct(p.w,1,false):''}${p.rc!=null?' · risk share '+pct(p.rc,1,false):''}${p.chg!=null?` · today <span class="${cls(p.chg)}">${pct(p.chg,2)}</span>`:''}</span></div>
   ${p.what?`<div class="lab">What happened</div><div class="txt sm">${p.what}</div>`:''}
   ${p.why?`<div class="lab">Why it matters</div><div class="txt sm">${p.why}</div>`:''}
   ${p.next?`<div class="lab">Next step</div><div class="txt sm">${p.next}</div>`:''}
   ${(p.triggers||[]).length?`<div class="lab">Triggers (rule-based)</div>${p.triggers.map(x=>`<div class="sm" style="margin:2px 0"><span class="pill p-${esc(x.level)}" style="font-size:calc(13.5px*var(--bfs,1))">${LV[x.level]||esc(x.level)}</span> ${esc(x.text)} <span class="mut" style="font-size:calc(14.5px*var(--bfs,1))">(${esc(x.source)})</span></div>`).join('')}`:(p.level==='none'?'<div class="sm mut" style="margin-top:8px">No rule triggered.</div>':'')}
   ${(p.theses||[]).length?`<div class="lab">Theses</div>${p.theses.map(x=>`<span class="qc s-${esc(x.status)}" title="${esc(x.thesis)}">${esc((x.thesis||'').split(':')[0])} ${esc(TH[x.status]||x.status)}</span>`).join('')}`:''}
   ${p.next_earnings?`<div class="sm mut" style="margin-top:6px">Next earnings: ${esc(fmtDate(p.next_earnings))}</div>`:''}
   ${acts}
  </div><div>
   <div class="lab" style="margin-top:0">New headlines (${p.n_news})</div>
   ${(p.stories||[]).length?`<div style="margin:2px 0 6px">${p.stories.map(s=>`<span class="qc st-${esc(s.status)}" title="since ${esc(s.since||'')}">${esc(ST[s.status]||s.status)}: ${esc(s.title)}</span>`).join('')}</div>`:''}
   ${(p.news||[]).length?p.news.map(n=>{const dc=n.dir==='positive'?'var(--pos)':n.dir==='negative'?'var(--neg)':'var(--faint)';return `<div class="nrow" data-url="${esc(n.url)}"><span class="mut" style="min-width:40px;font-size:calc(15px*var(--bfs,1))">${esc(fmtDate(n.date).slice(0,6))}</span><i style="width:7px;height:7px;border-radius:50%;background:${dc};margin-top:6px;flex:none"></i><div class="grow clamp">${esc(n.title)}</div><span class="${cls(n.car)}" style="font-size:calc(15px*var(--bfs,1));white-space:nowrap">${n.car!=null?pct(n.car):''}</span></div>`}).join(''):'<div class="sm mut">No material headlines.</div>'}
   ${p.n_news>6?`<div class="sm" style="margin-top:6px;color:var(--acc);cursor:pointer" data-news="${esc(p.t)}">All ${p.n_news} headlines on the News page</div>`:''}
  </div></div>`}).join('');
  const empty=`<div class="empty">${OV&&lf==='act'?'No open actions.':'No positions in this selection.'}</div>`;
  if(!OV)$('#pl').innerHTML=cards(P)||empty;
  else{const rk=p=>p.level==='decide'?0:p.level==='read'?1:2;
   const T=P.slice().sort((a,b)=>(!!a.act-!!b.act)||(rk(a)-rk(b))||((b.w||0)-(a.w||0)));
   if(sel&&!T.find(p=>p.t===sel))sel=null; const sp=T.find(p=>p.t===sel);
   $('#pl').innerHTML=T.length?`<div class="tgrid">${T.map(tile).join('')}</div>${sp?`<div class="detail">${cards([sp])}</div>`:'<div class="sm mut" style="margin-top:8px">Click a tile for details.</div>'}`:empty;
   $$('#pl .tl').forEach(e=>e.onclick=()=>{sel=globalThis.__blumSel=sel===e.dataset.sel?null:e.dataset.sel;draw()})}
  $$('#pl [data-tog]').forEach(e=>e.onclick=ev=>{if(ev.target.closest('[data-t]'))return;if(OV){sel=globalThis.__blumSel=null;draw();return}const t=e.dataset.tog;opened.has(t)?opened.delete(t):opened.add(t);draw()});
  $$('#pl .acts').forEach(box=>box.querySelectorAll('[data-st]').forEach(b=>b.onclick=()=>{const inp=box.querySelector('input');
   setTriggerValue('act',{t:box.dataset.a,state:b.dataset.st,note:inp?inp.value:'',n:Date.now()})}));
  $$('#pl [data-t]').forEach(e=>e.onclick=()=>setTriggerValue('open',{t:e.dataset.t,n:Date.now()}));
  $$('#pl .nrow').forEach(e=>e.onclick=()=>e.dataset.url&&window.open(e.dataset.url,'_blank','noopener'));
  $$('#pl [data-news]').forEach(e=>e.onclick=()=>setTriggerValue('news',Date.now()));
 }
 $$('#lf button').forEach(b=>b.onclick=()=>{lf=b.dataset.l;$$('#lf button').forEach(x=>x.classList.toggle('on',x===b));draw()});
 if($('#shid'))$('#shid').onclick=()=>{showHid=!showHid;draw()};
 draw();
 root.addEventListener('mouseover',e=>{const n=e.target.closest&&e.target.closest('.num[data-tip]');if(n)n.classList.toggle('tr',n.getBoundingClientRect().left>window.innerWidth*0.55)});
 (__RICH_TIP__)(root, root);
}
""".replace("__RICH_TIP__", RICH_TIP_JS)

_brief = st.components.v2.component("finrobot_brief", css=CSS, js=JS)


def render_brief(payload, key="brief"):
    return _brief(data=payload, key=key, on_open_change=lambda: None, on_doc_change=lambda: None,
                  on_news_change=lambda: None, on_act_change=lambda: None)
