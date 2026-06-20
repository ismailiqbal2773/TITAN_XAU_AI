#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const DIR = '/home/z/my-project/scripts/weighting/diagrams';
const OUT = '/home/z/my-project/scripts/weighting/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
const diagrams = [
  { html: 'd01_architecture.html',       png: 'd01_architecture.png',       w: 1600, h: 1300 },
  { html: 'd02_metrics.html',            png: 'd02_metrics.png',            w: 1600, h: 1200 },
  { html: 'd03_algorithms.html',         png: 'd03_algorithms.png',         w: 1600, h: 1400 },
  { html: 'd04_dynamic_weights.html',    png: 'd04_dynamic_weights.png',    w: 1600, h: 1200 },
  { html: 'd05_class_design.html',       png: 'd05_class_design.png',       w: 1600, h: 1400 },
  { html: 'd06_validation.html',         png: 'd06_validation.png',         w: 1600, h: 1200 },
  { html: 'd07_benchmarks.html',         png: 'd07_benchmarks.png',         w: 1600, h: 1200 },
  { html: 'd08_deployment.html',         png: 'd08_deployment.png',         w: 1600, h: 1100 },
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
  await browser.close(); console.log('\nAll weighting diagrams rendered.');
})();
