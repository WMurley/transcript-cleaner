// Review names in the default mode: names grouped under their call (a name in several calls asked once at the top),
// a progress bar that moves as names are decided, and an AI-tools fold that stays open across clicks.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium, EXE, PYTHON} from './test_browser.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HOME = path.join(HERE, `ClientVault-progress-${process.pid}`);
const themes = path.join(HOME, '_themes');
fs.mkdirSync(themes, {recursive:true});
fs.writeFileSync(path.join(themes, 'active.json'), JSON.stringify({tour_done:true}));
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], {env:{...process.env, CLEANER_HOME:HOME, CLEANER_THEMES:themes}});
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
  await api('/api/owner',{name:'Morgan Reyes'});
  await api('/api/upload',{files:[{name:'progress.txt',text:[
    'Morgan Reyes: Thanks for joining. Priya Nair, Priya Nair asked about the timeline.',
    'Morgan Reyes: Lena Haugen sent the quote and Marcus Delgado signed it.',
    'Morgan Reyes: Ruth Okafor will check the numbers with Greenline Grocers.',
    'Morgan Reyes: I asked Hermes to draft the summary, and Hermes did it well.',
  ].join('\n')},{name:'second.txt',text:'Morgan Reyes: Lena Haugen called again about the quote.\n'}]});
  await page.reload(); await page.waitForSelector('.rv-tag');
  if (process.env.CALLS_SHOT) { await page.emulateMedia({colorScheme:'dark'}); await page.screenshot({path:process.env.CALLS_SHOT}); await page.emulateMedia({colorScheme:'light'}); }
  const tag=await page.locator('.rv-tag').first().evaluate(b=>({button:b.tagName==='BUTTON', text:b.textContent, oneLine:b.getBoundingClientRect().height<30}));
  check('a clean call with names left shows a one-line pill, not a wrapped link', tag.button && tag.oneLine && /^\d+ names? to review/.test(tag.text));
  await page.locator('.rv-tag').first().click(); await page.waitForSelector('.rv-progress');
  check('...and the pill opens Review names', (await page.textContent('main h1')).includes('Review names'));
  const total=await page.evaluate(()=>reviewGroups().length);
  const titles=await page.locator('.rv-call-title').allTextContents();
  const card=text=>page.locator('.rv-call',{has:page.locator('.rv-call-title',{hasText:text})});
  check('names are grouped under each call, with the call name as the heading',
    titles.includes('progress.txt') && await page.locator('details.rv-once:not(.rv-tools)').count()===0);
  check('a name in two calls is asked once, in a card at the top', titles[0]==='In more than one call'
    && (await card('In more than one call').textContent()).includes('Lena Haugen') && !(await card('progress.txt').textContent()).includes('Lena Haugen'));
  check('rows inside a call card leave the file name out', !(await card('progress.txt').locator('.rv-meta').allTextContents()).some(t=>t.includes('progress.txt')));
  check('the progress bar starts at zero of every name', (await page.textContent('.rv-progress')).includes(`0 of ${total} names reviewed`));
  const onceRows=()=>card('progress.txt').locator('.rv-row');
  const before=await onceRows().count();
  await onceRows().last().locator('[data-rv-quick=keep]').click();
  await page.waitForFunction(n=>[...document.querySelectorAll('.rv-call')].find(c=>c.querySelector('.rv-call-title').textContent==='progress.txt').querySelectorAll('.rv-row').length===n-1, before);
  check('Fine to show on a name leaves the rest of the list in view',
    await onceRows().count()===before-1 && await onceRows().first().isVisible());
  if (process.env.REVIEW_SHOT) await page.screenshot({path:process.env.REVIEW_SHOT, fullPage:true});  // optional: look at it
  check('...and moves the progress bar', (await page.textContent('.rv-progress')).includes(`1 of ${total} names reviewed`)
    && await page.evaluate(()=>parseFloat(document.querySelector('.rv-bar > span').style.width))>0);
  const tools=page.locator('details.rv-tools');
  if (await tools.count()) {
    await tools.locator('summary').click();
    await page.locator('.rv-list [data-rv-quick=keep]').first().click();
    await page.waitForFunction(n=>reviewGroups().length===n-2, total);
    check('the AI-tools fold stays open after a click elsewhere on the page', await page.locator('details.rv-tools').evaluate(d=>d.open));
  } else check('the sample has an AI-tools fold to test', false);
  await page.click('[data-rv-hide]');  // Keep all hidden
  await page.waitForFunction(()=>!reviewGroups().filter(r=>rvKind(r)!=='tool').length);
  for (const b of await page.locator('[data-rv-quick=tool]').all()) { await b.click(); await page.waitForTimeout(300); }
  await page.waitForSelector('.card.empty');
  check('finishing shows a full bar with every name counted', (await page.textContent('.rv-progress')).includes(`${total} of ${total} names reviewed`)
    && (await page.textContent('.rv-progress')).includes('All done'));
  check('browser has no runtime errors',errors.length===0);
  console.log(`\n${checks.filter(Boolean).length}/${checks.length} review progress checks passed`);
  if(checks.some(c=>!c)) process.exitCode=1;
} finally {
  await browser?.close(); server.kill();
  await new Promise(r=>setTimeout(r,800));
  fs.rmSync(HOME,{recursive:true,force:true});  // this run's throwaway vault
}
