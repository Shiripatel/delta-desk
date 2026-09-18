/* Shared AI components: ranking table and radar. Talks to /markets/ai and /markets/radar.
   Usage: DDAI.ranking({...ids}) and DDAI.radar({...ids}); both return {load(index), refresh()}. */
window.DDAI=(function(){
  var fmt=function(n,d){return Number(n).toLocaleString('en-IN',{minimumFractionDigits:d==null?2:d,maximumFractionDigits:d==null?2:d})};
  var esc=function(x){return String(x==null?'':x).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
  var pct=function(x){return x==null?'—':(x>0?'+':'')+fmt(x)+' %'};
  var cls=function(x){return x>0.05?'up':x<-0.05?'dn':''};
  function get(u){return fetch(u).then(function(r){if(!r.ok)throw new Error(r.status);return r.json()})}
  function hash(s){var h=0;for(var i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))>>>0;return h}
  function band(s){return s>=7?'g':s>=4?'a':'r'}
  function inWl(sym){return !!(window.DDWL&&window.DDWL.has(sym))}
  function starBtn(sym){if(!window.DDWL)return '';var on=inWl(sym);return '<button class="star" data-star="'+esc(sym)+'" aria-pressed="'+on+'" title="'+(on?'remove from':'add to')+' watchlist">'+(on?'★':'☆')+'</button>'}
  function bindStars(root){root.addEventListener('click',function(e){var b=e.target.closest('button[data-star]');if(!b||!window.DDWL)return;e.stopPropagation();
    var on=b.getAttribute('aria-pressed')==='true';(on?window.DDWL.remove(b.dataset.star):window.DDWL.add(b.dataset.star)).then(function(){b.setAttribute('aria-pressed',String(!on));b.textContent=on?'☆':'★'})})}
  function mono(name,sym){if(window.DDUI)return window.DDUI.logo(sym,name);var h=0;for(var i=0;i<sym.length;i++)h=(h*31+sym.charCodeAt(i))>>>0;var parts=(name||sym).split(/\s+/);return '<span class="mono" style="--h:'+(h%360)+'">'+esc(((parts[0]||'?')[0]+(parts[1]?parts[1][0]:'')).toUpperCase())+'</span>'}
  function ring(v,max){var p=Math.max(0,Math.min(1,v/max)),c=2*Math.PI*14;
    return '<span class="ring '+band(v)+'" title="'+v+' / '+max+'"><svg viewBox="0 0 34 34" aria-hidden="true"><circle class="bg" cx="17" cy="17" r="14"/><circle class="fg" cx="17" cy="17" r="14" stroke-dasharray="'+(c*p).toFixed(1)+' '+c.toFixed(1)+'"/></svg><b>'+v+'</b></span>'}
  function spark(pts){if(!pts||pts.length<2)return '';var W=84,H=28,lo=Math.min.apply(null,pts),hi=Math.max.apply(null,pts),rg=hi-lo||1;
    var xy=pts.map(function(p,i){return [(i/(pts.length-1))*(W-2)+1,H-2-((p-lo)/rg)*(H-4)]});
    var d=xy.map(function(q,i){return (i?'L':'M')+q[0].toFixed(1)+' '+q[1].toFixed(1)}).join(' ');
    return '<svg class="spark" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="3-month price path"><path class="a" d="'+d+' L'+xy[xy.length-1][0].toFixed(1)+' '+H+' L'+xy[0][0].toFixed(1)+' '+H+' Z"/><path class="l" d="'+d+'"/></svg>'}

  /* ---- ranking table ---------------------------------------------------------------- */
  function ranking(o){
    var head=document.getElementById(o.head),body=document.getElementById(o.body),meta=document.getElementById(o.meta),note=o.note&&document.getElementById(o.note);
    var data=null,key='score',dir='desc',limit=o.limit||50,index=o.index||'NIFTY50',mode=o.mode||'short';
    function render(){if(!data)return;var rows=data.entries.slice().sort(function(a,b){var x=a[key],y=b[key];x=x==null?-1e9:x;y=y==null?-1e9:y;return dir==='asc'?x-y:y-x});
      body.innerHTML=rows.map(function(r){return '<tr><td class="num muted">'+r.rank+'</td><td class="co"><span class="cowrap">'+mono(r.name,r.symbol)+'<span>'+starBtn(r.symbol)+' <a href="/analysis#'+esc(r.symbol)+'/3m" title="open analysis"><b>'+esc(r.symbol)+'</b></a><em>'+esc(r.name)+'</em></span></span></td><td class="muted">'+esc(r.sector)+'</td>'+
        '<td class="num"><b>'+(r.win_rate==null?'—':fmt(r.win_rate,1)+' %')+'</b></td><td class="num">'+ring(r.score,10)+'</td><td class="num '+cls(r.forecast_3m)+'">'+pct(r.forecast_3m)+'</td>'+
        '<td class="num '+cls(r.ret_3m)+'">'+pct(r.ret_3m)+'</td><td>'+spark(r.spark)+'</td><td class="num">'+ring(r.risk,10)+'</td><td class="num muted">'+fmt(r.weight,1)+'</td></tr>'}).join('')
        ||'<tr><td colspan="10" class="muted">no history available for this universe</td></tr>';
      if(meta)meta.textContent=data.count+' ranked · showing '+rows.length+' · '+(data.mode||'short')+' term · history: '+data.source+' · computed '+new Date(data.computed_at*1000).toTimeString().slice(0,5);
      if(note)note.textContent=data.note;
      if(o.onData)o.onData(data)}
    function load(ix,lim,md){if(ix!=null)index=ix;if(lim!=null)limit=lim;if(md!=null)mode=md;if(meta)meta.textContent='computing… (first run fetches history per symbol)';
      return get('/markets/ai?index='+encodeURIComponent(index)+'&limit='+limit+'&mode='+mode).then(function(d){data=d;render()}).catch(function(e){if(meta)meta.textContent='failed: '+e})}
    head.addEventListener('click',function(e){var b=e.target.closest('button[data-k]');if(!b)return;if(key===b.dataset.k)dir=dir==='desc'?'asc':'desc';else{key=b.dataset.k;dir='desc'}
      Array.prototype.forEach.call(head.querySelectorAll('button[data-k]'),function(x){x.removeAttribute('data-dir')});b.dataset.dir=dir;render()});
    bindStars(body);
    document.addEventListener('dd:watchlist',function(){if(data)render()});
    document.addEventListener('dd:domains',function(){if(data)render()});
    return {load:load,refresh:render,data:function(){return data}};
  }

  /* ---- radar ---------------------------------------------------------------------------- */
  function radar(o){
    var svg=document.getElementById(o.svg),box=document.getElementById(o.box),tip=document.getElementById(o.tip),play=document.getElementById(o.play),
        scrub=document.getElementById(o.scrub),day=document.getElementById(o.day),movers=o.movers&&document.getElementById(o.movers),meta=document.getElementById(o.meta),
        note=o.note&&document.getElementById(o.note),picks=o.picks&&document.getElementById(o.picks);
    var rd=null,frame=0,timer=null,index=o.index||'NIFTY50',days=o.days||5,C=340,trails=o.trails!==false,mode=o.mode||'short';
    function pos(p,sectors){var n=sectors.length,si=Math.max(0,sectors.indexOf(p.sector)),base=(si/n)*2*Math.PI-Math.PI/2,spread=(2*Math.PI/n)*0.78;
      var ang=base+((hash(p.symbol)%1000)/1000-0.5)*spread;var r=34+(10-p.score)*30+((hash(p.symbol+'r')%100)/100-0.5)*14;
      return [C+r*Math.cos(ang),C+r*Math.sin(ang)]}
    function build(sectors){var n=sectors.length,s='';
      for(var sc=1;sc<=10;sc++){var r=34+(10-sc)*30;s+='<circle class="ring-r'+(sc>=7?' buy':sc<=3?' sell':' hold')+'" cx="'+C+'" cy="'+C+'" r="'+r+'"/>';if(sc%3===1||sc===10)s+='<text x="'+(C+4)+'" y="'+(C-r+11)+'">'+sc+'</text>'}
      s+='<text class="zone" x="'+C+'" y="'+(C-34-30*3+22)+'" text-anchor="middle">buy zone</text><text class="zone" x="'+C+'" y="'+(C+34+30*5.5)+'" text-anchor="middle">hold · no trade</text><text class="zone" x="'+C+'" y="'+(C+34+30*8.5)+'" text-anchor="middle">sell zone</text>';
      sectors.forEach(function(sec,i){var a=(i/n)*2*Math.PI-Math.PI/2;s+='<line class="spoke" x1="'+(C+34*Math.cos(a))+'" y1="'+(C+34*Math.sin(a))+'" x2="'+(C+318*Math.cos(a))+'" y2="'+(C+318*Math.sin(a))+'"/>';
        var am=a+Math.PI/n,lx=C+330*Math.cos(am),ly=C+330*Math.sin(am);s+='<text class="lbl" x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'" text-anchor="'+(Math.cos(am)>0.2?'start':Math.cos(am)<-0.2?'end':'middle')+'">'+esc(sec)+'</text>'});
      s+='<g class="trails"></g><g class="pts"></g>';svg.innerHTML=s}
    function draw(){if(!rd)return;var f=rd.frames[frame],sectors=rd.sectors;
      var g=svg.querySelector('.pts'),tg=svg.querySelector('.trails'),have={};Array.prototype.forEach.call(g.children,function(el){have[el.dataset.sym]=el});
      var t='';
      f.points.forEach(function(p){var xy=pos(p,sectors),r=(3.5+Math.sqrt(p.weight)*2.2).toFixed(1),el=have[p.symbol];
        if(!el){el=document.createElementNS('http://www.w3.org/2000/svg','g');el.dataset.sym=p.symbol;el.innerHTML='<circle r="'+r+'"/>'+(p.weight>=2?'<text x="'+(+r+3)+'" y="3.5">'+esc(p.symbol)+'</text>':'');g.appendChild(el)}
        el.setAttribute('class','pt '+band(p.score)+(inWl(p.symbol)?' wl':''));el.style.transform='translate('+xy[0].toFixed(1)+'px,'+xy[1].toFixed(1)+'px)';delete have[p.symbol];
        if(trails&&frame>0){var pts=[];for(var k=0;k<=frame;k++){var q=rd.frames[k].points.filter(function(x){return x.symbol===p.symbol})[0];if(q)pts.push(pos(q,sectors))}
          if(pts.length>1&&pts.some(function(q){return Math.abs(q[0]-pts[0][0])+Math.abs(q[1]-pts[0][1])>1}))t+='<path class="trail" d="'+pts.map(function(q,i){return (i?'L':'M')+q[0].toFixed(1)+' '+q[1].toFixed(1)}).join(' ')+'"/>'}});
      Object.keys(have).forEach(function(k){have[k].remove()});tg.innerHTML=t;
      if(day)day.textContent=(f.asof||'—')+' · session '+(frame+1)+' / '+rd.frames.length;if(scrub)scrub.value=frame;
      var first=rd.frames[0].points.reduce(function(m,p){m[p.symbol]=p.score;return m},{});
      if(movers){var mv=f.points.filter(function(p){return first[p.symbol]!=null}).map(function(p){return {s:p.symbol,a:first[p.symbol],b:p.score,d:p.score-first[p.symbol]}}).filter(function(x){return x.d}).sort(function(x,y){return Math.abs(y.d)-Math.abs(x.d)}).slice(0,8);
        movers.innerHTML=mv.map(function(x){return '<tr><td><b>'+esc(x.s)+'</b></td><td class="num muted">'+x.a+'</td><td class="num '+(x.d>0?'up':'dn')+'">'+x.b+' ('+(x.d>0?'+':'')+x.d+')</td></tr>'}).join('')||'<tr><td colspan="3" class="muted">no score changes in the window</td></tr>'}
      if(picks){var top=f.points.filter(function(p){return p.score>=7}).sort(function(a,b){return b.score-a.score||b.weight-a.weight}).slice(0,8);
        picks.innerHTML=top.map(function(p){return '<div class="pick"><span class="cowrap">'+mono(p.name,p.symbol)+'<span>'+starBtn(p.symbol)+' <a href="/analysis#'+esc(p.symbol)+'/3m"><b>'+esc(p.symbol)+'</b></a> <em>'+esc(p.name)+'</em></span></span>'+ring(p.score,10)+'</div>'}).join('')||'<div class="muted" style="padding:8px 0">nothing in the buy zone in this universe today</div>'}
      if(o.onFrame)o.onFrame(f,frame,rd)}
    function stop(){clearInterval(timer);timer=null;if(play){play.textContent='▶ replay '+days+' '+(rd&&rd.step==='week'?'weeks':'sessions');play.classList.remove('on')}}
    function load(ix,md){if(ix!=null)index=ix;if(md!=null)mode=md;stop();if(meta)meta.textContent='computing… (first run fetches history per symbol)';
      return get('/markets/radar?index='+encodeURIComponent(index)+'&days='+days+'&mode='+mode).then(function(d){rd=d;frame=d.frames.length-1;if(scrub)scrub.max=d.frames.length-1;build(d.sectors);
        if(meta)meta.textContent=d.frames[frame].points.length+' stocks · '+(d.mode||'short')+' term · history: '+d.source+' · last '+d.frames.length+' '+(d.step==='week'?'weeks':'sessions');if(note)note.textContent=d.note;stop();draw()}).catch(function(e){if(meta)meta.textContent='failed: '+e})}
    if(play)play.addEventListener('click',function(){if(timer){stop();return}if(!rd)return;frame=0;draw();play.textContent='■ stop';play.classList.add('on');
      timer=setInterval(function(){if(frame>=rd.frames.length-1){stop();return}frame++;draw()},1100)});
    if(scrub)scrub.addEventListener('input',function(){stop();frame=+this.value;draw()});
    svg.addEventListener('mousemove',function(e){var g=e.target.closest('.pt');if(!g||!rd){tip.style.display='none';return}var p=rd.frames[frame].points.filter(function(x){return x.symbol===g.dataset.sym})[0];if(!p)return;
      tip.style.display='block';tip.innerHTML='<b>'+esc(p.symbol)+'</b> '+esc(p.name)+'<br>score '+p.score+' · low-risk '+p.risk+' · forecast 3M '+pct(p.forecast_3m)+'<br>last '+fmt(p.last)+' · 1d '+pct(p.ret_1d)+' · 1M '+pct(p.ret_1m)+' · wt '+fmt(p.weight,1)+' %<br>click: chart'+(window.DDWL?' · shift-click: watchlist':'');
      var b=box.getBoundingClientRect();tip.style.left=(e.clientX-b.left+14)+'px';tip.style.top=(e.clientY-b.top+14)+'px'});
    svg.addEventListener('mouseleave',function(){tip.style.display='none'});
    svg.addEventListener('click',function(e){var g=e.target.closest('.pt');if(!g)return;var s=g.dataset.sym;if(e.shiftKey&&window.DDWL){(inWl(s)?window.DDWL.remove(s):window.DDWL.add(s)).then(draw);return}location.href='/analysis#'+encodeURIComponent(s)+'/3m'});
    if(picks)bindStars(picks);
    document.addEventListener('dd:watchlist',function(){if(rd)draw()});
    return {load:load,refresh:draw,data:function(){return rd}};
  }
  return {ranking:ranking,radar:radar,ring:ring,spark:spark,fmt:fmt,esc:esc,pct:pct,cls:cls,get:get};
})();
