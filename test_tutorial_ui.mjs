// Invented data only; the native folder opener is replaced in the test launcher.
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium,EXE,PYTHON} from './test_browser.mjs';
const HERE=path.dirname(fileURLToPath(import.meta.url));
const WIDTH=Number(process.argv[2]||1440),OUT=path.join(HERE,'_tutorial-shots');fs.mkdirSync(OUT,{recursive:true});
const HOME=path.join(HERE,`ClientVault-tutorial-${process.pid}`),themes=path.join(HOME,'_themes');
fs.mkdirSync(themes,{recursive:true});
const server=spawn(PYTHON,['-u',path.join(HERE,'test_tutorial_server.py'),'--no-window'],{env:{...process.env,CLEANER_HOME:HOME,CLEANER_THEMES:themes}});
let browser,page,lastCheck='startup';
const checks=[],errors=[];
const check=(label,ok)=>{checks.push(!!ok);lastCheck=label;console.log((ok?'PASS  ':'FAIL  ')+label);};
try{
 const url=await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(Error('Startup timeout')),20000);
   server.stdout.on('data',d=>{const m=String(d).match(/http:\/\/127\.0\.0\.1:\d+\//);if(m){clearTimeout(timer);resolve(m[0]);}});
   server.stderr.on('data',d=>console.error(String(d)));
   server.on('exit',c=>{clearTimeout(timer);reject(Error('Server exited '+c));});
 });
 browser=await chromium.launch({executablePath:EXE});
 page=await browser.newPage({viewport:{width:WIDTH,height:1000}});
 page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(url);await page.waitForSelector('[data-action=tour-skip]');
 check('first-run welcome offers the guided sample',await page.locator('#tour [data-action=tutorial-start]').count()===1);
 await page.click('[data-action=tour-skip]');
 const importStructure=await page.locator('#drop').evaluate(el=>({text:el.innerText,classes:el.className,padding:getComputedStyle(el).padding,background:getComputedStyle(el).backgroundColor}));
 check('sample is available in the real import area',await page.locator('#drop [data-action=tutorial-load]').count()===1);
 await page.evaluate(()=>{S.mode='dark';render();});
 await page.screenshot({path:path.join(OUT,`normal-dark-${WIDTH}.png`)});
 const intakeClip=()=>page.evaluate(()=>{const a=document.querySelector('.export-destination').getBoundingClientRect(),b=document.getElementById('drop').getBoundingClientRect();return {x:a.left,y:a.top,width:a.width,height:b.bottom-a.top};});
 await page.screenshot({path:path.join(OUT,`normal-intake-${WIDTH}.png`),clip:await intakeClip()});
 await page.evaluate(()=>{S.mode='auto';render();});
 check('unset export folder has a visible heading, status and primary chooser',await page.locator('.export-destination h2').innerText().then(t=>t.includes('Clean export folder')&&t.includes('Not set'))&&await page.locator('.export-destination [data-action=output-browse].primary').count()===1);
 const panelGap=()=>page.evaluate(()=>{const folder=document.querySelector('.export-destination').getBoundingClientRect(),drop=document.getElementById('drop').getBoundingClientRect();return drop.top-folder.bottom;});
 check('real export folder and import panels have at least 20px separation',(await panelGap())>=20);
 await page.screenshot({path:path.join(OUT,`normal-${WIDTH}.png`)});
 const token=await page.evaluate(()=>TOKEN);
 const api=(route,body)=>page.evaluate(async([r,b,t])=>{
  const response=await fetch(r,{method:b?'POST':'GET',headers:{'X-Token':t,'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});
  return {status:response.status,data:await response.json()};
 },[route,body,token]);
 check('sample loader refuses to run in the private workspace',(await api('/api/tutorial',{action:'load'})).status===400);
 await api('/api/client',{full_name:'Jane Whitfield'});
 await api('/api/allow',{add:'Morgan Reyes'});
 fs.mkdirSync(HOME+'-exports',{recursive:true});
 await api('/api/output',{path:HOME+'-exports'});
 await api('/api/upload',{files:[{name:'existing.txt',text:'Jane Whitfield: Existing invented call.'}]});
 const prior=(await api('/api/state')).data;
 await page.reload();await page.click('[data-view=clients]');await page.click('[data-action=new-client]');
 await page.fill('#client-form [name=full_name]','Unsubmitted private draft');
 await page.click('#app-tools [data-action=tutorial-start]');
 await page.waitForFunction(()=>S.tutorial?.active);
 let state=(await api('/api/state')).data;
 const practiceHome=state.home;
 check('tutorial starts empty, apart from its invented owner',!state.calls.length&&!state.clients.length&&!state.companies.length&&state.allow.includes('Morgan Reyes'));
 check('sample storage and exports are separate from the original workspace',state.home!==prior.home&&state.output_dir!==prior.output_dir);
 check('private form draft is absent from the tutorial',!(await page.textContent('body')).includes('Unsubmitted private draft'));
 check('Next waits for the sample to be imported',await page.isDisabled('[data-action=guide-next]'));
 check('cannot finish before exporting and opening the folder',(await api('/api/tutorial',{action:'finish'})).status===400);
 check('invalid tutorial steps leave progress unchanged',(await api('/api/tutorial',{action:'progress',step:7})).status===400&&(await api('/api/state')).data.tutorial.step===0);
 for(const [route,body]of [['/api/output',{path:HOME+'-other'}],['/api/vault',{path:HOME}],['/api/practice',{on:true}],['/api/fathom',{pull_ids:[1]}],['/api/export-review',{on:false}]])
  check(`tutorial blocks ${route} from changing private context`,(await api(route,body)).status===400);
 await page.click('[data-action=guide-pause]');check('Pause hides the guide but retains the sample workspace',await page.locator('#guide-panel').isHidden()&&(await api('/api/state')).data.home===practiceHome);
 await page.click('#app-tools [data-action=tutorial-start]');
 const tutorialStructure=await page.locator('#drop').evaluate(el=>({text:el.innerText,classes:el.className,padding:getComputedStyle(el).padding,background:getComputedStyle(el).backgroundColor}));
 check('tutorial preserves the real import controls, copy and styling',JSON.stringify(tutorialStructure)===JSON.stringify(importStructure)&&await page.locator('#drop [data-action=pick], #drop [data-action=paste-open], #drop [data-action=fathom-open]').count()===3&&await page.locator('#picker').count()===1);
 check('real-call Fathom import stays visible but disabled in the sample workspace',await page.isDisabled('#drop [data-action=fathom-open]'));
 check('tutorial export folder and import panels have at least 20px separation',(await panelGap())>=20);
 await page.evaluate(()=>{S.mode='dark';render();});
 await page.click('[data-action=guide-pause]');
 await page.screenshot({path:path.join(OUT,`tutorial-dark-${WIDTH}.png`)});
 await page.screenshot({path:path.join(OUT,`tutorial-intake-${WIDTH}.png`),clip:await intakeClip()});
 await page.evaluate(()=>{S.mode='auto';render();});
 await page.click('#app-tools [data-action=tutorial-start]');
 await page.click('#sample-preview summary');
 check('sample preview explicitly provides invented names and contacts',(await page.textContent('#sample-preview pre')).includes('Derek Olsen')&&(await page.textContent('#sample-preview pre')).includes('derek@bluefern.example'));
 await page.screenshot({path:path.join(OUT,`sample-${WIDTH}.png`)});
 await page.click('[data-action=tutorial-load]');await page.waitForFunction(()=>S.calls.length===1&&view==='review');
 const originalSample=await api('/api/call?file=guided-first-call.txt&kind=raw');  // calls are clean straight away now; the original is kept as usual
 check('one click loads the supplied transcript and opens the review list',originalSample.data.text===(await api('/api/state')).data.tutorial.sample);
 check('invented unknown identities are hidden straight away and listed for review',await page.evaluate(()=>S.calls[0].status==='clean'&&S.review.some(r=>r.name==='Derek Olsen'&&/^PERSON-\d+$/.test(r.token))));
 const derek=(await api('/api/state')).data.review.find(r=>r.name==='Derek Olsen');
 const guideText=()=>page.locator('#guide-panel').innerText();
 const waitForTarget=()=>page.waitForFunction(()=>{const t=document.querySelector('.guided-target'),p=document.getElementById('guide-panel');if(!t)return false;const r=t.getBoundingClientRect(),b=p.getBoundingClientRect();return r.top>=68&&r.bottom<=innerHeight-16&&!(r.bottom>b.top&&r.top<b.bottom&&r.right>b.left&&r.left<b.right);});
 check('Needs you explains which card to open and highlights its real button',(await guideText()).includes('Click Save as a client')&&await page.locator(`[data-identity="${derek.id}"].guided-target`).count()===1);
 await page.click(`[data-identity="${derek.id}"]:not([data-identity-action])`);
 await page.waitForSelector('#identity-form');
 check('opening the form changes the instructions to person details',(await guideText()).includes('1. Confirm the person')&&await page.locator('#identity-form [name=full_name].guided-target').count()===1);
 check('tutorial field outline is red',await page.locator('.guided-target').evaluate(el=>getComputedStyle(el).outlineColor)==='rgb(229, 57, 53)');
 await page.fill('#identity-form [name=aliases]','D. Olsen');
 await page.click('[data-action=guide-show-company]');
 await waitForTarget();
 check('company guidance names both forms and highlights the company field',(await guideText()).includes('Bluefern Bakery, Bluefern')&&await page.locator('#identity-form [name=company_names].guided-target').count()===1);
 await page.screenshot({path:path.join(OUT,`company-fields-${WIDTH}.png`)});
 await page.click('[data-action=guide-show-save]');
 await waitForTarget();
 check('save guidance points to the real submit and explains what comes next',(await guideText()).includes('Next takes you to Companies')&&await page.locator('#identity-form button[type=submit].guided-target').count()===1);
 check('guide field navigation preserves edits and does not create records',await page.inputValue('#identity-form [name=aliases]')==='D. Olsen'&&await page.evaluate(()=>!S.clients.length&&!S.companies.length)&&await page.isDisabled('[data-action=guide-next]'));
 await page.screenshot({path:path.join(OUT,`save-directions-${WIDTH}.png`)});
 await page.click('[data-action=identity-close]');
 await page.click(`[data-identity="${derek.id}"]:not([data-identity-action])`);
 check('reopening a question restores the first form instruction',(await guideText()).includes('1. Confirm the person'));
 await page.screenshot({path:path.join(OUT,`person-${WIDTH}.png`)});
 // The inline company suggestion is the same workflow used for a real call.
 await page.selectOption('#identity-form [name=company_code]','__new__');
 await page.fill('#identity-form [name=company_names]','Bluefern Bakery, Bluefern');
 await page.click('#identity-form button[type=submit]');await page.waitForFunction(()=>!identityDraft);
 // Answer any separate company question, using the saved company when offered.
 if(await page.locator('[data-identity]').count()){
  await page.locator('[data-identity]').first().click();
  const action=page.locator('#identity-form [name=action][value=existing]');
  if(await action.count())await action.check();
  await page.selectOption('#identity-form [name=code]',(await api('/api/state')).data.companies[0].code);
  await page.click('#identity-form button[type=submit]');await page.waitForFunction(()=>!identityDraft);
 }
 await page.waitForFunction(()=>S.calls[0].status==='clean');
 const savedSample=(await api('/api/state')).data;
 await api('/api/tutorial',{action:'load',files:[{name:'private.txt',text:'Unexpected input'}]});
 check('repeated sample loads preserve tagging and use only the built-in sample',JSON.stringify((await api('/api/state')).data.calls)===JSON.stringify(savedSample.calls)&&(await api('/api/call?file=guided-first-call.txt&kind=raw')).data.text===originalSample.data.text);
 check('tagging links a person to the company and releases the sample',await page.evaluate(()=>S.clients.length===1&&S.companies.length===1&&S.clients[0].company_code===S.companies[0].code));
 check('saving confirms success and highlights Next',(await guideText()).includes('Person and company saved')&&await page.locator('[data-action=guide-next].guided-target:not([disabled])').count()===1);
 await page.click('[data-action=guide-next]');await page.waitForFunction(()=>view==='companies');
 check('Companies shows its linked person',await page.locator('main').innerText().then(t=>t.includes('Derek Olsen')));
 check('company instructions point directly to the saved person',await page.locator('[data-action=company-edit-person].guided-target').count()===1);
 await page.click('[data-action=company-edit-person].guided-target');
 check('viewing the person explains the next comparison step',(await guideText()).includes('click Next to review before and after')&&await page.locator('[data-action=guide-next].guided-target').count()===1);
 await page.click('[data-action=guide-back]');await page.waitForFunction(()=>view==='review');
 check('Back preserves completed work',await page.evaluate(()=>S.clients.length===1&&S.tutorial.step===1));
 await page.click('[data-action=guide-next]');await page.click('[data-action=guide-next]');
 await page.waitForSelector('#compare-original .compare-change');
 check('before/after shows source identities and sanitized replacements',(await page.textContent('#compare-original')).includes('Derek Olsen')&&!(await page.textContent('#doc')).includes('Derek Olsen'));
 await page.screenshot({path:path.join(OUT,`comparison-${WIDTH}.png`)});
 check('comparison requires a review acknowledgement',await page.isDisabled('[data-action=guide-next]'));
 check('comparison instructions explain both copies and the acknowledgement',(await guideText()).includes('Original (private)')&&(await guideText()).includes('I checked both copies'));
 await page.click('[data-action=guide-reviewed]');await page.click('[data-action=guide-next]');
 await page.waitForFunction(()=>view==='settings');
 check('folder step keeps both visible paths',await page.locator('main').innerText().then(t=>t.includes('Clean export folder')&&t.includes('Private storage')));
 check('folder instructions explain each destination and the next action',(await guideText()).includes('approved, shareable copies')&&(await guideText()).includes('originals and the saved identity list')&&(await guideText()).includes('Click Next to return to Calls'));
 await page.click('[data-view=clients]');check('manual tab changes offer a return to the current step',await page.locator('[data-action=guide-goto]').count()===1);
 await page.click('[data-action=guide-goto]');
 await page.reload();await page.waitForFunction(()=>view==='settings'&&S.tutorial.step===4);
 check('reload resumes the saved step in its tab',await page.locator('#guide-panel h2').innerText()==='Know where files land');
 await page.click('[data-action=guide-next]');await page.waitForSelector('[data-action=approve-export]');
 await page.click('[data-action=approve-export]');await page.waitForFunction(()=>S.tutorial.exported);
 state=(await api('/api/state')).data;
 const exportFile=path.join(state.output_dir,state.calls[0].clean_name);
 const exported=fs.readFileSync(exportFile,'utf8');
 check('approval writes a neutral filename with sanitized sample text',!path.basename(exportFile).includes('Derek')&&!/Derek|Olsen|Bluefern|459-928-8815|derek@/i.test(exported));
 check('sample was not exported into the original destination',fs.readdirSync(prior.output_dir).length===0);
 check('export success gives a clear next action',(await guideText()).includes('Clean copy exported')&&await page.locator('[data-action=guide-next].guided-target').count()===1);
 await page.click('[data-action=guide-next]');await page.waitForFunction(()=>view==='settings');
 await page.click('[data-action=output-open]');await page.waitForFunction(()=>S.tutorial.folder_opened);
 for(const width of [1440,900,390]){
  await page.setViewportSize({width,height:900});
  check(`guide fits and has reachable controls at ${width}px`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)&&await page.locator('[data-action=guide-next]').isVisible());
 }
 await page.click('[data-action=guide-next]');await page.waitForFunction(()=>!S.tutorial.active);
 state=(await api('/api/state')).data;
 check('Finish restores original calls, identities and output destination',JSON.stringify(state.calls)===JSON.stringify(prior.calls)&&JSON.stringify(state.clients)===JSON.stringify(prior.clients)&&state.home===prior.home&&state.output_dir===prior.output_dir);
 // Reload intentionally loses unsaved drafts; test memory preservation separately.
 await page.setViewportSize({width:1440,height:1000});
 await page.click('[data-view=clients]');await page.click('[data-action=new-client]');
 await page.fill('#client-form [name=full_name]','Unsubmitted private draft');
 await page.click('#app-tools [data-action=tutorial-start]');await page.waitForFunction(()=>S.tutorial.active);
 await page.click('#guide-panel [data-action=guide-exit]');await page.waitForFunction(()=>!S.tutorial.active);
 check('early Exit restores the previous tab and unsaved draft',await page.inputValue('#client-form [name=full_name]')==='Unsubmitted private draft');
 await page.click('[data-view=calls]');
 const hasCalls=await page.evaluate(()=>S.calls.length>0);
 check('once you have calls of your own, the sample steps out of the import area',!hasCalls||(await page.locator('#drop [data-action=tutorial-load], #sample-preview').count())===0);
 if(hasCalls){await page.click('#app-tools [data-action=tutorial-start]');await page.waitForFunction(()=>S.tutorial.active);}
 await page.click('#drop [data-action=tutorial-load]');await page.waitForFunction(()=>S.tutorial.active&&view==='review'&&S.calls.length===1);
 check('the sample still starts an isolated exercise (from Guided tutorial once you have calls)',await page.evaluate(h=>S.home!==h&&S.calls[0].file===S.tutorial.call,prior.home));
 // The student can choose a different question or use scoped hiding. Neither
 // should leave a tutorial checkpoint without directions or a way forward.
 const companyQuestion=(await api('/api/state')).data.review.find(r=>/^Bluefern/.test(r.name));
 await page.click(`[data-identity="${companyQuestion.id}"]:not([data-identity-action])`);
 await page.check('#identity-form [name=kind][value=person]');
 check('opening a company as a person gives the exact correction',(await guideText()).includes('Set Type to Company')&&await page.locator('#identity-form .ie-type.guided-target').count()===1);
 await page.check('#identity-form [name=kind][value=company]');
 check('company-first instructions explain full and short names',(await guideText()).includes('Confirm the company names')&&(await guideText()).includes('Bluefern Bakery, Bluefern'));
 await page.check('#identity-form [name=path][value=hide]');
 check('a scoped-hide choice explains the saved-record exercise',(await guideText()).includes('Create or link a saved record')&&await page.locator('#identity-form .ie-path.guided-target').count()===1);
 await page.click('#identity-form button[type=submit]');await page.waitForFunction(()=>!identityDraft);
 for(let i=0;i<10&&await page.locator('[data-rv-hide]').count();i++){
  await page.locator('[data-rv-hide]').first().click();await page.waitForTimeout(300);  // Keep hidden, one name at a time
 }
 check('hiding every name offers a fresh sample instead of a dead end',await page.locator('[data-action=guide-restart-sample].guided-target').count()===1&&await page.isDisabled('[data-action=guide-next]'));
 const hiddenSampleHome=(await api('/api/state')).data.home;
 await page.click('[data-action=guide-restart-sample]');await page.waitForFunction(h=>S.home!==h&&S.tutorial.step===1&&view==='review',hiddenSampleHome);
 check('fresh-sample recovery restores the review without private data',await page.evaluate(()=>S.calls.length===1&&S.calls[0].status==='clean'&&S.review.some(r=>r.name==='Derek Olsen')&&!S.clients.length&&!S.companies.length));
 await page.click('#guide-panel [data-action=guide-exit]');await page.waitForFunction(()=>!S.tutorial.active);
 check('fresh-sample recovery still restores the original workspace',JSON.stringify((await api('/api/state')).data.calls)===JSON.stringify(prior.calls));
 await api('/api/practice',{on:true});await page.reload();
 const practice=(await api('/api/state')).data;
 await page.click('#app-tools [data-action=tutorial-start]');await page.waitForFunction(()=>S.tutorial.active);
 await page.click('#guide-panel [data-action=guide-exit]');await page.waitForFunction(()=>!S.tutorial.active);
 state=(await api('/api/state')).data;
 check('starting inside practice mode returns to the same practice workspace',state.practice&&state.home===practice.home&&state.calls.length===practice.calls.length);
 check('browser has no runtime errors',errors.length===0);
 console.log(`${checks.filter(Boolean).length}/${checks.length} tutorial UI checks passed`);
 if(checks.some(c=>!c))process.exitCode=1;
}catch(e){
 process.exitCode=1;
 console.error(`CRASH after "${lastCheck}": ${e.message.split('\n')[0]}`);
 const where=await page?.evaluate(()=>({view,step:S?.tutorial?.step,guide:document.getElementById('guide-panel')?.innerText.slice(0,160),draft:!!identityDraft})).catch(()=>null);
 if(where)console.error('App state: '+JSON.stringify(where));
 if(errors.length)console.error('Browser errors: '+errors.join(' | '));
 await page?.screenshot({path:path.join(OUT,'crash.png')}).then(()=>console.error('Screenshot: '+path.join(OUT,'crash.png'))).catch(()=>{});
}finally{await browser?.close();server.kill();}
