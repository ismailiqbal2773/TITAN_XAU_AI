#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const DIR = '/home/z/my-project/scripts/validator/diagrams';
const OUT = '/home/z/my-project/scripts/validator/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
const diagrams = [
  { html: 'd01_architecture.html',  png: 'd01_architecture.png',  w: 1600, h: 1100 },
  { html: 'd02_checklist.html',      png: 'd02_checklist.png',      w: 1400, h: 1800 },
  { html: 'd03_passfail.html',       png: 'd03_passfail.png',       w: 1600, h: 1000 },
  { html: 'd04_scoring.html',        png: 'd04_scoring.png',        w: 1600, h: 1100 },
  { html: 'd05_certification.html',  png: 'd05_certification.png',  w: 1600, h: 1000 },
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
  await browser.close(); console.log('\nAll validator diagrams rendered.');
})();
