// Click-through test of "Paste a transcript" and the light/dark switch, synthetic data only.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
import { chromium, EXE, PYTHON } from './test_browser.mjs';
const VAULT = path.join(HERE, `ClientVault-paste-${process.pid}`);
fs.mkdirSync(path.join(VAULT, 'private'), { recursive: true });
for (const f of ['clients.csv', 'companies.csv', 'allow.txt']) fs.copyFileSync(path.join(HERE, 'test-fixtures', f), path.join(VAULT, 'private', f));
const env = { ...process.env, CLEANER_HOME: VAULT, CLEANER_THEMES: path.join(VAULT, '_themes') };
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], { env });
const url = await new Promise(res => server.stdout.on('data', d => { const m = String(d).match(/http:\/\/127\.0\.0\.1:\d+\//); if (m) res(m[0]); }));
const browser = await chromium.launch({ executablePath: EXE });
const bctx = await browser.newContext();
await bctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: url.replace(/\/$/, '') });
const page = await bctx.newPage();
const ok = [];
const check = (label, cond) => { ok.push(cond); console.log((cond ? 'PASS  ' : 'FAIL  ') + label); };
try {
  await page.goto(url);
  await page.waitForSelector('main h1');
  // first run: the tour opens by itself, Skip closes it, and it stays closed
  check('first open of an empty app shows the tour', await page.isVisible('.tour'));
  await page.click('[data-action="tour-skip"]');
  await page.reload(); await page.waitForSelector('main h1');
  check('after Skip, the tour does not come back on reopen', !(await page.isVisible('.tour')));
  // practice mode: sample calls, a banner, and back out again
  await page.click('[data-action="practice-on"]');
  await page.waitForSelector('.practice-bar');
  check('practice mode loads the five sample calls behind a clear banner', (await page.$$('.calls .row')).length === 5);
  await page.click('.practice-bar [data-action="practice-off"]');
  await page.waitForFunction(() => !document.querySelector('.practice-bar'));
  check('leaving practice mode returns to your own (empty) calls', (await page.$$('.calls .row')).length === 0);
  await page.click('[data-action="paste-open"]');
  await page.fill('#paste-text', '[00:00:03] Morgan Reyes: Hi Jane, thanks for joining.\n[00:00:06] Jane Whitfield: Of course. Email me at jane@bluefernbakery.com.');
  await page.click('#paste-form button[type="submit"]');
  await page.waitForSelector('.row.sel', { timeout: 30000 });
  const row = await page.textContent('.row.sel');
  check('pasted text becomes a call named pasted-<date>.txt, cleaned', /pasted-\d{4}-\d\d-\d\d-\d{4}\.txt/.test(row) && /Clean/.test(row));
  await page.waitForFunction(() => document.getElementById('doc')?.textContent.includes('C001'));
  const doc = await page.textContent('#doc');
  check('clean copy shows C001 and C001-EMAIL, no name or address', doc.includes('C001-EMAIL') && !doc.includes('Jane') && !doc.includes('@'));
  check("the call says what was removed", /Removed from this call:.*name.*email/.test(await page.textContent('.note.removed')));
  await page.click('[data-action="copy-clean"]');
  await page.waitForTimeout(300);
  const clip = await page.evaluate(() => navigator.clipboard.readText());
  check('Copy clean puts the clean transcript on the clipboard', clip.includes('C001-EMAIL') && !clip.includes('Jane'));
  // output folder: set by path (Browse... opens the computer's own picker, which a hidden browser can't click)
  await page.evaluate(async ([t, file]) => fetch('/api/approve-export', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' },
    body: JSON.stringify({ file }) }), [await page.evaluate(() => TOKEN), await page.evaluate(() => S.calls[0].file)]);
  const outDir = path.join(VAULT, '..', `_paste-library-${process.pid}`); fs.mkdirSync(outDir, { recursive: true });
  const set = await page.evaluate(async ([t, d]) => (await fetch('/api/output', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: d, send_all: true }) })).json(), [await page.evaluate(() => TOKEN), outDir]);
  check('the clean-calls folder receives the clean copy only', set.state.output_ok && fs.readdirSync(outDir).length === 1
    && !fs.readFileSync(path.join(outDir, fs.readdirSync(outDir)[0]), 'utf8').includes('Jane'));
  await page.click('[data-mode-set="dark"]');
  const bgDark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.click('[data-mode-set="light"]');
  const bgLight = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check('light/dark switch changes the page immediately', bgDark !== bgLight);
  await page.reload();
  await page.waitForSelector('main h1');
  check('the chosen mode is remembered after reopening', await page.evaluate(() => document.documentElement.dataset.mode) === 'light');

  // name and logo, through the real screen
  const zlib = await import('node:zlib');
  const crc = b => { let c, t = []; for (let n = 0; n < 256; n++) { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
    let x = 0xffffffff; for (const v of b) x = t[(x ^ v) & 0xff] ^ (x >>> 8); return (x ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type), data]);
    const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const W = 600, H = 400, raw = Buffer.alloc((W * 4 + 1) * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) raw.set([200, 90, 50, 255], y * (W * 4 + 1) + 1 + x * 4);
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4); ihdr.set([8, 6, 0, 0, 0], 8);
  const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
  const logoFile = path.join(VAULT, 'my-logo.png'); fs.writeFileSync(logoFile, png);
  await page.goto(url + '#appearance'); await page.reload(); await page.waitForSelector('#brand-form');
  await page.fill('#brand-form [name=name]', 'Client Calls Desk');
  await page.setInputFiles('#logo-picker', logoFile);
  await page.waitForSelector('#brand-form img');
  check('a big, non-square picture is previewed as the new logo', true);
  await page.click('#brand-form button[type=submit]');
  await page.waitForFunction(() => document.title === 'Client Calls Desk');
  check('saving renames the app (window title and sidebar)', (await page.textContent('#brand')).includes('Client Calls Desk'));
  const logo = await page.evaluate(async () => { const r = await fetch('/logo.png'); const b = new Uint8Array(await r.arrayBuffer());
    const dv = new DataView(b.buffer); return [r.status, dv.getUint32(16), dv.getUint32(20)]; });
  check('the stored logo was squared and shrunk to 256 x 256', logo[0] === 200 && logo[1] === 256 && logo[2] === 256);
  const ico = await page.evaluate(async () => { const b = new Uint8Array(await (await fetch('/favicon.ico')).arrayBuffer()); return [b[2], b[4], b[22], b[23]]; });
  check('the window icon (and desktop shortcut icon) now uses the logo', ico[0] === 1 && ico[1] === 1 && ico[2] === 0x89 && ico[3] === 0x50);
  const bad = await page.evaluate(async t => (await fetch('/api/brand', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' },
    body: JSON.stringify({ logo: btoa('not an image') }) })).status, await page.evaluate(() => TOKEN));
  check('something that is not an image is refused', bad === 400);
  await page.click('[data-action="reset-logo"]');
  await page.waitForFunction(() => !document.querySelector('#brand img'));
  check('"Use the original icon" brings the shield back', true);

  // what to hide: switch company names off (confirm the warning), the clean copy keeps them
  page.on('dialog', d => d.accept());
  await page.goto(url + '#settings'); await page.reload(); await page.waitForSelector('[data-hide="companies"]');
  await page.click('label.switch:has([data-hide="companies"])');
  await page.waitForFunction(() => document.querySelector('[data-hide="companies"]') && !document.querySelector('[data-hide="companies"]').checked);
  const hideState = await page.evaluate(async t => (await (await fetch('/api/state', { headers: { 'X-Token': t } })).json()).hide, await page.evaluate(() => TOKEN));
  check('switching company names off is saved (after the warning)', hideState.companies === false && hideState.people === true);
  await page.click('label.switch:has([data-hide="companies"])');
  await page.waitForFunction(() => document.querySelector('[data-hide="companies"]')?.checked);
  check('and switching it back on works', true);
  // the default icon follows the look's accent colour
  const tok = await page.evaluate(() => TOKEN);
  const md = fs.readFileSync(path.join(HERE, 'test-fixtures', 'clay-design.md'), 'utf8');
  await page.evaluate(async ([t, md]) => fetch('/api/theme', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify({ text: md }) }), [tok, md]);
  const px = await page.evaluate(async () => { const b = new Uint8Array(await (await fetch('/favicon.ico?x=' + Date.now())).arrayBuffer());
    const off = 22 + 40; for (let i = off; i < b.length - 4; i += 4) if (b[i + 3] === 255 && !(b[i] === 255 && b[i + 1] === 255 && b[i + 2] === 255)) return [b[i + 2], b[i + 1], b[i]]; return null; });
  check('with the Clay look, the window icon turns terracotta too', px && px[0] > 150 && px[2] < 90);
  await page.evaluate(async t => fetch('/api/theme', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify({ use: '' }) }), tok);
  // move the private files to another folder (Browse... opens the computer's picker; here by path)
  const os = await import('node:os');
  const dest = fs.mkdtempSync(path.join(os.tmpdir(), 'tc-vault-'));
  const mv = await page.evaluate(async ([t, d]) => { const r = await fetch('/api/vault', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify({ path: d }) }); return [r.status, await r.json()]; }, [tok, dest]);
  check('moving the private files: the app now lives in the new folder, calls intact',
    mv[0] === 200 && mv[1].state.home.startsWith(dest) && mv[1].state.calls.length >= 1 && fs.existsSync(path.join(dest, 'TranscriptCleaner-Vault', 'private', 'vault.db')));
} finally {
  await browser.close();
  server.kill();
}
console.log(`\n${ok.filter(Boolean).length}/${ok.length} checks passed`);
process.exit(ok.every(Boolean) ? 0 : 1);
