#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const DIR = '/home/z/my-project/scripts/mc/diagrams';
const OUT = '/home/z/my-project/scripts/mc/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
const diagrams = [
  { html: 'd01_methodology.html',    png: 'd01_methodology.png',    w: 1600, h: 1100 },
  { html: 'd02_randomization.html',  png: 'd02_randomization.png',  w: 1600, h: 1100 },
  { html: 'd03_survival_score.html', png: 'd03_survival_score.png', w: 1600, h: 1100 },
  { html: 'd04_pass_fail.html',      png: 'd04_pass_fail.png',      w: 1600, h: 1100 },
  { html: 'd05_reporting.html',      png: 'd05_reporting.png',      w: 1600, h: 1100 },
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
    await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(500);
    await page.screenshot({ path: png, fullPage: false, clip: { x: 0, y: 0, width: d.w, height: d.h } });
    await page.close(); console.log(`✓ ${d.png}`);
  }
  await browser.close(); console.log('\nAll Monte Carlo diagrams rendered.');
})();
