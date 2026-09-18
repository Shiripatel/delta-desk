/* Shared header behaviour: the Markets item opens the market-analysis menu on hover (and on focus),
   and clicking it goes to the Markets overview. Injected so every page carries the same menu. */
(function(){
  /* theme: stored choice wins; otherwise Mist (light grey), or Ink when the system prefers dark */
  var THEMES=[['mist','Mist · light grey'],['white','White'],['paper','Paper · warm'],['ink','Ink · dark'],['midnight','Midnight · blue']];
  var theme=null;try{theme=localStorage.getItem('dd.theme')}catch(e){}
  if(theme==='dark')theme='ink';
  if(theme)document.documentElement.dataset.theme=theme;
  var status=document.querySelector('.status');
  if(status){var sel=document.createElement('select');sel.id='theme';sel.title='colour theme';
    sel.innerHTML=THEMES.map(function(t){return '<option value="'+t[0]+'">'+t[1]+'</option>'}).join('');
    var cur=theme||(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'ink':'mist');sel.value=cur;
    sel.addEventListener('change',function(){document.documentElement.dataset.theme=sel.value;try{localStorage.setItem('dd.theme',sel.value)}catch(e){}});
    var safe=document.getElementById('safe');status.insertBefore(sel,safe||null)}
  var link=document.querySelector('.nav a[href="/markets"]');if(!link||link.closest('.has-mega'))return;
  var cols=[
    ['Real-time quotes',[['stocks','Stock market','indices, constituents, movers'],['options','Options market','NIFTY chain, IV, OI, Greeks'],['futures','Futures market','index futures, basis, OI'],['etf','ETF market','index, gold, silver, global'],['forex','Forex market','USDINR, EURINR, GBPINR, JPYINR']]],
    ['Technical tools',[['screener','Stock screener','index, sector, change, price'],['heatmap','Heat map','weight × change, breadth'],['ai','AI ranking','score, win rate, forecast, risk'],['radar','AI radar','bullseye of scores, replay 5 days'],['earnings','Earnings calendar','results dates'],['flows','Institutional tracker','FII / DII daily flows'],['ipo','IPO tracker','upcoming, open, listing']]],
    ['Trading news',[['news','Headlines','latest from public feeds'],['calendar','Financial calendar','expiries, holidays, RBI'],['trending','Trending topics','terms across headlines'],['watchlist','Watchlist','your lists, any asset class']]]
  ];
  var wrap=document.createElement('span');wrap.className='has-mega';link.parentNode.insertBefore(wrap,link);wrap.appendChild(link);
  var mega=document.createElement('div');mega.className='mega';mega.setAttribute('role','menu');
  mega.innerHTML='<div class="cols">'+cols.map(function(c){return '<div><h5>'+c[0]+'</h5>'+c[1].map(function(i){return '<a href="/markets#/'+i[0]+'" data-view="'+i[0]+'">'+i[1]+'<small>'+i[2]+'</small></a>'}).join('')+'</div>'}).join('')+'</div>';
  wrap.appendChild(mega);
  /* on the markets page a menu click only changes the hash; make sure the router runs even for the same hash */
  mega.addEventListener('click',function(e){var a=e.target.closest('a[data-view]');if(!a)return;if(location.pathname==='/markets'){e.preventDefault();var h='#/'+a.dataset.view;if(location.hash===h)window.dispatchEvent(new HashChangeEvent('hashchange'));else location.hash=h;wrap.classList.remove('open')}});
  link.addEventListener('click',function(e){if(location.pathname==='/markets'){e.preventDefault();if(location.hash==='#/overview'||location.hash===''){location.hash='#/overview';window.dispatchEvent(new HashChangeEvent('hashchange'))}else location.hash='#/overview'}});
  document.addEventListener('keydown',function(e){if(e.key==='Escape')wrap.classList.remove('open')});
})();
