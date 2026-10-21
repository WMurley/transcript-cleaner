// Transcript Cleaner UI audit, in the style of the Learn design-pass tools.
// Renders every screen in both looks (Default, Function), both modes (light, dark) and four window widths,
// with synthetic data only, and flags: words broken mid-word, sideways scroll, content spilling out of its box,
// text below WCAG contrast, and console errors. Screenshots land in _audit/ for eyeballing.
// Run: node audit.mjs   (uses the Learn tools' playwright-core + isolated headless shell; nothing new installed)
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
import { chromium, EXE, PYTHON } from './test_browser.mjs';
const OUT = path.join(HERE, '_audit');
fs.mkdirSync(OUT, { recursive: true });

const VAULT = path.join(HERE, 'ClientVault-shots');           // same synthetic vault as shot.py: pass 1 only, so Review names has items
const env = { ...process.env, CLEANER_HOME: VAULT, CLEANER_THEMES: path.join(VAULT, '_themes') };
const py = PYTHON;
if (!fs.existsSync(path.join(VAULT, 'private', 'clients.csv'))) {  // build it here, so the audit never depends on another script having run
  fs.rmSync(VAULT, { recursive: true, force: true });
  fs.mkdirSync(path.join(VAULT, 'private'), { recursive: true });
  fs.mkdirSync(path.join(VAULT, '_themes'), { recursive: true });
  for (const f of ['clients.csv', 'companies.csv', 'allow.txt']) fs.copyFileSync(path.join(HERE, 'test-fixtures', f), path.join(VAULT, 'private', f));
  fs.writeFileSync(path.join(VAULT, '_themes', 'active.json'), JSON.stringify({ tour_done: true }));
  spawnSync(py, [path.join(HERE, 'clean.py'), path.join(HERE, 'test-calls')], { env, cwd: HERE });
}
// the looks under test: a dark-accent theme (Clay) and an invented pale-accent, ink-outline theme with a narrow UI font
for (const look of ['clay', 'pale-accent']) fs.copyFileSync(path.join(HERE, 'test-fixtures', `${look}-design.md`), path.join(VAULT, '_themes', `${look}.md`));
const server = spawn(py, ['-u', path.join(HERE, 'app.py'), '--no-window'], { env });
const url = await new Promise(res => server.stdout.on('data', d => { const m = String(d).match(/http:\/\/127\.0\.0\.1:\d+\//); if (m) res(m[0]); }));

const browser = await chromium.launch({ executablePath: EXE });
const ctx = await browser.newContext();
const boot = await ctx.newPage();
await boot.goto(url);
const token = await boot.evaluate(() => TOKEN);
const post = (p, body) => boot.evaluate(async ([p, body, t]) => (await fetch(p, { method: 'POST', headers: { 'X-Token': t, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).status, [p, body, token]);
await post('/api/upload', {files:[{name:'repeat-review.txt', text:'Derek Olsen: The team at Olsen Builds approved the scope.'}]});

const LOOKS = [['default', ''], ['clay', 'clay'], ['pale', 'pale-accent']];
const MODES = ['light', 'dark'];
const WIDTHS = [1920, 1440, 1100, 900, 700];
const requestedViews=process.argv.find(a=>a.startsWith('--views='))?.slice(8).split(',');
const VIEWS = ['calls', 'calls:zoom-2026-09-14-bluefern-kickoff.txt', 'calls:zoom-2026-09-14-bluefern-kickoff.txt:compare', 'review', 'review:open', 'restore', 'clients', 'clients:C001', 'companies', 'companies:O001', 'companies:O001:add-person', 'appearance', 'settings', 'tutorial', 'tutorial:preview'].filter(v=>!requestedViews||requestedViews.includes(v));

function checks() {
  const out = { hscroll: false, broken: [], spill: [], contrast: [], spacing: [] };
  const vw = window.innerWidth;
  out.hscroll = document.documentElement.scrollWidth > vw + 1 || document.querySelector('main').scrollWidth > document.querySelector('main').clientWidth + 1;
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const folder=document.querySelector('.export-destination'),drop=document.getElementById('drop');
  if(folder&&drop&&visible(folder)&&visible(drop)&&drop.getBoundingClientRect().top-folder.getBoundingClientRect().bottom<19.5)out.spacing.push('Export destination and import area need 20px separation');
  const label = el => (el.className && typeof el.className === 'string' ? el.tagName.toLowerCase() + '.' + el.className.split(' ')[0] : el.tagName.toLowerCase());
  const rgba = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lum = ([r, g, b]) => { const f = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bgOf = el => { for (let e = el; e; e = e.parentElement) { const c = rgba(getComputedStyle(e).backgroundColor); if (c && c[3] > 0.5) return c; } return [255, 255, 255, 1]; };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  for (let n; (n = walker.nextNode());) {
    const text = n.textContent; const el = n.parentElement;
    if (!text.trim() || !el || !visible(el) || el.closest('pre.doc, script, style, option, .toast, .busy')) continue;
    // 1. words split across lines (the "Whi / tfiel / d" bug). Filenames may break at hyphens, so skip those.
    if (!el.closest('.calls .name, .panel h2, .mini-list, .rcard .tag, .q-where, .gc-file, .path')) {
      const re = /[^\s-]{2,}/g; let m;  // hyphens are fair places to wrap
      while ((m = re.exec(text))) {
        const r = document.createRange(); r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
        const lines = new Set([...r.getClientRects()].filter(x => x.width > 0).map(x => Math.round(x.top)));
        if (lines.size > 1) { out.broken.push(`${label(el)}: "${m[0]}"`); break; }
      }
    }
    // 2. contrast
    if (!seen.has(el)) {
      seen.add(el);
      const s = getComputedStyle(el); const fg = rgba(s.color); const bg = bgOf(el);
      if (fg && fg[3] > 0.5 && !el.closest('[disabled], .btn:disabled')) {
        const L1 = lum(fg), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
        const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight) >= 600;
        const need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
        if (ratio < need) out.contrast.push(`${label(el)} "${text.trim().slice(0, 24)}" ${ratio.toFixed(2)} (needs ${need})`);
      }
    }
  }
  // 3. boxes whose content spills past their right edge, or that run off the window
  for (const el of document.querySelectorAll('main *, aside *, #app-tools *, #guide-panel *')) {
    if (!visible(el) || el.closest('pre.doc, .sr-only')) continue;  // screen-reader-only text is meant to be clipped
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    if (r.right > vw + 1) out.spill.push(`${label(el)} runs off the window by ${Math.round(r.right - vw)}px`);
    else if (el.scrollWidth > el.clientWidth + 2 && !['auto', 'scroll'].includes(s.overflowX) && el.children.length === 0 && el.clientWidth > 0)
      out.spill.push(`${label(el)} text wider than its box`);
  }
  out.broken = [...new Set(out.broken)]; out.spill = [...new Set(out.spill)].slice(0, 8); out.contrast = [...new Set(out.contrast)].slice(0, 8);
  return out;
}

const report = [];
let problems = 0, loads = 0;
for (const [look, themeId] of LOOKS) {
  await post('/api/theme', { use: themeId });
  for (const mode of MODES) {
    await post('/api/mode', { mode });
    for (const width of WIDTHS) {
      const page = await ctx.newPage();
      await page.setViewportSize({ width, height: 900 });
      const errors = [];
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      page.on('pageerror', e => errors.push(String(e)));
      for (const view of VIEWS) {
        const isTutorial=view.startsWith('tutorial');
        await page.goto(`${url}?n=${++loads}#${isTutorial?'calls':view}`);  // one fresh load per screen (the query string forces it)
        await page.waitForSelector('main h1');
        if(isTutorial)await page.click('#app-tools [data-action=tutorial-start]');
        if(view==='tutorial:preview')await page.click('#sample-preview summary');
        if (view.endsWith(':add-person')) await page.click('[data-action=company-add-person]');
        if (view.endsWith(':compare')) {
          await page.click('[data-tab=compare]'); await page.waitForSelector('#compare-original .compare-change');
        }
        if (view === 'review:open') { await page.locator('[data-rv-open]').first().click(); await page.waitForTimeout(300); }  // a row opened to show where the name was said
        await page.waitForTimeout(view.startsWith('calls:') ? 600 : 150);
        const r = await page.evaluate(checks);
        const name = `${look}-${mode}-${width}-${view.replace(/[:.]/g, '_')}`;
        await page.screenshot({ path: path.join(OUT, name + '.png') });
        const issues = (r.hscroll ? 1 : 0) + r.broken.length + r.spill.length + r.contrast.length + r.spacing.length + errors.length;
        problems += issues;
        report.push({ look, mode, width, view, ...r, errors: [...errors] });
        if (issues) console.log(`FLAG ${name}\n` + [r.hscroll && '  sideways scroll', ...r.broken.map(x => '  broken word ' + x),
          ...r.spill.map(x => '  spill ' + x), ...r.contrast.map(x => '  contrast ' + x), ...r.spacing.map(x=>'  spacing '+x), ...errors.map(x => '  console ' + x)].filter(Boolean).join('\n'));
        errors.length = 0;
        if(isTutorial)await post('/api/tutorial',{action:'exit'});
      }
      await page.close();
    }
  }
}
await post('/api/theme', { use: '' });
await post('/api/mode', { mode: 'auto' });
fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 1));
console.log(`\n${report.length} screens checked, ${problems} issue(s). Screenshots: ${OUT}`);
await browser.close();
server.kill();
process.exit(problems ? 1 : 0);
