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
    await page.waitForSelector('form[aria-label="Sign in form"]', { timeout: 10000 });
    result.steps.push({ step: 'Open login page', passed: true });

    await page.fill('#email', EMAIL);
    await page.fill('#password', PASSWORD);
    await Promise.all([
      page.waitForURL('**/dashboard', { timeout: 30000 }),
      page.click('button[type="submit"]'),
    ]);
    result.steps.push({ step: 'Login with seeded admin', passed: page.url().includes('/dashboard') });

    await page.waitForSelector('text=Dashboard', { timeout: 10000 });
    result.steps.push({ step: 'Authenticated navigation visible', passed: await page.locator('text=Dashboard').count() > 0 });

    await page.goto(`${BASE_URL}/analytics`, { waitUntil: 'networkidle', timeout: 30000 });
    result.steps.push({ step: 'Navigate to /analytics', passed: page.url().includes('/analytics') });
    result.steps.push({
      step: 'Analytics dataset browser visible',
      passed: await page.locator('text=Dataset browser').count() > 0,
    });

    await page.locator('button:has-text("Analytics Test Registry")').first().click();
    await page.waitForSelector('text=Analytics-ready', { timeout: 10000 });
    result.steps.push({ step: 'Select analytics dataset', passed: true });

    await page.click('button:has-text("Query Builder")');
    await page.waitForSelector('text=Build and run an analytics query for the selected dataset', { timeout: 10000 });
    result.steps.push({ step: 'Query Builder opens', passed: true });

    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('#email', EMAIL);
    await page.fill('#password', 'WrongPassword!');
    await page.click('button[type="submit"]');
    await page.waitForSelector('text=Invalid email or password.', { timeout: 10000 });
    result.steps.push({ step: 'Invalid credentials safe error shown', passed: true });

    await browser.close();
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    await browser.close();
    console.error(JSON.stringify({ error: error.message, steps: result.steps, consoleErrors: result.consoleErrors, networkErrors: result.networkErrors, requests: result.requests }, null, 2));
    process.exit(1);
  }
})();
