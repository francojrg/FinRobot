"""
Portfolio-Detailseite der App (Streamlit components v2, Design wie Home): Performance, Positionen, Attribution,
Risiko, Optimierung mit Backtest, Entscheidungen und Kosten. Eigene SVG-Charts, keine externen Bibliotheken.
"""
import streamlit as st

from company_view import COMMON_JS
from home_view import CSS as HOME_CSS

CSS = HOME_CSS + r"""
.beta{display:inline-block;font-size:calc(13.5px*var(--bfs,1));font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:#B9770E;background:rgba(239,159,39,.15);border:1px solid rgba(239,159,39,.35);border-radius:6px;padding:0 6px;margin-left:8px;vertical-align:3px;cursor:help;line-height:17px}
.seg .beta{margin-left:5px;vertical-align:1px;font-size:calc(12.5px*var(--bfs,1));padding:0 4px;line-height:15px}
.nav{position:sticky;top:0;z-index:4;background:var(--bg);padding:8px 0;margin:0 0 6px;border-bottom:1px solid var(--line)}
.tbl{width:100%;border-collapse:collapse;font-size:calc(16px*var(--bfs,1))}
.tbl th{font-weight:500;color:var(--mut);text-align:right;padding:8px 7px;border-bottom:1px solid var(--line2);cursor:pointer;white-space:nowrap;user-select:none}
.tbl th:first-child,.tbl td:first-child{text-align:left}.tbl th:hover{color:var(--tx)}
.tbl td{text-align:right;padding:8px 7px;border-bottom:1px solid var(--line);white-space:nowrap}
.tbl tr.click:hover td{background:var(--hov);cursor:pointer}
.tbl th.on{color:var(--tx)}
.scroll{overflow-x:auto}
#txtab th:nth-child(2),#txtab th:nth-child(3),#txtab td:nth-child(2),#txtab td:nth-child(3){text-align:left}
.hb{display:flex;align-items:center;gap:10px;margin:6px 0;font-size:calc(16px*var(--bfs,1))}
.hb .lab{width:78px;flex:none}.hb .trk{flex:1;position:relative;height:16px}
.hb .mid{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--line2)}
.hb .v{width:120px;text-align:right;flex:none}
.sect{scroll-margin-top:60px}
.c2{grid-column:span 2}@media (max-width:1100px){.c2{grid-column:span 4}}@media (max-width:640px){.c2{grid-column:span 6}}
.lgg{grid-template-columns:repeat(auto-fill,minmax(118px,1fr))!important}
.note{font-size:calc(15.5px*var(--bfs,1));color:var(--mut);background:var(--soft);border-radius:10px;padding:10px 12px}
"""

JS = COMMON_JS + r"""
const PAL=['#185FA5','#1D9E75','#7F77DD','#D85A30','#BA7517','#D4537E','#378ADD','#888780'];
const eur=v=>v==null?'–':(v<0?'−€':'€')+NF(0).format(Math.abs(v));
const eurS=v=>v==null?'–':(v>0?'+€':v<0?'−€':'€')+NF(0).format(Math.abs(v));
const num=(v,d=2)=>v==null?'–':NF(d).format(v);

// Linienchart mit Zeitraum und Tooltip: series=[{name,d,v,color,dash}]; ret=[{name,d,v}] Indexreihen fuer die Rendite im Zeitraum
const RANGES=['1M','YTD','1Y','3Y','5Y','Max'];
function rangeFrom(r,first,last){const f=new Date(last);
 if(r==='1M')f.setMonth(f.getMonth()-1);else if(r==='YTD')return new Date(last.getFullYear()-1,11,31);
 else if(r==='1Y')f.setFullYear(f.getFullYear()-1);else if(r==='3Y')f.setFullYear(f.getFullYear()-3);
 else if(r==='5Y')f.setFullYear(f.getFullYear()-5);else return new Date(first);return f}
function lineChart(el,series,{fmt=v=>NF(0).format(v),H=260,norm=false,ranges=true,range0='Max',ret=null}={}){
 const wrap=document.createElement('div');el.appendChild(wrap);
 const base0=series[0]&&series[0].d||[];const first0=base0.length?new Date(base0[0]):null,last0=base0.length?new Date(base0[base0.length-1]):null;
 const avail=r=>r==='Max'||!first0||rangeFrom(r,first0,last0)>=new Date(first0.getTime()-10*864e5);
 let range=avail(range0)?range0:'Max';
 const segHtml=ranges?`<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:8px"><div class="seg">${RANGES.map(r=>`<button data-r="${r}" class="${r===range?'on':''}" ${avail(r)?'':'disabled title="Series shorter than this period" style="opacity:.35;cursor:default"'}>${r}</button>`).join('')}</div><div class="sm rr"></div></div>`:'';
 wrap.innerHTML=segHtml+`<div class="chart"><div class="tip"></div></div><div class="legend">${series.map(s=>`<span><i class="sw" style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}</div>`;
 const box=wrap.querySelector('.chart'),tip=wrap.querySelector('.tip'),rr=wrap.querySelector('.rr');
 function draw(){[...box.querySelectorAll('svg,.empty')].forEach(x=>x.remove());
  const base=series[0];if(!base||!base.d||base.d.length<2){box.insertAdjacentHTML('afterbegin','<div class="empty">No time series.</div>');return}
  const last=new Date(base.d[base.d.length-1]),from=rangeFrom(range,base.d[0],last);
  let i0=0;base.d.forEach((d,i)=>{if(new Date(d)<=from)i0=i});          // letzter Punkt bis zum Stichtag = Basis
  const dates=base.d.slice(i0);
  if(dates.length<2){box.insertAdjacentHTML('afterbegin','<div class="empty">Too few data points for this period.</div>');return}
  const S=series.map(s=>{const m=Object.fromEntries((s.d||[]).map((d,i)=>[d,s.v[i]]));let v=dates.map(d=>m[d]??null);
   if(norm){const f=v.find(x=>x!=null);if(f)v=v.map(x=>x==null?null:x/f*100)}return{...s,vv:v}});
  if(rr){const R=(ret||series.filter(s=>!s.noRet)).map(s=>{const m=Object.fromEntries((s.d||[]).map((d,i)=>[d,s.v[i]]));
     const v=dates.map(d=>m[d]).filter(x=>x!=null);return v.length>1?`${esc(s.name)} <b class="${cls(v[v.length-1]/v[0]-1)}">${pct(v[v.length-1]/v[0]-1)}</b>`:''}).filter(Boolean);
   rr.innerHTML=R.length?`<span class="mut">Return ${range==='Max'?'total':range}:</span> `+R.join(' <span class="mut">·</span> '):''}
  const W=Math.max(320,box.clientWidth),pl=8,pr=58,pt=10,pb=24;const all=S.flatMap(s=>s.vv).filter(x=>x!=null);
  let lo=Math.min(...all),hi=Math.max(...all);const pad=(hi-lo)*.08||1;lo-=pad;hi+=pad;
  const X=i=>pl+i/(dates.length-1)*(W-pl-pr),Y=y=>pt+(1-(y-lo)/(hi-lo))*(H-pt-pb);
  const path=a=>a.map((y,i)=>y==null?'':`${i&&a[i-1]!=null?'L':'M'}${X(i).toFixed(1)},${Y(y).toFixed(1)}`).join('');
  const short=(new Date(dates[dates.length-1])-new Date(dates[0]))<400*864e5;
  let g='';for(let k=0;k<=4;k++){const y=lo+(hi-lo)*k/4;g+=`<line x1="${pl}" x2="${W-pr}" y1="${Y(y)}" y2="${Y(y)}" stroke="var(--line)"/><text x="${W-pr+6}" y="${Y(y)+4}">${fmt(y)}</text>`}
  const nt=Math.min(6,dates.length);for(let k=0;k<nt;k++){const i=Math.round(k*(dates.length-1)/(nt-1||1));const d=dates[i];g+=`<text x="${X(i)}" y="${H-6}" text-anchor="${k===0?'start':k===nt-1?'end':'middle'}">${short?d.slice(8,10)+'.'+d.slice(5,7)+'.':d.slice(5,7)+'/'+d.slice(2,4)}</text>`}
  box.insertAdjacentHTML('afterbegin',`<svg width="${W}" height="${H}" style="display:block">${g}${S.slice().reverse().map(s=>`<path d="${path(s.vv)}" fill="none" stroke="${s.color}" stroke-width="${s.w||1.8}" ${s.dash?`stroke-dasharray="${s.dash}"`:''} stroke-linejoin="round"/>`).join('')}
   <line class="vx" y1="${pt}" y2="${H-pb}" stroke="var(--line2)" style="display:none"/><rect x="${pl}" y="0" width="${W-pl-pr}" height="${H}" fill="transparent" class="hv"/></svg>`);
  const sv=box.querySelector('svg'),vx=sv.querySelector('.vx');
  sv.querySelector('.hv').onmousemove=e=>{const bx=sv.getBoundingClientRect();const i=Math.max(0,Math.min(dates.length-1,Math.round((e.clientX-bx.left-pl)/(W-pl-pr)*(dates.length-1))));
   vx.setAttribute('x1',X(i));vx.setAttribute('x2',X(i));vx.style.display='';const d=dates[i];
   tip.innerHTML=`<div class="mut">${d.slice(8,10)}.${d.slice(5,7)}.${d.slice(0,4)}</div>`+S.map(s=>s.vv[i]!=null?`<div><i class="sw" style="background:${s.color}"></i>${esc(s.name)}: <b>${fmt(s.vv[i])}</b></div>`:'').join('');
   tip.style.display='block';const tx=X(i)+14;tip.style.left=(tx+tip.offsetWidth>W?X(i)-tip.offsetWidth-14:tx)+'px';tip.style.top='10px'};
  sv.querySelector('.hv').onmouseleave=()=>{vx.style.display='none';tip.style.display='none'}}
 wrap.querySelectorAll('.seg button:not([disabled])').forEach(b=>b.onclick=()=>{range=b.dataset.r;wrap.querySelectorAll('.seg button').forEach(x=>x.classList.toggle('on',x===b));draw()});
 draw(); return draw;
}

export default function(component){
 const {data,parentElement,setTriggerValue}=component; const D=data||{}; const root=mount(parentElement); darkMode(root,parentElement);
 const P=D.perf, tx=D.mode==='tx', S=D.stats||{};
 const per=Object.fromEntries((D.periods||[]).map(p=>[p.p,p]));
 const V=D.view||'full', DEP=V!=='analysis', ANA=V!=='depot';
 let h=`<div class="top"><div><h1>${esc(D.title)}</h1><div class="sub">As of ${esc(D.date||'–')} · ${tx?'from your transaction history':'from weights (no transactions, so no portfolio value in EUR)'}${ANA?` · position limit ${pct(D.cap,0,false)}, sector limit ${pct(D.sector_cap,0,false)}`:''}</div></div></div>
 <div class="nav"><div class="seg" id="nv">${(DEP&&!ANA?[['perf','Performance'],['alloc','Positions'],['pos','Table'],['txl','Transactions']]
    :!DEP?[['aperf','Performance'],['attr','Contributions'],['risk','Risk'],['opt','Optimisation<span class="beta">Beta</span>'],['dec','Decisions']]
    :[['perf','Performance'],['alloc','Allocation'],['pos','Table'],['attr','Contributions'],['risk','Risk'],['opt','Optimisation<span class="beta">Beta</span>'],['dec','Decisions'],['txl','Transactions']]).filter(([k])=>(k!=='attr'&&k!=='dec'&&k!=='txl')||(tx&&(k!=='txl'||(D.tx||[]).length))).map(([k,l],i)=>`<button data-s="${k}" class="${i?'':'on'}">${l}</button>`).join('')}</div></div>`;
 h+=`<div class="grid">`;
 const k=(l,v,s,c='')=>`<div class="kpi c2 sm"><div class="l">${l}</div><div class="v ${c}">${v}</div><div class="s">${s}</div></div>`;
 const POS=D.positions||[], dayP=POS.some(p=>p.chg!=null)?POS.reduce((s,p)=>s+(p.w||0)*(p.chg||0),0):null;
 if(DEP&&!ANA){const ytd=per['YTD']||{},y1=per['1 year']||{};
  const big=POS.filter(p=>p.w>0).sort((a,b)=>b.w-a.w), ur=POS.reduce((s,p)=>s+(p.unreal||0),0), co=POS.reduce((s,p)=>s+(p.unreal!=null?(p.cost||0):0),0);
  const kDay=k('Today',pct(dayP,2),tx&&dayP!=null?eurS(dayP*P.final_value):'weighted price move',cls(dayP));
  const kY=k('Year to date',pct(ytd.r),'benchmark '+pct(ytd.b),cls(ytd.r))+k('1 year',pct(y1.r),'benchmark '+pct(y1.b),cls(y1.r));
  h+=tx?k('Portfolio value'+ii('Market value of all holdings in EUR today; net invested = deposits minus withdrawals.'),eur(P.final_value),'net invested '+eur(P.net_invested))+kDay
       +k('Unrealised gain'+ii('Current value minus purchase cost of the shares you still hold.'),eurS(ur),co?pct(ur/co,1)+' on the cost of shares held':'positions held',cls(ur))
       +k('Total gain'+ii('Portfolio value minus net invested: unrealised gains plus realised gains from sales plus dividends, after fees.'),eurS(P.final_value-P.net_invested),'incl. sales and dividends',cls(P.final_value-P.net_invested))+kY
   :k('Positions',big.length,'largest '+(big[0]?esc(big[0].t)+' '+pct(big[0].w,0,false):'–'))+kDay+kY
       +k('Return p.a. ('+(D.years_hist||3)+' y)',pct(S.cagr),'benchmark '+pct(S.bench_cagr),cls(S.cagr))+k('Sharpe',num(S.sharpe),'risk-adjusted')}
 else{
 if(tx){h+=(DEP?k('Portfolio value',eur(P.final_value),'net invested '+eur(P.net_invested)):k('Excess return p.a.'+ii('Time-weighted return of your portfolio minus that of the MSCI ACWI per year.'),P.ttwror_pa!=null&&P.bench_tw_pa!=null?pct(P.ttwror_pa-P.bench_tw_pa):'–','time-weighted vs. benchmark',cls(P.ttwror_pa-P.bench_tw_pa)))+k('Return p.a. (time-weighted)'+ii('True time-weighted rate of return (TTWROR): investment performance independent of when you added or withdrew money.'),pct(P.ttwror_pa),'benchmark '+pct(P.bench_tw_pa),cls(P.ttwror_pa))
   +k('Personal return p.a.'+ii('Money-weighted return (IRR): your actual return including the timing of your deposits; the benchmark figure uses the same cash flows.'),pct(P.mwr),'money-weighted (IRR), bench '+pct(P.bench_mwr),cls(P.mwr))}
 else{h+=k('Year to date',pct((per['YTD']||{}).r),'benchmark '+pct((per['YTD']||{}).b),cls((per['YTD']||{}).r))+k('1 year',pct((per['1 year']||{}).r),'benchmark '+pct((per['1 year']||{}).b),cls((per['1 year']||{}).r))
   +k('Return p.a. ('+(D.years_hist||3)+' y)',pct(S.cagr),'benchmark '+pct(S.bench_cagr),cls(S.cagr))}
 h+=k('Sharpe · Sortino'+ii('Return per unit of risk: Sharpe uses total volatility, Sortino only downside volatility. Above 1 is good.'),num(S.sharpe)+' · '+num(S.sortino),'risk-adjusted')+k('Max drawdown'+ii('Largest peak-to-trough fall of the portfolio over the history window.'),pct(S.max_dd),'volatility '+pct(S.vol,0,false),'neg')+k('Beta · tracking error'+ii('Beta: how strongly the portfolio moves with the benchmark (1 = same). Tracking error: how much it deviates from it per year.'),num(S.beta)+' · '+pct(S.tracking_error,0,false),'Info Ratio '+num(S.info_ratio));}

 // Struktur
 const st=D.struct||{};
 const strHtml=`<div class="card" style="grid-column:span ${tx&&(D.attribution||[]).length?6:12}"><div class="ch"><h3>Structure${ii('Weights by sector, country and currency; the effective number of positions (1/HHI) shows how diversified the portfolio really is.')}</h3><div class="seg" id="sm">${['sector','country','currency'].filter(x=>st[x]).map((x,i)=>`<button data-k="${x}" class="${i?'':'on'}">${{sector:'Sector',country:'Country',currency:'Currency'}[x]}</button>`).join('')}</div></div><div id="sv"></div>
  <div class="sm mut" style="margin-top:10px">Effective ${num(st.effective_n,1)} positions · top 5 ${pct(st.top5,0,false)} · HHI ${num(st.hhi,3)}</div></div>`;

 // Performance
 const SIDE=ANA&&((D.years||[]).length||D.never_sold||!tx);
 h+=`<div class="card ${SIDE?'c8':'c12'} sect" id="s-${DEP?'perf':'aperf'}"><div class="ch"><div><h3>${!DEP?'Return vs. benchmark (start = 100)'+ii('Time-weighted performance of your portfolio vs. the MSCI ACWI in EUR, both indexed to 100 – deposits and withdrawals do not distort it.'):tx?'Portfolio value'+ii('Value of your portfolio in EUR, a benchmark that received the same deposits and withdrawals (MSCI ACWI), and your net invested capital.'):'Performance (start = 100)'}</h3><div class="meta">${!DEP?(tx?'time-weighted, i.e. without the effect of deposits and withdrawals':'price series of the current weights vs. the benchmark'):tx?'portfolio, benchmark with the same cash flows, net invested capital':'price series of the current weights vs. the benchmark'}</div></div></div><div id="pc"></div>
  <div class="chips">${(D.periods||[]).map(p=>`<div class="chip"><span class="mut">${esc({'YTD':'Year to date','1 year':'1 year','3 years':'3 years p.a.','5 years':'5 years p.a.','Since start':p.ann?'Since start p.a.':'Whole period'}[p.p]||p.p)}</span><b class="${cls(p.r)}">${pct(p.r)}</b><span class="mut">vs. ${pct(p.b)}${p.pl!=null?' · '+eurS(p.pl):''}</span></div>`).join('')}</div></div>`;
 if(SIDE){h+=`<div class="c4 stack">`;
 if((D.years||[]).length){h+=`<div class="card"><div class="ch"><h3>Calendar years</h3><span class="meta">portfolio vs. benchmark</span></div><div id="yc"></div></div>`}
 if(D.never_sold){const N=D.never_sold;const diff=N.value-N.actual_sec_value-N.proceeds_and_income;
  h+=`<div class="card"><div class="ch"><h3>What if you had never sold?${ii('Simulates keeping every share you ever bought (no sales) and compares that value with your actual holdings plus the cash from sales and income.')}</h3></div><div class="sm">Had you never sold, the portfolio would be worth <b>${eur(N.value)}</b> today, instead of ${eur(N.actual_sec_value)} plus ${eur(N.proceeds_and_income)} from sales and income.</div>
   <div class="sm ${cls(-diff)}" style="margin-top:8px">Sales have ${diff>0?'cost':'earned'} ${eur(Math.abs(diff))} · IRR ${pct(N.actual_mwr)} instead of ${pct(N.mwr)}</div></div>`}
 if(!tx){h+=strHtml.replace(/style="grid-column:span \d+"/,'');h+=`<div class="card"><div class="ch"><h3>More with transactions</h3></div><div class="sm mut">With a transaction file (e.g. sample_transactions.csv) this page also shows the portfolio value in EUR, calendar years, contributions per holding, your buy and sell decisions with their impact, and costs.</div></div>`}
 h+=`</div>`;

}
 // Positionskarte + Allokation
 if(DEP){ h+=`<div class="card c6 sect" id="s-alloc"><div class="ch"><div><h3>Positions${ii('Treemap of your holdings: area = weight. Colour by status from the Weekly Brief, by today’s move or by 1-year return. Positions below 1% are grouped as Other.')}</h3><div class="meta">area = weight · click opens the company</div></div>
   <div class="seg" id="tmode"><button data-m="level" class="on">Status</button><button data-m="chg">Today</button><button data-m="ret1y">1 year</button></div></div>
   <div class="tm" id="tm"></div><div class="legend" id="tml"></div><div class="tip" id="ttip"></div></div>
  <div class="card c6"><div class="ch"><h3>Allocation</h3><span class="meta">${(D.positions||[]).length} positions</span></div><div id="dn"></div></div>`;

 // Positionen
 var cols=tx?[['t','Holding'],['w','Weight'],['value','Value'],['cost','Cost'],['unreal','Unrealised'],['pl','Total gain'],['div','Dividends received'],['chg','Today'],['ret1y','1 year'],['sector','Sector'],['pe','Fwd P/E'],['upside','Upside']]:[['t','Holding'],['sector','Sector'],['w','Weight'],['value',tx?'Value':'Notional'],['chg','Today'],['ret1y','1 year'],['vol','Vol'],['rc','Risk share'],['pe','Fwd P/E'],['upside','Upside']].concat(tx?[['cost','Cost'],['pl','Total gain'],['div','Dividends'],['irr','IRR']]:[]);
 h+=`<div class="card c12 sect" id="s-pos"><div class="ch"><div><h3>All positions</h3><div class="meta">${tx?'Value = today’s value · Unrealised = value minus cost of shares held · Total gain = unrealised plus realised gains and dividends received · ':''}click a column header to sort · click a row to open the company</div></div></div><div class="scroll"><table class="tbl" id="pt"></table></div></div>`;

}
 // Beitraege
 if(ANA){
 if(tx&&(D.attribution||[]).length){h+=`<div class="card c6 sect" id="s-attr" style="grid-column:span 6"><div class="ch"><h3>Contributions, last 12 months${ii('Profit or loss per holding over the last 12 months in EUR, including realised gains and dividends.')}</h3><span class="meta">gain/loss per holding</span></div><div id="ab"></div>
   ${D.costs&&D.costs.n_trades!=null?`<div class="note" style="margin-top:12px">Costs (12 months): ${D.costs.n_trades} trades, turnover ${pct(D.costs.turnover,1,false)}, fees ${eur(D.costs.fees)}, taxes ${eur(D.costs.taxes)} · total result ${eurS(D.costs.total_pl)}</div>`:''}</div>`}
 if(tx)h+=strHtml;
 // Risiko
 const BS=D.bench_stats||{}; const bn=Object.keys(BS);
 const rk=[['cagr','Return p.a.',1],['vol','Volatility',0],['sharpe','Sharpe',-2],['sortino','Sortino',-2],['max_dd','Max drawdown',1],['var95_1d','VaR 95% (1 day)',1],['cvar95_1d','CVaR 95% (1 day)',1]];
 h+=`<div class="card c7 sect" id="s-risk"><div class="ch"><h3>Risk comparison${ii('Risk metrics of the current weights over the history window vs. benchmarks. VaR/CVaR: loss not exceeded on 95% of days / average loss on the worst 5% of days.')}</h3><span class="meta">${D.years_hist||3} years of history</span></div><div class="scroll"><table class="tbl"><tr><th>Metric</th><th>Portfolio</th>${bn.map(b=>`<th>${esc(b)}</th>`).join('')}</tr>
  ${rk.map(([key,l,d])=>`<tr><td>${l}</td><td><b>${d<0?num(S[key],-d):pct(S[key],d,key==='cagr')}</b></td>${bn.map(b=>`<td>${d<0?num(BS[b][key],-d):pct(BS[b][key],d,key==='cagr')}</td>`).join('')}</tr>`).join('')}</table></div></div>`;
 h+=`<div class="card c5"><div class="ch"><h3>Stress tests${ii('How the current portfolio would have done in historical stress periods (e.g. the 2022 rate shock), compared with the benchmark.')}<span class="beta" title="Beta: simplified model, results not yet validated">Beta</span></h3><span class="meta">historical periods</span></div>${(D.stress||[]).map(s=>`<div class="row" style="padding:9px 0"><div class="grow sm">${esc(s.scenario)}<div class="mut" style="font-size:calc(14.5px*var(--bfs,1))">${esc(s.from||'')} to ${esc(s.to||'')}</div></div><span class="sm ${cls(s.portfolio)}">${pct(s.portfolio)}</span><span class="sm mut" style="width:100px;text-align:right">Bench ${pct(s.benchmark)}</span></div>`).join('')||'<div class="empty">No stress tests.</div>'}
  <div class="sm mut" style="margin:12px 0 4px">Risk share vs. weight</div><div id="rcb"></div></div>`;

 // Optimierung
 const O=D.opt||[];
 h+=`<div class="card c12 sect" id="s-opt"><div class="ch"><div><h3>Optimisation${ii('Alternative weightings (minimum variance, max Sharpe, risk parity, equal weight) under a position limit, estimated from the price history; the backtest rebalances quarterly. A model view, not a trading recommendation.')}<span class="beta" title="Beta: simplified model, results not yet validated">Beta</span></h3><div class="meta">estimates from ${D.years_hist||3} years of history, position limit ${pct(D.cap,0,false)} · not a trading recommendation</div></div><div class="seg" id="os">${O.filter(o=>o.k!=='current').map((o,i)=>`<button data-k="${esc(o.name)}" class="${i?'':'on'}">${esc(o.name)}</button>`).join('')}</div></div>
  <div class="grid" style="gap:18px"><div class="c5"><div class="scroll"><table class="tbl"><tr><th>Strategy</th><th>Return</th><th>Vol</th><th>Sharpe</th><th>Turnover</th></tr>
  ${O.map(o=>`<tr><td>${o.k==='current'?'<b>'+esc(o.name)+'</b>':esc(o.name)}</td><td>${pct(o.exp_return)}</td><td>${pct(o.vol,0,false)}</td><td>${num(o.sharpe)}</td><td>${pct(o.turnover,0,false)}</td></tr>`).join('')}</table></div>
  <div class="sm mut" style="margin-top:12px">Weights: current (grey) vs. selected strategy (blue)</div><div id="ow"></div></div>
  <div class="c7"><div class="sm" style="font-weight:600;margin-bottom:4px">Backtest ${esc(D.bt.start||'')} to ${esc(D.bt.end||'')}</div><div id="btc"></div>
  <div class="scroll" style="margin-top:8px"><table class="tbl"><tr><th>Strategy</th><th>Return p.a.</th><th>Vol</th><th>Sharpe</th><th>Max DD</th></tr>
  ${(D.bt.stats||[]).map(s=>`<tr><td>${esc(s.name)}</td><td class="${cls(s.cagr)}">${pct(s.cagr)}</td><td>${pct(s.vol,0,false)}</td><td>${num(s.sharpe)}</td><td>${pct(s.max_dd)}</td></tr>`).join('')}</table></div></div></div></div>`;

 // Entscheidungen
 if(tx){const dec=(D.decisions||[]).slice().sort((a,b)=>(b.impact_eur||0)-(a.impact_eur||0));
  const row=x=>`<tr class="click" data-t="${esc(x.ticker)}"><td>${esc(fmtDate(x.date))}</td><td>${x.type==='buy'?'Buy':'Sell'} <span class="tk">${esc(x.ticker)}</span></td><td>${eur(x.eur)}</td><td class="${cls(x.ret_stock)}">${pct(x.ret_stock,0)} <span class="mut">/ ${pct(x.ret_bench,0)}</span></td><td class="${cls(x.excess)}">${pct(x.excess,0)}</td><td class="${cls(x.impact_eur)}"><b>${eurS(x.impact_eur)}</b></td></tr>`;
  const head='<tr><th>Date</th><th>Decision</th><th>Amount</th><th>Stock / bench since</th><th>Excess</th><th>Impact</th></tr>';
  h+=`<div class="card c7 sect" id="s-dec"><div class="ch"><div><h3>Your decisions${ii('Every buy and sell compared with the alternative of buying the benchmark instead: how the stock did since vs. the index, and the effect in EUR. Shows the best and the weakest decisions.')}</h3><div class="meta">every transaction vs. “bought the benchmark instead” · best and weakest</div></div></div>
   <div class="scroll"><table class="tbl">${head}${dec.slice(0,5).map(row).join('')}<tr><td colspan="6" class="mut" style="text-align:center">…</td></tr>${dec.slice(-4).map(row).join('')}</table></div></div>`;
  h+=`<div class="card c5"><div class="ch"><h3>Learning curve${ii('The decisions with the largest negative effect: buys that lagged the index, sales before a further rise.')}</h3><span class="meta">largest deviations</span></div>${(D.mistakes||[]).map(m=>`<div class="row" style="padding:9px 0"><div class="grow sm"><span class="tk">${esc(m.ticker)}</span> ${m.type==='buy'?'Buy':'Sell'} on ${esc(fmtDate(m.date))}<div class="mut">${esc(m.kind||'')}</div></div><span class="sm neg">${eurS(m.impact_eur)}</span></div>`).join('')||'<div class="empty">No notable mistakes.</div>'}
</div>`;
  if((D.warnings||[]).length)h+=`<div class="card c12"><details><summary style="cursor:pointer;font-weight:600">Notes on your data (${D.warnings.length}) <span class="sm mut" style="font-weight:400">· plausibility check of transactions and prices</span></summary>
   <ul class="sm" style="margin:10px 0 0 18px;padding:0;line-height:1.6">${D.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul></details></div>`}
}
 if(DEP&&tx&&(D.tx||[]).length){const yrs=[...new Set(D.tx.map(x=>x.date.slice(0,4)))].sort().reverse();
  h+=`<div class="card c12 sect" id="s-txl"><div class="ch"><div><h3>Transactions${ii('All bookings from your broker exports (buys, sells, dividends, deposits, fees, taxes), filterable by type, year and holding.')}</h3><div class="meta">all bookings from your exports · click a header to sort · click a row to open the company</div></div>
   <label class="search" style="max-width:300px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg><input id="txq" placeholder="Filter holdings, e.g. AMZN" autocomplete="off"></label></div>
   <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:8px"><div class="seg" id="txt">${[['all','All'],['trade','Buys & sells'],['buy','Buys'],['sell','Sells'],['inc','Dividends & interest'],['cash','Deposits/withdrawals'],['other','Other']].map(([k,l],i)=>`<button data-k="${k}" class="${i?'':'on'}">${l}</button>`).join('')}</div>
   <div class="seg" id="txy"><button data-y="all" class="on">All years</button>${yrs.map(y=>`<button data-y="${y}">${y}</button>`).join('')}</div></div>
   <div class="sm mut" id="txs" style="margin-bottom:6px"></div><div class="scroll"><table class="tbl" id="txtab"></table></div>
   <div style="text-align:center;margin-top:8px"><button class="btn" id="txmore" style="height:32px">Show more</button></div></div>`}
 h+=`</div>`;
 root.innerHTML=h;
 const $=s=>root.querySelector(s),$$=s=>[...root.querySelectorAll(s)];
 $$('#nv button').forEach(b=>b.onclick=()=>{$$('#nv button').forEach(x=>x.classList.toggle('on',x===b));const el=root.querySelector('#s-'+b.dataset.s);if(el)el.scrollIntoView({behavior:'smooth',block:'start'})});

 // Performance-Chart
 const SR=D.series; const draws=[];
 if(!DEP&&SR&&SR.twr&&SR.btwr){const ser=[{name:'Portfolio',d:SR.twr.d,v:SR.twr.v,color:'#378ADD',w:2.2},{name:'Benchmark',d:SR.btwr.d,v:SR.btwr.v,color:'#888780',dash:'5 4'}];
  draws.push(lineChart($('#pc'),ser,{fmt:v=>NF(0).format(v),norm:true,H:280,range0:'Max'}))}
 else if(SR&&SR.value){const ser=[{name:'Portfolio',d:SR.value.d,v:SR.value.v,color:'#378ADD',w:2.2}];
  if(SR.bench)ser.push({name:'Benchmark',d:SR.bench.d,v:SR.bench.v,color:'#888780',dash:'5 4'});if(SR.invested)ser.push({name:'Net invested',d:SR.invested.d,v:SR.invested.v,color:'#BA7517',dash:'2 3',w:1.4});
  const RET=SR.kind==='eur'?[SR.twr&&{name:'Portfolio',...SR.twr},SR.btwr&&{name:'Benchmark',...SR.btwr}].filter(Boolean):ser.filter(s=>s.name!=='Net invested');
  draws.push(lineChart($('#pc'),ser,{fmt:SR.kind==='eur'?(v=>'€'+NF(0).format(v/1000)+'k'):(v=>NF(0).format(v)),norm:SR.kind!=='eur',H:280,range0:'Max',ret:RET}))}
 else $('#pc').innerHTML='<div class="empty">No price history.</div>';

 // Kalenderjahre
 if($('#yc')){const Y=D.years;const mx=Math.max(.05,...Y.flatMap(y=>[Math.abs(y.r||0),Math.abs(y.b||0)]));
  $('#yc').innerHTML=Y.map(y=>`<div class="hb"><span class="lab">${esc(y.p)}</span><div class="trk"><div class="mid"></div>
   ${[[y.r,'#378ADD',0],[y.b,'var(--line2)',9]].map(([v,c,o])=>v==null?'':`<div style="position:absolute;top:${o}px;height:7px;border-radius:3px;background:${c};${v>=0?`left:50%;width:${v/mx*50}%`:`right:50%;width:${-v/mx*50}%`}"></div>`).join('')}</div>
   <span class="v"><b class="${cls(y.r)}">${pct(y.r)}</b> <span class="mut">${pct(y.b)}</span></span></div>`).join('')+'<div class="legend"><span><i class="sw" style="background:#378ADD"></i>Portfolio</span><span><i class="sw" style="background:var(--line2)"></i>Benchmark</span></div>'}

 // Positionstabelle
 let sortK='w',sortD=-1;
 function drawT(){const R=(D.positions||[]).slice().sort((a,b)=>{const x=a[sortK],y=b[sortK];if(x==null)return 1;if(y==null)return -1;return (typeof x==='string'?x.localeCompare(y):x-y)*sortD});
  const f={t:p=>`<span class="tk">${esc(p.t)}</span>${p.level&&p.level!=='none'?` <span class="pill p-${p.level}" style="font-size:calc(13.5px*var(--bfs,1))">${LV[p.level]}</span>`:''}`,sector:p=>`<span class="mut" style="display:inline-block;max-width:130px;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom" title="${esc(p.sector||'')}">${esc(p.sector||'–')}</span>`,
   w:p=>pct(p.w,1,false),value:p=>eur(p.value),chg:p=>`<span class="${cls(p.chg)}">${pct(p.chg,2)}</span>`,ret1y:p=>`<span class="${cls(p.ret1y)}">${pct(p.ret1y,0)}</span>`,vol:p=>pct(p.vol,0,false),
   rc:p=>`<span style="${p.rc!=null&&p.w&&p.rc>1.3*p.w?'color:var(--dec);font-weight:600':''}">${pct(p.rc,1,false)}</span>`,pe:p=>num(p.pe,1),upside:p=>`<span class="${cls(p.upside)}">${pct(p.upside,0)}</span>`,
   cost:p=>eur(p.cost),unreal:p=>p.unreal==null?'–':`<span class="${cls(p.unreal)}">${eurS(p.unreal)}</span>${p.cost?` <span class="mut">${pct(p.unreal/p.cost,0)}</span>`:''}`,pl:p=>`<span class="${cls(p.pl)}">${eurS(p.pl)}</span>`,div:p=>eur(p.div),irr:p=>`<span class="${cls(p.irr)}">${pct(p.irr,0)}</span>`};
  $('#pt').innerHTML=`<tr>${cols.map(([k,l])=>`<th data-k="${k}" class="${k===sortK?'on':''}">${l}${k===sortK?(sortD<0?' ↓':' ↑'):''}</th>`).join('')}</tr>`+R.map(p=>`<tr class="click" data-t="${esc(p.t)}">${cols.map(([k])=>`<td>${f[k](p)}</td>`).join('')}</tr>`).join('');
  $$('#pt th').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(k===sortK)sortD=-sortD;else{sortK=k;sortD=(k==='t'||k==='sector')?1:-1}drawT()});
  $$('#pt tr.click').forEach(r=>r.onclick=()=>setTriggerValue('open',{t:r.dataset.t,n:Date.now()}))}
 if($('#pt'))drawT();
 // Transaktionsliste
 if($('#txtab')){const TL={buy:'Buy',sell:'Sell',dividend:'Dividend',interest:'Interest',income:'Refund',deposit:'Deposit',withdrawal:'Withdrawal',fee:'Fee',tax:'Tax',
   transfer_in:'Transfer in',transfer_out:'Transfer out',deliver_in:'Delivery in',deliver_out:'Delivery out'};
  const GRP={trade:['buy','sell'],buy:['buy'],sell:['sell'],inc:['dividend','interest','income'],cash:['deposit','withdrawal']};
  const TC={buy:'var(--acc)',sell:'#BA7517',dividend:'var(--pos)',interest:'var(--pos)',income:'var(--pos)',deposit:'var(--mut)',withdrawal:'var(--mut)',fee:'var(--neg)',tax:'var(--neg)'};
  let tk='all',ty='all',tq='',lim=30,sk='date',sd=-1;
  const cur=(v,c)=>v==null?'–':NF(2).format(v)+(c&&c!=='EUR'?' '+esc(c):' €');
  const tcols=[['date','Date'],['type','Type'],['ticker','Holding'],['shares','Shares'],['price','Price'],['amount','Amount'],['fee','Fees'],['tax','Taxes']];
  function drawTx(){const known=Object.values(GRP).flat();
   let L=D.tx.filter(x=>(tk==='all'||(tk==='other'?!known.includes(x.type):GRP[tk].includes(x.type)))&&(ty==='all'||x.date.startsWith(ty))&&(!tq||(x.ticker+' '+(x.name||'')).toLowerCase().includes(tq)));
   L=L.slice().sort((a,b)=>{const x=a[sk],y=b[sk];if(x==null||x==='')return 1;if(y==null||y==='')return -1;return (typeof x==='string'?x.localeCompare(y):x-y)*sd});
   const sum=t=>L.filter(x=>t.includes(x.type)).reduce((s,x)=>s+(x.amount||0),0);
   const fees=L.reduce((s,x)=>s+(x.fee||0),0);
   $('#txs').innerHTML=`${L.length} bookings · buys ${eur(sum(['buy']))} · sells ${eur(sum(['sell']))} · dividends & interest ${eur(sum(['dividend','interest']))} · fees ${eur(fees)}`;
   $('#txtab').innerHTML=`<tr>${tcols.map(([k,l])=>`<th data-k="${k}" class="${k===sk?'on':''}">${l}${k===sk?(sd<0?' ↓':' ↑'):''}</th>`).join('')}</tr>`+
    L.slice(0,lim).map(x=>`<tr class="${x.ticker?'click':''}" data-t="${esc(x.ticker)}"><td>${esc(fmtDate(x.date))}</td>
     <td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${TC[x.type]||'var(--line2)'};margin-right:6px"></span>${esc(TL[x.type]||x.type)}</td>
     <td>${x.ticker?`<span class="tk">${esc(x.ticker)}</span>`:''}${x.name&&x.name!==x.ticker?` <span class="mut" style="display:inline-block;max-width:220px;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom">${esc(x.name)}</span>`:''}</td>
     <td>${x.shares!=null?NF(x.shares%1?3:0).format(x.shares):'–'}</td><td>${cur(x.price,x.currency)}</td>
     <td class="${x.type==='sell'||GRP.inc.includes(x.type)?'pos':''}">${cur(x.amount,x.currency)}</td><td>${x.fee?cur(x.fee,x.currency):'–'}</td><td>${x.tax?cur(x.tax,x.currency):'–'}</td></tr>`).join('')
    +(L.length?'':`<tr><td colspan="8" class="mut" style="text-align:center">No bookings in this selection.</td></tr>`);
   $('#txmore').style.display=L.length>lim?'':'none';
   $$('#txtab th').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(k===sk)sd=-sd;else{sk=k;sd=(k==='ticker'||k==='type')?1:-1}drawTx()});
   $$('#txtab tr.click').forEach(r=>r.onclick=()=>r.dataset.t&&setTriggerValue('open',{t:r.dataset.t,n:Date.now()}))}
  $$('#txt button').forEach(b=>b.onclick=()=>{tk=b.dataset.k;$$('#txt button').forEach(x=>x.classList.toggle('on',x===b));lim=30;drawTx()});
  $$('#txy button').forEach(b=>b.onclick=()=>{ty=b.dataset.y;$$('#txy button').forEach(x=>x.classList.toggle('on',x===b));lim=30;drawTx()});
  $('#txq').oninput=e=>{tq=e.target.value.trim().toLowerCase();lim=30;drawTx()};
  $('#txmore').onclick=()=>{lim+=100;drawTx()};
  drawTx()}
 $$('tr.click[data-t]').forEach(r=>{if(!r.closest('#pt'))r.onclick=()=>setTriggerValue('open',{t:r.dataset.t,n:Date.now()})});

 // ---------- Donut
 function drawDonut(){
  const A=(D.positions||[]).filter(p=>p.w>0).sort((a,b)=>b.w-a.w).map(p=>({k:p.t,v:p.w})); const dn=$('#dn'); if(!A.length){dn.innerHTML='<div class="empty">No weights.</div>';return}
  const tot=A.reduce((s,a)=>s+a.v,0), R=118, r=80, cx=125, cy=125; let a0=-Math.PI/2, arcs='';
  A.forEach((a,i)=>{const a1=a0+a.v/tot*2*Math.PI, big=a1-a0>Math.PI?1:0, p=(rr,t)=>[cx+rr*Math.cos(t),cy+rr*Math.sin(t)];
   const [x0,y0]=p(R,a0),[x1,y1]=p(R,a1),[x2,y2]=p(r,a1),[x3,y3]=p(r,a0);
   arcs+=`<path data-i="${i}" d="M${x0},${y0}A${R},${R} 0 ${big} 1 ${x1},${y1}L${x2},${y2}A${r},${r} 0 ${big} 0 ${x3},${y3}Z" fill="${PAL[i%PAL.length]}" stroke="var(--bg)" stroke-width="1.5" style="cursor:pointer;transition:opacity .12s"/>`;a0=a1});
  dn.innerHTML=`<div style="display:flex;gap:22px;align-items:center;flex-wrap:wrap;justify-content:center"><svg width="250" height="250" viewBox="0 0 250 250" style="flex:none;max-width:100%">${arcs}
   <text id="dc1" x="125" y="119" text-anchor="middle" style="font-size:calc(16px*var(--bfs,1));fill:var(--mut)">Largest position</text><text id="dc2" x="125" y="143" text-anchor="middle" style="font-size:calc(20px*var(--bfs,1));font-weight:600;fill:var(--tx)"></text></svg>
   <div class="grow lgg" style="min-width:220px">${A.map((a,i)=>`<div class="lg" data-i="${i}" data-t="${esc(a.k)}"><span class="d" style="background:${PAL[i%PAL.length]}"></span><span class="tk grow">${esc(a.k)}</span><span>${pct(a.v,1,false)}</span></div>`).join('')}</div></div>`;
  const c1=dn.querySelector('#dc1'),c2=dn.querySelector('#dc2'); const reset=()=>{c1.textContent='Largest position';c2.textContent=`${A[0].k} ${pct(A[0].v,0,false)}`;dn.querySelectorAll('path').forEach(p=>p.style.opacity=1)};
  const hl=i=>{c1.textContent=A[i].k;c2.textContent=pct(A[i].v,1,false);dn.querySelectorAll('path').forEach(p=>p.style.opacity=(+p.dataset.i===i)?1:.35)};
  dn.querySelectorAll('path,.lg').forEach(el=>{el.onmouseenter=()=>hl(+el.dataset.i);el.onmouseleave=reset;el.onclick=()=>setTriggerValue('open',{t:A[+el.dataset.i].k,n:Date.now()})});reset();
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
  const card=tm.parentElement,free=card.getBoundingClientRect().bottom-tm.getBoundingClientRect().top-($('#tml').offsetHeight||0)-26;
  const H=free>300?Math.min(Math.round(free),560):300; tm.style.height=H+'px';   // Kachelflaeche fuellt die Karte neben der Allokation
  const W=tm.clientWidth||600,tot=P.reduce((s,p)=>s+p.w,0); const rects=squarify(P.map(p=>({...p,a:p.w/tot*W*H})),0,0,W,H);
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
   el.onclick=()=>setTriggerValue('open',{t:q.t,n:Date.now()});
   el.onmousemove=e=>{const card=tm.parentElement.getBoundingClientRect();ttip.innerHTML=`<div><span class="tk">${esc(q.t)}</span> <span class="mut">${esc(q.name&&q.name!==q.t?q.name:'')}</span></div>
    <div>Weight ${pct(q.w,1,false)}${q.value!=null?' · '+eur(q.value):''}</div><div>${LV[q.level]}${q.thesis?' · thesis '+TH[q.thesis]:''}</div>
    <div class="mut">Today ${pct(q.chg,2)} · 1 year ${pct(q.ret1y,0)}${q.rc!=null?' · risk share '+pct(q.rc,1,false):''}</div>${q.sector?`<div class="mut">${esc(q.sector)}</div>`:''}`;
    ttip.style.display='block';let lx=e.clientX-card.left+14;if(lx+ttip.offsetWidth>card.width)lx=e.clientX-card.left-ttip.offsetWidth-14;ttip.style.left=lx+'px';ttip.style.top=(e.clientY-card.top+14)+'px'};
   el.onmouseleave=()=>{ttip.style.display='none'}});
 }
 $$('#tmode button').forEach(bt=>bt.onclick=()=>{tmode=bt.dataset.m;$$('#tmode button').forEach(x=>x.classList.toggle('on',x===bt));drawTree()});


 if(DEP){drawDonut(); drawTree(); draws.push(drawTree);}

 // Beitraege
 if($('#ab')){const A=(D.attribution||[]).slice().sort((a,b)=>b.pl_eur-a.pl_eur);const mx=Math.max(1,...A.map(a=>Math.abs(a.pl_eur)));
  $('#ab').innerHTML=A.map(a=>`<div class="hb"><span class="lab tk">${esc(a.ticker)}</span><div class="trk"><div class="mid"></div><div style="position:absolute;top:4px;height:8px;border-radius:3px;background:${a.pl_eur>=0?'#1D9E75':'#E24B4A'};${a.pl_eur>=0?`left:50%;width:${a.pl_eur/mx*50}%`:`right:50%;width:${-a.pl_eur/mx*50}%`}"></div></div><span class="v ${cls(a.pl_eur)}">${eurS(a.pl_eur)} <span class="mut">${pct(a.contribution,1)}</span></span></div>`).join('')}

 // Struktur
 function drawS(k){const L=Object.entries(st[k]||{}).sort((a,b)=>b[1]-a[1]);const mx=Math.max(...L.map(x=>x[1]),.01);
  $('#sv').innerHTML=L.map(([n,v],i)=>`<div style="margin:8px 0"><div style="display:flex;justify-content:space-between" class="sm"><span>${esc(n)}</span><span>${pct(v,1,false)}${k==='sector'&&D.sector_cap&&v>D.sector_cap?' <span class="pill p-read" style="font-size:calc(13.5px*var(--bfs,1))">above limit</span>':''}</span></div><div class="bar" style="margin-top:4px"><i style="width:${v/mx*100}%;background:${PAL[i%PAL.length]}"></i></div></div>`).join('')}
 const fk=['sector','country','currency'].find(x=>st[x]); if(fk&&$('#sv'))drawS(fk); $$('#sm button').forEach(b=>b.onclick=()=>{$$('#sm button').forEach(x=>x.classList.toggle('on',x===b));drawS(b.dataset.k)});

 // Risikoanteil
 const RC=(D.positions||[]).filter(p=>p.rc!=null).sort((a,b)=>b.rc-a.rc).slice(0,6);const rmx=Math.max(.01,...RC.map(p=>Math.max(p.rc,p.w||0)));
 if($('#rcb'))$('#rcb').innerHTML=RC.map(p=>`<div style="display:flex;align-items:center;gap:10px;margin:6px 0" class="sm"><span class="tk" style="width:84px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(p.t)}</span><div class="grow"><div class="bar" style="height:7px;margin-bottom:3px"><i style="width:${p.rc/rmx*100}%;background:${p.rc>1.3*(p.w||0)?'#E24B4A':'#378ADD'}"></i></div><div class="bar" style="height:4px"><i style="width:${(p.w||0)/rmx*100}%;background:var(--line2)"></i></div></div><span style="width:86px;text-align:right">${pct(p.rc,1,false)} <span class="mut">/ ${pct(p.w,0,false)}</span></span></div>`).join('');

 // Optimierung: Gewichte
 const OW=D.opt_w||{};const cur=OW['Current weights']||{};
 function drawW(name){const tw=OW[name]||{};const T=Object.keys(cur).sort((a,b)=>(cur[b]||0)-(cur[a]||0));const mx=Math.max(.01,...T.flatMap(t=>[cur[t]||0,tw[t]||0]));
  $('#ow').innerHTML=T.map(t=>`<div style="display:flex;align-items:center;gap:10px;margin:5px 0" class="sm"><span class="tk" style="width:84px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(t)}</span><div class="grow"><div class="bar" style="height:5px;margin-bottom:2px"><i style="width:${(cur[t]||0)/mx*100}%;background:var(--line2)"></i></div><div class="bar" style="height:5px"><i style="width:${(tw[t]||0)/mx*100}%;background:#378ADD"></i></div></div><span style="width:110px;text-align:right">${pct(cur[t],1,false)} → <b>${pct(tw[t],1,false)}</b></span></div>`).join('')}
 const fo=(D.opt||[]).find(o=>o.k!=='current'); if(fo&&$('#ow'))drawW(fo.name); $$('#os button').forEach(b=>b.onclick=()=>{$$('#os button').forEach(x=>x.classList.toggle('on',x===b));drawW(b.dataset.k)});

 // Backtest
 const BC=(D.bt.curves||[]).filter(c=>c.d&&c.d.length>1);
 if(!$('#btc')){}else if(BC.length)draws.push(lineChart($('#btc'),BC.map((c,i)=>({name:c.name,d:c.d,v:c.v,color:c.name.startsWith('MSCI')?'#888780':PAL[i%PAL.length],dash:c.name.startsWith('MSCI')?'5 4':null,w:c.name==='Current weights'?2.4:1.5})),{norm:true,H:240,ranges:false}));
 else $('#btc').innerHTML='<div class="empty">Kein Backtest.</div>';

 if(root._ro)root._ro.disconnect();let lw=root.clientWidth;root._ro=new ResizeObserver(()=>{if(Math.abs(root.clientWidth-lw)>8){lw=root.clientWidth;draws.forEach(f=>f&&f())}});root._ro.observe(root);
}
"""

_portfolio = st.components.v2.component("finrobot_portfolio", css=CSS, js=JS)


def render_portfolio(payload, key="portfolio"):
    return _portfolio(data=payload, key=key, on_open_change=lambda: None)
