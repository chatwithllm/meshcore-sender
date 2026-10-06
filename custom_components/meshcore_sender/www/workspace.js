/* Local, authenticated Home Assistant panel. No independent radio connection. */
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<ha-icon icon="mdi:${name}"></ha-icon>`;
const timeLabel = value => new Date(value * 1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});

class MeshCoreWorkspace extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:'open'});
    this.view = 'inbox';
    this.selected = null;
    this.targets = new Set();
    this.query = '';
    this.sort = 'az';
    this.filter = 'all';
    this.drafts = {reply:'', compose:''};
    this.interval = 30;
    this.messagePrefix = 'ping';
    this.busy = false;
    this.data = null;
    this.entryId = null;
  }
  set hass(value) { this._hass = value; if (this.isConnected && !this.timer) this.start(); }
  connectedCallback() { if (this._hass) this.start(); }
  disconnectedCallback() { clearInterval(this.timer); this.timer = null; }
  start() {
    if (this.timer) return;
    this.render();
    this.refresh();
    this.timer = setInterval(() => { this.countdown(); if (!this.polling && !this.busy) this.refresh(); }, 2000);
  }
  async request(action='snapshot', fields={}) {
    return this._hass.callWS({type:'meshcore_sender/workspace', action,
      ...(this.entryId ? {entry_id:this.entryId} : {}), ...fields});
  }
  async refresh() {
    this.polling = true;
    try {
      const data = await this.request();
      if (!this.data) {
        this.interval = data.range.running ? data.range.interval : data.settings?.interval || 30;
        this.messagePrefix = data.range.running ? data.range.prefix : data.settings?.prefix || 'ping';
        this.targets = new Set(data.range.running ? data.range.targets : data.settings?.targets || (data.settings?.target ? [data.settings.target] : []));
      }
      const signature = JSON.stringify([data.nodes, data.messages, data.favorites, data.available, data.health?.radio_ok, data.entries]);
      const changed = this.signature !== signature || this.pendingRender;
      this.data = data;
      this.entryId = data.entry_id;
      this.clockOffset = data.range.server_now * 1000 - Date.now();
      this.error = '';
      // Keep focus, scroll position and drafts intact while background data changes.
      const editing = ['INPUT','TEXTAREA','SELECT'].includes(this.shadowRoot.activeElement?.tagName);
      if (changed && !editing && this.view !== 'range') { this.render(); this.pendingRender = false; }
      else { this.updateStatus(); this.pendingRender = changed; }
      this.signature = signature;
      if (this.view === 'range') this.updateRange();
    } catch (err) {
      this.error = err.message || 'Cannot reach the radio workspace';
      if (!this.data) this.render(); else this.updateStatus();
    } finally { this.polling = false; }
  }
  async action(action, fields={}) {
    if (this.busy) return;
    this.busy = true; this.notice = ''; this.render();
    try {
      this.data = await this.request(action, fields);
      this.clockOffset = this.data.range.server_now * 1000 - Date.now();
      if (action === 'send') {
        const sent = this.data.messages.filter(m => m.direction === 'out').slice(-fields.targets.length);
        this.notice = sent.some(m => ['failed','unconfirmed'].includes(m.status))
          ? 'Transmission finished. Check delivery status below.' : 'Message sent';
        this.drafts[this.view === 'inbox' ? 'reply' : 'compose'] = '';
      }
      this.error = '';
    } catch (err) { this.error = err.message || 'Action failed'; }
    finally { this.busy = false; this.signature = null; this.render(); }
  }
  nodeName(id) { return this.data?.nodes.find(n => n.id === id)?.name || id?.replace(/^dm:/,'') || 'Unknown'; }
  conversations() {
    const groups = new Map();
    for (const m of this.data?.messages || []) {
      const key = m.target || m.conversation;
      if (!groups.has(key)) groups.set(key, {id:key, name:m.name, target:m.target, messages:[]});
      const group = groups.get(key);
      group.messages.push(m); group.last = m;
      group.name = m.name || group.name;
    }
    return [...groups.values()].sort((a,b) => b.last.received_at-a.last.received_at);
  }
  picker() {
    const favorites = this.data?.favorites || [];
    const nodes = (this.data?.nodes || []).filter(n => n.name.toLowerCase().includes(this.query.toLowerCase()) &&
      (this.filter === 'all' || (this.filter === 'channels' ? n.id.startsWith('chan:') : n.kind === this.filter)))
      .sort((a,b) => (this.sort === 'az' ? 1 : -1) * a.name.localeCompare(b.name, undefined, {numeric:true}));
    return `<div class="picker-head"><input id="search" type="search" placeholder="Search contacts or channels" aria-label="Search contacts or channels" value="${escapeHTML(this.query)}"><select id="sort" aria-label="Sort names"><option value="az" ${this.sort==='az'?'selected':''}>A–Z</option><option value="za" ${this.sort==='za'?'selected':''}>Z–A</option></select></div>
      <div class="filters" aria-label="Contact type">${[['all','All'],['node','Nodes'],['repeater','Repeaters'],['room','Rooms'],['channels','Channels']].map(([id,label]) => `<button data-filter="${id}" aria-pressed="${this.filter===id}" class="${this.filter===id?'active':''}">${label}</button>`).join('')}</div>
      <div class="targets">${nodes.map(n => `<div class="target"><label><input type="checkbox" value="${escapeHTML(n.id)}" ${this.targets.has(n.id)?'checked':''}><span>${escapeHTML(n.name)}</span><small>${n.id.startsWith('chan:')?'Channel':escapeHTML(n.kind)}</small></label><button class="icon favorite" data-favorite="${escapeHTML(n.id)}" aria-label="${favorites.includes(n.id)?'Unfavorite':'Favorite'} ${escapeHTML(n.name)}" title="${favorites.includes(n.id)?'Remove favorite':'Add favorite'}">${icon(favorites.includes(n.id)?'star':'star-outline')}</button></div>`).join('') || '<p class="empty-small">No matching contacts</p>'}</div>
      <div class="selection">${this.targets.size ? [...this.targets].map(id=>`<span>${escapeHTML(this.nodeName(id))}<button class="icon" data-remove="${escapeHTML(id)}" title="Remove target" aria-label="Remove ${escapeHTML(this.nodeName(id))}">${icon('close')}</button></span>`).join('') : 'No targets selected'}</div>`;
  }
  inbox() {
    const groups = this.conversations();
    const current = groups.find(g=>g.id===this.selected);
    const list = `<aside class="conversation-list"><div class="list-heading"><h2>Inbox</h2><span>${groups.length}</span><button class="icon" id="new-message" title="New message" aria-label="New message">${icon('square-edit-outline')}</button></div><div class="conversation-items">${groups.map(g=>`<button class="conversation ${g.id===this.selected?'selected':''}" data-conversation="${escapeHTML(g.id)}"><span class="conversation-top"><strong>${escapeHTML(this.nodeName(g.target) !== 'Unknown' ? this.nodeName(g.target) : g.name)}</strong><time>${timeLabel(g.last.received_at)}</time></span><span class="preview">${g.last.direction==='out'?'You: ':''}${escapeHTML(g.last.text)}</span></button>`).join('') || '<p class="empty-small">No messages received yet</p>'}</div></aside>`;
    const detail = current ? `<section class="chat"><header class="chat-heading"><button class="icon mobile-back" id="back" title="Inbox" aria-label="Back to inbox">${icon('arrow-left')}</button><div><h2>${escapeHTML(current.target ? this.nodeName(current.target) : current.name)}</h2><span>${current.target?.startsWith('chan:')?'Channel':'Direct conversation'} · ${current.messages.length} messages</span></div></header>
      ${current.target?.startsWith('chan:')?'<div class="channel-note">Channel broadcasts do not return delivery ACKs. Receiving a message does not guarantee a return path.</div>':''}
      <div class="messages">${current.messages.map(m=>`<article class="message ${m.direction==='out'?'out':'in'}"><div class="message-meta">${escapeHTML(m.sender)} · ${timeLabel(m.received_at)}</div><div class="bubble">${escapeHTML(m.text)}</div><div class="delivery ${escapeHTML(m.status)}">${escapeHTML({delivered:'Delivered · ACK',broadcast:'Broadcast sent · no delivery ACK',unconfirmed:'Sent · delivery unconfirmed',failed:'Failed',sending:'Sending…',received:'Received'}[m.status] || m.status)}${m.direction==='in' && m.hops != null ? ` · ${m.hops===255?'direct':`${m.hops} hops`}`:''}</div></article>`).join('')}</div>
      <form id="reply-form" class="reply"><textarea id="reply" rows="2" aria-label="Reply" placeholder="Reply to ${escapeHTML(current.name)}" ${!current.target?'disabled':''}>${escapeHTML(this.drafts.reply)}</textarea><button class="primary" ${this.busy||!current.target?'disabled':''}>${icon('send')}<span>Send</span></button></form>${!current.target?'<p class="unknown-note">This sender is not in the radio’s contacts. A reply is unavailable until its contact advert is received.</p>':''}</section>`
      : '<section class="chat empty-chat"><ha-icon icon="mdi:message-text-outline"></ha-icon><h2>Your radio inbox</h2><p>Select a conversation or compose a message.</p><button id="compose-empty" class="primary">New message</button></section>';
    return `<div class="inbox ${current?'has-conversation':''}">${list}${detail}</div>`;
  }
  compose() {
    return `<section class="tool"><h2>New message</h2><div class="tool-grid"><div><label class="field-label" for="compose">Message</label><textarea id="compose" rows="4" placeholder="Write a message…">${escapeHTML(this.drafts.compose)}</textarea><div class="byte-count" id="bytes"></div><h3>Recipients</h3>${this.picker()}<button id="send-compose" class="primary" ${this.busy?'disabled':''}>${icon('send')} Send message</button></div><aside class="info"><h3>Delivery</h3><p>Direct messages show the radio’s delivery ACK. Channels are broadcasts and cannot confirm receipt by each member.</p><p>One transmission per selected contact or channel. Maximum 150 UTF-8 bytes per message.</p></aside></div></section>`;
  }
  rangeView() {
    return `<section class="tool"><div class="section-title"><h2>Range test</h2><span id="live" class="live"></span></div><div class="tool-grid"><div><div class="range-fields"><label>Interval (seconds)<input id="interval" type="number" inputmode="numeric" min="5" max="300" step="1" value="${this.interval}"></label><label>Message prefix<input id="prefix" maxlength="40" value="${escapeHTML(this.messagePrefix)}"></label></div><h3>Targets</h3>${this.picker()}<div class="actions"><button id="start" class="primary" ${this.busy?'disabled':''}>${icon('play')} Start test</button><button id="stop" ${this.busy?'disabled':''}>${icon('stop')} Stop</button></div></div><aside class="range-stats"><h3>Current test</h3><div id="range-info"></div><progress id="progress" max="1" value="0" aria-label="Time until next transmission"></progress><div id="stats"></div></aside></div><h3>Transmission log</h3><div class="range-log" id="range-log"></div></section>`;
  }
  contacts() {
    return `<section class="tool"><h2>Contacts & channels</h2>${this.picker()}<p class="muted">${this.data?.nodes.length || 0} available · ${this.data?.favorites.length || 0} favorites</p></section>`;
  }
  render() {
    const oldScroll = this.shadowRoot.querySelector('.messages');
    const bottom = !oldScroll || oldScroll.scrollHeight-oldScroll.scrollTop-oldScroll.clientHeight < 60;
    const scroll = oldScroll?.scrollTop || 0;
    this.shadowRoot.innerHTML = `<style>${MeshCoreWorkspace.styles}</style><div class="shell"><header class="app-heading"><ha-menu-button id="ha-menu"></ha-menu-button><h1>MeshCore</h1><div id="connection" class="connection"></div><button class="icon" id="refresh" title="Refresh workspace" aria-label="Refresh workspace">${icon('refresh')}</button></header>
      ${this.data?.entries.length>1?`<label class="radio-picker">Radio<select id="radio">${this.data.entries.map(e=>`<option value="${escapeHTML(e.id)}" ${e.id===this.entryId?'selected':''}>${escapeHTML(e.name)}</option>`).join('')}</select></label>`:''}
      <nav aria-label="MeshCore views">${[['inbox','message-text-outline','Inbox'],['compose','square-edit-outline','Compose'],['range','signal-distance-variant','Range'],['contacts','account-multiple-outline','Contacts']].map(([id,i,label])=>`<button data-view="${id}" aria-current="${this.view===id?'page':'false'}" class="${this.view===id?'active':''}">${icon(i)}<span>${label}</span></button>`).join('')}</nav><div class="feedback" role="status"></div><main>${!this.data?'<div class="loading">Connecting to your radio workspace…</div>':!this.data.history_supported?'<section class="tool"><h2>Native radio connection required</h2><p>This inbox workspace currently supports the Bluetooth and BLE bridge connections. Existing server-mode controls remain available on the device page.</p></section>':this.view==='inbox'?this.inbox():this.view==='compose'?this.compose():this.view==='range'?this.rangeView():this.contacts()}</main></div>`;
    this.bind(); this.updateStatus(); this.updateRange(); this.byteCount();
    const messages = this.shadowRoot.querySelector('.messages');
    if (messages) messages.scrollTop = bottom ? messages.scrollHeight : scroll;
  }
  bind() {
    const root = this.shadowRoot;
    const menu = root.getElementById('ha-menu');
    menu.hass = this._hass; menu.narrow = this.narrow;
    root.querySelectorAll('[data-view]').forEach(el=>el.onclick=()=>{this.view=el.dataset.view;this.render();});
    root.querySelectorAll('[data-conversation]').forEach(el=>el.onclick=()=>{this.selected=el.dataset.conversation;this.drafts.reply='';this.render();});
    root.querySelectorAll('[data-filter]').forEach(el=>el.onclick=()=>{this.filter=el.dataset.filter;this.render();});
    root.querySelectorAll('[data-remove]').forEach(el=>el.onclick=()=>{this.targets.delete(el.dataset.remove);this.render();});
    root.querySelectorAll('[data-favorite]').forEach(el=>el.onclick=()=>this.action('favorite',{targets:[el.dataset.favorite],enabled:!this.data.favorites.includes(el.dataset.favorite)}));
    root.querySelectorAll('.target input').forEach(el=>el.onchange=()=>{el.checked?this.targets.add(el.value):this.targets.delete(el.value);this.render();});
    const on = (id,event,handler) => { const el=root.getElementById(id); if(el) el[event]=handler; };
    on('refresh','onclick',()=>this.refresh());
    on('radio','onchange',e=>{this.entryId=e.target.value;this.selected=null;this.targets.clear();this.signature=null;this.refresh();});
    on('back','onclick',()=>{this.selected=null;this.render();});
    for(const id of ['new-message','compose-empty']) on(id,'onclick',()=>{this.view='compose';this.render();});
    on('search','oninput',e=>{const position=e.target.selectionStart;this.query=e.target.value;this.render();const input=root.getElementById('search');input.focus();input.setSelectionRange(position,position);});
    on('sort','onchange',e=>{this.sort=e.target.value;this.render();});
    on('reply','oninput',e=>{this.drafts.reply=e.target.value;});
    on('compose','oninput',e=>{this.drafts.compose=e.target.value;this.byteCount();});
    on('interval','oninput',e=>{this.interval=Number(e.target.value);});
    on('prefix','oninput',e=>{this.messagePrefix=e.target.value;});
    on('reply-form','onsubmit',e=>{e.preventDefault();const current=this.conversations().find(g=>g.id===this.selected);this.send(current?.target?[current.target]:[],this.drafts.reply);});
    on('send-compose','onclick',()=>this.send([...this.targets],this.drafts.compose));
    on('start','onclick',()=>{
      if(!this.targets.size || !Number.isInteger(this.interval) || this.interval<5 || this.interval>300 || !this.messagePrefix.trim()) {
        this.error='Select targets, a prefix and an interval from 5 to 300 seconds.';this.updateStatus();return;
      }
      this.action('start',{targets:[...this.targets],interval:this.interval,prefix:this.messagePrefix});
    });
    on('stop','onclick',()=>this.action('stop'));
  }
  send(targets,text) {
    if(!targets.length || !text.trim() || new TextEncoder().encode(text.trim()).length>150) {
      this.error='Choose recipients and enter a message of 1–150 UTF-8 bytes.';this.updateStatus();return;
    }
    this.action('send',{targets,text:text.trim()});
  }
  byteCount() {
    const el=this.shadowRoot.getElementById('bytes');
    if(el) { const size=new TextEncoder().encode(this.drafts.compose).length;el.textContent=`${size} / 150 bytes`;el.classList.toggle('error',size>150); }
  }
  updateStatus() {
    const feedback=this.shadowRoot.querySelector('.feedback');
    if(feedback) { feedback.textContent=this.error||this.notice||'';feedback.classList.toggle('error',Boolean(this.error)); }
    const status=this.shadowRoot.getElementById('connection');
    if(status) { const online=this.data?.available && this.data?.health?.radio_ok;
      status.innerHTML=`<span class="dot ${online?'online':''}"></span>${this.error?'Unavailable':online?'Connected':this.data?'Radio offline':'Connecting'}<span class="contact-count"> · ${this.data?.nodes.length||0} contacts</span>`; }
    const rangeTab=this.shadowRoot.querySelector('[data-view="range"]');
    if(rangeTab) {
      rangeTab.querySelector('.range-indicator')?.remove();
      if(this.data?.range.running) {
        rangeTab.insertAdjacentHTML('beforeend','<span class="range-indicator dot online pulse" aria-label="Test running"></span>');
        rangeTab.title=`Live range test · ${this.data.range.sent} sent · ${this.data.range.acked} ACKs`;
      } else rangeTab.title='Range test';
    }
  }
  updateRange() {
    const r=this.data?.range;
    if(!r || !this.shadowRoot.getElementById('range-info')) return;
    const root=this.shadowRoot;
    root.getElementById('live').innerHTML=r.running?'<span class="dot online pulse"></span> Live':'Idle';
    root.getElementById('range-info').innerHTML=`<div class="totals"><strong>${r.sent}</strong> sent <strong>${r.acked}</strong> ACKs</div><p>${escapeHTML(r.started_by?`Started by ${r.started_by}`:'No test started')}</p>${r.targets?.length?`<p>${escapeHTML(r.targets.map(id=>this.nodeName(id)).join(', '))} · every ${r.interval}s</p>`:''}<p id="next"></p>`;
    root.getElementById('stats').innerHTML=`<table><thead><tr><th>Target</th><th>Sent</th><th>ACK</th></tr></thead><tbody>${Object.entries(r.per_target||{}).map(([id,s])=>`<tr><td>${escapeHTML(this.nodeName(id))}</td><td>${s.sent}</td><td>${id.startsWith('chan:')?'—':`${s.acked} (${s.sent?Math.round(s.acked/s.sent*100):0}%)`}</td></tr>`).join('')}</tbody></table>${r.targets?.some(id=>id.startsWith('chan:'))?'<p class="muted">Channels: broadcast count, no delivery ACK</p>':''}`;
    root.getElementById('range-log').innerHTML=[...(r.log||[])].reverse().map(l=>`<div><time>${escapeHTML(l.ts)}</time><strong>${escapeHTML(this.nodeName(l.target))} #${l.seq}</strong><span>${escapeHTML(l.detail)}${l.acked?` · ${l.rtt_ms}ms`:''}</span></div>`).join('') || '<p class="empty-small">No transmissions yet</p>';
    root.getElementById('start').disabled=this.busy||r.running||!this.data.available;
    root.getElementById('stop').disabled=this.busy||!r.running;
    this.countdown();
  }
  countdown() {
    const r=this.data?.range, next=this.shadowRoot.getElementById('next'), progress=this.shadowRoot.getElementById('progress');
    if(!r||!next) return;
    const seconds=r.next_due_at ? Math.max(0,Math.ceil(r.next_due_at-(Date.now()+(this.clockOffset||0))/1000)) : 0;
    next.textContent=!r.running?'Test stopped':r.next_due_at?`Next transmission in ${seconds}s`:'Sending…';
    progress.value=r.running? r.next_due_at?Math.max(0,Math.min(1,1-seconds/r.interval)):1:0;
  }
  static styles = `
    :host { display:block;height:100%;color:var(--primary-text-color,#202124);background:var(--primary-background-color,#f5f6f8);font:14px var(--paper-font-body1_-_font-family,Roboto,Arial,sans-serif);letter-spacing:0; }
    .shell{background:var(--primary-background-color,#f5f6f8);min-height:100%}
    *{box-sizing:border-box}button,input,textarea,select{font:inherit;letter-spacing:0}button{cursor:pointer}button:disabled{opacity:.45;cursor:default}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:2px}ha-icon{--mdc-icon-size:22px;flex:none}h1{font-size:20px;margin:0}h2{font-size:18px;margin:0}h3{font-size:13px;margin:20px 0 10px;color:var(--secondary-text-color);font-weight:600}p{line-height:1.5}button{border:1px solid var(--divider-color,#ddd);border-radius:6px;background:transparent;color:inherit;min-height:40px;padding:8px 14px;display:inline-flex;align-items:center;justify-content:center;gap:8px}button.primary{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff);border-color:transparent}button.icon{padding:8px;width:40px;height:40px;flex:none;border:0}input,textarea,select{border:1px solid var(--divider-color,#ddd);border-radius:6px;padding:11px;color:inherit;background:var(--card-background-color,#fff);min-width:0}textarea{width:100%;resize:vertical;line-height:1.45}input[type=checkbox]{width:18px;height:18px;accent-color:var(--primary-color)}
    .shell{max-width:1440px;margin:auto;padding:0 24px 24px}.app-heading{height:64px;display:flex;align-items:center;gap:12px}.connection{margin-left:auto;color:var(--secondary-text-color);font-size:13px;display:flex;align-items:center;gap:6px}.dot{display:inline-block;width:8px;height:8px;background:#8a929b;border-radius:50%;flex:none}.dot.online{background:#2bb673}.pulse{animation:pulse 1.5s ease-in-out infinite}@keyframes pulse{50%{opacity:.35}}@media(prefers-reduced-motion:reduce){.pulse{animation:none}}
    nav{display:flex;border-bottom:1px solid var(--divider-color,#ddd);gap:8px;margin-bottom:16px}nav button{border:0;border-radius:0;padding:12px 18px;min-height:48px;border-bottom:3px solid transparent}nav button.active{border-bottom-color:var(--primary-color);color:var(--primary-color)}.feedback:empty{display:none}.feedback{padding:12px 0;color:var(--secondary-text-color)}.error{color:var(--error-color,#db4437)!important}.radio-picker{display:flex;align-items:center;gap:12px;padding-bottom:8px}.radio-picker select{max-width:100%}main{min-width:0}.loading{padding:48px;text-align:center}
    .inbox{display:grid;grid-template-columns:300px minmax(0,1fr);height:calc(100dvh - 160px);min-height:400px;border:1px solid var(--divider-color,#ddd);border-radius:6px;overflow:hidden;background:var(--card-background-color,#fff)}.conversation-list{border-right:1px solid var(--divider-color,#ddd);display:flex;flex-direction:column;min-height:0;min-width:0}.list-heading{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--divider-color,#ddd)}.list-heading h2{font-size:16px}.list-heading>span{color:var(--secondary-text-color)}.list-heading button{margin-left:auto}.conversation-items{overflow:auto}.conversation{display:block;text-align:left;width:100%;min-height:76px;padding:14px 16px;border:0;border-radius:0;border-bottom:1px solid var(--divider-color,#ddd)}.conversation.selected{background:var(--secondary-background-color,#edf4f7);box-shadow:inset 3px 0 var(--primary-color)}.conversation-top{display:flex;align-items:center;gap:10px}.conversation-top strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}.conversation time{font-size:11px;color:var(--secondary-text-color);white-space:nowrap}.preview{display:block;margin-top:7px;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.chat{display:flex;flex-direction:column;min-width:0;min-height:0}.chat-heading{display:flex;align-items:center;gap:10px;padding:16px 20px;flex:none;border-bottom:1px solid var(--divider-color,#ddd)}.chat-heading h2{overflow-wrap:anywhere}.chat-heading span{display:block;font-size:12px;color:var(--secondary-text-color);margin-top:5px}.mobile-back{display:none!important}.channel-note{padding:10px 20px;background:var(--secondary-background-color);color:var(--secondary-text-color);font-size:12px;line-height:1.4}.messages{flex:1;overflow:auto;padding:20px;overscroll-behavior:contain}.message{margin-bottom:18px;max-width:85%;width:fit-content}.message.out{margin-left:auto}.message-meta{color:var(--secondary-text-color);font-size:11px;margin-bottom:5px}.message.out .message-meta,.message.out .delivery{text-align:right}.bubble{padding:10px 14px;background:var(--secondary-background-color,#edf0f3);border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5}.message.out .bubble{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}.delivery{color:var(--secondary-text-color);font-size:11px;margin-top:5px}.delivered{color:#249a62}.failed{color:var(--error-color,#db4437)}.reply{display:flex;align-items:flex-end;gap:10px;padding:14px 20px;border-top:1px solid var(--divider-color,#ddd);flex:none}.reply textarea{flex:1;min-height:48px;max-height:140px}.reply button{height:48px}.unknown-note{padding:0 20px;font-size:12px}.empty-chat{align-items:center;justify-content:center;text-align:center;color:var(--secondary-text-color);padding:24px;gap:14px}.empty-chat ha-icon{--mdc-icon-size:40px}.empty-chat p{margin:0}.empty-small{padding:20px;color:var(--secondary-text-color)}
    .tool{padding:8px 0 24px}.tool-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,.65fr);gap:32px;margin-top:20px}.field-label{display:block;margin-bottom:8px;color:var(--secondary-text-color)}.picker-head{display:flex;gap:8px;margin-bottom:10px}.picker-head input{flex:1;width:100%}.picker-head select{width:82px}.filters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}.filters button{min-height:36px;padding:6px 10px;font-size:12px}.filters .active{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:transparent}.targets{border:1px solid var(--divider-color,#ddd);border-radius:6px;overflow:auto;max-height:320px;background:var(--card-background-color,#fff)}.target{display:flex;align-items:center;border-bottom:1px solid var(--divider-color,#ddd);padding:2px 8px;min-height:48px}.target:last-child{border:0}.target label{display:flex;gap:10px;align-items:center;flex:1;min-width:0;cursor:pointer;padding:6px 0}.target label span{flex:1;overflow-wrap:anywhere}.target small{font-size:10px;color:var(--secondary-text-color);text-transform:uppercase}.favorite{color:var(--secondary-text-color)}.selection{display:flex;flex-wrap:wrap;gap:6px;color:var(--secondary-text-color);padding:12px 0;min-height:44px;font-size:12px}.selection>span{display:flex;align-items:center;padding-left:8px;background:var(--secondary-background-color);border-radius:4px}.selection button{width:28px!important;height:28px!important;min-height:28px;padding:4px}.selection ha-icon{--mdc-icon-size:16px}.info{border-left:1px solid var(--divider-color);padding-left:24px;color:var(--secondary-text-color)}.info h3{margin-top:0}.byte-count{font-size:12px;color:var(--secondary-text-color);margin-top:6px}.range-fields{display:grid;grid-template-columns:1fr 1fr;gap:12px}.range-fields label{display:flex;flex-direction:column;gap:8px;color:var(--secondary-text-color);font-size:12px}.range-fields input{width:100%;font-size:16px}.section-title{display:flex;align-items:center;justify-content:space-between}.live{display:flex;align-items:center;gap:6px;color:var(--secondary-text-color);font-size:12px}.actions{display:flex;gap:8px}.range-stats{min-width:0;border-left:1px solid var(--divider-color);padding-left:24px}.range-stats h3{margin-top:0}.range-stats p{color:var(--secondary-text-color);font-size:12px;overflow-wrap:anywhere}.totals{display:flex;align-items:baseline;gap:8px;color:var(--secondary-text-color)}.totals strong{font-size:28px;color:var(--primary-text-color)}progress{width:100%;height:8px;accent-color:var(--primary-color);margin:4px 0 20px}table{border-collapse:collapse;width:100%;font-size:12px}th,td{text-align:right;padding:10px 4px;border-bottom:1px solid var(--divider-color);overflow-wrap:anywhere}th:first-child,td:first-child{text-align:left;max-width:180px}th{color:var(--secondary-text-color);font-weight:500}.range-log{max-height:250px;overflow:auto;border-top:1px solid var(--divider-color)}.range-log>div{display:grid;grid-template-columns:70px minmax(0,1fr) minmax(0,1fr);gap:12px;padding:10px 0;font-size:12px;border-bottom:1px solid var(--divider-color);overflow-wrap:anywhere}.range-log time,.range-log span,.muted{color:var(--secondary-text-color)}
    @media(max-width:700px){.shell{padding:0 12px calc(16px + env(safe-area-inset-bottom))}.app-heading{height:56px;gap:8px}.app-heading>ha-icon{display:none}h1{font-size:18px}.contact-count{display:none}.connection{font-size:12px}nav{gap:0;margin-bottom:12px}nav button{flex:1;min-width:0;padding:10px 4px;gap:5px;font-size:12px}nav ha-icon{--mdc-icon-size:18px}.inbox{display:block;height:calc(100dvh - 140px);min-height:360px}.conversation-list{height:100%;border-right:0}.chat{height:100%;display:none}.inbox.has-conversation .conversation-list{display:none}.inbox.has-conversation .chat{display:flex}.mobile-back{display:inline-flex!important}.chat-heading{padding:10px}.chat-heading h2{font-size:16px}.messages{padding:14px}.message{max-width:90%}.reply{padding:10px;gap:8px}.reply textarea{font-size:16px;resize:none}.reply button{padding:10px;min-width:48px}.reply button span{display:none}.channel-note{padding:10px 14px}.tool-grid{grid-template-columns:minmax(0,1fr);gap:24px}.info,.range-stats{border-left:0;border-top:1px solid var(--divider-color);padding:18px 0 0}.info{display:none}.tool>h2{font-size:18px}.targets{max-height:280px}.picker-head input{font-size:16px}.filters{gap:5px}.filters button{padding:8px;font-size:12px;min-height:40px}.range-fields input{font-size:16px}.range-log>div{grid-template-columns:62px minmax(0,1fr);gap:6px}.range-log>div span{grid-column:2}.range-stats h3{margin:0 0 14px}.radio-picker select{flex:1}}
  `;
}
customElements.define('meshcore-workspace', MeshCoreWorkspace);
