/* Shared page helpers. Every page loads this before its own script and uses window.DD:
   formatting (fmt, pct, esc, pad), fetch (get), the IST clock and the index ticker. */
window.DD=(function(){
  var D={};
  D.fmt=function(n,d){return Number(n).toLocaleString('en-IN',{minimumFractionDigits:d==null?2:d,maximumFractionDigits:d==null?2:d})};
  D.esc=function(x){return String(x==null?'':x).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
  D.pct=function(x){return x==null?'—':(x>0?'+':'')+D.fmt(x)+' %'};
  D.cls=function(x,eps){eps=eps==null?0.005:eps;return x>eps?'up':x<-eps?'dn':''};
  D.pad=function(x){return (x<10?'0':'')+x};
  D.get=function(u){return fetch(u).then(function(r){if(!r.ok)throw new Error(r.status);return r.json()})};
  /* IST clock in #clock */
  D.clock=function(){var el=document.getElementById('clock');if(!el)return;(function tick(){var n=new Date(),t=new Date(n.getTime()+(330+n.getTimezoneOffset())*60000);el.textContent=D.pad(t.getHours())+':'+D.pad(t.getMinutes())+' IST';setTimeout(tick,1000)})()};
  /* index ticker in #ticker: o.endpoint (/markets/indices or /markets/indicators), o.order (keys), o.every (ms) */
  D.ticker=function(o){var box=document.getElementById('ticker');if(!box)return;o=o||{};var endpoint=o.endpoint||'/markets/indices',order=o.order||['NIFTY50','BANKNIFTY','FINNIFTY','SENSEX','INDIAVIX'],every=o.every||10000;
    function paint(){D.get(endpoint).then(function(list){var by={};list.forEach(function(i){by[i.code||i.key]=i});
      box.innerHTML=order.map(function(c){var ix=by[c];if(!ix)return '';var q=ix.quote,d=ix.decimals!=null?ix.decimals:2;return '<a href="/analysis#'+D.esc(c)+'/3m" data-sym="'+D.esc(c)+'"><span class="n">'+D.esc(ix.name)+'</span><span class="v num">'+(q?D.fmt(q.ltp,d):'—')+'</span><span class="c num '+(q?D.cls(q.change_pct):'')+'">'+(q?D.pct(q.change_pct):'no data')+'</span></a>'}).join('')+'<span class="src">'+D.esc(window.__src||'')+'</span>'}).catch(function(){})}
    D.get('/markets/source').then(function(s){window.__src=s.name+(s.delay_min?' · '+s.delay_min+' min delayed':' · live');paint()}).catch(paint);
    setInterval(function(){if(!document.hidden)paint()},every)};
  D.boot=function(){D.clock()};
  return D;
})();
