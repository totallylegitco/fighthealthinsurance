// Denial Watch page (templates/denial_watch.html). Plain script, no build step:
// it draws the tile maps, line charts and bar lists from the JSON that the
// view embeds with json_script (static/denial_watch.json, built by
// scripts/denial_watch/build_bundle.py).
(function(){
const DATA_EL=document.getElementById('dw-data');const ROOT=document.querySelector('.dw');
if(!DATA_EL||!ROOT)return;
const D=JSON.parse(DATA_EL.textContent);
const $=id=>document.getElementById(id);
const NAMES={AL:'Alabama',AK:'Alaska',AZ:'Arizona',AR:'Arkansas',CA:'California',CO:'Colorado',CT:'Connecticut',DE:'Delaware',DC:'District of Columbia',FL:'Florida',GA:'Georgia',HI:'Hawaii',ID:'Idaho',IL:'Illinois',IN:'Indiana',IA:'Iowa',KS:'Kansas',KY:'Kentucky',LA:'Louisiana',ME:'Maine',MD:'Maryland',MA:'Massachusetts',MI:'Michigan',MN:'Minnesota',MS:'Mississippi',MO:'Missouri',MT:'Montana',NE:'Nebraska',NV:'Nevada',NH:'New Hampshire',NJ:'New Jersey',NM:'New Mexico',NY:'New York',NC:'North Carolina',ND:'North Dakota',OH:'Ohio',OK:'Oklahoma',OR:'Oregon',PA:'Pennsylvania',RI:'Rhode Island',SC:'South Carolina',SD:'South Dakota',TN:'Tennessee',TX:'Texas',UT:'Utah',VT:'Vermont',VA:'Virginia',WA:'Washington',WV:'West Virginia',WI:'Wisconsin',WY:'Wyoming'};
const BYNAME=Object.fromEntries(Object.entries(NAMES).map(([k,v])=>[v,k]));
const GRID=[['AK',0,0],['ME',0,11],['VT',1,10],['NH',1,11],['WA',2,1],['ID',2,2],['MT',2,3],['ND',2,4],['MN',2,5],['IL',2,6],['WI',2,7],['MI',2,8],['NY',2,9],['RI',2,10],['MA',2,11],['OR',3,1],['NV',3,2],['WY',3,3],['SD',3,4],['IA',3,5],['IN',3,6],['OH',3,7],['PA',3,8],['NJ',3,9],['CT',3,10],['CA',4,1],['UT',4,2],['CO',4,3],['NE',4,4],['MO',4,5],['KY',4,6],['WV',4,7],['VA',4,8],['MD',4,9],['DE',4,10],['AZ',5,2],['NM',5,3],['KS',5,4],['AR',5,5],['TN',5,6],['NC',5,7],['SC',5,8],['DC',5,9],['OK',6,4],['LA',6,5],['MS',6,6],['AL',6,7],['GA',6,8],['HI',7,0],['TX',7,4],['FL',7,9]];
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const safeUrl=u=>/^https:\/\//.test(String(u))?esc(u):'#';
const fmt=n=>Math.round(n).toLocaleString('en-US');
const pct=(x,d=1)=>(x*100).toFixed(d)+'%';
const big=n=>n>=1e9?(n/1e9).toFixed(1)+' billion':n>=1e6?(n/1e6).toFixed(1)+' million':fmt(n);
const money=n=>n>=1e9?'$'+(n/1e9).toFixed(1)+'B':n>=1e6?'$'+(n/1e6).toFixed(0)+'M':'$'+n.toLocaleString('en-US',{maximumFractionDigits:n<100?2:0});
const css=v=>getComputedStyle(ROOT).getPropertyValue(v).trim();
const lum=hex=>{const m=hex.replace('#','');if(m.length<6)return 1;const r=parseInt(m.substr(0,2),16),g=parseInt(m.substr(2,2),16),b=parseInt(m.substr(4,2),16);return (0.299*r+0.587*g+0.114*b)/255};

/* ticker */
const T=D.trend[D.trend.length-1];
const perDay=T.denied/T.days, perMs=perDay/86400000;
$('perday').textContent=fmt(perDay);
function tick(){const n=new Date();const mid=new Date(n.getFullYear(),n.getMonth(),n.getDate());$('tick').textContent=fmt((n-mid)*perMs);}
tick();setInterval(tick,250);

/* stats */
const inRate=T.in_rate, apShare=T.appeals_all/T.denied, won=T.overturned/T.appeals;
const imr25=D.imr_trend.find(r=>r.y===2025);
$('stats').innerHTML=[
  [pct(inRate,0),'of in-network claims denied on HealthCare.gov plans in 2024'],
  ['1 in '+Math.round(1/apShare),'denials led to an internal appeal in 2024: '+fmt(T.appeals_all)+' appeals, '+big(T.denied)+' denials'],
  [pct(won,0),'of internal appeals won at the insurer in 2024, down from '+pct(D.trend[3].overturned/D.trend[3].appeals,0)+' the year before'],
  [pct(imr25.r,0),'of California independent reviews went the patient\'s way in 2025 (a later, separate step)']
].map(([b,s])=>`<div class="stat"><b class="num">${b}</b><span>${s}</span></div>`).join('');

/* tile map engine */
const S=48,G=2.5,OX=6,OY=6;
function drawMap(svg,valueOf,scale,labelOf,onPick,sel){
  if(!svg.dataset.built){
    let h='';
    for(const [st,r,c] of GRID){const x=OX+c*(S+G), y=OY+r*(S+G);
      h+=`<g data-s="${st}" tabindex="0" role="button"><rect x="${x}" y="${y}" width="${S}" height="${S}" rx="3"/><text x="${x+S/2}" y="${y+21}" text-anchor="middle">${st}</text><text class="v" x="${x+S/2}" y="${y+37}" text-anchor="middle"></text></g>`;}
    svg.innerHTML=h;svg.dataset.built='1';
    svg.querySelectorAll('g').forEach(g=>{
      const pick=()=>svg._pick(g.dataset.s);
      g.addEventListener('mouseenter',pick);g.addEventListener('click',pick);g.addEventListener('focus',pick);
      g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick();}});
    });
  }
  svg._pick=onPick;
  svg.querySelectorAll('g').forEach(g=>{
    const st=g.dataset.s, v=valueOf(st), col=v==null?css('--na'):scale(v);
    const ink=v==null?css('--na-ink'):(lum(col)<0.55?'#ffffff':'#15202b');
    g.classList.toggle('sel',st===sel);
    g.querySelector('rect').setAttribute('fill',col);
    const [t1,t2]=g.querySelectorAll('text');t1.style.fill=ink;t2.style.fill=ink;t2.textContent=v==null?'':labelOf(v);
    g.setAttribute('aria-label',NAMES[st]+(v==null?', no data':', '+labelOf(v)));
  });
}
function binScale(breaks,colors){return v=>{let i=0;while(i<breaks.length&&v>=breaks[i])i++;return colors[i];};}
function legend(el,breaks,colors,lab){ /* ranges include the lower bound */
  const parts=[];for(let i=0;i<colors.length;i++){const lo=i===0?null:breaks[i-1],hi=i<breaks.length?breaks[i]:null;
    parts.push(`<div><i style="background:${colors[i]}"></i><span class="num">${lo==null?'< '+lab(hi):hi==null?lab(lo)+'+':lab(lo)+'–'+lab(hi)}</span></div>`);}
  parts.push(`<div><i style="background:${css('--na')}"></i><span>No data</span></div>`);
  el.innerHTML=parts.join('');
}
const DC=['--d0','--d1','--d2','--d3','--d4','--d5'].map(css);
const UC=['--u0','--u1','--u2','--u3','--u4','--u5'].map(css);
const HC=['--h0','--h1','--h2','--h3','--h4','--h5'].map(css);
const DIV=['#1f5fa8','#88afdb','#e6e9ee','#f09a72','#b8321f'];

/* denial map */
let dm='rate', dsel='FL';
const ST=D.states;
const DM={
  rate:{v:s=>ST[s]?ST[s].rate:null,b:[.10,.14,.17,.20,.25],c:DC,l:x=>pct(x,0),t:x=>pct(x,1)},
  chg:{v:s=>ST[s]&&ST[s].prev!=null?ST[s].rate-ST[s].prev:null,b:[-.03,-.01,.01,.03],c:DIV,l:x=>(x>0?'+':'')+(x*100).toFixed(0)+' pt',t:x=>(x>0?'+':'')+(x*100).toFixed(1)},
  won:{v:s=>ST[s]&&ST[s].won!=null?ST[s].won:null,b:[.15,.25,.35,.45,.55],c:UC,l:x=>pct(x,0),t:x=>pct(x,1)}
};
function dRead(s){dsel=s;const r=ST[s];let h=`<div class="st">${NAMES[s]}</div>`;
  if(!r)h+=`<div class="ln">Not in this data. ${NAMES[s]} runs its own marketplace, or had no HealthCare.gov insurers reporting.</div>`;
  else h+=`<div class="ln"><b class="num">${pct(r.rate)}</b> of in-network claims denied (${big(r.denied)} of ${big(r.claims)})</div>`+
    (r.prev!=null?`<div class="ln">2023: <span class="num">${pct(r.prev)}</span> (${r.rate>=r.prev?'up':'down'} ${Math.abs((r.rate-r.prev)*100).toFixed(1)} points)</div>`:'')+
    `<div class="ln">${r.won!=null?`<b class="num">${pct(r.won,0)}</b> of internal appeals won (${fmt(r.overturned)} of ${fmt(r.appeals)})`:'Too few appeals reported to show a win rate'} · ${r.issuers} insurer${r.issuers>1?'s':''}</div>`;
  $('dread').innerHTML=h;drawD();}
function drawD(){const m=DM[dm];drawMap($('dmap'),m.v,binScale(m.b,m.c),m.t,dRead,dsel);legend($('dleg'),m.b,m.c,m.l);}
function dBars(){const arr=Object.entries(ST).sort((a,b)=>b[1].rate-a[1].rate);const mx=arr[0][1].rate;
  const row=([s,r],cls)=>`<div class="bar ${cls}"><div class="nm"><span>${NAMES[s]}</span></div><div class="track"><div class="fill" style="width:${r.rate/mx*100}%"></div></div><div class="val num">${pct(r.rate)}</div></div>`;
  $('dbars').innerHTML=arr.slice(0,5).map(x=>row(x,'')).join('')+'<div class="note" style="text-align:center">···</div>'+arr.slice(-5).map(x=>row(x,'low')).join('');}
document.querySelectorAll('#dmode button').forEach(b=>b.onclick=()=>{dm=b.dataset.m;document.querySelectorAll('#dmode button').forEach(x=>x.setAttribute('aria-pressed',x===b));drawD();});
dRead(dsel);dBars();

/* line chart */
function line(svg,pts,{ymin,ymax,fmtY,ticks,color,label}){
  const W=560,H=270,L=46,R=16,Tp=18,B=34;const xs=pts.map(p=>p.x);const x0=Math.min(...xs),x1=Math.max(...xs);
  const X=x=>L+(x-x0)/(x1-x0||1)*(W-L-R), Y=y=>Tp+(1-(y-ymin)/(ymax-ymin))*(H-Tp-B);
  let h='<g class="axis">';for(const t of ticks){h+=`<line x1="${L}" x2="${W-R}" y1="${Y(t)}" y2="${Y(t)}"/><text x="${L-8}" y="${Y(t)+4}" text-anchor="end" font-size="12">${fmtY(t)}</text>`;}h+='</g>';
  const step=Math.ceil(pts.length/8);pts.forEach((p,i)=>{if(i%step===0||i===pts.length-1)h+=`<text x="${X(p.x)}" y="${H-10}" text-anchor="middle" font-size="12">${p.x}</text>`;});
  h+=`<path d="${pts.map((p,i)=>(i?'L':'M')+X(p.x).toFixed(1)+' '+Y(p.y).toFixed(1)).join(' ')}" fill="none" stroke="${color}" stroke-width="3" stroke-linejoin="round"/>`;
  pts.forEach((p,i)=>{h+=`<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="${i===pts.length-1?5:3.5}" fill="${color}" stroke="${css('--card')}" stroke-width="1.5"/>`;});
  const lp=pts[pts.length-1];h+=`<text x="${X(lp.x)-8}" y="${Y(lp.y)-12}" text-anchor="end" font-size="14" font-weight="700" style="fill:${color}">${label(lp.y)}</text>`;
  svg.innerHTML=h;
}
function drawLines(){line($('tline'),D.trend.map(t=>({x:t.year,y:t.rate})),{ymin:.10,ymax:.25,ticks:[.10,.15,.20,.25],fmtY:y=>pct(y,0),color:css('--accent'),label:y=>pct(y)+' denied'});
line($('imrline'),D.imr_trend.filter(r=>r.y>=2012).map(r=>({x:r.y,y:r.r})),{ymin:.3,ymax:.8,ticks:[.3,.4,.5,.6,.7,.8],fmtY:y=>pct(y,0),color:css('--teal'),label:y=>pct(y,0)+' overturned'});}
drawLines();
$('ttable').innerHTML='<thead><tr><th>Year</th><th class="r">Denied</th><th class="r">Rate</th><th class="r">Appeals</th><th class="r">Won</th></tr></thead><tbody>'+
  D.trend.map(t=>`<tr><td>${t.year}</td><td class="r num">${big(t.denied)}</td><td class="r num">${pct(t.rate)}</td><td class="r num">${fmt(t.appeals)}</td><td class="r num">${pct(t.overturned/t.appeals,0)}</td></tr>`).join('')+'</tbody>';

/* reasons */
const rmax=D.reasons[0].v, rtot=D.reasons.reduce((a,r)=>a+r.v,0);
$('reasons').innerHTML=D.reasons.map(r=>`<div class="bar ${/medically|Experimental/.test(r.k)?'hl':''}"><div class="nm"><span>${esc(r.k)}</span><span class="note num">${big(r.v)}</span></div><div class="track"><div class="fill" style="width:${r.v/rmax*100}%"></div></div><div class="val num">${r.v/rtot<0.01?'&lt;1%':pct(r.v/rtot,0)}</div></div>`).join('');

/* insurers */
const IS=D.issuers;const states=[...new Set(IS.map(i=>i.s))].sort((a,b)=>NAMES[a].localeCompare(NAMES[b]));
$('istate').innerHTML='<option value="">All states: highest and lowest 10</option>'+states.map(s=>`<option value="${esc(s)}">${esc(NAMES[s]||s)}</option>`).join('');
function iDraw(){const s=$('istate').value;let rows;
  if(s){rows=IS.filter(i=>i.s===s).sort((a,b)=>b.r-a.r);$('icount').textContent=rows.length+' insurers';}
  else{const all=[...IS].sort((a,b)=>b.r-a.r);rows=[...all.slice(0,10),null,...all.slice(-10)];$('icount').textContent=IS.length+' insurers in '+states.length+' states';}
  const mx=Math.max(...IS.map(i=>i.r));
  $('itable').innerHTML='<thead><tr><th>Insurer</th><th>State</th><th>Denial rate</th><th class="r">Claims</th><th class="r">Appeals won</th></tr></thead><tbody>'+
   rows.map(i=>i?`<tr><td>${esc(i.n)}</td><td>${esc(i.s)}</td><td class="num" style="white-space:nowrap"><span class="mini" style="width:${Math.max(2,i.r/mx*90)}px"></span>${pct(i.r)}</td><td class="r num">${big(i.c)}</td><td class="r num">${i.a!=null?pct(i.o/i.a,0)+' <span class="note">('+fmt(i.o)+' of '+fmt(i.a)+')</span>':'<span class="note">too few</span>'}</td></tr>`:'<tr><td colspan="5" class="note" style="text-align:center">···</td></tr>').join('')+'</tbody>';}
$('istate').onchange=iDraw;iDraw();

/* prior authorization */
const PA=D.prior_auth||[];
const PAN={ma:'Medicare Advantage: share of standard (non-urgent) requests denied, by contract or plan.',mcd:'Medicaid managed care plans: share of standard requests denied, by state.',mkt:'HealthCare.gov insurers: share of standard requests denied, by state.',ffs:'State-run Medicaid (fee-for-service): share of standard requests denied.'};
function paDraw(k){const rows=PA.filter(r=>r.line===k&&r.std!=null).sort((a,b)=>b.std-a.std);
  if(!rows.length){$('panote').textContent=PAN[k]+' No reports in this group yet.';$('pabars').innerHTML='';return;}
  const mx=rows[0].std||1;
  $('panote').textContent=PAN[k]+' '+rows.length+' reports, from '+pct(rows[rows.length-1].std)+' to '+pct(rows[0].std)+'. Most count requests; any that count differently say so.';
  $('pabars').innerHTML=rows.map(r=>`<div class="bar"><div class="nm"><span><b>${esc(r.n)}</b> <span class="note">${esc(r.where)}${r.req?' · '+fmt(r.req)+' '+esc(r.unit||'requests'):''}${r.exp_posted?' · urgent requests: '+esc(r.exp_posted)+'% denied':''} · <a href="${safeUrl(r.url)}" rel="noopener">source</a>${r.note?'<br>'+esc(r.note):''}</span></span></div><div class="track"><div class="fill" style="width:${Math.max(1,r.std/mx*100)}%"></div></div><div class="val num">${esc(r.std_posted)}%</div></div>`).join('');}
document.querySelectorAll('#pamode button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#pamode button').forEach(x=>x.setAttribute('aria-pressed',x===b));paDraw(b.dataset.m);});
paDraw('ma');

/* IMR */
$('imrbars').innerHTML=D.imr_cat.map(r=>`<div class="bar hl"><div class="nm"><span>${esc(r.k)}</span><span class="note num">${fmt(r.n)} reviews</span></div><div class="track"><div class="fill" style="width:${r.r*100}%"></div></div><div class="val num">${pct(r.r,0)}</div></div>`).join('');

/* coverage map */
const SA=D.sahie, PL=D.places;
const sa=(y,s)=>{const r=SA[y][NAMES[s]];return r?r.pct/100:null};
let cm='unins', csel='TX';
const CM={
  unins:{v:s=>sa('2024',s),b:[.06,.08,.10,.12,.15],c:UC,l:x=>pct(x,0),t:x=>pct(x,1),name:'Uninsured under 65, 2024'},
  uchg:{v:s=>{const a=sa('2024',s),b=sa('2023',s);return a!=null&&b!=null?a-b:null},b:[-.006,-.002,.002,.006],c:DIV,l:x=>(x>0?'+':'')+(x*100).toFixed(1)+' pt',t:x=>(x>0?'+':'')+(x*100).toFixed(1),name:'Change in uninsured rate, 2023 to 2024'},
  fair_poor_health:{v:s=>PL[s]&&PL[s].fair_poor_health!=null?PL[s].fair_poor_health/100:null,b:[.15,.17,.19,.21,.23],c:HC,l:x=>pct(x,0),t:x=>pct(x,1),name:'Adults in fair or poor health'},
  diabetes:{v:s=>PL[s]&&PL[s].diabetes!=null?PL[s].diabetes/100:null,b:[.10,.11,.12,.13,.14],c:HC,l:x=>pct(x,0),t:x=>pct(x,1),name:'Adults with diabetes'},
  depression:{v:s=>PL[s]&&PL[s].depression!=null?PL[s].depression/100:null,b:[.20,.22,.24,.26,.28],c:HC,l:x=>pct(x,0),t:x=>pct(x,1),name:'Adults ever told they have depression'}
};
function cRead(s){csel=s;const a=sa('2024',s),b=sa('2023',s),p=PL[s]||{};const n=SA['2024'][NAMES[s]];
  $('cread').innerHTML=`<div class="st">${NAMES[s]}</div>`+
   (a!=null?`<div class="ln"><b class="num">${pct(a)}</b> uninsured under 65 (${fmt(n.n)} people), ${b!=null?(a>=b?'up':'down')+' from '+pct(b)+' in 2023':''}</div>`:'')+
   (p.fair_poor_health!=null?`<div class="ln">Fair or poor health <b class="num">${p.fair_poor_health}%</b> · diabetes <b class="num">${p.diabetes}%</b> · depression <b class="num">${p.depression}%</b></div>`:'<div class="ln">No CDC health estimates for this state in this release.</div>');
  drawC();}
function drawC(){const m=CM[cm];drawMap($('cmap'),m.v,binScale(m.b,m.c),m.t,cRead,csel);legend($('cleg'),m.b,m.c,m.l);
  const arr=GRID.map(g=>[g[0],m.v(g[0])]).filter(x=>x[1]!=null).sort((a,b)=>b[1]-a[1]);const mx=Math.max(...arr.map(x=>Math.abs(x[1])));
  $('cbarsh').textContent=m.name+': highest and lowest';
  const row=([s,v],cls)=>`<div class="bar ${cls}"><div class="nm"><span>${NAMES[s]}</span></div><div class="track"><div class="fill" style="width:${Math.abs(v)/mx*100}%;background:${cm.startsWith('u')?css('--blue'):css('--h4')}"></div></div><div class="val num">${m.l(v)}</div></div>`;
  $('cbars').innerHTML=arr.slice(0,5).map(x=>row(x,'')).join('')+'<div class="note" style="text-align:center">···</div>'+arr.slice(-5).map(x=>row(x,'')).join('');}
document.querySelectorAll('#cmode button').forEach(b=>b.onclick=()=>{cm=b.dataset.m;document.querySelectorAll('#cmode button').forEach(x=>x.setAttribute('aria-pressed',x===b));drawC();});
cRead(csel);

/* drugs */
const DG=D.drugs;
$('drugintro').textContent=`Total spending on prescription drugs under Medicare Part D was ${money(DG.total.y2024)} in 2024, up from ${money(DG.total.y2020)} in 2020. That counts what plans and patients paid together, before manufacturer rebates. Diabetes, heart and weight-loss drugs drove much of the growth.`;
const DGM={
  top:{note:'Total Part D spending on each drug in 2024 (plans and patients combined, before rebates).',v:d=>d.Tot_Spndng_2024,l:d=>money(d.Tot_Spndng_2024),sub:d=>fmt(d.Tot_Benes_2024)+' people'},
  per:{note:'Total yearly spending per patient in 2024, not what each patient paid out of pocket. Drugs with at least 1,000 Medicare patients.',v:d=>d.Avg_Spnd_Per_Bene_2024,l:d=>money(d.Avg_Spnd_Per_Bene_2024),sub:d=>fmt(d.Tot_Benes_2024)+' people'},
  growth:{note:'Growth in total spending from 2020 to 2024, among drugs with at least $100M of spending in 2020.',v:d=>d.Tot_Spndng_2024/d.Tot_Spndng_2020,l:d=>(d.Tot_Spndng_2024/d.Tot_Spndng_2020).toFixed(1)+'×',sub:d=>money(d.Tot_Spndng_2020)+' → '+money(d.Tot_Spndng_2024)},
  cheap:{note:'Lowest average total cost per prescription fill, 2024, among drugs taken by at least 2 million Medicare patients.',v:d=>d.Avg_Spnd_Per_Clm_2024,l:d=>money(d.Avg_Spnd_Per_Clm_2024),sub:d=>fmt(d.Tot_Benes_2024)+' people',low:true}
};
function dgDraw(k){const m=DGM[k],rows=DG[k];const mx=Math.max(...rows.map(m.v));$('dgnote').textContent=m.note;
  $('dgbars').innerHTML=rows.map(d=>`<div class="bar ${m.low?'low':''}"><div class="nm"><span><b>${esc(d.Brnd_Name)}</b> <span class="note">${esc(String(d.Gnrc_Name).toLowerCase())}</span></span><span class="note num">${m.sub(d)}</span></div><div class="track"><div class="fill" style="width:${m.v(d)/mx*100}%"></div></div><div class="val num">${m.l(d)}</div></div>`).join('');}
document.querySelectorAll('#dgmode button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#dgmode button').forEach(x=>x.setAttribute('aria-pressed',x===b));dgDraw(b.dataset.m);});
dgDraw('top');

})();
