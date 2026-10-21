// "Put names back": paste an agent's answer, real names appear, copy works, nothing is kept. Synthetic only.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, EXE, PYTHON } from './test_browser.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, '_restore-shots'); fs.mkdirSync(OUT, { recursive: true });
const VAULT = path.join(HERE, `ClientVault-restoreui-${process.pid}`), THEMES = path.join(VAULT, '_themes');
fs.mkdirSync(path.join(VAULT, 'private'), { recursive: true }); fs.mkdirSync(THEMES, { recursive: true });
for (const f of ['clients.csv', 'companies.csv', 'allow.txt']) fs.copyFileSync(path.join(HERE, 'test-fixtures', f), path.join(VAULT, 'private', f));
fs.writeFileSync(path.join(THEMES, 'active.json'), '{"tour_done": true}');
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], { env: { ...process.env, CLEANER_HOME: VAULT, CLEANER_THEMES: THEMES } });
const url = await new Promise(res => server.stdout.on('data', d => { const m = String(d).match(/http:\/\/127\.0\.0\.1:\d+\//); if (m) res(m[0]); }));
const browser = await chromium.launch({ executablePath: EXE });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: url.replace(/\/$/, '') });
const page = await ctx.newPage();
const errors = []; page.on('pageerror', e => errors.push(String(e)));
const ok = [];
const check = (label, cond) => { ok.push(!!cond); console.log((cond ? 'PASS  ' : 'FAIL  ') + label); };
const SECRET = 'Hi C001, thanks for the update on O001. Next step: email C001-EMAIL and ask [PERSON] about C099.';
try {
  await page.goto(url); await page.waitForSelector('main h1');
  const order = await page.$$eval('#nav button .label', b => b.map(x => x.textContent));
  check('"Put names back" sits after Review names in the sidebar', order.indexOf('Put names back') === order.indexOf('Review names') + 1);
  await page.click('[data-view=restore]');
  check('before pasting, the result area explains itself, and Copy says what to do instead of greying out',
    !(await page.isDisabled('[data-action="restore-copy"]')) && (await page.textContent('#restore-result')).includes('appears here')
    && await page.click('[data-action="restore-copy"]').then(() => page.textContent('#toast')).then(s => s.includes('Paste your agent')));
  await page.fill('#restore-in', SECRET);
  await page.waitForFunction(() => document.querySelector('#restore-out mark'));
  const out = await page.textContent('#restore-out');
  check('codes turn back into names, company and email as you type', out === 'Hi Jane, thanks for the update on Bluefern Bakery. Next step: email jane@bluefernbakery.com and ask [PERSON] about C099.');
  check('restored words are highlighted green, and ones that can\'t be restored amber',
    await page.locator('#restore-out mark.rs-restored').count() === 3 && await page.locator('#restore-out mark.rs-hidden').count() === 1 && await page.locator('#restore-out mark.rs-unknown').count() === 1);
  check('the summary says what could not be restored and why', /not saved in this app/.test(await page.textContent('#restore-summary')) && /hidden without a record/.test(await page.textContent('#restore-summary')));
  await page.click('[data-action="restore-copy"]');
  check('Copy puts the version with real names on the clipboard', (await page.evaluate(() => navigator.clipboard.readText())) === out);
  await page.click('[data-action="restore-copy-note"]');
  check('the agent instructions can be copied', (await page.evaluate(() => navigator.clipboard.readText())).includes('Keep every code exactly as written'));
  await page.screenshot({ path: path.join(OUT, 'restore.png') });
  const stored = await page.evaluate(() => JSON.stringify(Object.assign({}, localStorage)) + JSON.stringify(Object.assign({}, sessionStorage)));
  check('nothing typed here is kept in the browser', !stored.includes('C001') && !stored.includes('Jane'));
  await page.reload(); await page.waitForSelector('main h1'); await page.click('[data-view=restore]');
  check('after a reload the page is empty again', (await page.inputValue('#restore-in')) === '');
  check('no browser errors', errors.length === 0);
} finally {
  await browser.close(); server.kill();
  fs.rmSync(VAULT, { recursive: true, force: true });
}
console.log(`\n${ok.filter(Boolean).length}/${ok.length} checks passed`);
process.exit(ok.every(Boolean) ? 0 : 1);
