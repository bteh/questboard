import { chromium } from 'playwright';

const out = process.env.SHOT_DIR;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });

await page.waitForSelector('.qb-demo-sheet.open', { timeout: 25000 });
await page.waitForTimeout(1600); // let it type
const kicker = await page.locator('.qb-sheet-kicker').innerText();
const text = await page.locator('.qb-sheet-text').innerText();
const sheetBox = await page.locator('.qb-demo-sheet').boundingBox();
const slotBoxes = await page.locator('.qb-land-slot').evaluateAll((els) =>
  els.map((el) => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }),
);
await page.screenshot({ path: `${out}/landing-sheet.png`, clip: { x: 0, y: 300, width: 1440, height: 650 } });
const summary = await page.evaluate(async () => {
  const r = await fetch('/api/v1/board/summary');
  const d = await r.json();
  return { status: r.status, total: d.total };
});
console.log(JSON.stringify({ kicker, text, sheetBox, slotBoxes, summary }, null, 2));
await browser.close();
