// Undo in the app: the pop-up after a one-click decision offers Undo for 10 seconds, and Recent decisions
// lists every answer with Undo. Also pins that a Which client answer updates an already-clean call.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium, EXE, PYTHON} from './test_browser.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HOME = path.join(HERE, `ClientVault-undo-${process.pid}`);
const themes = path.join(HOME, '_themes');
fs.mkdirSync(themes, {recursive:true});
fs.writeFileSync(path.join(themes, 'active.json'), JSON.stringify({tour_done:true}));
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], {env:{...process.env, CLEANER_HOME:HOME, CLEANER_THEMES:themes}});
let browser;
const checks=[], errors=[];
const check=(label, ok)=>{checks.push(!!ok); console.log((ok?'PASS  ':'FAIL  ')+label);};
const shot=async(page,name)=>{ if (process.env.UNDO_SHOTS) await page.screenshot({path:path.join(process.env.UNDO_SHOTS,name)}); };
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
  const alvarez=(await api('/api/client',{full_name:'Mike Alvarez'})).data.code;
  const chen=(await api('/api/client',{full_name:'Mike Chen'})).data.code;
  await api('/api/upload',{files:[{name:'undo.txt',text:'Morgan Reyes: Lena Haugen sent the quote. Mike will sign it.\n'}]});
  const cleanText=async()=>(await api('/api/call?file=undo.txt&kind=clean')).data.text;
  await page.reload(); await page.click('[data-view=review]'); await page.waitForSelector('.rv-row');

  // Fine to show -> Undo from the pop-up
  await page.locator('.rv-row',{hasText:'Lena Haugen'}).locator('[data-rv-quick=keep]').click();
  await page.waitForSelector('#toast.show.has-undo');
  check('Fine to show offers Undo in the pop-up', (await page.textContent('#toast')).includes('Lena Haugen stays visible in every call'));
  await shot(page,'undo-toast.png');
  await page.mouse.move(5,5); await page.waitForTimeout(6000);
  check('...and the Undo stays up longer than a normal pop-up (still there after 6 seconds)', await page.locator('#toast.show .toast-undo').isVisible());
  check('Lena shows in the clean copy before Undo', (await cleanText()).includes('Lena Haugen'));
  await page.click('#toast .toast-undo');
  await page.waitForFunction(()=>S.review.some(r=>r.name==='Lena Haugen'));
  check('Undo puts the name back in Review names', await page.locator('.rv-row',{hasText:'Lena Haugen'}).count()===1);
  check('...hides it again in the clean copy', !(await cleanText()).includes('Lena Haugen'));
  check('...and says so', (await page.textContent('#toast')).includes('Undone'));

  // Which Mike: the answer updates the already-clean call (bug fixed 10-21), and Undo from Recent decisions
  await page.locator('.rv-row',{hasText:'Which Mike?'}).locator(`[data-value="${chen}"]`).click();
  await page.waitForSelector('#toast.show.has-undo');
  check('a Which client answer updates the clean copy right away', (await cleanText()).includes(chen) && !(await cleanText()).includes(alvarez));
  check('...and its pop-up names the client', (await page.textContent('#toast')).includes(`Mike is Mike Chen (${chen})`));
  await page.click('[data-view=decisions]'); await page.waitForSelector('.dec-row');
  const labels=await page.locator('.dec-label').allTextContents();
  check('Recent decisions lists every answer, newest first', labels[0].startsWith('Mike is Mike Chen') && labels.some(l=>l.startsWith('Lena Haugen shows in every call')));
  check('...and marks the undone one', (await page.locator('.dec-row.undone').textContent()).includes('Lena Haugen'));
  await shot(page,'recent-decisions.png');
  await page.locator('.dec-row',{hasText:'Mike is Mike Chen'}).locator('[data-undo]').click();
  await page.waitForSelector('.dec-row.undone >> text=Mike is Mike Chen');
  check('Undo from Recent decisions brings the Which Mike question back', (await api('/api/state')).data.review.some(r=>r.kind==='ambiguous') && !(await cleanText()).includes(chen));

  // the final check's Leave it -> Undo
  const st=(await api('/api/state')).data;
  fs.appendFileSync(path.join(HOME,'clean',st.calls.find(c=>c.file==='undo.txt').clean_name),'\n- The quote from Tidewater Freight is due.\n');
  await page.reload(); await page.click('[data-call="undo.txt"]'); await page.waitForSelector('.fc-row');
  await page.locator('.fc-row',{hasText:'Tidewater Freight'}).locator('[data-final-ok]').click();
  await page.waitForSelector('#toast.show.has-undo');
  check('Leave it in the final check offers Undo', await page.locator('.fc-row',{hasText:'Tidewater Freight'}).count()===0);
  await page.click('#toast .toast-undo');
  await page.waitForSelector('.fc-row >> text=Tidewater Freight');
  check('...and Undo brings the question back', await page.locator('.fc-row',{hasText:'Tidewater Freight'}).count()===1);

  check('browser has no runtime errors',errors.length===0);
  console.log(`\n${checks.filter(Boolean).length}/${checks.length} undo UI checks passed`);
  if(checks.some(c=>!c)) process.exitCode=1;
} finally {
  await browser?.close(); server.kill();
  await new Promise(r=>setTimeout(r,800));
  fs.rmSync(HOME,{recursive:true,force:true});  // this run's throwaway vault
}
