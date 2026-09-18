/* Watchlist pane: multiple named lists, search-to-add, live quotes every 3 s. Talks to /markets/watchlist. */
(function(){
  var pane=document.getElementById('wlPane');if(!pane)return;
  var $=function(s,r){return (r||pane).querySelector(s)};
  var fmt=function(n,d){return Number(n).toLocaleString('en-IN',{minimumFractionDigits:d==null?2:d,maximumFractionDigits:d==null?2:d})};
  var esc=function(x){return String(x==null?'':x).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
  var cls=function(x){return x>0.005?'up':x<-0.005?'dn':''};
  function get(u){return fetch(u).then(function(r){if(!r.ok)throw new Error(r.status);return r.json()})}
  function send(m,u){return fetch(u,{method:m}).then(function(r){return r.json()})}
  var data=null,active=null;
  try{active=localStorage.getItem('dd.wl.active')}catch(e){}

  pane.innerHTML='<div class="hd"><input id="wlq" placeholder="Search eg: infy, nifty fut, gold bees" autocomplete="off"><span class="cnt" id="wlCnt"></span><div class="sug" id="wlSug"></div></div>'+
    '<div class="rows" id="wlRows"></div><div class="ft" id="wlFt"></div>';

  function name(){var names=Object.keys(data.lists);if(!active||names.indexOf(active)<0)active=names[0];return active}
  function render(d){data=d;var n=name(),rows=d.lists[n]||[];
    $('#wlCnt').textContent=rows.length+' / 250';
    $('#wlRows').innerHTML=rows.length?rows.map(function(r){var q=r.quote||{};var dd=r.kind==='forex'?4:2;var kindTag=r.kind==='stock'?'NSE':r.kind==='index'?'IDX':r.kind==='future'?'FUT':r.kind.toUpperCase();
      return '<div class="wlrow" data-key="'+esc(r.key)+'"><span class="sym">'+esc(r.key.replace(/^FUT:[A-Z0-9]+:/,''))+'<small>'+esc(kindTag)+'</small><em>'+esc(r.name)+'</em></span>'+
        '<span class="chg num '+cls(q.change||0)+'">'+(q.change!=null?(q.change>0?'+':'')+fmt(q.change,dd):'—')+'</span>'+
        '<span class="pct num '+cls(q.change_pct||0)+'">'+(q.change_pct!=null?(q.change_pct>0?'+':'')+fmt(q.change_pct)+'%':'—')+'</span>'+
        '<span class="ltp num '+cls(q.change||0)+'">'+(q.ltp!=null?fmt(q.ltp,dd):'—')+'</span>'+
        '<span class="act"><button class="a" data-act="agent" title="Send to the desk (coming: run the agents on this symbol)">agents</button><button class="x" data-act="rm" title="Remove">✕</button></span></div>'}).join('')
      :'<div class="empty">Empty list. Search above to add stocks, indices, futures, ETFs or currency pairs.</div>';
    var names=Object.keys(d.lists);
    $('#wlFt').innerHTML=names.map(function(x,i){return '<button data-list="'+esc(x)+'" aria-pressed="'+(x===n)+'" title="'+esc(x)+'">'+(i+1)+' · '+esc(x)+'</button>'}).join('')+'<button class="new" data-act="new">+ new</button>'+(names.length>1?'<button class="del" data-act="del" title="Delete this list">delete</button>':'');
    document.dispatchEvent(new CustomEvent('dd:watchlist',{detail:{active:n,keys:rows.map(function(r){return r.key})}}))}
  function load(){return get('/markets/watchlist').then(render).catch(function(){$('#wlRows').innerHTML='<div class="empty">watchlist unavailable (is deltadesk serve running?)</div>'})}

  pane.addEventListener('click',function(e){
    var b=e.target.closest('button[data-list]');if(b){active=b.dataset.list;try{localStorage.setItem('dd.wl.active',active)}catch(x){}render(data);return}
    var a=e.target.closest('button[data-act]');if(!a)return;
    if(a.dataset.act==='rm'){send('DELETE','/markets/watchlist/'+encodeURIComponent(name())+'/'+encodeURIComponent(a.closest('.wlrow').dataset.key)).then(render)}
    else if(a.dataset.act==='new'){var n=prompt('New watchlist name');if(n){send('POST','/markets/watchlist/'+encodeURIComponent(n)).then(function(d){active=n;render(d)})}}
    else if(a.dataset.act==='del'){if(confirm('Delete watchlist "'+name()+'"?'))send('DELETE','/markets/watchlist/'+encodeURIComponent(name())).then(function(d){active=null;render(d)})}
    else if(a.dataset.act==='agent'){document.dispatchEvent(new CustomEvent('dd:agent-symbol',{detail:{key:a.closest('.wlrow').dataset.key}}))}
  });
  var q=$('#wlq'),sug=$('#wlSug'),timer=null;
  q.addEventListener('input',function(){clearTimeout(timer);var v=q.value.trim();if(!v){sug.style.display='none';return}
    timer=setTimeout(function(){get('/markets/search?q='+encodeURIComponent(v)).then(function(rs){sug.innerHTML=rs.map(function(r){return '<button data-key="'+esc(r.key)+'"><span><b>'+esc(r.key)+'</b> <span style="color:var(--ink-3)">'+esc(r.name)+'</span></span><span style="color:var(--ink-3)">'+esc(r.kind==='stock'?r.sector:r.kind)+'</span></button>'}).join('')||'<button disabled>no match</button>';sug.style.display='block'})},120)});
  q.addEventListener('keydown',function(e){if(e.key==='Escape'){sug.style.display='none';q.blur()}});
  sug.addEventListener('click',function(e){var b=e.target.closest('button[data-key]');if(!b)return;send('POST','/markets/watchlist/'+encodeURIComponent(name())+'/'+encodeURIComponent(b.dataset.key)).then(render);q.value='';sug.style.display='none'});
  document.addEventListener('click',function(e){if(!e.target.closest('.wlpane .hd'))sug.style.display='none'});
  document.addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();q.focus();q.select()}});
  var tg=document.getElementById('wlToggle');if(tg)tg.addEventListener('click',function(){pane.dataset.open=pane.dataset.open==='1'?'0':'1'});

  load();setInterval(function(){if(!document.hidden)load()},3000);
})();
