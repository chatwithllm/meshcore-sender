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
    await page.setContent(`<style>body{margin:0;--primary-background-color:#101418;--card-background-color:#1c2228;--secondary-background-color:#283039;--primary-text-color:#eef2f5;--secondary-text-color:#a7b1ba;--primary-color:#369cec;--text-primary-color:#fff;--divider-color:#374049}</style><meshcore-workspace></meshcore-workspace>`);
    await page.addScriptTag({path:path.resolve(__dirname,'../custom_components/meshcore_sender/www/workspace.js')});
    await page.evaluate(() => {
      window.calls = [];
      const now = Date.now()/1000;
      const state = {entry_id:'fixture', entries:[{id:'fixture',name:'Radio'}],available:true,
        health:{radio_ok:true},history_supported:true, favorites:[], settings:{interval:30,target:'dm:OptimusPrime'},
        nodes:[{id:'dm:OptimusPrime',name:'OptimusPrime',kind:'node'}, {id:'chan:1',name:'Family Mesh',kind:'private'},
          {id:'dm:Long',name:'A rather long contact name for mobile overflow checks',kind:'repeater'}],
        messages:[{id:'one',conversation:'pk:abc',target:'dm:OptimusPrime',name:'OptimusPrime',sender:'OptimusPrime',text:'<img src=x onerror="window.hacked=true"> Hello',received_at:now,direction:'in',status:'received'},
          {id:'two',conversation:'chan:1',target:'chan:1',name:'Family Mesh',sender:'You',text:'Radio check',received_at:now-100,direction:'out',status:'broadcast'}],
        range:{server_now:now,running:false,targets:[],sent:0,acked:0,interval:30,log:[],per_target:{}}};
      document.querySelector('meshcore-workspace').hass = {callWS:async msg => {
        window.calls.push(msg);
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
    await page.close();
  }
  await browser.close();
  assert.deepEqual(errors,[]);
  console.log('Workspace browser checks passed at 375, 390, 768 and 1366px; fixture actions only, no radio transmissions.');
})().catch(err => {console.error(err);process.exit(1);});
