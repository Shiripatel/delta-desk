/* Shared header: theme choice, the Join-beta pill and the legal footer, injected so every page carries the same. */
(function(){
  /* theme: stored choice wins; otherwise Mist (light grey), or Ink when the system prefers dark */
  var THEMES=[['mist','Mist · light grey'],['white','White'],['ink','Ink · dark']];
  var theme=null;try{theme=localStorage.getItem('dd.theme')}catch(e){}
  if(theme==='dark')theme='ink';if(theme==='paper'||theme==='midnight'){theme='mist';try{localStorage.setItem('dd.theme',theme)}catch(e){}}
  if(theme)document.documentElement.dataset.theme=theme;
  var status=document.querySelector('.status');
  if(status){var sel=document.createElement('select');sel.id='theme';sel.title='colour theme';
    sel.innerHTML=THEMES.map(function(t){return '<option value="'+t[0]+'">'+t[1]+'</option>'}).join('');
    var cur=theme||(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'ink':'mist');sel.value=cur;
    sel.addEventListener('change',function(){document.documentElement.dataset.theme=sel.value;try{localStorage.setItem('dd.theme',sel.value)}catch(e){}});
    status.appendChild(sel)}
  /* beta pill in the header, standard footer on every page */
  if(status&&!document.getElementById('betaLink')&&location.pathname!=='/beta'){var b=document.createElement('a');b.id='betaLink';b.href='/beta';b.className='beta';b.textContent='Join beta';status.insertBefore(b,status.firstChild)}
  var foot=document.querySelector('footer .wrap');
  if(foot){var y=new Date().getFullYear();foot.className='wrap legal';foot.innerHTML='<div class="l1"><b>✢ Delta Desk</b> · beta · an agentic desk for Indian markets. Paper trading only. Nothing here is investment advice.</div>'+
    '<div class="l2">Delta Desk is not a SEBI-registered investment adviser, research analyst or broker. Every score, verdict, forecast and impact call is the output of a transparent rules model (v0) for information and education only. Equity and F&amp;O trading carries risk of loss; a large majority of individual F&amp;O traders lose money. Quotes are delayed about 15 minutes unless marked live. Data: Yahoo Finance, TradingView, NSE Indices, public RSS feeds; logos belong to their owners.</div>'+
    '<div class="l3"><span>© '+y+' Delta Desk. All rights reserved.</span><span><a href="/legal#disclaimer">Disclaimer</a><a href="/legal#risk">Risk disclosure</a><a href="/legal#terms">Terms</a><a href="/legal#privacy">Privacy</a><a href="/legal#data">Data sources</a><a href="/legal#contact">Contact</a><a href="/beta">Beta &amp; alerts</a></span></div>'}
})();

/* Global search (Ctrl K or /), the mobile bottom bar and its More sheet. Injected on every page. */
(function(){
  var D=window.DD;if(!D)return;
  var ICON={search:'<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',home:'<svg viewBox="0 0 24 24"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>',
    star:'<svg viewBox="0 0 24 24"><path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z"/></svg>',news:'<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h10M7 17h6"/></svg>',
    more:'<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/></svg>'};
  /* header search button */
  var status=document.querySelector('.status');
  if(status&&!document.getElementById('ddSearch')){var sb=document.createElement('button');sb.id='ddSearch';sb.className='sbtn';sb.type='button';sb.title='Search any symbol (Ctrl K)';sb.innerHTML=ICON.search+'<span>Search</span><kbd>Ctrl K</kbd>';status.insertBefore(sb,status.firstChild);sb.addEventListener('click',open)}
  /* palette */
  var pal=document.createElement('div');pal.id='ddPalette';pal.className='palette';pal.hidden=true;pal.setAttribute('role','dialog');pal.setAttribute('aria-label','Search');
  pal.innerHTML='<div class="pal-box"><input id="ddPalQ" placeholder="Search stocks, indices, ETFs, FX, commodities…" autocomplete="off" spellcheck="false"><div class="pal-list" id="ddPalList"></div><div class="pal-hint">↑ ↓ move · Enter opens the analysis · <b>+ watch</b> adds to your watchlist · Esc closes</div></div>';
  document.body.appendChild(pal);
  var q=pal.querySelector('#ddPalQ'),list=pal.querySelector('#ddPalList'),rows=[],sel=0,timer=null,last='';
  function open(){pal.hidden=false;q.value='';list.innerHTML='<div class="pal-empty">Start typing: RELIANCE, nifty, gold, usdinr…</div>';rows=[];setTimeout(function(){q.focus()},0)}
  function close(){pal.hidden=true}
  function paint(){list.innerHTML=rows.length?rows.map(function(r,i){return '<button data-key="'+D.esc(r.key)+'" aria-selected="'+(i===sel)+'"><span><b>'+D.esc(r.key)+'</b><small>'+D.esc(r.name)+(r.sector?' · '+D.esc(r.sector):'')+'</small></span><span class="pill">'+D.esc(r.kind)+'</span><span class="add" data-add="'+D.esc(r.key)+'">+ watch</span></button>'}).join(''):'<div class="pal-empty">No match. Try the NSE symbol or the first word of the name.</div>'}
  function search(v){if(v===last)return;last=v;D.get('/markets/search?q='+encodeURIComponent(v)).then(function(rs){rows=rs;sel=0;paint()}).catch(function(){})}
  function go(key){location.href='/analysis#'+encodeURIComponent(key)+'/3m/fundamental';if(location.pathname==='/analysis'){location.reload()}}
  q.addEventListener('input',function(){clearTimeout(timer);var v=q.value.trim();if(!v){rows=[];list.innerHTML='<div class="pal-empty">Start typing: RELIANCE, nifty, gold, usdinr…</div>';return}timer=setTimeout(function(){search(v)},110)});
  q.addEventListener('keydown',function(e){if(e.key==='ArrowDown'){e.preventDefault();if(rows.length){sel=(sel+1)%rows.length;paint()}}else if(e.key==='ArrowUp'){e.preventDefault();if(rows.length){sel=(sel-1+rows.length)%rows.length;paint()}}
    else if(e.key==='Enter'){e.preventDefault();if(rows[sel])go(rows[sel].key);else if(q.value.trim())go(q.value.trim().toUpperCase())}else if(e.key==='Escape'){close()}});
  list.addEventListener('click',function(e){var a=e.target.closest('[data-add]');if(a){e.stopPropagation();D.watch(a.dataset.add).then(function(){a.textContent='✓ watching'}).catch(function(){});return}var b=e.target.closest('button[data-key]');if(b)go(b.dataset.key)});
  pal.addEventListener('click',function(e){if(e.target===pal)close()});
  document.addEventListener('keydown',function(e){var tag=(e.target&&e.target.tagName||'').toLowerCase();var typing=tag==='input'||tag==='textarea'||tag==='select'||(e.target&&e.target.isContentEditable);
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(pal.hidden)open();else close();return}
    if(e.key==='/'&&!typing&&pal.hidden){e.preventDefault();open();return}
    if(e.key==='Escape'&&!pal.hidden){close()}});
  /* mobile bottom bar */
  if(!document.getElementById('ddBottom')){var path=location.pathname;var cur=function(h){return (h==='/'?path==='/':path.indexOf(h)===0)?' aria-current="page"':''};
    var bar=document.createElement('nav');bar.id='ddBottom';bar.className='bottom';bar.setAttribute('aria-label','Main');
    bar.innerHTML='<a href="/"'+cur('/')+'>'+ICON.home+'Home</a><a href="/watchlist"'+cur('/watchlist')+'>'+ICON.star+'Watchlist</a><button type="button" id="ddBottomSearch">'+ICON.search+'Search</button><a href="/news"'+cur('/news')+'>'+ICON.news+'News</a><button type="button" id="ddMore">'+ICON.more+'More</button>';
    document.body.appendChild(bar);bar.querySelector('#ddBottomSearch').addEventListener('click',open);
    var bg=document.createElement('div');bg.className='sheet-bg';var sh=document.createElement('div');sh.className='sheet';sh.setAttribute('role','menu');
    sh.innerHTML=[['/heatmap','Heatmap'],['/ipo','IPO'],['/forex','Forex'],['/global','Global'],['/desk','Agents'],['/sniper','Sniper'],['/beta','Beta & alerts'],['/legal','Legal']].map(function(x){return '<a href="'+x[0]+'"'+cur(x[0])+'>'+x[1]+'</a>'}).join('');
    document.body.appendChild(bg);document.body.appendChild(sh);
    function toggle(on){sh.classList.toggle('open',on);bg.classList.toggle('open',on)}
    bar.querySelector('#ddMore').addEventListener('click',function(){toggle(!sh.classList.contains('open'))});bg.addEventListener('click',function(){toggle(false)})}
})();
