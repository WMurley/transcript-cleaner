import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium, EXE, PYTHON} from './test_browser.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HOME = path.join(HERE, `ClientVault-review-${process.pid}`);
const themes = path.join(HOME, '_themes');
fs.mkdirSync(themes, {recursive:true});
fs.writeFileSync(path.join(themes, 'active.json'), JSON.stringify({tour_done:true}));
// strict mode (calls wait until every name is answered): this suite checks those workflows
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], {env:{...process.env, CLEANER_HOLD_UNKNOWN: '1', CLEANER_HOME:HOME, CLEANER_THEMES:themes}});
let browser;
const checks=[], errors=[];
const check=(label, ok)=>{checks.push(!!ok); console.log((ok?'PASS  ':'FAIL  ')+label);};
try {
  const url=await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(new Error('App startup timed out')),20000);
    server.stdout.on('data', d=>{const m=String(d).match(/http:\/\/127\.0\.0\.1:\d+\//); if(m){clearTimeout(timeout);resolve(m[0]);}});
    server.on('exit', c=>{clearTimeout(timeout);reject(new Error('Server exited '+c));});
  });
  browser=await chromium.launch({executablePath:EXE});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(url); await page.waitForSelector('main h1');
  const token=await page.evaluate(()=>TOKEN);
  const api=(route,body)=>page.evaluate(async([r,b,t])=>{
    const response=await fetch(r,{method:b?'POST':'GET',headers:{'X-Token':t,'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});
    return {status:response.status,data:await response.json()};
  },[route,body,token]);
  await api('/api/allow',{add:'Morgan Reyes'});
  const jane=await api('/api/client',{full_name:'Jane Whitfield'});
  const right=await api('/api/client',{full_name:'Jane Other'});
  await api('/api/upload',{files:[{name:'one.txt',text:'Jane Whitfield: Scope approved.\nMorgan Reyes: Mark the invoice paid.'},{name:'other.txt',text:'Jane Whitfield: Other scope pending.'}]});
  await api('/api/approve-export',{file:'one.txt'});
  await page.reload(); await page.click('[data-call="one.txt"]'); await page.click('[data-tab=compare]');
  await page.waitForSelector('#compare-original [data-action=correct-change]');
  check('before/after shows the private original alongside the coded copy', (await page.textContent('#compare-original')).includes('Jane Whitfield') && !(await page.textContent('#doc')).includes('Jane Whitfield'));
  check('ordinary words are not highlighted as replacements', !(await page.locator('#compare-original .compare-change').allTextContents()).some(s=>s.includes('Mark')));
  for(const width of [1440,900,390]) {
    await page.setViewportSize({width,height:1000});
    check(`before/after fits at ${width}px`,!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)));
  }
  await page.setViewportSize({width:1440,height:1000});
  page.once('dialog', d=>d.accept('Jane Whitfield'));
  await page.click('#compare-original [data-action=correct-change]');
  check('clicking a highlighted original opens a call-specific correction',await page.inputValue('#identity-form [name=action]:checked')==='link_call');
  await page.selectOption('#identity-form [name=code]',right.data.code);
  await page.click('#identity-form button[type=submit]');
  await page.waitForFunction(c=>!identityDraft && document.getElementById('doc')?.textContent.includes(c),right.data.code);
  const updated=await api('/api/state');
  check('a correction revokes prior export approval',!updated.data.calls.find(c=>c.file==='one.txt').export_approved);
  const untouched=await api('/api/call?file=other.txt&kind=clean');
  check('a call-specific correction leaves the other call and saved record unchanged',untouched.data.text.includes(jane.data.code)&&updated.data.clients.find(c=>c.code===jane.data.code).full_name==='Jane Whitfield');
  const reconstruct=await api('/api/compare?file=one.txt');
  const original=await api('/api/call?file=one.txt&kind=raw');
  const clean=await api('/api/call?file=one.txt&kind=clean');
  check('comparison columns reconstruct the complete saved copies',reconstruct.data.original.map(s=>s.text).join('')===original.data.text && reconstruct.data.clean.map(s=>s.text).join('')===clean.data.text);

  await api('/api/upload',{files:[{name:'group-one.txt',text:'Theo Marchetti: Scope approved.'},{name:'group-two.txt',text:'Theo Marchetti: Scope pending.'}]});
  await page.reload(); await page.click('[data-view=review]');
  check('matching questions appear once, naming both calls',await page.locator('.rv-row').count()===1&&(await page.textContent('.rv-row')).includes('two calls'));
  await page.click('[data-rv-open]');
  check('...and show both calls\' context when opened',(await page.textContent('.rv-row')).includes('group-one.txt')&&(await page.textContent('.rv-row')).includes('group-two.txt'));
  const rows=await page.evaluate(()=>S.review);
  const group=await page.evaluate(()=>reviewGroups()[0]);
  await page.click('[data-identity-action=hide_call]');
  const second=rows.find(r=>r.file==='group-two.txt').id;
  await page.uncheck(`#identity-form [data-review-row="${second}"]`);
  await page.click('#identity-form button[type=submit]'); await page.waitForFunction(()=>!identityDraft);
  let state=await api('/api/state');
  check('a grouped call-specific answer applies only to checked calls',state.data.calls.find(c=>c.file==='group-one.txt').status==='clean'&&state.data.calls.find(c=>c.file==='group-two.txt').status==='held');
  const stale=await api('/api/identity',{review_ids:group.group_ids,kind:'person',action:'hide_call'});
  check('a stale group is refused rather than partially applied',stale.status===400);
  await api('/api/upload',{files:[{name:'group-three.txt',text:'Theo Marchetti: Another scope approved.'}]});
  await page.reload(); await page.click('[data-view=review]'); await page.click('[data-identity]');
  await page.click('#identity-form button[type=submit]'); await page.waitForFunction(()=>!identityDraft);
  state=await api('/api/state');
  check('one grouped record releases matching calls without duplicate people',state.data.clients.filter(c=>c.full_name==='Theo Marchetti').length===1&&state.data.calls.filter(c=>c.file.startsWith('group-')).every(c=>c.status==='clean'));
  const held=await api('/api/upload',{files:[{name:'held.txt',text:'Derek Olsen: Scope pending.'}]});
  const heldCompare=await api('/api/compare?file=held.txt');
  check('comparison refuses held calls until questions are resolved',heldCompare.status===409);
  check('browser has no runtime errors',errors.length===0);
  console.log(`\n${checks.filter(Boolean).length}/${checks.length} review UI checks passed`);
  if(checks.some(c=>!c)) process.exitCode=1;
} finally {await browser?.close();server.kill();}
