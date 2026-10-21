// Browser-test runtime. Prefer this repo's dev dependency; reuse local design tools when present.
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
export const PYTHON = process.env.CLEANER_PYTHON || path.join(HERE, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
let runtime;
try {
  const { chromium } = await import('playwright-core');
  const full = chromium.executablePath();
  let executable = full;
  const match = full.match(/^(.*)[\\/]chromium-(\d+)[\\/]/);
  if (match) {
    const shell = path.join(match[1], `chromium_headless_shell-${match[2]}`);
    if (fs.existsSync(shell)) for (const folder of fs.readdirSync(shell)) {
      const candidate = path.join(shell, folder, process.platform === 'win32' ? 'chrome-headless-shell.exe' : 'chrome-headless-shell');
      if (fs.existsSync(candidate)) executable = candidate;
    }
  }
  runtime = { chromium, EXE: process.env.CHROME_EXE || executable };
} catch {
  // no playwright-core here: use a browser helper named in CLEANER_BROWSER_HELPER or a local, git-ignored .browser-helper file
  const saved = path.join(HERE, '.browser-helper');
  const helper = process.env.CLEANER_BROWSER_HELPER || (fs.existsSync(saved) ? fs.readFileSync(saved, 'utf8').trim() : '');
  if (!helper) throw new Error('Browser tests need playwright-core: run npm install, then npx playwright-core install --only-shell chromium');
  runtime = await import(pathToFileURL(helper).href);
}
export const chromium = runtime.chromium;
export const EXE = runtime.EXE;
