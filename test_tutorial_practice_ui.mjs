// While the guided tutorial runs, Settings must not say practice is on (Wade, 10-21: he thought he was in practice
// mode and was still in the tutorial). It offers one button that leaves the tutorial and opens the sample calls.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium, EXE, PYTHON} from './test_browser.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HOME = path.join(HERE, `ClientVault-tutpractice-${process.pid}`);
const themes = path.join(HOME, '_themes');
fs.mkdirSync(themes, {recursive:true});
fs.writeFileSync(path.join(themes, 'active.json'), JSON.stringify({tour_done:true}));
const server = spawn(PYTHON, ['-u', path.join(HERE, 'test_tutorial_server.py'), '--no-window'], {env:{...process.env, CLEANER_HOME:HOME, CLEANER_THEMES:themes}});
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
  await api('/api/tutorial',{action:'start'});
  await page.reload(); await page.waitForSelector('main h1');
  await page.evaluate(()=>{ view='settings'; render(); });
  const settings=await page.textContent('main');
  check('during the tutorial, Settings says you are in the tutorial', settings.includes("You're in the guided tutorial right now"));
  check('...and never offers "Leave practice", which read as if practice mode were on', !(await page.locator('[data-action=practice-off]').count()));
  await page.click('[data-action=tutorial-to-practice]');
  await page.waitForFunction(()=>!S.tutorial?.active && S.practice && S.calls.length>1);
  const st=(await api('/api/state')).data;
  check('one click leaves the tutorial and opens the practice sample calls', !st.tutorial.active && st.practice
    && st.calls.some(c=>c.file==='zoom-2026-09-14-bluefern-kickoff.txt'));
  check('...with the sample clients saved, so Put names back works on them', st.clients.some(c=>c.code==='C001' && c.full_name==='Jane Whitfield'));
  check('the practice banner shows, not the tutorial one', (await page.textContent('main')).includes('Practice mode.'));
  check('browser has no runtime errors',errors.length===0);
  console.log(`\n${checks.filter(Boolean).length}/${checks.length} tutorial-to-practice checks passed`);
  if(checks.some(c=>!c)) process.exitCode=1;
} finally {
  await browser?.close(); server.kill();
  await new Promise(r=>setTimeout(r,800));
  for (const d of [HOME, HOME+'-practice']) fs.rmSync(d,{recursive:true,force:true});  // this run's throwaway vaults
}
