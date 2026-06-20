#!/usr/bin/env node
// Render Broker Compatibility Engine diagrams as high-res PNGs.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const DIAGRAMS_DIR = '/home/z/my-project/scripts/broker_engine/diagrams';
const OUTPUT_DIR = '/home/z/my-project/scripts/broker_engine/diagrams/png';

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const diagrams = [
  { html: 'd01_architecture.html',         png: 'd01_architecture.png',         w: 1600, h: 1100 },
  { html: 'd02_flowchart.html',            png: 'd02_flowchart.png',            w: 1400, h: 1700 },
  { html: 'd03_state_machines.html',       png: 'd03_state_machines.png',       w: 1600, h: 1100 },
  { html: 'd04_validation_errors.html',    png: 'd04_validation_errors.png',    w: 1600, h: 1100 },
  { html: 'd05_class_integration.html',    png: 'd05_class_integration.png',    w: 1600, h: 1100 },
  { html: 'd06_test_pyramid.html',         png: 'd06_test_pyramid.png',         w: 1600, h: 1100 },
];

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ deviceScaleFactor: 2 });
  for (const d of diagrams) {
    const htmlPath = path.join(DIAGRAMS_DIR, d.html);
    const pngPath = path.join(OUTPUT_DIR, d.png);
    if (!fs.existsSync(htmlPath)) { console.error(`Missing: ${htmlPath}`); continue; }
    const page = await context.newPage();
    await page.setViewportSize({ width: d.w, height: d.h });
    await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(400);
    await page.screenshot({ path: pngPath, fullPage: false, clip: { x: 0, y: 0, width: d.w, height: d.h } });
    await page.close();
    console.log(`✓ ${d.png}`);
  }
  await browser.close();
  console.log('\nAll broker engine diagrams rendered.');
})();
