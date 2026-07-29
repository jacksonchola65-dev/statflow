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
    const dashboardText = await page.evaluate(() => document.body.innerText);
    console.log('DASHBOARD_BODY_SNIPPET', dashboardText.slice(0, 1200));
    console.log('DASHBOARD_INCLUDES_DASHBOARD', dashboardText.includes('Dashboard'));
    await page.goto(`${BASE_URL}/analytics`, { waitUntil: 'networkidle', timeout: 30000 });
    const analyticsText = await page.evaluate(() => document.body.innerText);
    console.log('ANALYTICS_BODY_SNIPPET', analyticsText.slice(0, 1200));
    console.log('ANALYTICS_INCLUDES_DATASET_BROWSER', analyticsText.includes('Dataset browser'));
    console.log('ANALYTICS_INCLUDES_ANALYTICS_READY', analyticsText.includes('Analytics-ready'));
    const datasetButtonCount = await page.locator('button:has-text("Analytics Test Registry")').count();
    console.log('BUTTON_COUNT', datasetButtonCount);
    await browser.close();
  } catch (err) {
    console.error('ERR', err.message);
    await browser.close();
    process.exit(1);
  }
})();
