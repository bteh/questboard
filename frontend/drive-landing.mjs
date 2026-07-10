import { chromium } from 'playwright';

const out = process.env.SHOT_DIR;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
const errors = [];
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(`console: ${m.text()}`);
});

await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

const posters = await page.locator('.qb-board-body .qb-poster').count();
const pins = await page.locator('.qb-board-body .qb-pin').count();
const chips = await page.locator('.qb-win-chips .qb-chip, .qb-win-chips [class*="chip" i]').allTextContents();
const chipsRaw = await page.locator('.qb-win-chips').innerText().catch(() => '(none)');
const feltBg = await page
  .locator('.qb-board-body')
  .evaluate((el) => {
    const cs = getComputedStyle(el);
    return { border: cs.borderTopWidth + ' ' + cs.borderTopColor, felt: cs.getPropertyValue('--qb-felt').trim() };
  });
const bringLines = await page.locator('.qb-board-body .qb-p-bring-body').allTextContents();
const rewards = await page.locator('.qb-board-body .qb-p-reward-value').allTextContents();
const kinds = await page.locator('.qb-board-body .qb-p-kind').allTextContents();
const stamps = await page.locator('.qb-stamp-card .qb-st').count();
const foot = await page.locator('.qb-fnote').innerText();

// let the demo loop run: ghost shows, mark stamps near the clip control
await page.waitForTimeout(3500);
const markStamped = await page.locator('.qb-demo-mark.stamped').count();
const markBox = await page.locator('.qb-demo-mark').boundingBox();
const clipBox = await page.locator('.qb-board-body .qb-poster-clip').first().boundingBox();
await page.waitForTimeout(4500);
const sheetOpen = await page.locator('.qb-demo-sheet.open').count();
const sheetText = await page.locator('.qb-sheet-text').innerText().catch(() => '');

await page.screenshot({ path: `${out}/landing-hero.png`, clip: { x: 0, y: 0, width: 1440, height: 950 } });
await page.locator('.qb-scene-stamps').scrollIntoViewIfNeeded();
await page.waitForTimeout(1400);
await page.screenshot({ path: `${out}/landing-stamps.png` });

// odometer total vs summary total
const summary = await page.evaluate(async () => {
  const r = await fetch('/api/v1/board/summary');
  return r.json();
});
await page.locator('[data-odo]').scrollIntoViewIfNeeded();
await page.waitForTimeout(2500);
const odo = await page.locator('.qb-odo-cells').first().innerText();

// mobile pass
await page.setViewportSize({ width: 390, height: 844 });
await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);
await page.screenshot({ path: `${out}/landing-mobile.png` });
const bodyOverflow = await page.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
);

console.log(
  JSON.stringify(
    {
      posters,
      pins,
      kinds,
      chips: chips.length ? chips : chipsRaw.split('\n'),
      feltBg,
      bringLines,
      rewards,
      stamps,
      foot,
      markStamped,
      markBox,
      clipBox,
      sheetOpen,
      sheetText: sheetText.slice(0, 120),
      odo: odo.replace(/\n/g, ''),
      summaryTotal: summary.total,
      mobileOverflowPx: bodyOverflow,
      errors,
    },
    null,
    2,
  ),
);
await browser.close();
