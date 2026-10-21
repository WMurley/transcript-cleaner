// Your team: "On my team" on a speaker's row, the Settings card, copy, paste with preview, remove. Synthetic only.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, EXE, PYTHON } from './test_browser.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, '_team-shots'); fs.mkdirSync(OUT, { recursive: true });
const VAULT = path.join(HERE, `ClientVault-teamui-${process.pid}`), THEMES = path.join(VAULT, '_themes');
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
const clean = () => page.evaluate(async () => { return (await (await fetch(`/api/call?file=team-call.txt&kind=clean`, { headers: { 'X-Token': TOKEN } })).json()).text; });
try {
  await page.goto(url); await page.waitForSelector('main h1');
  await page.evaluate(async () => { await fetch('/api/upload', { method: 'POST', headers: { 'X-Token': TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: [{ name: 'team-call.txt', text: 'Priya Shah: Morning. Omar Haddad joins later.\nOmar Haddad: Here now. Lena Berg asked about the van.\n' }] }) }); });
  await page.goto(url + '?r=1#review'); await page.waitForSelector('.rv-row');
  const row = page.locator('.rv-row').filter({ hasText: 'Priya Shah' }).first();
  check('a speaker\'s row offers "On my team" instead of "Fine to show"',
    await row.locator('[data-rv-team]').count() === 1 && await row.locator('[data-rv-quick=keep]').count() === 0);
  const lena = page.locator('.rv-row').filter({ hasText: 'Lena Berg' }).first();
  check('someone only mentioned still gets "Fine to show"', await lena.count() === 0 || await lena.locator('[data-rv-quick=keep]').count() === 1);
  await row.locator('[data-rv-team]').click();
  await page.waitForFunction(() => S.team.includes('Priya Shah'));
  check('"On my team" saves them, takes them off the list, and shows them in the clean copy',
    await page.locator('.rv-row').filter({ hasText: 'Priya Shah' }).count() === 0 && (await clean()).includes('Priya Shah: Morning'));

  await page.click('[data-view=settings]'); await page.waitForSelector('#team-card');
  check('Settings lists the team', (await page.textContent('#team-card')).includes('Priya Shah'));
  await page.screenshot({ path: path.join(OUT, 'team-card.png') });
  await page.click('[data-action=team-copy]');
  await page.waitForTimeout(300);
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  check('Copy team list puts a plain-text list on the clipboard', copied.startsWith('#') && copied.split(/\r?\n/).includes('Priya Shah'));

  await page.click('[data-action=team-open]');
  await page.fill('#team-text', 'Omar Haddad\nJane Whitfield\ntool: Gamma\n');
  await page.click('[data-action=team-preview]');
  await page.waitForSelector('.team-preview');
  const pv = await page.textContent('.team-preview');
  check('the preview says what will happen before anything is saved',
    /Omar Haddad.*Will stay visible/.test(pv) && /Jane Whitfield.*saved client/.test(pv) && /Add 2/.test(pv) && !(await page.evaluate(() => S.team.includes('Omar Haddad'))));
  await page.screenshot({ path: path.join(OUT, 'team-preview.png') });
  await page.click('[data-action=team-import]');
  await page.waitForFunction(() => S.team.includes('Omar Haddad'));
  check('importing adds the teammate and tool, and leaves the client out',
    (await clean()).includes('Omar Haddad: Here now') && !(await page.evaluate(() => S.team.includes('Jane Whitfield'))) && (await page.evaluate(() => S.tools.includes('Gamma'))));

  await page.click('[data-team-remove="Omar Haddad"]');
  await page.waitForFunction(() => !S.team.includes('Omar Haddad'));
  check('removing a teammate hides them again', !(await clean()).includes('Omar'));

  await page.fill('#team-form input[name=add]', 'Jane Whitfield'); await page.click('#team-form button[type=submit]');
  await page.waitForTimeout(400);
  check('a saved client can\'t be added by hand either', (await page.textContent('#toast')).includes('saved client') && !(await page.evaluate(() => S.team.includes('Jane Whitfield'))));
  check('no page errors', errors.length === 0);
} finally {
  await browser.close(); server.kill();
  fs.rmSync(VAULT, { recursive: true, force: true });
}
console.log(`\n${ok.filter(Boolean).length}/${ok.length} checks passed`);
process.exit(ok.every(Boolean) ? 0 : 1);
