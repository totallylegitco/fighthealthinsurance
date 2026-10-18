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
const money=n=>n>=1e9?'$'+(n/1e9).toFixed(1)+'B':n>=1e6?'$'+(n/1e6).toFixed(0)+'M':'$'+n.toLocaleString('en-US',n<100?{minimumFractionDigits:2,maximumFractionDigits:2}:{maximumFractionDigits:0});
const css=v=>getComputedStyle(ROOT).getPropertyValue(v).trim();
/* WCAG relative luminance, to pick the tile label ink with the higher contrast. */
const lin=c=>{c/=255;return c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4)};
const relLum=hex=>{const m=hex.replace('#','');if(m.length<6)return 1;return 0.2126*lin(parseInt(m.substr(0,2),16))+0.7152*lin(parseInt(m.substr(2,2),16))+0.0722*lin(parseInt(m.substr(4,2),16))};
const DARK_INK='#15202b';
const inkOn=bg=>{const l=relLum(bg);return (1.05/(l+0.05))>=((l+0.05)/(relLum(DARK_INK)+0.05))?'#ffffff':DARK_INK};

/* ticker */
const T=D.trend[D.trend.length-1];
const perDay=T.in_denied/T.days, perMs=perDay/86400000;
$('perday').textContent=fmt(perDay);
function tick(){const n=new Date();const mid=new Date(n.getFullYear(),n.getMonth(),n.getDate());$('tick').textContent=fmt((n-mid)*perMs);}
tick();
/* Pausable (WCAG 2.2.2); starts paused for anyone who asks for reduced motion. */
let timer=null;const pauseBtn=$('tickpause');
function run(on){if(on&&!timer)timer=setInterval(tick,250);if(!on&&timer){clearInterval(timer);timer=null;}if(pauseBtn)pauseBtn.textContent=on?'Pause the counter':'Start the counter';}
run(!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches));
if(pauseBtn)pauseBtn.addEventListener('click',()=>run(!timer));

/* stats */
const inRate=T.in_rate, apShare=T.appeals_all/T.in_denied, won=T.overturned/T.appeals;
const imr25=D.imr_trend.find(r=>r.y===2025);
$('stats').innerHTML=[
  [pct(inRate,0),'claims denied','in-network, on HealthCare.gov plans, '+T.year],
  /* Tens, matching the page's "about 1 for every 320". */
  [fmt(Math.round(1/apShare/10)*10),'denials per appeal',T.year+': '+big(T.in_denied)+' in-network denials, '+fmt(T.appeals_all)+' internal appeals'],
  [pct(won,0),'appeals won','at the insurer, '+T.year],
  [pct(imr25.r,0),'reviews won','by patients at California\'s independent review, 2025, a later step']
].map(([b,l,s])=>`<div class="dw-stat"><p class="dw-stat-head"><b class="dw-num">${b}</b> <strong>${l}</strong></p><span>${s}</span></div>`).join('');

/* tile map engine */
const S=48,G=2.5,OX=6,OY=6;
function drawMap(svg,valueOf,scale,labelOf,onPick,sel,naOf=()=>', no data'){
  if(!svg.dataset.built){
    let h='';
    for(const [st,r,c] of GRID){const x=OX+c*(S+G), y=OY+r*(S+G);
      h+=`<g data-s="${st}" tabindex="0" role="button"><rect x="${x}" y="${y}" width="${S}" height="${S}" rx="3"/><text x="${x+S/2}" y="${y+21}" text-anchor="middle" class="dw-code">${st}</text><text class="dw-v" x="${x+S/2}" y="${y+37}" text-anchor="middle"></text></g>`;}
    svg.innerHTML=h;svg.dataset.built='1';svg._pinned=sel;
    svg.querySelectorAll('g').forEach(g=>{
      const pin=()=>{svg._pinned=g.dataset.s;svg._pick(g.dataset.s);};
      /* No pick on focus: tabbing out of the map would pick every tile after yours. */
      g.addEventListener('mouseenter',()=>svg._pick(g.dataset.s));g.addEventListener('click',pin);
      g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pin();}});
    });
    /* Hover previews; leaving the map goes back to the state picked, so its readout link can be reached. */
    svg.addEventListener('mouseleave',()=>{if(svg._pinned!==svg._sel)svg._pick(svg._pinned);});
  }
  svg._pick=onPick;svg._sel=sel;
  svg.querySelectorAll('g').forEach(g=>{
    const st=g.dataset.s, v=valueOf(st), col=v==null?css('--dw-na'):scale(v);
    const ink=v==null?css('--dw-na-ink'):inkOn(col);
    g.classList.toggle('dw-sel',st===sel);
    g.querySelector('rect').setAttribute('fill',col);
    const [t1,t2]=g.querySelectorAll('text');t1.style.fill=ink;t2.style.fill=ink;t2.textContent=v==null?'':labelOf(v);
    g.setAttribute('aria-label',NAMES[st]+(v==null?naOf(st):', '+labelOf(v)));
  });
}
function binScale(breaks,colors){return v=>{let i=0;while(i<breaks.length&&v>=breaks[i])i++;return colors[i];};}
function legend(el,breaks,colors,lab,na='No data'){ /* ranges include the lower bound */
  const parts=[];for(let i=0;i<colors.length;i++){const lo=i===0?null:breaks[i-1],hi=i<breaks.length?breaks[i]:null;
    parts.push(`<div><i style="background:${colors[i]}"></i><span class="dw-num">${lo==null?'< '+lab(hi):hi==null?lab(lo)+'+':lab(lo)+'–'+lab(hi)}</span></div>`);}
  parts.push(`<div><i style="background:${css('--dw-na')}"></i><span>${na}</span></div>`);
  el.innerHTML=parts.join('');
}
const DC=['--dw-d0','--dw-d1','--dw-d2','--dw-d3','--dw-d4','--dw-d5'].map(css);
const UC=['--dw-u0','--dw-u1','--dw-u2','--dw-u3','--dw-u4','--dw-u5'].map(css);
const HC=['--dw-h0','--dw-h1','--dw-h2','--dw-h3','--dw-h4','--dw-h5'].map(css);
const DIV=['#1f5fa8','#88afdb','#e6e9ee','#f09a72','#b8321f'];

/* Network views: in-network first everywhere; a figure a view leaves out says why where it would be. */
const OM=D.oon_meta, IS=D.issuers;
const short=n=>String(n).replace(/,? Inc\.?$/,'');
const andList=a=>a.length<2?a.join(''):a.slice(0,-1).join(', ')+' and '+a[a.length-1];
const cantBe=names=>andList(names.map(short))+' reported more out-of-network denials than claims, which can\'t be right';
const inTen=Math.round(T.in_claims/T.all_claims*10);

/* denial map */
let dm='in', dsel='FL';
const ST=D.states;
const RB=[.10,.14,.17,.20,.25];
const ALLGONE=Object.keys(ST).filter(s=>ST[s].all.why==='error').sort((a,b)=>NAMES[a].localeCompare(NAMES[b]));
const DM={
  in:{v:s=>ST[s]?ST[s].rate:null,b:RB,c:DC,l:x=>pct(x,0),t:x=>pct(x,1),
    note:`In-network claims: care from doctors, hospitals and pharmacies that have a contract with the plan. About ${inTen} in 10 claims are in network, and every plan pays for in-network care, so this view compares insurers most evenly.`},
  /* No state figures: most would mostly show plan type (dnote says so). */
  out:{v:()=>null,b:[],c:[],na:'Not shown by state',naOf:s=>ST[s]?', out-of-network rates not shown by state':', no data',
    note:`Insurers denied ${pct(T.out_rate,0)} of out-of-network claims in ${T.year} (${big(T.out_denied)} of ${big(T.out_claims)}), about twice the in-network rate. We don't show them state by state. In ${OM.plan_types_year}, ${OM.net_only.issuers} of the ${T.out_issuers} insurers reporting them sold only network-only plans (every plan an HMO or EPO), which mostly don't cover out-of-network care by design, so a state's rate would mostly show which kinds of plans its insurers sell, not how they handle claims. <a href="#insurers" data-iview="out">See out-of-network rates insurer by insurer</a>.`},
  all:{v:s=>ST[s]&&ST[s].all.rate!=null?ST[s].all.rate:null,b:RB,c:DC,l:x=>pct(x,0),t:x=>pct(x,1),na:'No data or left out',
    naOf:s=>!ST[s]?', no data':ST[s].all.why==='error'?', no figure: '+cantBe(ST[s].all.left_out):', no figure',
    note:`In-network and out-of-network claims together: ${pct(T.all_rate,0)} denied in ${T.year}. About ${inTen} in 10 claims are in network, so these rates sit close to the in-network ones.`+
      (ALLGONE.length?` ${andList(ALLGONE.map(s=>NAMES[s]))} ${ALLGONE.length>1?'show':'shows'} no figure here, because ${esc(cantBe(ALLGONE.flatMap(s=>ST[s].all.left_out)))}.`:'')},
  chg:{v:s=>ST[s]&&ST[s].prev!=null?ST[s].rate-ST[s].prev:null,b:[-.03,-.01,.01,.03],c:DIV,l:x=>(x>0?'+':'')+(x*100).toFixed(0)+' pt',t:x=>(x>0?'+':'')+(x*100).toFixed(1),
    note:'Change in each state\'s in-network denial rate since 2023, in percentage points. There\'s no out-of-network version, because those changes mostly reflect which insurers reported each year.'},
  won:{v:s=>ST[s]&&ST[s].won!=null?ST[s].won:null,b:[.15,.25,.35,.45,.55],c:UC,l:x=>pct(x,0),t:x=>pct(x,1),
    note:`Share of internal appeals that insurers reversed in ${T.year}, for states with at least 50 appeals. Appeals aren't split by network, so there's no out-of-network version.`}
};
/* FHI's state help page, at the slug state_help.json uses: the name, lower case, hyphens for spaces. */
const HELP=ROOT.dataset.stateHelp||'';
const helpLink=s=>HELP?`<div class="dw-readout-line"><a href="${esc(HELP+NAMES[s].toLowerCase().replace(/ /g,'-')+'/')}">Where to get help in ${esc(NAMES[s])}</a></div>`:'';
const line1=h=>`<div class="dw-readout-line">${h}</div>`;
function outRead(s,r){const o=r.out;
  return line1('Out-of-network claims aren\'t shown state by state (why, under the map).')+
    (o.issuers?line1(`Sold only network-only plans in ${OM.plan_types_year}: ${o.net_only} of ${o.issuers} insurer${o.issuers>1?'s':''} here`):'')+
    (o.left_out.length?line1(esc(cantBe(o.left_out))+'.'):'')+
    (IS.some(i=>i.s===s)?line1(`<a href="#insurers" data-iview="out" data-istate="${esc(s)}">See ${esc(NAMES[s])} insurer by insurer</a>`):'');}
function allRead(s,r){const a=r.all;
  return line1(a.rate!=null?`<b class="dw-num">${pct(a.rate)}</b> of all claims denied, in and out of network (${big(a.denied)} of ${big(a.claims)})`:
    a.why==='error'?`No all-claims figure for ${NAMES[s]}: ${esc(cantBe(a.left_out))}.`:'No all-claims figure: not every insurer here reported both kinds of claims.');}
function dRead(s){dsel=s;const r=ST[s];let h=`<div class="dw-readout-state">${NAMES[s]}</div>`;
  if(!r)h+=`<div class="dw-readout-line">Not in this data. ${NAMES[s]} runs its own marketplace, or had no HealthCare.gov insurers reporting.</div>`;
  else h+=(dm==='out'?outRead(s,r):dm==='all'?allRead(s,r):'')+`<div class="dw-readout-line"><b class="dw-num">${pct(r.rate)}</b> of in-network claims denied (${big(r.denied)} of ${big(r.claims)})</div>`+
    (r.prev!=null?`<div class="dw-readout-line">2023: <span class="dw-num">${pct(r.prev)}</span> (${r.rate>=r.prev?'up':'down'} ${Math.abs((r.rate-r.prev)*100).toFixed(1)} points)</div>`:'')+
    `<div class="dw-readout-line">${r.won!=null?`<b class="dw-num">${pct(r.won,0)}</b> of internal appeals won (${fmt(r.overturned)} of ${fmt(r.appeals)})`:'Too few appeals reported to show a win rate'} · ${r.issuers} reporting insurer${r.issuers>1?'s':''}${r.issuers===1?', so these are that company\'s figures':r.issuers===2?', so these are those companies\' figures':''}</div>`;
  $('dread').innerHTML=h+helpLink(s);drawD();}
function drawD(){const m=DM[dm];drawMap($('dmap'),m.v,binScale(m.b,m.c),m.t,dRead,dsel,m.naOf);legend($('dleg'),m.b,m.c,m.l,m.na);$('dnote').innerHTML=m.note;}
/* The bars follow the all-claims view; the other views show in-network. */
function dBars(){const all=dm==='all',val=s=>all?ST[s].all.rate:ST[s].rate;
  const arr=Object.keys(ST).filter(s=>val(s)!=null).sort((a,b)=>val(b)-val(a));const mx=val(arr[0]);
  $('dbarsh').textContent='Highest and lowest '+(all?'all-claims':'in-network')+' denial rates';
  const row=(s,cls)=>`<div class="dw-bar ${cls}"><div class="dw-bar-name"><span>${NAMES[s]}</span></div><div class="dw-bar-track"><div class="dw-bar-fill" style="width:${val(s)/mx*100}%"></div></div><div class="dw-bar-value dw-num">${pct(val(s))}</div></div>`;
  $('dbars').innerHTML=arr.slice(0,5).map(x=>row(x,'')).join('')+'<div class="dw-note dw-gap-row">···</div>'+arr.slice(-5).map(x=>row(x,'dw-bar-low')).join('');}
document.querySelectorAll('#dmode button').forEach(b=>b.onclick=()=>{dm=b.dataset.m;document.querySelectorAll('#dmode button').forEach(x=>x.setAttribute('aria-pressed',x===b));dRead(dsel);dBars();});
dRead(dsel);dBars();

/* line chart */
function line(svg,pts,{ymin,ymax,fmtY,ticks,color,label}){
  const W=560,H=270,L=46,R=16,Tp=18,B=34;const xs=pts.map(p=>p.x);const x0=Math.min(...xs),x1=Math.max(...xs);
  const X=x=>L+(x-x0)/(x1-x0||1)*(W-L-R), Y=y=>Tp+(1-(y-ymin)/(ymax-ymin))*(H-Tp-B);
  let h='<g class="dw-axis">';for(const t of ticks){h+=`<line x1="${L}" x2="${W-R}" y1="${Y(t)}" y2="${Y(t)}"/><text x="${L-8}" y="${Y(t)+4}" text-anchor="end" font-size="12">${fmtY(t)}</text>`;}h+='</g>';
  const step=Math.ceil(pts.length/8);pts.forEach((p,i)=>{if(i%step===0||i===pts.length-1)h+=`<text x="${X(p.x)}" y="${H-10}" text-anchor="middle" font-size="12">${p.x}</text>`;});
  h+=`<path d="${pts.map((p,i)=>(i?'L':'M')+X(p.x).toFixed(1)+' '+Y(p.y).toFixed(1)).join(' ')}" fill="none" stroke="${color}" stroke-width="3" stroke-linejoin="round"/>`;
  pts.forEach((p,i)=>{h+=`<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="${i===pts.length-1?5:3.5}" fill="${color}" stroke="${'#ffffff'}" stroke-width="1.5"/>`;});
  const lp=pts[pts.length-1];h+=`<text x="${X(lp.x)-8}" y="${Y(lp.y)-12}" text-anchor="end" font-size="14" font-weight="700" style="fill:${color}">${label(lp.y)}</text>`;
  svg.innerHTML=h;
}
/* trend: the 2020 and 2021 files count in-network claims only, so the other views start in 2022 */
let tv='in';
const TV={
  in:{lab:'in-network',ymin:.10,ymax:.25,ticks:[.10,.15,.20,.25]},
  out:{lab:'out-of-network',ymin:.30,ymax:.45,ticks:[.30,.35,.40,.45]},
  all:{lab:'all-claims',ymin:.10,ymax:.25,ticks:[.10,.15,.20,.25]}
};
const who=x=>short(x.n).includes(NAMES[x.s])?short(x.n):short(x.n)+' in '+NAMES[x.s];
const LEFT=Object.values(D.trend.reduce((a,t)=>{t.left_out.forEach(x=>{(a[x.s+x.id]=a[x.s+x.id]||{x,y:[]}).y.push(t.year);});return a;},{})).map(({x,y})=>`${who(x)} (${andList(y.map(String))})`);
function tDraw(){const m=TV[tv],rows=D.trend.filter(t=>t[tv+'_rate']!=null),y0=rows[0].year,y1=rows[rows.length-1].year;
  line($('tline'),rows.map(t=>({x:t.year,y:t[tv+'_rate']})),{ymin:m.ymin,ymax:m.ymax,ticks:m.ticks,fmtY:y=>pct(y,0),color:css('--dw-red'),label:y=>pct(y)+' denied'});
  $('tline').setAttribute('aria-label',`Line chart of the ${m.lab} denial rate by year, ${y0} to ${y1}`);
  $('tnote').textContent=tv==='in'?`In-network claims, ${y0} to ${y1}.`:
    (tv==='out'?`Out-of-network claims, ${y0} to ${y1}. Insurers have reported them separately only since ${y0} claims.`:`All claims, in and out of network, ${y0} to ${y1}, the years insurers split the two.`)+
    (LEFT.length?` Left out because they reported more out-of-network denials than claims, which can't be right: ${andList(LEFT)}.`:'');
  /* Appeals aren't split by network, so the out-of-network table has no appeals column. */
  $('ttable').innerHTML=`<thead><tr><th>Year</th><th class="dw-r">Denied</th><th class="dw-r">Rate</th>${tv==='out'?'':'<th class="dw-r">Appeals</th>'}</tr></thead><tbody>`+
    rows.map(t=>`<tr><td>${t.year}</td><td class="dw-r dw-num">${big(t[tv+'_denied'])}</td><td class="dw-r dw-num">${pct(t[tv+'_rate'])}</td>${tv==='out'?'':`<td class="dw-r dw-num">${fmt(t.appeals_all)}</td>`}</tr>`).join('')+'</tbody>';}
document.querySelectorAll('#tmode button').forEach(b=>b.onclick=()=>{tv=b.dataset.m;document.querySelectorAll('#tmode button').forEach(x=>x.setAttribute('aria-pressed',x===b));tDraw();});
tDraw();
line($('imrline'),D.imr_trend.map(r=>({x:r.y,y:r.r})),{ymin:.3,ymax:.8,ticks:[.3,.4,.5,.6,.7,.8],fmtY:y=>pct(y,0),color:css('--dw-teal'),label:y=>pct(y,0)+' overturned'});

/* reasons */
const rmax=D.reasons[0].v, rtot=D.reasons.reduce((a,r)=>a+r.v,0);
$('reasons').innerHTML=D.reasons.map(r=>`<div class="dw-bar ${/medically|Experimental/.test(r.k)?'dw-bar-hl':''}"><div class="dw-bar-name"><span>${esc(r.k)}</span><span class="dw-note dw-num">${big(r.v)}</span></div><div class="dw-bar-track"><div class="dw-bar-fill" style="width:${r.v/rmax*100}%"></div></div><div class="dw-bar-value dw-num">${r.v/rtot<0.01?'&lt;1%':pct(r.v/rtot,0)}</div></div>`).join('');

/* insurers: the same rows in every view; a rate a view leaves out says why in its row */
const states=[...new Set(IS.map(i=>i.s))].sort((a,b)=>NAMES[a].localeCompare(NAMES[b]));
$('istate').innerHTML='<option value="">All states</option>'+states.map(s=>`<option value="${esc(s)}">${esc(NAMES[s]||s)}</option>`).join('');
let iv='in';
const nNet=IS.filter(i=>i.net_only).length;
const IV={
  in:{rate:'Denial rate',claims:'Claims',range:'Insurer denial rates, lowest to highest',
    note:'In-network claims, the fairest comparison, since every plan pays for in-network care.'},
  out:{rate:'Out-of-network denial rate',claims:'Out-of-network claims',range:'Out-of-network denial rates, lowest to highest',
    note:`Out-of-network rates show only for insurers that also sold PPO or POS plans in ${OM.plan_types_year} and had at least ${fmt(OM.min_claims)} out-of-network claims. Network-only plans (every plan an HMO or EPO) mostly don't cover out-of-network care by design, so an out-of-network denial rate would mostly show plan type, not how the insurer handles claims. ${nNet} of these ${IS.length} insurers sold only network-only plans. Shopping for a plan that pays for some out-of-network care? Look for a PPO or POS. Got emergency care, or saw an out-of-network doctor at an in-network hospital? Surprise-billing rules may protect you: see <a href="#who-to-call">Who to call</a>.`},
  all:{rate:'All-claims denial rate',claims:'All claims',range:'All-claims denial rates, lowest to highest',
    note:`In-network and out-of-network claims together. <span class="dw-chip">Network-only plans</span> marks an insurer that sold only HMO or EPO plans in ${OM.plan_types_year}: its rate here includes out-of-network care those plans mostly don't cover by design, so it runs higher partly for that reason.`}
};
/* Why a row has no rate in this view; it takes the claims column's width too. */
const WHY={
  net_only:()=>'Network-only plans: out-of-network care mostly not covered by design',
  types_unknown:()=>`Not shown: its ${OM.plan_types_year} plans aren't in CMS's plan list`,
  few:i=>`Too few out-of-network claims (${fmt(i.out.c)})`,
  error:i=>`Can't be right: ${fmt(i.out.d)} out-of-network denials reported for ${fmt(i.out.c)} claims`,
  missing:()=>'Not reported'
};
const cell=i=>iv==='in'?{r:i.r,c:i.c,why:null}:i[iv];
const noneWhy=g=>g.every(i=>cell(i).why==='net_only')?(g.length>1?'None: every insurer here sold only network-only plans':'None: it sold only network-only plans'):'None shown: pick the state to see why';
function iDraw(){const s=$('istate').value,v=IV[iv],out=iv==='out';
  $('inote').innerHTML=v.note;
  const mx=Math.max(...IS.filter(i=>cell(i).r!=null).map(i=>cell(i).r));
  /* All states: one row per state, so no company is set against another state's. */
  if(!s){$('icount').textContent=IS.length+' insurers in '+states.length+' states';
    $('itable').innerHTML=`<thead><tr><th>State</th><th class="dw-r">Insurers</th><th>${v.range}</th>${out?'':`<th class="dw-r">${v.claims}</th>`}</tr></thead><tbody>`+
     states.map(st=>{const g=IS.filter(i=>i.s===st),gs=g.filter(i=>cell(i).r!=null),rs=gs.map(i=>cell(i).r),lo=Math.min(...rs),hi=Math.max(...rs),c=gs.reduce((a,i)=>a+cell(i).c,0);
      const range=gs.length?`<td class="dw-num" style="white-space:nowrap"><span class="dw-range" aria-hidden="true"><span class="dw-range-fill" style="left:${lo/mx*100}%;width:${Math.max(2,(hi-lo)/mx*100)}%"></span></span>${gs.length>1?pct(lo)+' to '+pct(hi):pct(lo)+' (one insurer)'}</td>`:`<td class="dw-note">${noneWhy(g)}</td>`;
      return `<tr><td><button type="button" class="dw-pick" data-s="${esc(st)}">${esc(NAMES[st]||st)}</button></td><td class="dw-r dw-num">${gs.length<g.length?gs.length+' of '+g.length:g.length}</td>${range}${out?'':`<td class="dw-r dw-num">${gs.length?big(c):''}</td>`}</tr>`;}).join('')+'</tbody>';
    $('itable').querySelectorAll('.dw-pick').forEach(b=>b.onclick=()=>{$('istate').value=b.dataset.s;iDraw();$('istate').focus();});
    return;}
  const rows=IS.filter(i=>i.s===s).sort((a,b)=>(cell(b).r??-1)-(cell(a).r??-1)||(cell(b).c||0)-(cell(a).c||0));$('icount').textContent=rows.length+' insurers';
  $('itable').innerHTML=`<thead><tr><th>Insurer</th><th>State</th><th>${v.rate}</th><th class="dw-r">${v.claims}</th>${out?'':'<th class="dw-r">Appeals won</th>'}</tr></thead><tbody>`+
   rows.map(i=>{const x=cell(i);
    return `<tr><td>${esc(i.n)}${iv==='all'&&i.net_only?' <span class="dw-chip">Network-only plans</span>':''}</td><td>${esc(i.s)}</td>${x.r!=null?`<td class="dw-num" style="white-space:nowrap"><span class="dw-mini" style="width:${Math.max(2,x.r/mx*90)}px"></span>${pct(x.r)}</td><td class="dw-r dw-num">${big(x.c)}</td>`:`<td class="dw-note" colspan="2">${esc(WHY[x.why](i))}</td>`}${out?'':`<td class="dw-r dw-num">${i.a!=null&&i.o!=null?pct(i.o/i.a,0)+' <span class="dw-note">('+fmt(i.o)+' of '+fmt(i.a)+')</span>':i.a!=null?'<span class="dw-note">not reported ('+fmt(i.a)+' appeals)</span>':'<span class="dw-note">too few</span>'}</td>`}</tr>`;}).join('')+'</tbody>';}
function setIView(m){iv=m;document.querySelectorAll('#iview button').forEach(x=>x.setAttribute('aria-pressed',x.dataset.m===m));iDraw();}
document.querySelectorAll('#iview button').forEach(b=>b.onclick=()=>setIView(b.dataset.m));
/* Links in the map's note and readout open the insurer table on their view and state. */
ROOT.addEventListener('click',e=>{const a=e.target.closest('a[data-iview]');if(!a)return;
  if(a.dataset.istate&&states.includes(a.dataset.istate))$('istate').value=a.dataset.istate;setIView(a.dataset.iview);});
$('istate').onchange=iDraw;iDraw();

/* prior authorization */
const PA=D.prior_auth||[];
const PAN={ma:'Medicare Advantage: share of standard (non-urgent) requests denied, by contract or plan.',mcd:'Medicaid managed care plans: share of standard requests denied, by state.',mkt:'HealthCare.gov insurers: share of standard requests denied, by state.',ffs:'State-run Medicaid (fee-for-service): share of standard requests denied.'};
function paDraw(k){const rows=PA.filter(r=>r.line===k&&r.std!=null).sort((a,b)=>b.std-a.std);
  if(!rows.length){$('panote').textContent=PAN[k]+' No reports in this group yet.';$('pabars').innerHTML='';return;}
  const mx=rows[0].std||1;
  $('panote').textContent=PAN[k]+' '+rows.length+' reports, from '+pct(rows[rows.length-1].std)+' to '+pct(rows[0].std)+'. Most count requests; any that count differently say so.';
  $('pabars').innerHTML=rows.map(r=>`<div class="dw-bar"><div class="dw-bar-name"><span><b>${esc(r.n)}</b> <span class="dw-note">${esc(r.where)}${r.req?' · '+fmt(r.req)+' '+esc(r.unit||'requests'):''}${r.exp_posted?' · urgent requests: '+esc(r.exp_posted)+'% denied':''} · <a href="${safeUrl(r.url)}" rel="noopener">source</a>${r.note?'<br>'+esc(r.note):''}</span></span></div><div class="dw-bar-track"><div class="dw-bar-fill" style="width:${Math.max(1,r.std/mx*100)}%"></div></div><div class="dw-bar-value dw-num">${esc(String(r.std_posted).replace(/^\./,'0.'))}%</div></div>`).join('');}
document.querySelectorAll('#pamode button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#pamode button').forEach(x=>x.setAttribute('aria-pressed',x===b));paDraw(b.dataset.m);});
paDraw('ma');

/* IMR */
$('imrbars').innerHTML=D.imr_cat.map(r=>`<div class="dw-bar dw-bar-hl"><div class="dw-bar-name"><span>${esc(r.k)}</span><span class="dw-note dw-num">${fmt(r.n)} reviews</span></div><div class="dw-bar-track"><div class="dw-bar-fill" style="width:${r.r*100}%"></div></div><div class="dw-bar-value dw-num">${pct(r.r,0)}</div></div>`).join('');

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
  $('cread').innerHTML=`<div class="dw-readout-state">${NAMES[s]}</div>`+
   (a!=null?`<div class="dw-readout-line"><b class="dw-num">${pct(a)}</b> uninsured under 65 (${fmt(n.n)} people), ${b!=null?(a===b?'the same as in 2023':(a>b?'up':'down')+' from '+pct(b)+' in 2023'):''}</div>`:'')+
   (p.fair_poor_health!=null?`<div class="dw-readout-line">Fair or poor health <b class="dw-num">${p.fair_poor_health}%</b> · diabetes <b class="dw-num">${p.diabetes}%</b> · depression <b class="dw-num">${p.depression}%</b></div>`:'<div class="dw-readout-line">No CDC estimates for these measures in this state in this release.</div>');
  drawC();}
function drawC(){const m=CM[cm];drawMap($('cmap'),m.v,binScale(m.b,m.c),m.t,cRead,csel);legend($('cleg'),m.b,m.c,m.l);
  const arr=GRID.map(g=>[g[0],m.v(g[0])]).filter(x=>x[1]!=null).sort((a,b)=>b[1]-a[1]);const mx=Math.max(...arr.map(x=>Math.abs(x[1])));
  $('cbarsh').textContent=m.name+': highest and lowest';
  const row=([s,v],cls)=>`<div class="dw-bar ${cls}"><div class="dw-bar-name"><span>${NAMES[s]}</span></div><div class="dw-bar-track"><div class="dw-bar-fill" style="width:${Math.abs(v)/mx*100}%;background:${cm.startsWith('u')?css('--dw-blue'):css('--dw-purple')}"></div></div><div class="dw-bar-value dw-num">${m.l(v)}</div></div>`;
  $('cbars').innerHTML=arr.slice(0,5).map(x=>row(x,'')).join('')+'<div class="dw-note dw-gap-row">···</div>'+arr.slice(-5).map(x=>row(x,'')).join('');}
document.querySelectorAll('#cmode button').forEach(b=>b.onclick=()=>{cm=b.dataset.m;document.querySelectorAll('#cmode button').forEach(x=>x.setAttribute('aria-pressed',x===b));drawC();});
cRead(csel);

/* drugs */
const DG=D.drugs;
$('drugintro').textContent=`Total spending on prescription drugs under Medicare Part D was ${money(DG.total.y2024)} in 2024. That counts what Medicare, plans and patients paid together, before manufacturer rebates.`;
const DGM={
  top:{note:'Total Part D spending on each drug in 2024 (Medicare, plans and patients combined, before rebates), by brand-name listing: other forms and generics of the same medicine count separately.',v:d=>d.Tot_Spndng_2024,l:d=>money(d.Tot_Spndng_2024),sub:d=>fmt(d.Tot_Benes_2024)+' people'},
  per:{note:'Total yearly spending per patient in 2024, not what each patient paid out of pocket. Drugs with at least 1,000 Medicare patients.',v:d=>d.Avg_Spnd_Per_Bene_2024,l:d=>money(d.Avg_Spnd_Per_Bene_2024),sub:d=>fmt(d.Tot_Benes_2024)+' people'},
  growth:{note:'Growth in total spending from 2020 to 2024, among drugs with at least $100M of spending in 2020.',v:d=>d.Tot_Spndng_2024/d.Tot_Spndng_2020,l:d=>(d.Tot_Spndng_2024/d.Tot_Spndng_2020).toFixed(1)+'×',sub:d=>money(d.Tot_Spndng_2020)+' → '+money(d.Tot_Spndng_2024)},
  cheap:{note:'Lowest average total cost per prescription fill, 2024, among drugs taken by at least 2 million Medicare patients.',v:d=>d.Avg_Spnd_Per_Clm_2024,l:d=>money(d.Avg_Spnd_Per_Clm_2024),sub:d=>fmt(d.Tot_Benes_2024)+' people',low:true}
};
/* Same letters means a generic listed under its own name: say it once. */
const sameName=(a,b)=>String(a).toLowerCase().replace(/[^a-z]/g,'')===String(b).toLowerCase().replace(/[^a-z]/g,'');
function dgDraw(k){const m=DGM[k],rows=DG[k];const mx=Math.max(...rows.map(m.v));$('dgnote').textContent=m.note;
  /* The tag note only where a tag is shown; the tag gets its own row so the figures don't wrap. */
  $('dgprice').hidden=!rows.some(d=>d.medicare_price);
  /* Only where a drug whose price ends is listed. */
  $('dgends').hidden=!rows.some(d=>d.medicare_price&&d.medicare_price.until);
  $('dgbars').innerHTML=rows.map(d=>`<div class="dw-bar ${m.low?'dw-bar-low':''}${d.medicare_price?' dw-bar-tagged':''}"><div class="dw-bar-name"><span><b>${esc(d.Brnd_Name)}</b>${d.use?` <span class="dw-drug-use">for ${esc(d.use)}</span>`:''}${sameName(d.Brnd_Name,d.Gnrc_Name)?'':` <span class="dw-note">· ${esc(String(d.Gnrc_Name).toLowerCase())}</span>`}</span><span class="dw-note dw-num">${m.sub(d)}</span></div>${d.medicare_price?`<span class="dw-chip dw-bar-chip">${esc(d.medicare_price.label)}</span>`:''}<div class="dw-bar-track"><div class="dw-bar-fill" style="width:${m.v(d)/mx*100}%"></div></div><div class="dw-bar-value dw-num">${m.l(d)}</div></div>`).join('');}
document.querySelectorAll('#dgmode button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#dgmode button').forEach(x=>x.setAttribute('aria-pressed',x===b));dgDraw(b.dataset.m);});
dgDraw('top');

})();
