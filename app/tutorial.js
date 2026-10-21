// Optional guided sample. Private form drafts stay only in this window's memory.
let guideOpen = true, guideReturnUI = null;
let guideReviewPart = 0, guideReviewDraftId = null;
const GUIDE = [
  {view:'calls', title:'Try a sample call', target:()=>guideCall()?'[data-action=guide-next]':'[data-action=tutorial-load]', body:'Your first exercise is provided: a made-up client call with a person, company, email and phone number. Click Use sample call to clean it and see which details need your review. You can try your own transcripts after the tutorial.', done:()=>!!guideCall()},
  {view:'review', context:guideReviewContext, done:()=>guideCall()?.status==='clean' && !!guidePerson() && S.companies.length>0},
  {view:'companies', context:guideCompanyContext, done:()=>!!guidePerson()?.company_code},
  {view:'calls', context:guideCompareContext, done:()=>!!S.tutorial.reviewed&&!identityDraft},
  {view:'settings', title:'Know where files land', target:'.settings-grid > .card:first-child', body:'Read the two folder labels in Settings. This exercise already has a temporary export folder, so no setup is needed here.', items:['Clean export folder: approved, shareable copies land here.','Private storage: originals and the saved identity list live here.','Click Next to return to Calls and approve the sample.'], done:()=>true},
  {view:'calls', title:'Approve and export', target:'[data-action=approve-export]', body:'Click Approve clean copy and export after reviewing the sample. The app sends only the clean copy to the tutorial folder. If a correction changes it later, it needs approval again.', done:()=>!!guideCall()?.export_approved && !!S.tutorial.exported},
  {view:'settings', title:'Find your exported copy', target:'[data-action=output-open]', body:'Click Open folder beside Clean export folder. You will find the sample under a neutral call ID. Finish returns you to your own workspace, ready to use the same steps with a real call.', done:()=>!!S.tutorial.exported && !!S.tutorial.folder_opened},
];
function guideCall(){return S.calls.find(c=>c.file===S.tutorial?.call);}
function guidePerson(){const c=guideCall();return c&&S.clients.find(p=>codesOf(c).includes(p.code));}
function guideReviewContext(){
  const d=identityDraft, pending=S.review.filter(r=>r.file===S.tutorial.call);
  const button=r=>`[data-identity="${r.id}"]:not([data-identity-action])`;
  if(!d){
    guideReviewPart=0;guideReviewDraftId=null;
    if(GUIDE[1].done())return {title:'Person and company saved',body:'The sample is now clean. Your saved records give the person and company stable codes. Click Next to see Derek inside Companies.',target:'[data-action=guide-next]'};
    const person=pending.find(r=>r.name==='Derek Olsen');
    if(person)return {title:'Start with Derek Olsen',body:'Review names lists the names the cleaner wasn’t sure about. They’re already hidden in the clean copy; saving Derek as a client gives him a lasting code instead.',items:['Find Derek Olsen in the list.','Click Save as a client on his row.','The next instructions will walk you through the form.'],target:button(person)};
    if(pending.length)return {title:'Resolve the remaining name',body:`The sample still has a question about ${pending[0].name}. Click its Save as a person or Save as a company choice. For Bluefern, set Type to Company and include both Bluefern Bakery and Bluefern as names.`,target:button(pending[0])};
    return {title:'Try creating the linked records',body:'The sample is resolved, but this exercise also needs a saved person and company. Start a fresh sample to practice creating them together.',action:{name:'guide-restart-sample',label:'Start a fresh sample'},target:'[data-action=guide-restart-sample]'};
  }
  if(d.file!==S.tutorial.call)return {title:'Return to the sample question',body:'Close this form with Cancel, then open the Derek Olsen card from the sample call.',target:'[data-action=identity-close]'};
  if(guideReviewDraftId!==d.review_id){guideReviewDraftId=d.review_id;guideReviewPart=0;}
  const isCompany=/^bluefern\b/i.test(d.detected);
  if(d.kind!==(isCompany?'company':'person'))return {title:isCompany?'This name is a company':'This name is a person',body:`Set Type to ${isCompany?'Company':'Person'} for ${d.detected}. Then follow the form instructions.`,target:'#identity-form .ie-type'};
  if(!['new','existing'].includes(d.action))return {title:'Create or link a saved record',body:'This exercise teaches saved identities. Set Answer to Save it, then choose New, or Someone already saved if you created the record earlier.',target:'#identity-form .ie-path'};
  if(d.action==='existing')return {title:'Choose the saved record',body:`Select the saved ${isCompany?'company':'person'} that matches ${d.detected}, then click Save.`,items:['Check the name and code in the dropdown.','Saving checks the sample again.'],target:d.code?'#identity-form button[type=submit]':'#identity-form [name=code]'};
  if(isCompany)return {title:'Confirm the company names',body:'In Company name and short names, enter Bluefern Bakery, Bluefern. The transcript uses both forms, so both should point to the same company.',items:['Keep Answer on Save it, with New company chosen.','Click Save after checking the names.'],target:'#identity-form [name=names]'};
  if(guideReviewPart===0)return {title:'1. Confirm the person',body:'Check the first part of the form. These values are already filled in for the sample.',items:['Type: Person.','Answer: Save it, New person.','Full name: Derek Olsen. Other names can stay blank for this sample.'],target:'#identity-form [name=full_name]',action:{name:'guide-show-company',label:'Show company fields'}};
  if(guideReviewPart===1)return {title:'2. Link the company',body:'Use the Company field in the same form to link Derek to Bluefern.',items:[S.companies.length?'Choose Bluefern Bakery from Company, or add it here if it is not listed.':'Choose Add a company here... under Company.','Check Company name and short names: Bluefern Bakery, Bluefern.','Emails and phone numbers are optional here; detected contact details are still hidden when those fields are blank.'],target:d.company_code==='__new__'?'#identity-form [name=company_names]':'#identity-form [name=company_code]',action:{name:'guide-show-save',label:'Show save button'}};
  return {title:'3. Save',body:'Click Save in the form. That saves Derek and his company, then checks the sample again.',items:['Leave the separate-record checkbox unchecked for this new sample.','If a question remains, the guide will point to it.','Once the sample is clean, Next takes you to Companies.'],target:'#identity-form button[type=submit]',action:{name:'guide-show-company',label:'Review company fields'}};
}
function guideCompanyContext(){
  const p=guidePerson();
  if(!p?.company_code)return {title:'Link Derek to the company',body:'In the company detail panel, use Link an existing person.',items:['Select Derek Olsen from the dropdown.','Click Link person.','When Derek appears under People, click Next.'],target:'#company-link-person [name=person_code]'};
  if(companyPerson?.client_code===p.code)return {title:'Derek’s saved details',body:'This is the same person record you created in Review names. You can edit names and contacts here. No edits are required for this sample; click Next to review before and after.',target:'[data-action=guide-next]'};
  return {title:'Find Derek under People',body:'Derek is listed inside Bluefern Bakery, with his person code. Click his name to see the saved details, or click Next to review the transcript.',target:`[data-action=company-edit-person][data-person-code="${p.code}"]`};
}
function guideCompareContext(){
  if(identityDraft)return {title:'Save your correction',body:'Choose the correct record for this call, or hide the selected phrase in this call. Click Save, then check the updated before/after copies.',target:'#identity-form button[type=submit]'};
  if(S.tutorial.reviewed)return {title:'Review recorded',body:'Click Next to see the export and private storage locations in Settings.',target:'[data-action=guide-next]'};
  return {title:'Review before and after',body:'Read the two copies of the sample before approving it.',items:['Original (private), on the left: Derek and Bluefern remain visible here.','Clean copy, on the right: their names become codes, and contacts become placeholders. Morgan is the allowed owner name.','To fix a missed phrase, select it in the original and tag it. When both copies look right, click I checked both copies below.'],target:'#compare-original'};
}
function guideNavigate(){
  const step=S.tutorial.step;
  view=GUIDE[step].view; identityDraft=null;
  if(view==='calls'){selCall=step>=3?S.tutorial.call:null;callTab=step===3?'compare':'clean';}
  if(view==='companies')selCompany=guidePerson()?.company_code||S.companies[0]?.code||null;
  render();
  requestAnimationFrame(()=>{
    scrollGuideTarget();
  });
}
function scrollGuideTarget(){
    const target=document.querySelector('.guided-target');if(!target)return;
    const r=target.getBoundingClientRect(),panel=document.getElementById('guide-panel'),p=panel&&!panel.hidden?panel.getBoundingClientRect():null;
    const covered=p&&r.bottom>p.top&&r.top<p.bottom&&r.right>p.left&&r.left<p.right;
    if(r.top<68||r.bottom>innerHeight-16||covered)target.scrollIntoView({block:'center',behavior:'smooth'});
}
function renderGuide(){
  let tools=document.getElementById('app-tools');
  if(!tools){tools=document.createElement('div');tools.id='app-tools';tools.className='app-tools';document.body.appendChild(tools);}
  tools.innerHTML=`<button class="btn" data-action="tutorial-start" aria-label="${S.tutorial?.active?'Resume':'Start'} guided first call" title="Guided first call"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 5v16M3 3h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5v17h-5a4 4 0 0 0-4 1 4 4 0 0 0-4-1H3z"/></svg>${S.tutorial?.active?'Resume tutorial':'Guided tutorial'}</button>`;
  let panel=document.getElementById('guide-panel');
  if(!panel){panel=document.createElement('section');panel.id='guide-panel';panel.className='card guide-panel';panel.setAttribute('aria-label','Guided first call');document.body.appendChild(panel);}
  document.querySelectorAll('.guided-target').forEach(el=>el.classList.remove('guided-target'));
  panel.hidden=!S.tutorial?.active||!guideOpen;
  document.body.classList.toggle('guiding',!panel.hidden);
  if(panel.hidden){panel.innerHTML='';return;}
  const n=S.tutorial.step, step=GUIDE[n], done=step.done();
  let content=step.context?step.context():step;
  if(n===0&&done)content={title:'Sample loaded',body:'Click Next to review the names in Review names.',target:'[data-action=guide-next]'};
  if(n===5&&done)content={title:'Clean copy exported',body:'Approval saved the clean copy in the sample export folder. Click Next to open that folder.',target:'[data-action=guide-next]'};
  if(n===6&&done)content={title:'You found the exported copy',body:'The folder contains the clean sample under a neutral call ID. Click Finish tutorial to return to your own workspace.',target:'[data-action=guide-next]'};
  panel.innerHTML=`<div class="tag" aria-live="polite">Guided first call: step ${n+1} of ${GUIDE.length}</div><progress max="${GUIDE.length}" value="${n+1}" aria-label="Tutorial progress"></progress><h2>${esc(content.title)}</h2><p>${esc(content.body)}</p>
    ${content.items?`<ol class="guide-instructions">${content.items.map(item=>`<li>${esc(item)}</li>`).join('')}</ol>`:''}
    ${content.action?`<button class="btn" data-action="${content.action.name}">${esc(content.action.label)}</button>`:''}
    ${n===3&&!done&&!identityDraft?'<button class="btn" data-action="guide-reviewed">I checked both copies</button>':''}
    ${view!==step.view?'<button class="btn" data-action="guide-goto">Go to this step</button>':''}
    <div class="actions" style="margin-top:14px"><button class="btn" data-action="guide-back" ${n?'':'disabled'}>Back</button><button class="btn primary" data-action="guide-next" ${done?'':'disabled'}>${n===GUIDE.length-1?'Finish tutorial':'Next'}</button><button class="btn" data-action="guide-pause">Pause</button><button class="btn" data-action="guide-exit">Exit</button></div>`;
  if(view===step.view)document.querySelector(typeof content.target==='function'?content.target():content.target)?.classList.add('guided-target');
}
async function startGuide(){
  if(S.tutorial?.active){guideOpen=true;return guideNavigate();}
  rememberDrafts();
  const snapshot={view,selCall,callTab,selClient,selCompany,companyPerson,identityDraft,pasting,pastedText,fathomOpen,fathomCalls,fathomMore,fathomSel,fathomLabel,formDrafts:new Map(formDrafts),reviewSelections:new Map(reviewSelections)};
  const r=await api('/api/tutorial',{action:'start'});
  guideReturnUI=snapshot;formDrafts.clear();skipDraftCapture=true;
  pasting=false;pastedText='';fathomOpen=false;fathomCalls=null;fathomSel=new Set();fathomLabel='';reviewSelections.clear();selClient=selCompany=companyPerson=identityDraft=null;comparisonData=null;
  tourStep=-1;S=r.state;guideOpen=true;guideNavigate();
}
async function exitGuide(finish=false){
  const r=await api('/api/tutorial',{action:finish?'finish':'exit'});
  S=r.state;formDrafts.clear();reviewSelections.clear();skipDraftCapture=true;guideOpen=true;
  if(guideReturnUI){({view,selCall,callTab,selClient,selCompany,companyPerson,identityDraft,pasting,pastedText,fathomOpen,fathomCalls,fathomMore,fathomSel,fathomLabel}=guideReturnUI);for(const [k,v]of guideReturnUI.formDrafts)formDrafts.set(k,v);for(const [k,v]of guideReturnUI.reviewSelections)reviewSelections.set(k,v);}
  else{view='calls';selCall=null;callTab='clean';selClient=selCompany=companyPerson=identityDraft=null;pasting=false;pastedText='';fathomOpen=false;fathomCalls=null;fathomSel=new Set();fathomLabel='';}
  guideReturnUI=null;comparisonData=null;render();
}
