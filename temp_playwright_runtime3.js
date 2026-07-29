const { chromium } = require('playwright');
const BASE_URL = 'http://127.0.0.1:5173';
const EMAIL = 'admin@statflow.test';
const PASSWORD = 'ChangeMe123!';
(async () => {
  const result = { steps: [], consoleErrors: [], networkErrors: [], requests: [] };
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error') result.consoleErrors.push(msg.text());
  });
  page.on('requestfailed', (req) => {
    result.networkErrors.push({ url: req.url(), status: req.failure()?.errorText || 'failed' });
  });
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/v1/') || url.includes('/auth/')) {
      result.requests.push({ method: res.request().method(), url, status: res.status() });
    }
  });

  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    result.steps.push({ step: 'Open login page', passed: true });

    await page.waitForSelector('#email', { timeout: 15000 });
    await page.fill('#email', EMAIL);
    await page.fill('#password', PASSWORD);
    await Promise.all([
      page.waitForURL('**/dashboard', { timeout: 30000 }),
      page.click('button[type="submit"]'),
    ]);
    result.steps.push({ step: 'Login succeeds and redirects to dashboard', passed: page.url().includes('/dashboard') });

    const dashboardVisible = await page.locator('text=/dashboard/i').count();
    result.steps.push({ step: 'Dashboard navigation visible', passed: dashboardVisible > 0, found: dashboardVisible });

    await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
    const authPersisted = await page.locator('text=/dashboard/i').count();
    result.steps.push({ step: 'Session remains authenticated after reload', passed: authPersisted > 0, found: authPersisted });

    await page.goto(`${BASE_URL}/analytics`, { waitUntil: 'networkidle', timeout: 30000 });
    result.steps.push({ step: 'Navigate to /analytics after login', passed: page.url().includes('/analytics') });

    const datasetBrowserCount = await page.locator('text=/dataset browser/i').count();
    result.steps.push({ step: 'Analytics dataset browser visible', passed: datasetBrowserCount > 0, found: datasetBrowserCount });

    const registryButtonCount = await page.locator('button:has-text("Analytics Test Registry")').count();
    result.steps.push({ step: 'Analytics test dataset button present', passed: registryButtonCount > 0, found: registryButtonCount });

    await page.locator('button:has-text("Analytics Test Registry")').first().click();
    await page.waitForSelector('text=/analytics-ready/i', { timeout: 15000 });
    result.steps.push({ step: 'Selected dataset shows analytics-ready details', passed: true });

    await page.click('button:has-text("Query Builder")');
    await page.waitForSelector('text=/Build and run an analytics query for the selected dataset/i', { timeout: 15000 });
    result.steps.push({ step: 'Query Builder opens for selected dataset', passed: true });

    await context.clearCookies();
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('#email', EMAIL);
    await page.fill('#password', 'WrongPassword!');
    await page.click('button[type="submit"]');
    await page.waitForSelector('text=Invalid email or password.', { timeout: 15000 });
    result.steps.push({ step: 'Invalid credentials show safe error', passed: true });

    await browser.close();
    console.log(JSON.stringify(result, null, 2));
  } catch (err) {
    await browser.close();
    console.error(JSON.stringify({ error: err.message, steps: result.steps, consoleErrors: result.consoleErrors, networkErrors: result.networkErrors, requests: result.requests }, null, 2));
    process.exit(1);
  }
})();
