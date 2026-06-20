#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const DIR = '/home/z/my-project/scripts/exec_engine/diagrams';
const OUT = '/home/z/my-project/scripts/exec_engine/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

const diagrams = [
  { html: 'd01_architecture.html',      png: 'd01_architecture.png',      w: 1600, h: 1100 },
  { html: 'd02_execution_flow.html',    png: 'd02_execution_flow.png',    w: 1400, h: 1900 },
  { html: 'd03_lifecycle.html',         png: 'd03_lifecycle.png',         w: 1600, h: 1100 },
  { html: 'd04_slippage_eqs.html',      png: 'd04_slippage_eqs.png',      w: 1600, h: 1100 },
  { html: 'd05_error_recovery.html',    png: 'd05_error_recovery.png',    w: 1600, h: 1100 },
  { html: 'd06_performance.html',       png: 'd06_performance.png',       w: 1600, h: 700 },
  { html: 'd07_tests.html',             png: 'd07_tests.png',             w: 1600, h: 1000 },
];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ deviceScaleFactor: 2 });
  for (const d of diagrams) {
    const html = path.join(DIR, d.html);
    const png = path.join(OUT, d.png);
    if (!fs.existsSync(html)) { console.error(`Missing: ${html}`); continue; }
    const page = await ctx.newPage();
    await page.setViewportSize({ width: d.w, height: d.h });
    await page.goto('file://' + html, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(400);
    await page.screenshot({ path: png, fullPage: false, clip: { x: 0, y: 0, width: d.w, height: d.h } });
    await page.close();
    console.log(`✓ ${d.png}`);
  }
  await browser.close();
  console.log('\nAll exec engine diagrams rendered.');
})();
