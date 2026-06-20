#!/usr/bin/env node
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const DIR = '/home/z/my-project/scripts/titan-v2/diagrams';
const OUT = '/home/z/my-project/scripts/titan-v2/diagrams/png';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
const diagrams = [
  { html: 'd01_system_architecture.html',  png: 'd01_system_architecture.png',  w: 1600, h: 1200 },
  { html: 'd02_folder_structure.html',     png: 'd02_folder_structure.png',     w: 1600, h: 1200 },
  { html: 'd03_service_architecture.html', png: 'd03_service_architecture.png', w: 1600, h: 1200 },
  { html: 'd04_data_flow.html',            png: 'd04_data_flow.png',            w: 1600, h: 1100 },
  { html: 'd05_module_dependency.html',    png: 'd05_module_dependency.png',    w: 1600, h: 1200 },
  { html: 'd06_uml_class.html',            png: 'd06_uml_class.png',            w: 1600, h: 1200 },
  { html: 'd07_deployment_topology.html',  png: 'd07_deployment_topology.png',  w: 1600, h: 1200 },
  { html: 'd08_testing_pyramid.html',      png: 'd08_testing_pyramid.png',      w: 1600, h: 1100 },
  { html: 'd09_nfr.html',                  png: 'd09_nfr.png',                  w: 1600, h: 1100 },
  { html: 'd10_champion_challenger.html',  png: 'd10_champion_challenger.png',  w: 1600, h: 1100 },
  { html: 'd11_ai_stack.html',             png: 'd11_ai_stack.png',             w: 1600, h: 1100 },
  { html: 'd12_metrics.html',              png: 'd12_metrics.png',              w: 1600, h: 1100 },
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
  await browser.close(); console.log('\nAll 12 TITAN v2 diagrams rendered.');
})();
