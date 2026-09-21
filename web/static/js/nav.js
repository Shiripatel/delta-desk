/* Shared header: theme choice, the Join-beta pill and the legal footer, injected so every page carries the same. */
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
  /* beta pill in the header, standard footer on every page */
  if(status&&!document.getElementById('betaLink')&&location.pathname!=='/beta'){var b=document.createElement('a');b.id='betaLink';b.href='/beta';b.className='beta';b.textContent='Join beta';status.insertBefore(b,status.firstChild)}
  var foot=document.querySelector('footer .wrap');
  if(foot){var y=new Date().getFullYear();foot.className='wrap legal';foot.innerHTML='<div class="l1"><b>✢ Delta Desk</b> · beta · an agentic desk for Indian markets. Paper trading only. Nothing here is investment advice.</div>'+
    '<div class="l2">Delta Desk is not a SEBI-registered investment adviser, research analyst or broker. Every score, verdict, forecast and impact call is the output of a transparent rules model (v0) for information and education only. Equity and F&amp;O trading carries risk of loss; a large majority of individual F&amp;O traders lose money. Quotes are delayed about 15 minutes unless marked live. Data: Yahoo Finance, TradingView, NSE Indices, public RSS feeds; logos belong to their owners.</div>'+
    '<div class="l3"><span>© '+y+' Delta Desk. All rights reserved.</span><span><a href="/legal#disclaimer">Disclaimer</a><a href="/legal#risk">Risk disclosure</a><a href="/legal#terms">Terms</a><a href="/legal#privacy">Privacy</a><a href="/legal#data">Data sources</a><a href="/legal#contact">Contact</a><a href="/beta">Beta &amp; alerts</a></span></div>'}
})();
