const { chromium } = require('playwright');
const path = require('path');
const BASE = 'http://127.0.0.1:5173';
const EMAIL = 'admin@statflow.test';
const PASSWORD = 'ChangeMe123!';
const CSV = path.resolve(__dirname, 'temp_valid_import.csv');

async function doPage(name, page) {
  console.log(`=== ${name} start ===`);
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL('**/dashboard', { timeout: 20000 });
  console.log(`${name} dashboard url`, page.url());
  await page.goto(`${BASE}/import`, { waitUntil: 'networkidle' });
  console.log(`${name} import url`, page.url());
  const count = await page.locator('input[type=file]').count();
  console.log(`${name} input count`, count);
  if (count > 0) {
    const outer = await page.locator('input[type=file]').first().evaluate(el => el.outerHTML);
    console.log(`${name} outer`, outer);
    await page.locator('input[type=file]').first().setInputFiles(CSV);
    console.log(`${name} attached file ok`);
  }
}

(async () => {
  const browser = await chromium.launch();
  const page1 = await browser.newPage();
  await doPage('page1', page1);
  const page2 = await browser.newPage();
  await doPage('page2', page2);
  await browser.close();
})();