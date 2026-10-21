// Click-through of deleting a call from its row (two-step) and from the preview, synthetic calls only.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
import { chromium, EXE, PYTHON } from './test_browser.mjs';
const VAULT = path.join(HERE, `ClientVault-delete-${process.pid}`);
fs.mkdirSync(path.join(VAULT, 'private'), { recursive: true });
for (const f of ['clients.csv', 'companies.csv', 'allow.txt']) fs.copyFileSync(path.join(HERE, 'test-fixtures', f), path.join(VAULT, 'private', f));
const env = { ...process.env, CLEANER_HOME: VAULT, CLEANER_THEMES: path.join(VAULT, '_themes') };
fs.mkdirSync(env.CLEANER_THEMES, { recursive: true }); fs.writeFileSync(path.join(env.CLEANER_THEMES, 'active.json'), '{"tour_done": true}');
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], { env });
const url = await new Promise(res => server.stdout.on('data', d => { const m = String(d).match(/http:\/\/127\.0\.0\.1:\d+\//); if (m) res(m[0]); }));
const browser = await chromium.launch({ executablePath: EXE });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('dialog', d => d.accept());
const ok = []; const check = (l, c) => { ok.push(!!c); console.log((c ? 'PASS  ' : 'FAIL  ') + l); };
try {
  await page.goto(url); await page.waitForSelector('main h1');
  const tok = await page.evaluate(() => TOKEN);
  const files = fs.readdirSync(path.join(HERE, 'test-calls')).map(n => ({ name: n, text: fs.readFileSync(path.join(HERE, 'test-calls', n), 'utf8') }));
  await page.evaluate(async ([t, f]) => fetch('/api/upload', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify({ files: f }) }), [tok, files]);
  await page.reload(); await page.waitForSelector('.calls .row');
  const before = (await page.$$('.calls .row')).length;
  // rename a call to something with a client's name in it: the clean copy's file name still hides it
  await page.click('[data-rename="fathom-2026-09-18-northgate-checkin.txt"]');
  await page.fill('.rename-form input', 'Priya Nair reminders call.txt');
  await page.click('.rename-form button[type=submit]');
  await page.waitForSelector('.calls .row:has-text("Priya Nair reminders call.txt")');
  const cleanNames = fs.readdirSync(path.join(VAULT, 'clean'));
  const renamed = await page.evaluate(() => S.calls.find(c => c.file === 'Priya Nair reminders call.txt'));
  check('renaming a call preserves its neutral export name and hides the client',
    /^call-[a-f0-9]{32}\.txt$/.test(renamed.clean_name) && cleanNames.includes(renamed.clean_name) && !cleanNames.some(n => /northgate|priya/i.test(n)));
  const target = 'zoom-2026-09-14-bluefern-kickoff.txt';
  await page.click(`[data-row-delete="${target}"]`);
  check('first click on the trash can asks "Delete?" instead of deleting', await page.isVisible(`[data-row-delete="${target}"][data-confirm]`) && (await page.$$('.calls .row')).length === before);
  await page.click('main h1');
  check('clicking anywhere else cancels it', !(await page.isVisible(`[data-row-delete="${target}"][data-confirm]`)));
  await page.click(`[data-row-delete="${target}"]`); await page.click(`[data-row-delete="${target}"][data-confirm]`);
  await page.waitForFunction(n => (document.querySelectorAll('.calls .row').length === n - 1), before);
  const left = fs.readdirSync(path.join(VAULT, 'raw')).concat(fs.readdirSync(path.join(VAULT, 'clean')));
  check('second click deletes it: gone from the list and from the vault folders', !left.some(n => n.includes('bluefern')));
  await page.click('.calls .row'); await page.waitForSelector('[data-action="delete-call"]');
  await page.click('[data-action="delete-call"]');
  await page.waitForFunction(n => (document.querySelectorAll('.calls .row').length === n - 2), before);
  check('"Delete call" in the preview works too (after its confirm)', true);
} finally { await browser.close(); server.kill(); }
console.log(`\n${ok.filter(Boolean).length}/${ok.length} checks passed`);
process.exit(ok.every(Boolean) ? 0 : 1);
