/* Shared UI helpers: company logos with a monogram fallback. Domains come from /markets/domains once. */
window.DDUI=(function(){
  var esc=function(x){return String(x==null?'':x).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
  var domains=null,pending=[];
  try{domains=JSON.parse(sessionStorage.getItem('dd.domains')||'null')}catch(e){}
  if(!domains){fetch('/markets/domains').then(function(r){return r.json()}).then(function(d){domains=d;try{sessionStorage.setItem('dd.domains',JSON.stringify(d))}catch(e){}
      pending.forEach(function(fn){fn()});pending=[];document.dispatchEvent(new CustomEvent('dd:domains'))}).catch(function(){domains={}})}
  function hue(s){var h=0;for(var i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))>>>0;return h%360}
  function initials(name,sym){var parts=String(name||sym||'?').replace(/\(.*?\)/g,'').trim().split(/\s+/);return ((parts[0]||'?')[0]+(parts[1]?parts[1][0]:'')).toUpperCase()}
  /* <span class="logo"> with an <img> when a domain is known; the monogram sits underneath and shows if the image fails */
  function logo(sym,name,domain){var d=domain||(domains&&domains[sym]);var mono='<span class="mono" style="--h:'+hue(sym||name||'')+'">'+esc(initials(name,sym))+'</span>';
    if(!d)return '<span class="logo">'+mono+'</span>';
    return '<span class="logo has"><img src="https://www.google.com/s2/favicons?domain='+encodeURIComponent(d)+'&sz=64" alt="" loading="lazy" onerror="this.parentNode.classList.remove(\'has\');this.remove()">'+mono+'</span>'}
  function ready(fn){if(domains)fn();else pending.push(fn)}
  function domain(sym){return domains&&domains[sym]||null}
  return {logo:logo,ready:ready,initials:initials,hue:hue,domain:domain};
})();
