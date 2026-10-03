
/* DESTINATION OVERRIDE -- additive, revert by deleting the <script> tag.
   Re-renders the destination list from the same /api/nodes data, using the
   same input values (chan:N / dm:<name>), so the existing send code is
   untouched. Adds: Contacts | Channels split, star-to-favorite (localStorage),
   favorites sorted to the top. */
(function () {
  var KEY = 'mc.favorites.v1';
  var DATA = [];

  function favs(){ try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch(e){ return []; } }
  function isFav(id){ return favs().indexOf(id) >= 0; }
  function toggle(id){
    var f = favs(), i = f.indexOf(id);
    if (i >= 0) f.splice(i,1); else f.push(id);
    localStorage.setItem(KEY, JSON.stringify(f));
    render();
  }
  function esc(s){ return String(s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }

  function row(it){
    return '<label class="drow' + (isFav(it.id)?' fav':'') + '">' +
      '<input type="checkbox" value="' + esc(it.id) + '">' +
      '<span class="dname">' + esc(it.name) + '</span>' +
      '<span class="did">' + esc(it.id) + '</span>' +
      '<button type="button" class="star" data-id="' + esc(it.id) + '" title="Favorite">' +
        (isFav(it.id)?'\u2605':'\u2606') + '</button></label>';
  }
  function sortFavFirst(a,b){
    return (isFav(b.id)?1:0)-(isFav(a.id)?1:0) || String(a.name).localeCompare(String(b.name));
  }
  function commonAncestor(nodes){
    var a = nodes[0];
    while (a && !nodes.every(function(n){ return a.contains(n); })) a = a.parentElement;
    return a;
  }
  function host(){
    var boxes = [...document.querySelectorAll('input[type=checkbox]')];
    return boxes.length ? commonAncestor(boxes) : null;
  }
  function col(title, items){
    if (!items.length) return '';
    return '<div class="dcol"><div class="dgroup">' + esc(title) + '</div>' +
           items.sort(sortFavFirst).map(row).join('') + '</div>';
  }
  function render(){
    var h = host(); if (!h || !DATA.length) return;
    var contacts = DATA.filter(function(i){ return i.kind === 'contact'; });
    var chans    = DATA.filter(function(i){ return i.kind !== 'contact'; });
    h.innerHTML = '<div class="dgrid">' + col('Contacts', contacts) + col('Channels', chans) + '</div>';
  }

  // capture the data the page already fetches
  var orig = window.fetch;
  window.fetch = function(u){
    var p = orig.apply(this, arguments);
    if (String(u).indexOf('/api/nodes') >= 0) {
      p.then(function(r){ return r.clone().json(); })
       .then(function(j){ DATA = j.nodes || []; setTimeout(render, 0); })
       .catch(function(){});
    }
    return p;
  };
  document.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('button.star');
    if (b) { e.preventDefault(); e.stopPropagation(); toggle(b.dataset.id); }
  }, true);

  // debug hook, used by the automated check
  window.__mcDest = { render: render, setData: function(d){ DATA = d; render(); } };

  var st = document.createElement('style');
  st.textContent =
    '.dgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}' +
    '@media (max-width:720px){.dgrid{grid-template-columns:1fr}}' +
    '.dgroup{font-size:11px;letter-spacing:.09em;text-transform:uppercase;opacity:.6;margin:2px 0 6px}' +
    '.drow{display:flex;align-items:center;gap:7px;padding:3px 0;font-size:13px}' +
    '.drow .did{font-size:11px;opacity:.45;margin-left:auto}' +
    '.drow .dname{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '.drow.fav .dname{font-weight:600}' +
    '.star{border:0;background:none;cursor:pointer;font-size:14px;line-height:1;padding:0 2px;opacity:.75}' +
    '.star:hover{opacity:1}';
  document.head.appendChild(st);
})();
