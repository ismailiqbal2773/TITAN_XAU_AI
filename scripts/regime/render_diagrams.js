#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const DIR = '/home/z/my-project/scripts/regime/diagrams';
const OUT = '/home/z/my-project/scripts/regime/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

const diagrams = [
  { html: 'd01_architecture.html',       png: 'd01_architecture.png',       w: 1600, h: 1100 },
  { html: 'd02_features.html',           png: 'd02_features.png',           w: 1600, h: 1100 },
  { html: 'd03_model_design.html',       png: 'd03_model_design.png',       w: 1600, h: 1100 },
  { html: 'd04_scoring.html',            png: 'd04_scoring.png',            w: 1600, h: 900 },
  { html: 'd05_validation.html',         png: 'd05_validation.png',         w: 1600, h: 1100 },
  { html: 'd06_false_positives.html',    png: 'd06_false_positives.png',    w: 1600, h: 1100 },
  { html: 'd07_backtest.html',           png: 'd07_backtest.png',           w: 1600, h: 1100 },
  { html: 'd08_transition_map.html',     png: 'd08_transition_map.png',     w: 1600, h: 800 },
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
  console.log('\nAll regime detection diagrams rendered.');
})();
