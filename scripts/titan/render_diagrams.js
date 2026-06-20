#!/usr/bin/env node
// Render all TITAN architecture diagrams as high-res PNGs via Playwright
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const DIAGRAMS_DIR = '/home/z/my-project/scripts/titan/diagrams';
const OUTPUT_DIR = '/home/z/my-project/scripts/titan/diagrams/png';

if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const diagrams = [
  { html: 'd01_folder_structure.html',  png: 'd01_folder_structure.png',  w: 1400, h: 1800 },
  { html: 'd02_service_architecture.html', png: 'd02_service_architecture.png', w: 1500, h: 1100 },
  { html: 'd03_data_flow.html',         png: 'd03_data_flow.png',         w: 1600, h: 2200 },
  { html: 'd04_module_deps.html',       png: 'd04_module_deps.png',       w: 1600, h: 1100 },
  { html: 'd05_class_diagrams.html',    png: 'd05_class_diagrams.png',    w: 1600, h: 2400 },
  { html: 'd06_deployment.html',        png: 'd06_deployment.png',        w: 1600, h: 1200 },
  { html: 'd07_vps.html',               png: 'd07_vps.png',               w: 1600, h: 1200 },
  { html: 'd08_production.html',        png: 'd08_production.png',        w: 1600, h: 1100 },
  { html: 'd09_testing.html',           png: 'd09_testing.png',           w: 1600, h: 1100 },
  { html: 'd10_latency.html',           png: 'd10_latency.png',           w: 1600, h: 700 },
  { html: 'd11_roadmap.html',           png: 'd11_roadmap.png',           w: 1600, h: 700 },
];

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    deviceScaleFactor: 2,  // 2x for crisp print quality
  });

  for (const d of diagrams) {
    const htmlPath = path.join(DIAGRAMS_DIR, d.html);
    const pngPath = path.join(OUTPUT_DIR, d.png);
    if (!fs.existsSync(htmlPath)) {
      console.error(`Missing: ${htmlPath}`);
      continue;
    }
    const page = await context.newPage();
    await page.setViewportSize({ width: d.w, height: d.h });
    await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
    // Wait for fonts
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    await page.screenshot({
      path: pngPath,
      fullPage: false,
      clip: { x: 0, y: 0, width: d.w, height: d.h },
      omitBackground: false,
    });
    await page.close();
    console.log(`✓ ${d.png}`);
  }

  await browser.close();
  console.log('\nAll diagrams rendered.');
})();
