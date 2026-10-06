// Run with PLAYWRIGHT_MODULE pointing to an installed Playwright package if needed.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless:true});
  const errors = [];
  for (const width of [375, 390, 768, 1366]) {
    const page = await browser.newPage({viewport:{width,height:844}});
    page.on('pageerror', err => errors.push(err.stack));
    await page.route('http://meshcore.test/',route=>route.fulfill({contentType:'text/html',body:`<style>body{margin:0;--primary-background-color:#101418;--card-background-color:#1c2228;--secondary-background-color:#283039;--primary-text-color:#eef2f5;--secondary-text-color:#a7b1ba;--primary-color:#369cec;--text-primary-color:#fff;--divider-color:#374049}</style><meshcore-workspace></meshcore-workspace>`}));
    await page.route('**/meshcore_sender_static/vendor/*',route=>route.fulfill({path:path.resolve(__dirname,'../custom_components/meshcore_sender/www/vendor',route.request().url().split('/').pop())}));
    await page.goto('http://meshcore.test/');
    await page.addScriptTag({path:path.resolve(__dirname,'../custom_components/meshcore_sender/www/workspace.js')});
    await page.evaluate(() => {
      window.calls = [];
      const now = Date.now()/1000;
      const state = {entry_id:'fixture', entries:[{id:'fixture',name:'Radio'}],available:true,
        health:{radio_ok:true,battery:{available:true,voltage:3.987,sampled_at:now}},battery_entity_id:'sensor.radio_battery_voltage',history_supported:true,pin_update_supported:true, favorites:[], settings:{interval:30,target:'dm:OptimusPrime'},
        nodes:[{id:'dm:OptimusPrime',name:'OptimusPrime',kind:'node',public_key:'a'.repeat(64)}, {id:'chan:1',name:'Family Mesh',kind:'private'},
          {id:'dm:Long',name:'A rather long contact name for mobile overflow checks',kind:'repeater'},
          {id:'dm:Bethpage Solar',name:'Bethpage Solar',kind:'repeater',lat:36.38932,lon:-86.262},
          {id:'dm:BlairOneW',name:'BlairOneW',kind:'repeater',lat:39.70739,lon:-85.99339},
          {id:'dm:Toronto',name:'Toronto',kind:'repeater',lat:43.6532,lon:-79.3832}],
        messages:[{id:'one',conversation:'pk:abc',target:'dm:OptimusPrime',name:'OptimusPrime',sender:'OptimusPrime',text:'<img src=x onerror="window.hacked=true"> Hello',received_at:now,direction:'in',status:'received'},
          {id:'two',conversation:'chan:1',target:'chan:1',name:'Family Mesh',sender:'You',text:'Radio check',received_at:now-100,direction:'out',status:'broadcast'}],
        remote:{enabled:false,controllers:[],agent_id:'',pending:0,history:[]},
        agents:[{id:'conversation.safe',name:'MeshCore AI',safe:true},{id:'conversation.unsafe',name:'Home control AI',safe:false}],
        range:{server_now:now,running:false,targets:[],sent:0,acked:0,interval:30,log:[],per_target:{}}};
      document.querySelector('meshcore-workspace').hass = {callWS:async msg => {
        window.calls.push(msg);
        if(msg.type==='meshcore_sender/update_radio_pin') return {ok:true,message:'PIN saved on the bridge. Reconnecting to the radio.'};
        if(msg.action==='start') state.range={...state.range,running:true,targets:msg.targets,interval:msg.interval,
          started_by:'Fixture user', next_due_at:now+msg.interval,sent:3,acked:2,
          per_target:{'dm:OptimusPrime':{sent:3,acked:2}},log:[]};
        if(msg.action==='stop') state.range={...state.range,running:false,stopped_by:'Fixture user',stopped_via:'HA',
          summary_messages:['Range test stopped. Start: Fixture user (HA). Stop: Fixture user (HA).',
            'Attempts 3; DM ACK 2/3; channel TX 0 (no delivery ACK).'],summary_delivery:[{target:'dm:OptimusPrime',ok:true,acked:true}]};
        if(msg.action==='favorite') state.favorites=msg.enabled?msg.targets:[];
        if(msg.action==='remote_settings') state.remote={...state.remote,enabled:msg.enabled,
          controllers:msg.controllers.map(key=>({key,name:'OptimusPrime'})),agent_id:msg.agent_id};
        return structuredClone(state);
      }};
    });
    await page.locator('#battery-status').getByText('3.987 V').waitFor();
    await page.evaluate(()=>document.querySelector('meshcore-workspace').addEventListener('hass-more-info',e=>window.moreInfo=e.detail));
    await page.getByRole('button',{name:'View battery voltage history',exact:true}).click();
    assert.equal(await page.evaluate(()=>window.moreInfo.entityId),'sensor.radio_battery_voltage');
    await page.evaluate(()=>{
      const panel=document.querySelector('meshcore-workspace');
      panel.data.health.battery.sampled_at=Date.now()/1000-181;panel.updateStatus();
    });
    assert.ok((await page.locator('#battery-status').textContent()).includes('unavailable'));
    await page.evaluate(()=>{
      const panel=document.querySelector('meshcore-workspace');
      panel.data.health.battery.sampled_at=Date.now()/1000;panel.updateStatus();
    });
    await page.getByRole('button',{name:/OptimusPrime/}).first().click();
    await assert.equal(await page.locator('meshcore-workspace .bubble img').count(),0);
    assert.equal(await page.evaluate(()=>window.hacked),undefined);
    const chat=await page.locator('meshcore-workspace .chat').boundingBox();
    if(width<=700) assert.ok(chat.width>width-40,'Mobile chat must use the full available width');
    await page.locator('#reply').fill('Draft remains intact');
    await page.waitForTimeout(2200);
    assert.equal(await page.locator('#reply').inputValue(),'Draft remains intact');
    await page.screenshot({path:`/tmp/meshcore-workspace-inbox-${width}.png`});
    await page.getByRole('button',{name:'Range',exact:true}).click();
    await page.locator('#interval').fill('60');
    await page.getByRole('button',{name:'Start test',exact:true}).click();
    await page.getByText('Started by Fixture user').waitFor();
    assert.ok((await page.locator('#range-info').textContent()).includes('every 60s'));
    assert.equal(await page.locator('#start').isDisabled(),true);
    assert.equal(await page.locator('#stop').isDisabled(),false);
    assert.ok((await page.locator('#stats').textContent()).includes('2 (67%)'));
    const call=await page.evaluate(()=>window.calls.find(c=>c.action==='start'));
    assert.deepEqual(call.targets,['dm:OptimusPrime']); assert.equal(call.interval,60);
    await page.screenshot({path:`/tmp/meshcore-workspace-range-${width}.png`,fullPage:true});
    await page.getByRole('button',{name:'Stop',exact:true}).click();
    assert.ok((await page.locator('[aria-label="Final test summary"]').textContent()).includes('DM ACK 2/3'));
    assert.ok((await page.locator('[aria-label="Final test summary"]').textContent()).includes('Stop: Fixture user (HA)'));
    await page.screenshot({path:`/tmp/meshcore-workspace-summary-${width}.png`,fullPage:true});
    await page.getByRole('button',{name:'Compose',exact:true}).click();
    await page.locator('#compose').fill('Hello');
    await page.locator('#search').fill('family');
    await page.locator('.target input[value="chan:1"]').check();
    const overflow=await page.evaluate(()=>{
      const root=document.querySelector('meshcore-workspace').shadowRoot;
      return [...root.querySelectorAll('input,textarea,button,.chat,.tool,.targets')].filter(el=>{
        const r=el.getBoundingClientRect();return r.width>0&&(r.right>innerWidth+1||r.left<0);
      }).map(el=>el.tagName+':'+el.className);
    });
    assert.deepEqual(overflow,[],`Overflow at ${width}px`);
    await page.getByRole('button',{name:'Update radio PIN',exact:true}).click();
    assert.equal(await page.locator('#radio-pin').getAttribute('type'),'password');
    await page.locator('#radio-pin').fill('012345');
    await page.waitForTimeout(2200);
    assert.equal(await page.locator('#radio-pin').inputValue(),'012345');
    await page.getByRole('button',{name:'Save & reconnect',exact:true}).click();
    await page.locator('#pin-dialog').waitFor({state:'detached'});
    assert.equal(await page.evaluate(()=>document.querySelector('meshcore-workspace').shadowRoot.textContent.includes('012345')),false);
    await page.getByRole('button',{name:'Map',exact:true}).click();
    await page.locator('.leaflet-interactive').first().waitFor();
    await page.locator('[data-map-node="dm:Bethpage Solar"]').click();
    await page.waitForTimeout(650);
    assert.equal(await page.evaluate(()=>document.querySelector('meshcore-workspace').leafletMap.getZoom()),12);
    await page.locator('.leaflet-popup-close-button').click();
    await page.waitForTimeout(2200);
    assert.equal(await page.locator('.leaflet-popup').count(),0,'Closing a popup must survive polling');
    assert.equal(await page.locator('[data-map-node="dm:Bethpage Solar"]').getAttribute('aria-pressed'),'true');
    await page.getByRole('button',{name:'Fit matching repeaters',exact:true}).click();
    await page.waitForTimeout(650);
    await page.locator('.leaflet-interactive').nth(1).click();
    await page.waitForTimeout(650);
    assert.equal(await page.locator('[data-map-node="dm:BlairOneW"]').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#map-origin').inputValue(),'dm:BlairOneW');
    assert.ok((await page.locator('[data-map-node="dm:BlairOneW"] .map-distance').textContent()).includes('0.0 km'));
    const distance=await page.locator('[data-map-node="dm:Bethpage Solar"] .map-distance').textContent();
    assert.ok(distance.includes('369.7 km')&&distance.includes('229.7 mi'),distance);
    await page.locator('#map-sort').selectOption('nearest');
    assert.deepEqual(await page.locator('[data-map-node]').evaluateAll(rows=>rows.map(row=>row.dataset.mapNode)),['dm:BlairOneW','dm:Bethpage Solar','dm:Toronto']);
    await page.locator('#map-sort').selectOption('farthest');
    assert.deepEqual(await page.locator('[data-map-node]').evaluateAll(rows=>rows.map(row=>row.dataset.mapNode)),['dm:Toronto','dm:Bethpage Solar','dm:BlairOneW']);
    await page.locator('#map-sort').selectOption('za');
    assert.equal(await page.locator('[data-map-node]').first().getAttribute('data-map-node'),'dm:Toronto');
    await page.locator('#map-sort').selectOption('nearest');
    await page.locator('#map-state').selectOption('TN');
    await page.waitForTimeout(650);
    assert.equal(await page.locator('[data-map-node]').count(),1);
    assert.equal(await page.locator('.leaflet-interactive').count(),1);
    assert.equal(await page.locator('[data-map-node="dm:Bethpage Solar"]').count(),1);
    assert.equal(await page.locator('.leaflet-popup').count(),0,'Hidden selected node must close its popup');
    assert.equal(await page.locator('[data-map-node][aria-pressed="true"]').count(),0);
    await page.waitForTimeout(2200);
    assert.equal(await page.locator('#map-state').inputValue(),'TN','State survives polling');
    assert.equal(await page.locator('#map-origin').inputValue(),'dm:BlairOneW','Reference survives filtering and polling');
    assert.equal(await page.locator('#map-sort').inputValue(),'nearest','Sort survives filtering and polling');
    assert.equal(await page.locator('[data-map-node="dm:Bethpage Solar"] .map-distance').textContent(),distance);
    await page.locator('#map-search').fill('no match');
    assert.equal(await page.locator('.leaflet-interactive').count(),0);
    assert.ok((await page.locator('#map-selection').textContent()).includes('0 of 3'));
    await page.locator('#map-search').fill('');
    await page.locator('#map-state').selectOption('IN');
    assert.equal(await page.locator('[data-map-node="dm:BlairOneW"]').count(),1);
    await page.locator('#map-state').selectOption('unclassified');
    assert.equal(await page.locator('[data-map-node="dm:Toronto"]').count(),1);
    await page.locator('#map-state').selectOption('');
    assert.equal(await page.locator('.leaflet-interactive').count(),3);
    await page.locator('#map-origin').selectOption('dm:Toronto');
    assert.equal(await page.locator('#map-origin').inputValue(),'dm:Toronto');
    assert.ok((await page.locator('[data-map-node="dm:Toronto"] .map-distance').textContent()).includes('0.0 km'));
    await page.getByRole('button',{name:'Contacts',exact:true}).click();
    await page.locator('#search').fill('optimus');
    await page.getByRole('button',{name:'Favorite OptimusPrime',exact:true}).click();
    await page.getByRole('button',{name:'Commands',exact:true}).click();
    await page.locator('#remote-enabled').check();
    await page.locator('[data-controller]').check();
    await page.locator('#remote-agent').selectOption('conversation.safe');
    assert.equal(await page.locator('#remote-agent option[value="conversation.unsafe"]').isDisabled(),true);
    await page.waitForTimeout(2200);
    assert.equal(await page.locator('#remote-enabled').isChecked(),true,'Draft survives polling');
    await page.getByRole('button',{name:'Save',exact:true}).click();
    assert.deepEqual(await page.evaluate(()=>window.calls.find(c=>c.action==='remote_settings').controllers),['a'.repeat(64)]);
    const commandsOverflow=await page.evaluate(()=>[...document.querySelector('meshcore-workspace').shadowRoot.querySelectorAll('#remote-form,.controller-list,#remote-agent,.command-history')].filter(el=>{const r=el.getBoundingClientRect();return r.right>innerWidth+1||r.left<0}).length);
    assert.equal(commandsOverflow,0);
    assert.equal(await page.getByRole('heading',{name:'Recent commands'}).isVisible(),true);
    await page.screenshot({path:`/tmp/meshcore-workspace-commands-${width}.png`,fullPage:true});
    await page.getByRole('button',{name:'Map',exact:true}).click();
    await page.locator('[data-map-node="dm:BlairOneW"]').waitFor();
    assert.equal(await page.locator('#map-origin').inputValue(),'dm:Toronto','Explicit reference survives tab re-entry');
    assert.equal(await page.locator('#map-sort').inputValue(),'nearest','Sort survives tab re-entry');
    await page.locator('#map-origin').selectOption('');
    assert.equal(await page.locator('.map-distance').count(),0);
    assert.equal(await page.locator('#map-sort').inputValue(),'az');
    assert.equal(await page.locator('#map-sort option[value="nearest"]').isDisabled(),true);
    await page.locator('#map-origin').selectOption('dm:BlairOneW');
    await page.locator('#map-state').selectOption('IN');
    await page.waitForTimeout(650);
    const mapOverflow=await page.evaluate(()=>[...document.querySelector('meshcore-workspace').shadowRoot.querySelectorAll('#map-state,#map-search,#map-canvas,.map-row')].filter(el=>{const r=el.getBoundingClientRect();return r.right>innerWidth+1||r.left<0}).length);
    assert.equal(mapOverflow,0);
    const listHeight=await page.locator('#map-list').evaluate(el=>el.clientHeight);
    assert.ok(listHeight>=(width<=700?360:480),`Taller list at ${width}px`);
    await page.screenshot({path:`/tmp/meshcore-workspace-map-${width}.png`,fullPage:true});
    assert.ok(await page.locator('.leaflet-tile').evaluateAll(images=>images.some(i=>i.complete&&i.naturalWidth>0)),'OSM tiles must render');
    await page.close();
  }
  await browser.close();
  assert.deepEqual(errors,[]);
  console.log('Workspace browser checks passed at 375, 390, 768 and 1366px; fixture actions only, no radio transmissions.');
})().catch(err => {console.error(err);process.exit(1);});
