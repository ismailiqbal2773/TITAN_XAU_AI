#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const DIR = '/home/z/my-project/scripts/ceo/diagrams';
const OUT = '/home/z/my-project/scripts/ceo/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
const diagrams = [
  { html: 'd01_architecture.html',       png: 'd01_architecture.png',       w: 1600, h: 1300 },
  { html: 'd02_rolling_windows.html',    png: 'd02_rolling_windows.png',    w: 1600, h: 1200 },
  { html: 'd03_health_scores.html',      png: 'd03_health_scores.png',      w: 1600, h: 1300 },
  { html: 'd04_detectors.html',          png: 'd04_detectors.png',          w: 1600, h: 1300 },
  { html: 'd05_decision_actions.html',   png: 'd05_decision_actions.png',   w: 1600, h: 1200 },
  { html: 'd06_uml.html',                png: 'd06_uml.png',                w: 1600, h: 1400 },
  { html: 'd07_db_schema.html',          png: 'd07_db_schema.png',          w: 1600, h: 1300 },
  { html: 'd08_tests_deployment.html',   png: 'd08_tests_deployment.png',   w: 1600, h: 1200 },
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
  await browser.close(); console.log('\nAll CEO diagrams rendered.');
})();
