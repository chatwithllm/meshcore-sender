// Run with PLAYWRIGHT_MODULE pointing to an installed Playwright package if needed.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless:true});
  const errors = [];
  for (const width of [375, 390, 768, 1366]) {
    const page = await browser.newPage({viewport:{width,height:844}});
    page.on('pageerror', err => errors.push(err.message));
    await page.route('http://meshcore.test/',route=>route.fulfill({contentType:'text/html',body:`<style>body{margin:0;--primary-background-color:#101418;--card-background-color:#1c2228;--secondary-background-color:#283039;--primary-text-color:#eef2f5;--secondary-text-color:#a7b1ba;--primary-color:#369cec;--text-primary-color:#fff;--divider-color:#374049}</style><meshcore-workspace></meshcore-workspace>`}));
    await page.route('**/meshcore_sender_static/vendor/*',route=>route.fulfill({path:path.resolve(__dirname,'../custom_components/meshcore_sender/www/vendor',route.request().url().split('/').pop())}));
    await page.goto('http://meshcore.test/');
    await page.addScriptTag({path:path.resolve(__dirname,'../custom_components/meshcore_sender/www/workspace.js')});
    await page.evaluate(() => {
      window.calls = [];
      const now = Date.now()/1000;
      const state = {entry_id:'fixture', entries:[{id:'fixture',name:'Radio'}],available:true,
        health:{radio_ok:true},history_supported:true,pin_update_supported:true, favorites:[], settings:{interval:30,target:'dm:OptimusPrime'},
        nodes:[{id:'dm:OptimusPrime',name:'OptimusPrime',kind:'node'}, {id:'chan:1',name:'Family Mesh',kind:'private'},
          {id:'dm:Long',name:'A rather long contact name for mobile overflow checks',kind:'repeater'},
          {id:'dm:Bethpage Solar',name:'Bethpage Solar',kind:'repeater',lat:36.38932,lon:-86.262},
          {id:'dm:BlairOneW',name:'BlairOneW',kind:'repeater',lat:39.70739,lon:-85.99339}],
        messages:[{id:'one',conversation:'pk:abc',target:'dm:OptimusPrime',name:'OptimusPrime',sender:'OptimusPrime',text:'<img src=x onerror="window.hacked=true"> Hello',received_at:now,direction:'in',status:'received'},
          {id:'two',conversation:'chan:1',target:'chan:1',name:'Family Mesh',sender:'You',text:'Radio check',received_at:now-100,direction:'out',status:'broadcast'}],
        range:{server_now:now,running:false,targets:[],sent:0,acked:0,interval:30,log:[],per_target:{}}};
      document.querySelector('meshcore-workspace').hass = {callWS:async msg => {
        window.calls.push(msg);
        if(msg.type==='meshcore_sender/update_radio_pin') return {ok:true,message:'PIN saved on the bridge. Reconnecting to the radio.'};
        if(msg.action==='start') state.range={...state.range,running:true,targets:msg.targets,interval:msg.interval,
          started_by:'Fixture user', next_due_at:now+msg.interval,sent:3,acked:2,
          per_target:{'dm:OptimusPrime':{sent:3,acked:2}},log:[]};
        if(msg.action==='stop') state.range.running=false;
        if(msg.action==='favorite') state.favorites=msg.enabled?msg.targets:[];
        return structuredClone(state);
      }};
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
    await page.getByRole('button',{name:'Fit all repeaters',exact:true}).click();
    await page.waitForTimeout(650);
    await page.locator('.leaflet-interactive').nth(1).click();
    await page.waitForTimeout(650);
    assert.equal(await page.locator('[data-map-node="dm:BlairOneW"]').getAttribute('aria-pressed'),'true');
    await page.screenshot({path:`/tmp/meshcore-workspace-map-${width}.png`,fullPage:true});
    assert.ok(await page.locator('.leaflet-tile').evaluateAll(images=>images.some(i=>i.complete&&i.naturalWidth>0)),'OSM tiles must render');
    await page.close();
  }
  await browser.close();
  assert.deepEqual(errors,[]);
  console.log('Workspace browser checks passed at 375, 390, 768 and 1366px; fixture actions only, no radio transmissions.');
})().catch(err => {console.error(err);process.exit(1);});
