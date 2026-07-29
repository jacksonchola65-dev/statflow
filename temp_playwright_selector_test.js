const { chromium } = require('playwright');
const BASE_URL = 'http://127.0.0.1:5173';
const EMAIL = 'admin@statflow.test';
const PASSWORD = 'ChangeMe123!';
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('#email', EMAIL);
    await page.fill('#password', PASSWORD);
    await Promise.all([
      page.waitForURL('**/dashboard', { timeout: 30000 }),
      page.click('button[type="submit"]'),
    ]);
    await page.waitForURL('**/dashboard', { timeout: 30000 });
    const dashboardCount = await page.locator('text=Dashboard').count();
    console.log('dashboardCount', dashboardCount);
    const dashboardExact = await page.locator('text="Dashboard"').count();
    console.log('dashboardExact', dashboardExact);
    await page.goto(`${BASE_URL}/analytics`, { waitUntil: 'networkidle', timeout: 30000 });
    const datasetCount = await page.locator('text=Dataset browser').count();
    console.log('datasetCount', datasetCount);
    const datasetExact = await page.locator('text="Dataset browser"').count();
    console.log('datasetExact', datasetExact);
    const analyticsReadyCount = await page.locator('text=Analytics-ready').count();
    console.log('analyticsReadyCount', analyticsReadyCount);
    const analyticsReadyExact = await page.locator('text="Analytics-ready"').count();
    console.log('analyticsReadyExact', analyticsReadyExact);
    await browser.close();
  } catch (err) {
    console.error('ERR', err);
    await browser.close();
    process.exit(1);
  }
})();
