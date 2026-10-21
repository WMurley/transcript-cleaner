// The final check card asks one plain question per leftover and never flags ordinary words starting a list item.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium, EXE, PYTHON} from './test_browser.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HOME = path.join(HERE, `ClientVault-finalui-${process.pid}`);
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
  await api('/api/upload',{files:[{name:'notes.md',text:'Morgan Reyes: Notes from the week.\n'}]});
  // plant leftovers straight into the clean copy, as if the detector had missed them
  const state=await api('/api/state');
  const cleanName=state.data.calls.find(c=>c.file==='notes.md').clean_name;
  const cleanFile=path.join(HOME,'clean',cleanName);
  fs.appendFileSync(cleanFile,'\n# Follow-ups from this week\n- Send the checklist.\n- Ask the print shop about menus.\n- Read the next chapter.\n'
    +'- The quote from Tidewater Freight is due. Write to ops@tidewater.example.\n');
  await page.reload(); await page.click('[data-call="notes.md"]');
  await page.waitForSelector('.fc-row');
  const qs=await page.locator('.fc-q').allTextContents();
  check('ordinary words starting a list item or heading are not asked about', !qs.some(q=>/Follow|Send|Ask|Read/.test(q)));
  check('a missed company is asked as one plain question', qs.includes('Is “Tidewater Freight” the name of a person or a company?'));
  check('a leftover email says what it is', qs.some(q=>q.startsWith('An email address is still showing')));
  const answers=async text=>(await page.locator('.fc-row',{hasText:text}).locator('button').allTextContents()).join('|');
  check('the answers match the question', await answers('Tidewater Freight” the name')==='Yes, hide it|No, leave it'
    && await answers('An email address')==='Hide it|Leave it showing');
  check('no jargon labels on the card', !(await page.textContent('#final-check')).match(/Might be a name|fine-to-keep|Codes like/));
  if (process.env.FC_SHOT) { await page.emulateMedia({colorScheme:'dark'}); await page.locator('#final-check').screenshot({path:process.env.FC_SHOT}); }
  check('browser has no runtime errors',errors.length===0);
  console.log(`\n${checks.filter(Boolean).length}/${checks.length} final check UI checks passed`);
  if(checks.some(c=>!c)) process.exitCode=1;
} finally {
  await browser?.close(); server.kill();
  await new Promise(r=>setTimeout(r,800));
  fs.rmSync(HOME,{recursive:true,force:true});  // this run's throwaway vault
}
