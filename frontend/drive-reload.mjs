import { chromium } from 'playwright';

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await ctx.newPage();

const grab = async (label) => {
  await page.waitForTimeout(1800);
  const chips = await page.locator('.qb-win-chips').innerText().catch(() => '(none)');
  const posters = await page.locator('.qb-board-body .qb-poster').count();
  console.log(label, '| posters:', posters, '| chips:', chips.replace(/\n/g, ' / '));
};

await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
await grab('load 1');
const cookies1 = await ctx.cookies();
const storage1 = await page.evaluate(() => Object.keys(localStorage).map((k) => `${k}=${(localStorage.getItem(k) || '').slice(0, 60)}`));
await page.reload({ waitUntil: 'networkidle' });
await grab('load 2');
const cookies2 = await ctx.cookies();
const storage2 = await page.evaluate(() => Object.keys(localStorage).map((k) => `${k}=${(localStorage.getItem(k) || '').slice(0, 60)}`));
console.log('cookies after load1:', JSON.stringify(cookies1.map((c) => `${c.name}=${c.value.slice(0, 30)}`)));
console.log('cookies after load2:', JSON.stringify(cookies2.map((c) => `${c.name}=${c.value.slice(0, 30)}`)));
console.log('storage after load1:', JSON.stringify(storage1));
console.log('storage after load2:', JSON.stringify(storage2));

// does the real board route also blank on this state?
await page.goto('http://localhost:5173/board', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);
const head = await page.locator('body').innerText();
const liveLine = head.match(/\d+\s+live/)?.[0] ?? '(no live line found)';
console.log('board route says:', liveLine);
await browser.close();
