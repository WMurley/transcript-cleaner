// Click-through of "Pull from Fathom" against a stand-in Fathom server (synthetic meetings only).
// Proves: listing never downloads transcripts, only ticked calls are fetched, a 195-minute call works.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
import { chromium, EXE, PYTHON } from './test_browser.mjs';
const KEY = 'ui-test-key-1234567890';
const now = Date.now(), iso = ms => new Date(ms).toISOString().replace(/\.\d+Z$/, 'Z');
const line = (i, who, text) => ({ speaker: { display_name: who }, text, timestamp: new Date(i * 6000).toISOString().slice(11, 19) });
const longTalk = Array.from({ length: 1950 }, (_, i) => line(i, i % 2 ? 'Jane Whitfield' : 'Morgan Reyes',
  i % 50 ? 'We talked through the wholesale schedule and the van routes again in some detail.' : 'Jane, email me at jane@bluefernbakery.com.'));
const MEETINGS = [
  { recording_id: 901, title: 'Alumni session (synthetic)', created_at: iso(now - 2 * 3600e3), recording_start_time: iso(now - 5.5 * 3600e3),
    recording_end_time: iso(now - 5.5 * 3600e3 + 195 * 60e3), calendar_invitees: [{ name: 'Jane Whitfield', email: 'jane@bluefernbakery.com' }] },
  { recording_id: 902, title: 'Northgate check-in', created_at: iso(now - 30 * 3600e3), recording_start_time: iso(now - 30 * 3600e3),
    recording_end_time: iso(now - 30 * 3600e3 + 25 * 60e3), calendar_invitees: [] },
  { recording_id: 903, title: 'Old call', created_at: iso(now - 20 * 86400e3), recording_start_time: iso(now - 20 * 86400e3),
    recording_end_time: iso(now - 20 * 86400e3 + 40 * 60e3), calendar_invitees: [] },
];
const TRANSCRIPTS = { 901: longTalk, 902: [line(1, 'Priya Nair', 'Reminders are live.')], 903: [line(1, 'Morgan Reyes', 'Old notes.')] };
const hits = [];
const fake = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  hits.push(u.pathname + (u.searchParams.has('include_transcript') ? ' +transcripts' : ''));
  if (req.headers['x-api-key'] !== KEY) { res.writeHead(401); return res.end(); }
  if (u.pathname === '/meetings') {
    const after = u.searchParams.get('created_after'), before = u.searchParams.get('created_before');
    const items = MEETINGS.filter(m => (!after || m.created_at >= after) && (!before || m.created_at < before));
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ items, next_cursor: null, limit: 50 }));
  }
  const m = u.pathname.match(/^\/recordings\/(\d+)\/transcript$/);
  if (m) { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ transcript: TRANSCRIPTS[m[1]] })); }
  res.writeHead(404); res.end();
});
await new Promise(r => fake.listen(0, '127.0.0.1', r));

const VAULT = path.join(HERE, `ClientVault-fathomui-${process.pid}`);
fs.mkdirSync(path.join(VAULT, 'private'), { recursive: true });
for (const f of ['clients.csv', 'companies.csv', 'allow.txt']) fs.copyFileSync(path.join(HERE, 'test-fixtures', f), path.join(VAULT, 'private', f));
const env = { ...process.env, CLEANER_HOME: VAULT, CLEANER_THEMES: path.join(VAULT, '_themes'),
  FATHOM_API_BASE: `http://127.0.0.1:${fake.address().port}`, FATHOM_KEY_TARGET: 'TranscriptCleaner/Fathom-UITEST' };
fs.mkdirSync(env.CLEANER_THEMES, { recursive: true });
fs.writeFileSync(path.join(env.CLEANER_THEMES, 'active.json'), '{"tour_done": true}');
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], { env });
const url = await new Promise(res => server.stdout.on('data', d => { const m = String(d).match(/http:\/\/127\.0\.0\.1:\d+\//); if (m) res(m[0]); }));
const browser = await chromium.launch({ executablePath: EXE });
const page = await browser.newPage();
const ok = [];
const check = (label, cond) => { ok.push(!!cond); console.log((cond ? 'PASS  ' : 'FAIL  ') + label); };
try {
  await page.goto(url); await page.waitForSelector('main h1');
  const tok = await page.evaluate(() => TOKEN);
  await page.evaluate(async ([t, k]) => fetch('/api/fathom', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify({ key: k }) }), [tok, KEY]);
  await page.reload(); await page.waitForSelector('[data-action="fathom-open"]');
  check('with a key saved, the Calls page offers "Pull from Fathom"', true);
  await page.click('[data-action="fathom-open"]');
  await page.click('[data-fathom-range="recent"]');
  await page.waitForSelector('.fathom-row');
  const rows = await page.$$eval('.fathom-row', r => r.map(x => x.textContent.replace(/\s+/g, ' ').trim()));
  check('"My most recent call" lists exactly one call: the 195-minute one', rows.length === 1 && rows[0].includes('Alumni session') && rows[0].includes('3 h 15 min'));
  check('listing calls never downloaded a transcript', !hits.some(h => h.includes('transcript')));
  await page.click('[data-fathom-range="7d"]');
  await page.waitForFunction(() => document.querySelectorAll('.fathom-row').length === 2);
  check('"Last 7 days" lists the two recent calls, not the old one', true);
  await page.click('.fathom-row:has-text("Northgate") input');  // untick it
  await page.click('[data-action="fathom-pull-selected"]');
  await page.waitForFunction(() => [...document.querySelectorAll('.calls .row')].length === 1, null, { timeout: 120000 });
  const fetched = hits.filter(h => h.startsWith('/recordings/'));
  check('only the ticked call\'s transcript was fetched', fetched.length === 1 && fetched[0] === '/recordings/901/transcript');
  const row = await page.textContent('.calls .row');
  check('the 195-minute call is in the app, cleaned, under a neutral name', /fathom-\d{4}-\d\d-\d\d-901\.txt/.test(row) && /Clean/.test(row));
  await page.click('[data-action="fathom-open"]');
  await page.click('[data-fathom-range="recent"]');
  await page.waitForSelector('.fathom-row');
  check('pulling again marks it "already in the app" and leaves it unticked',
    (await page.textContent('.fathom-row')).includes('already in the app') && await page.isDisabled('.fathom-row input'));
} finally {
  await page.evaluate(async t => fetch('/api/fathom', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify({ clear: true }) }), await page.evaluate(() => TOKEN)).catch(() => {});
  await browser.close(); server.kill(); fake.close();
}
console.log(`\n${ok.filter(Boolean).length}/${ok.length} checks passed`);
process.exit(ok.every(Boolean) ? 0 : 1);
