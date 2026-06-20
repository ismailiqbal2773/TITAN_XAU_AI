#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const DIR = '/home/z/my-project/scripts/readiness-v1.1/diagrams';
const OUT = '/home/z/my-project/scripts/readiness-v1.1/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
const diagrams = [
  { html: 'd01_scorecard.html',       png: 'd01_scorecard.png',       w: 1600, h: 1200 },
  { html: 'd02_c1_fixes.html',        png: 'd02_c1_fixes.png',        w: 1600, h: 1200 },
  { html: 'd03_c4_fixes.html',        png: 'd03_c4_fixes.png',        w: 1600, h: 1200 },
  { html: 'd04_c6_fixes.html',        png: 'd04_c6_fixes.png',        w: 1600, h: 1200 },
  { html: 'd05_c7_fixes.html',        png: 'd05_c7_fixes.png',        w: 1600, h: 1200 },
  { html: 'd06_final_verdict.html',   png: 'd06_final_verdict.png',   w: 1600, h: 1100 },
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
  await browser.close(); console.log('\nAll v1.1 diagrams rendered.');
})();
