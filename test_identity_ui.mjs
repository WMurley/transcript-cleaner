// Student workflows, synthetic calls only. No real vault or real Fathom credential.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, EXE, PYTHON } from './test_browser.mjs';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HOME = path.join(HERE, `ClientVault-identity-${process.pid}`);
const themes = path.join(HOME, '_themes');
const exports = HOME + '-exports';
fs.mkdirSync(themes, { recursive: true }); fs.mkdirSync(exports);
fs.writeFileSync(path.join(themes, 'active.json'), JSON.stringify({ tour_done: true }));
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], {
// strict mode (calls wait until every name is answered): this suite checks those workflows
  env: { ...process.env, CLEANER_HOLD_UNKNOWN: '1', CLEANER_HOME: HOME, CLEANER_THEMES: themes, FATHOM_KEY_TARGET: `TranscriptCleaner/TEST-UI-${process.pid}` }
});
let browser;
const checks = [], errors = [];
const check = (label, ok) => { checks.push(!!ok); console.log((ok ? 'PASS  ' : 'FAIL  ') + label); };
try {
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('App did not start')), 20000);
    server.stdout.on('data', d => { const m = String(d).match(/http:\/\/127\.0\.0\.1:\d+\//); if (m) { clearTimeout(timer); resolve(m[0]); } });
    server.on('exit', c => { clearTimeout(timer); reject(new Error('App exited ' + c)); });
  });
  browser = await chromium.launch({ executablePath: EXE });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(url); await page.waitForSelector('main h1');
  const token = await page.evaluate(() => TOKEN);
  const api = (route, body) => page.evaluate(async ([r,b,t]) => {
    const res = await fetch(r, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Token': t }, body: JSON.stringify(b) });
    return { status: res.status, data: await res.json() };
  }, [route, body, token]);
  await api('/api/allow', { add: 'Morgan Reyes' });
  await api('/api/output', { path: exports });
  await api('/api/upload', { files: [{ name: 'Derek-Bluefern.txt', text: 'Derek Olsen: The team at Bluefern Bakery approved it. Bluefern will send notes.\nMorgan Reyes: Sounds good, Deky. Email derek@bluefern.example or call 459-928-8815.' }] });
  await page.reload(); await page.click('[data-view=review]');
  const id = await page.evaluate(() => S.review.find(r => r.name === 'Derek Olsen').id);
  await page.click(`[data-identity="${id}"]`);
  await page.waitForSelector('#identity-form');
  check('review opens one form with company creation in place', await page.isVisible('#identity-form [name=company_names]'));
  const size = page.viewportSize(); await page.setViewportSize({ width: size.width, height: 420 });
  await page.focus('#identity-form [name=kind]:checked');
  check('only the main panel scrolls: hidden radios never stretch or scroll the window', await page.evaluate(() => document.scrollingElement.scrollHeight <= innerHeight + 1 && scrollY === 0));
  await page.setViewportSize(size);
  await page.fill('#identity-form [name=aliases]', 'Deky');
  await page.click('#identity-form .ie-more summary');
  await page.fill('#identity-form [name=emails]', 'derek@bluefern.example');
  await page.fill('#identity-form [name=phones]', '459-928-8815');
  await page.click('#identity-form button[type=submit]');
  await page.waitForFunction(() => S.clients.length === 1 && !identityDraft);
  const state = await page.evaluate(() => S);
  check('person and company are saved with a relationship', state.clients[0].company_code === state.companies[0].code);
  check('confirmed nickname and contacts are saved', state.clients[0].aliases.includes('Deky') && state.clients[0].phones === '459-928-8815');
  check('the call cleans after saving, without another trip to Settings', state.calls[0].status === 'clean' && !state.review.length);
  check('new installations wait for review before automatic export', state.review_before_export && fs.readdirSync(exports).length === 0);
  await page.click('[data-view=calls]'); await page.click('[data-call="Derek-Bluefern.txt"]');
  await page.waitForFunction(() => document.getElementById('doc')?.textContent.includes('C001'));
  check('clean preview hides name, alias, company and phone', !/Derek|Deky|Bluefern|928-8815/.test(await page.textContent('#doc')));
  await page.click('[data-action=approve-export]');
  await page.waitForFunction(() => S.calls[0].export_approved);
  check('approval delivers only a neutral filename', fs.readdirSync(exports).length === 1 && /^call-[a-f0-9]{32}\.txt$/.test(fs.readdirSync(exports)[0]));

  await page.click('[data-view=settings]');
  check('both folder paths and separate pickers are visible', (await page.textContent('main')).includes(exports) && (await page.textContent('main')).includes(HOME)
    && await page.isVisible('[data-action=output-browse]') && await page.isVisible('[data-action=vault-browse]'));
  check('both locations have Open folder actions', await page.isVisible('[data-action=output-open]') && await page.isVisible('[data-action=private-open]'));
  fs.mkdirSync(path.join(HERE, '_hardening'), { recursive: true });
  await page.screenshot({ path: path.join(HERE, '_hardening', 'settings.png'), fullPage: true });

  await page.click('[data-view=clients]'); await page.click('[data-action=new-client]');
  await page.fill('#client-form [name=full_name]', 'Nadia Okafor');
  await page.click('[data-view=companies]'); await page.click('[data-action=new-company]');
  await page.fill('#company-form [name=names]', 'Copperline Studio, Copperline');
  await page.click('#company-form button[type=submit]'); await page.waitForFunction(() => S.companies.length === 2);
  await page.click('[data-view=clients]');
  check('an unfinished client draft survives a trip to Companies', await page.inputValue('#client-form [name=full_name]') === 'Nadia Okafor');

  await page.click('[data-view=companies]'); await page.click(`[data-company="${state.companies[0].code}"]`);
  await page.fill('#company-form [name=names]', 'Bluefern Bakery, Bluefern, Bluefern team');
  await page.click('[data-action=company-add-person]');
  check('a person can be added inside the company with its link fixed', await page.inputValue('#company-person-form [name=company_code]') === state.companies[0].code);
  await page.fill('#company-person-form [name=full_name]', 'Elena Vasquez');
  await page.fill('#company-person-form [name=emails]', 'elena@bluefern.example');
  await page.click('[data-view=settings]'); await page.click('[data-view=companies]');
  check('a company person draft survives navigation', await page.inputValue('#company-person-form [name=full_name]') === 'Elena Vasquez');
  for (const width of [1440, 900, 390]) {
    await page.setViewportSize({width, height:1000});
    check(`company person form fits at ${width}px`, !(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)));
  }
  await page.setViewportSize({width:1440, height:1000});
  await page.click('#company-person-form button[type=submit]');
  await page.waitForFunction(() => S.clients.some(c => c.full_name === 'Elena Vasquez') && !companyPerson);
  check('saving a person stays on Companies and updates its people list', await page.evaluate(() => view === 'companies') && (await page.textContent('main')).includes('Elena Vasquez'));
  check('saving a person preserves unsaved company edits', await page.inputValue('#company-form [name=names]') === 'Bluefern Bakery, Bluefern, Bluefern team');
  const elena = await page.evaluate(() => S.clients.find(c => c.full_name === 'Elena Vasquez').code);
  await page.click(`[data-action=company-edit-person][data-person-code="${elena}"]`);
  await page.fill('#company-person-form [name=aliases]', 'Lena'); await page.click('#company-person-form button[type=submit]');
  await page.waitForFunction(() => !companyPerson);
  check('linked people can be edited inside their company', await page.evaluate(c => S.clients.find(p => p.code === c).aliases === 'Lena', elena));
  const unlinked = await api('/api/client', {full_name:'Rafi Haddad', emails:'rafi@example.test', notes:'Keep this note'});
  await page.reload(); await page.click('[data-view=companies]'); await page.click(`[data-company="${state.companies[0].code}"]`);
  await page.selectOption('#company-link-person [name=person_code]', unlinked.data.code); await page.click('#company-link-person button[type=submit]');
  await page.waitForFunction(c => S.clients.find(p => p.code === c)?.company_code, unlinked.data.code);
  check('linking an existing person preserves their contacts and notes', await page.evaluate(c => {const p = S.clients.find(p => p.code === c); return p.emails === 'rafi@example.test' && p.notes === 'Keep this note';}, unlinked.data.code));
  await page.click('[data-action=company-add-person]'); await page.fill('#company-person-form [name=full_name]', 'Cancelled Person'); await page.click('#company-person-form [data-action=close-company-person]');
  check('cancelling an inline person leaves the company selected and saves nothing', await page.evaluate(() => view === 'companies' && !companyPerson && !S.clients.some(p => p.full_name === 'Cancelled Person')));

  const dup = await api('/api/client', { full_name: 'Derek Olsen' });
  check('manual duplicate creation requests an explicit choice', dup.status === 409);
  const overlap = await api('/api/output', { path: path.join(HOME, 'raw') });
  check('the server rejects export into originals', overlap.status === 400);
  const invalid = await api('/api/open-folder', { kind: 'anything', path: 'C:/' });
  check('Open folder only accepts the two configured locations', invalid.status === 400);

  await api('/api/upload', { files: [{ name: 'collision.txt', text: 'Morgan Reyes: First scope approved.' }] });
  const collision = await api('/api/upload', { files: [{ name: 'collision.txt', text: 'Morgan Reyes: Second scope approved.' }] });
  check('a duplicate filename reports the newly imported call for selection', collision.data.added_files[0] === 'collision-2.txt');

  const person = await api('/api/client', { full_name: 'Deky Olsen' });
  const merged = await api('/api/merge', { keep: state.clients[0].code, remove: person.data.code });
  check('duplicate records can merge while preserving the alternate name', merged.status === 200 && merged.data.state.clients.find(c => c.code === state.clients[0].code).aliases.includes('Deky Olsen'));

  await api('/api/upload', { files: [{ name: 'new-person.txt', text: 'Priya Nair: Scope approved.' }] });
  const manual = await api('/api/client', { full_name: 'Priya Nair', company_names: 'Fernhill Studio, Fernhill' });
  check('manual creation links a company and releases affected held calls', manual.status === 200 && manual.data.state.calls.find(c => c.file === 'new-person.txt').status === 'clean'
    && manual.data.state.clients.find(c => c.full_name === 'Priya Nair').company_code);

  await api('/api/upload', { files: [{ name: 'oneoff.txt', text: 'Theo Marchetti: Scope approved.' }] });
  await page.reload(); await page.click('[data-view=review]');
  const theo = await page.evaluate(() => S.review.find(r => r.name === 'Theo Marchetti').id);
  await page.click(`[data-identity="${theo}"][data-identity-action=hide_call]`);
  await page.click('#identity-form button[type=submit]'); await page.waitForFunction(() => !identityDraft);
  await api('/api/upload', { files: [{ name: 'oneoff-next.txt', text: 'Theo Marchetti: Another scope approved.' }] });
  const next = await page.evaluate(async t => (await fetch('/api/state', { headers: { 'X-Token': t } })).json(), token);
  check('Hide in this call does not silently become a global rule', next.calls.find(c => c.file === 'oneoff-next.txt').status === 'held');
  await page.reload(); await page.click('[data-view=review]');
  const newTheo = await page.evaluate(() => S.review.find(r => r.name === 'Theo Marchetti').id);
  await page.click(`[data-identity="${newTheo}"]`);
  await page.screenshot({ path: path.join(HERE, '_hardening', 'tagging.png'), fullPage: true });
  for (const width of [1440, 900, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    check(`tagging form fits at ${width}px`, !(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)));
  }
  check('browser has no runtime errors', errors.length === 0);
  fs.writeFileSync(path.join(HERE, '_hardening', 'ui-results.json'), JSON.stringify({ checks, errors }, null, 2));
  console.log(`\n${checks.filter(Boolean).length}/${checks.length} UI checks passed`);
  if (checks.some(x => !x)) process.exitCode = 1;
} finally {
  await browser?.close(); server.kill();
}
