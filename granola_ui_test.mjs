// Click-through of Granola: connect in Settings, then "Pull from Granola" against a stand-in Granola server
// (synthetic notes only, shaped like docs.granola.ai). Proves: the key form works, listing never downloads
// transcripts, only ticked notes are fetched, they're cleaned like any call, and Fathom is untouched.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
import { chromium, EXE, PYTHON } from './test_browser.mjs';
const KEY = 'grn_uitest1234567890abc';
const now = Date.now(), iso = ms => new Date(ms).toISOString().replace(/\.\d+Z$/, 'Z');
const note = (id, title, ago) => ({ id, object: 'note', title, owner: { name: 'Morgan Reyes', email: 'morgan@example.com' },
  created_at: iso(now - ago), updated_at: iso(now - ago), deleted_at: null });
const NOTES = [note('not_aaaaaaaaaaaaa1', 'Bluefern kickoff with Jane Whitfield', 2 * 3600e3),
  note('not_bbbbbbbbbbbbb2', 'Northgate check-in', 30 * 3600e3), note('not_ccccccccccccc3', 'Old note', 20 * 86400e3)];
const line = (s, who, text, attribution = 'them') => ({ speaker: { source: attribution === 'me' ? 'microphone' : 'speaker', attribution, ...(who ? { name: who } : {}) },
  text, start_time: iso(now - 2 * 3600e3 + s * 1000), end_time: iso(now - 2 * 3600e3 + s * 1000 + 900) });
const FULL = {
  not_aaaaaaaaaaaaa1: { attendees: [{ name: 'Jane Whitfield', email: 'jane@bluefernbakery.com' }, { name: 'Rosa Delgado', email: 'rosa@tidewaterfreight.com' }],
    calendar_event: { invitees: [{ email: 'morgan@example.com' }, { email: 'rosa@tidewaterfreight.com' }] },
    transcript: [line(0, '', 'Hi Jane, how is the van schedule at Bluefern?', 'me'), line(5, 'Jane Whitfield', 'Better. Email jane@bluefernbakery.com if it slips.')] },
  not_bbbbbbbbbbbbb2: { attendees: [], calendar_event: null, transcript: [line(1, 'Priya Nair', 'Reminders are live.')] },
};
const hits = [];
const fake = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  hits.push(u.pathname + (u.searchParams.get('include') === 'transcript' ? ' +transcript' : ''));
  const send = (code, body) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
  if (req.headers.authorization !== `Bearer ${KEY}`) return send(401, { error: 'unauthorized' });
  if (u.pathname === '/v1/notes') {
    const after = u.searchParams.get('created_after'), before = u.searchParams.get('created_before');
    return send(200, { notes: NOTES.filter(n => (!after || n.created_at >= after) && (!before || n.created_at < before)), hasMore: false, cursor: null });
  }
  const m = u.pathname.match(/^\/v1\/notes\/(not_\w+)$/);
  if (m && FULL[m[1]]) return send(200, { ...NOTES.find(n => n.id === m[1]), ...FULL[m[1]] });
  send(404, { error: 'not found' });
});
await new Promise(r => fake.listen(0, '127.0.0.1', r));

const VAULT = path.join(HERE, `ClientVault-granolaui-${process.pid}`);
fs.mkdirSync(path.join(VAULT, 'private'), { recursive: true });
for (const f of ['clients.csv', 'companies.csv', 'allow.txt']) fs.copyFileSync(path.join(HERE, 'test-fixtures', f), path.join(VAULT, 'private', f));
const env = { ...process.env, CLEANER_HOME: VAULT, CLEANER_THEMES: path.join(VAULT, '_themes'), GRANOLA_PAUSE: '0',
  GRANOLA_API_BASE: `http://127.0.0.1:${fake.address().port}/v1`, GRANOLA_KEY_TARGET: 'TranscriptCleaner/Granola-UITEST',
  FATHOM_KEY_TARGET: 'TranscriptCleaner/Fathom-UITEST-unused' };
fs.mkdirSync(env.CLEANER_THEMES, { recursive: true });
fs.writeFileSync(path.join(env.CLEANER_THEMES, 'active.json'), '{"tour_done": true}');
const server = spawn(PYTHON, ['-u', path.join(HERE, 'app.py'), '--no-window'], { env });
const url = await new Promise(res => server.stdout.on('data', d => { const m = String(d).match(/http:\/\/127\.0\.0\.1:\d+\//); if (m) res(m[0]); }));
const browser = await chromium.launch({ executablePath: EXE });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = []; page.on('pageerror', e => errors.push(String(e)));
const ok = [];
const check = (label, cond) => { ok.push(!!cond); console.log((cond ? 'PASS  ' : 'FAIL  ') + label); };
try {
  await page.goto(url + '#settings'); await page.waitForSelector('#granola-form');
  check('Settings shows Granola beside Fathom, each with its own key form',
    await page.isVisible('#fathom-form') && await page.isVisible('#granola-form'));
  await page.fill('#granola-form [name=key]', 'not-a-granola-key-123');
  await page.click('#granola-form button[type=submit]');
  await page.waitForTimeout(400);
  check('a key without grn_ is refused with a plain message', await page.isVisible('#granola-form') && (await page.textContent('#toast')).includes('grn_'));
  await page.fill('#granola-form [name=key]', KEY);
  await page.click('#granola-form button[type=submit]');
  await page.waitForSelector('[data-action="fathom-open"][data-source="granola"]');
  check('connecting swaps the form for Pull from Granola and Remove key; Fathom stays unconnected',
    await page.isVisible('#fathom-form') && await page.locator('[data-action="fathom-clear"][data-source="granola"]').count() === 1);
  await page.click('[data-view=calls]');
  await page.click('#drop [data-action="fathom-open"][data-source="granola"]');
  check('the picker is titled for Granola', (await page.textContent('main h2:has-text("Pull from")')).includes('Granola'));
  await page.click('[data-fathom-range="7d"]');
  await page.waitForFunction(() => document.querySelectorAll('.fathom-row').length === 2);
  check('"Last 7 days" lists the two recent notes, not the old one', true);
  check('listing never downloaded a transcript', !hits.some(h => h.includes('transcript') || /not_/.test(h)));
  await page.click('.fathom-row:has-text("Northgate") input');  // untick it
  await page.click('[data-action="fathom-pull-selected"]');
  await page.waitForFunction(() => document.querySelectorAll('.calls .row').length === 1, null, { timeout: 120000 });
  const fetched = hits.filter(h => /not_/.test(h));
  check('only the ticked note was fetched', fetched.length === 1 && fetched[0] === '/v1/notes/not_aaaaaaaaaaaaa1 +transcript');
  const row = await page.textContent('.calls .row');
  check('the note is in the app under a neutral name', /granola-\d{4}-\d\d-\d\d-aaaaaaaaaaaaa1\.txt/.test(row) && !row.includes('Bluefern'));
  await page.waitForSelector('.suggest-card');
  const sg = await page.$$eval('.sg-row', r => r.map(x => ({ email: x.querySelector('.sg-email').textContent, name: x.querySelector('[data-sg-field=name]').value, company: x.querySelector('[data-sg-field=company]').value })));
  check('after the pull, the one unsaved invitee is suggested (not Jane, already saved, nor the note-taker)',
    sg.length === 1 && sg[0].email === 'rosa@tidewaterfreight.com' && sg[0].name === 'Rosa Delgado' && sg[0].company === 'Tidewater Freight');
  await page.click('[data-action="sg-save"]');
  await page.waitForFunction(() => S.clients.some(c => c.full_name === 'Rosa Delgado'), null, { timeout: 120000 });
  check('saving the suggestion creates the client with her company, and the card goes away',
    await page.evaluate(() => { const r = S.clients.find(c => c.full_name === 'Rosa Delgado'); return r.emails.includes('rosa@tidewaterfreight.com') && S.companies.some(c => c.code === r.company_code && /Tidewater Freight/.test(c.names)); })
    && await page.locator('.suggest-card').count() === 0);
  const tok = await page.evaluate(() => TOKEN);
  const file = await page.evaluate(() => S.calls[0].file);
  const clean = await page.evaluate(async ([t, f]) => (await (await fetch(`/api/call?file=${encodeURIComponent(f)}&kind=clean`, { headers: { 'X-Token': t } })).json()).text || '', [tok, file]);
  check('its clean copy has the client, company and email replaced', clean && !clean.includes('Jane') && !clean.includes('Bluefern') && !clean.includes('jane@'));
  await page.click('[data-action="fathom-open"][data-source="granola"]');
  await page.click('[data-fathom-range="7d"]');
  await page.waitForSelector('.fathom-row');
  check('listing again marks it "already in the app"', (await page.textContent('.fathom-row:has-text("Bluefern")')).includes('already in the app'));
  check('no browser errors', errors.length === 0);
} finally {
  await page.evaluate(async t => fetch('/api/granola', { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify({ clear: true }) }), await page.evaluate(() => TOKEN)).catch(() => {});
  await browser.close(); server.kill(); fake.close();
  fs.rmSync(VAULT, { recursive: true, force: true });
}
console.log(`\n${ok.filter(Boolean).length}/${ok.length} checks passed`);
process.exit(ok.every(Boolean) ? 0 : 1);
