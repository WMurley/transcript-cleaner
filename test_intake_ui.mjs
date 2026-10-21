// "Add many at once" on Clients: paste a list, preview, save, and the calls waiting on those people clean themselves.
// Synthetic calls and clients only.
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, EXE, PYTHON } from './test_browser.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VAULT = path.join(HERE, `ClientVault-intakeui-${process.pid}`), THEMES = path.join(VAULT, '_themes');
fs.mkdirSync(path.join(VAULT, 'private'), { recursive: true }); fs.mkdirSync(THEMES, { recursive: true });
for (const f of ['clients.csv', 'companies.csv', 'allow.txt']) fs.copyFileSync(path.join(HERE, 'test-fixtures', f), path.join(VAULT, 'private', f));
fs.writeFileSync(path.join(THEMES, 'active.json'), '{"tour_done": true}');
const env = { ...process.env, CLEANER_HOME: VAULT, CLEANER_THEMES: THEMES };
spawnSync(PYTHON, [path.join(HERE, 'clean.py'), path.join(HERE, 'test-calls')], { env, cwd: HERE });
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], { env });
const url = await new Promise(res => server.stdout.on('data', d => { const m = String(d).match(/http:\/\/127\.0\.0\.1:\d+\//); if (m) res(m[0]); }));
const browser = await chromium.launch({ executablePath: EXE });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = []; page.on('pageerror', e => errors.push(String(e)));
const ok = [];
const check = (label, cond) => { ok.push(!!cond); console.log((cond ? 'PASS  ' : 'FAIL  ') + label); };
try {
  await page.goto(url + '#clients'); await page.waitForSelector('main h1');
  const derekWaiting = await page.evaluate(() => S.review.some(r => r.name === 'Derek Olsen'));
  check('Derek Olsen is waiting in Needs you before the import', derekWaiting);
  await page.click('[data-action="bulk-open"]');
  await page.fill('#bulk-text', 'Name\tCompany\tEmail\nDerek Olsen\tOlsen Builds\tderek@olsenbuilds.com\nJane Whitfield\tBluefern Bakery\tjane@bluefernbakery.com\n\tNo Name Inc\t\n');
  await page.click('[data-action="bulk-preview"]');
  await page.waitForSelector('.bulk-row:not(.bulk-head)');
  const rows = await page.$$eval('.bulk-row:not(.bulk-head)', r => r.map(x => x.textContent.replace(/\s+/g, ' ').trim()));
  check('preview shows each person with what will happen', rows.length === 3 && /Derek Olsen.*New/.test(rows[0]) && /Jane Whitfield.*Already saved/.test(rows[1]) && /Needs a name/.test(rows[2]));
  check('only new people are ticked, and saved or nameless rows can\'t be', await page.isChecked('[data-bulk-pick="0"]') && await page.isDisabled('[data-bulk-pick="1"]') && await page.isDisabled('[data-bulk-pick="2"]'));
  check('the save button counts the ticked people', (await page.textContent('[data-action="bulk-save"]')).includes('one client'));
  await page.click('[data-action="bulk-save"]');
  await page.waitForFunction(() => S.clients.some(c => c.full_name === 'Derek Olsen'), null, { timeout: 120000 });
  const st = await page.evaluate(() => ({ derek: S.clients.find(c => c.full_name === 'Derek Olsen'), cos: S.companies.map(c => c.names), waiting: S.review.filter(r => /Olsen/.test(r.name)).length }));
  check('Derek is saved with his email, linked to a new Olsen Builds company', st.derek.emails.includes('derek@olsenbuilds.com') && st.cos.some(n => /Olsen Builds/.test(n)) && st.derek.company_code);
  check('his questions in Needs you were answered by the import (calls checked again)', st.waiting === 0);
  check('the panel closes after saving', await page.locator('.bulk-panel').count() === 0);
  check('no browser errors', errors.length === 0);
} finally {
  await browser.close(); server.kill();
  fs.rmSync(VAULT, { recursive: true, force: true });
}
console.log(`\n${ok.filter(Boolean).length}/${ok.length} checks passed`);
process.exit(ok.every(Boolean) ? 0 : 1);
