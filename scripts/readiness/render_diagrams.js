#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const DIR = '/home/z/my-project/scripts/readiness/diagrams';
const OUT = '/home/z/my-project/scripts/readiness/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
const diagrams = [
  { html: 'd01_overview.html',                png: 'd01_overview.png',                w: 1600, h: 1200 },
  { html: 'd02_matrix.html',                  png: 'd02_matrix.png',                  w: 1600, h: 1200 },
  { html: 'd03_critical_issues.html',         png: 'd03_critical_issues.png',         w: 1600, h: 1200 },
  { html: 'd04_code_security.html',           png: 'd04_code_security.png',           w: 1600, h: 1200 },
  { html: 'd05_perf_memory_latency.html',     png: 'd05_perf_memory_latency.png',     w: 1600, h: 1200 },
  { html: 'd06_final_verdict.html',           png: 'd06_final_verdict.png',           w: 1600, h: 1100 },
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
  await browser.close(); console.log('\nAll readiness diagrams rendered.');
})();
