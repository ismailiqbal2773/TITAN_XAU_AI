#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const DIR = '/home/z/my-project/scripts/risk_engine/diagrams';
const OUT = '/home/z/my-project/scripts/risk_engine/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
const diagrams = [
  { html: 'd01_architecture.html',  png: 'd01_architecture.png',  w: 1600, h: 1100 },
  { html: 'd02_risk_modes.html',    png: 'd02_risk_modes.png',    w: 1600, h: 900 },
  { html: 'd03_formulas.html',      png: 'd03_formulas.png',      w: 1600, h: 1100 },
  { html: 'd04_shutdown.html',      png: 'd04_shutdown.png',      w: 1400, h: 1700 },
  { html: 'd05_capital.html',       png: 'd05_capital.png',       w: 1600, h: 900 },
  { html: 'd06_tests.html',         png: 'd06_tests.png',         w: 1600, h: 900 },
  { html: 'd07_controls.html',      png: 'd07_controls.png',      w: 1600, h: 800 },
];
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ deviceScaleFactor: 2 });
  for (const d of diagrams) {
    const html = path.join(DIR, d.html); const png = path.join(OUT, d.png);
    if (!fs.existsSync(html)) { console.error(`Missing: ${html}`); continue; }
    const page = await ctx.newPage();
    await page.setViewportSize({ width: d.w, height: d.h });
    await page.goto('file://' + html, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(400);
    await page.screenshot({ path: png, fullPage: false, clip: { x: 0, y: 0, width: d.w, height: d.h } });
    await page.close(); console.log(`✓ ${d.png}`);
  }
  await browser.close(); console.log('\nAll risk engine diagrams rendered.');
})();
