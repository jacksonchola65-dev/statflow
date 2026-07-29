const { chromium } = require('playwright');
const BASE_URL = 'http://localhost:5173';
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
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
    result.steps.push({ step: 'Open home page', passed: page.url().startsWith(BASE_URL) });

    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.waitForSelector('form[aria-label="Sign in form"]', { timeout: 10000 });
    result.steps.push({ step: 'Navigate to login', passed: true });

    await page.fill('#email', EMAIL);
    await page.fill('#password', PASSWORD);
    await Promise.all([
      page.waitForNavigation({ url: '**/dashboard', timeout: 15000 }),
      page.click('button[type="submit"]'),
    ]);
    result.steps.push({ step: 'Login with seeded admin', passed: page.url().includes('/dashboard') });

    // Confirm authenticated navigation visible
    result.steps.push({ step: 'Authenticated navigation visible', passed: await page.locator('text=Dashboard').count() > 0 });

    // Refresh and confirm session persists
    await page.reload({ waitUntil: 'networkidle' });
    result.steps.push({ step: 'Session remains authenticated after refresh', passed: await page.locator('text=Dashboard').count() > 0 });

    // Navigate directly to protected route
    await page.goto(`${BASE_URL}/analytics`, { waitUntil: 'networkidle' });
    const analyticsVisible = await page.locator('text=Dataset browser').count();
    result.steps.push({ step: 'Protected route /analytics accessible after login', passed: analyticsVisible > 0 });

    // Verify invalid credentials safe error
    await context.clearCookies();
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.fill('#email', 'admin@statflow.test');
    await page.fill('#password', 'WrongPassword!');
    await page.click('button[type="submit"]');
    await page.waitForSelector('text=Invalid email or password.', { timeout: 10000 });
    result.steps.push({ step: 'Invalid credentials show safe error', passed: true });

    await browser.close();
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    await browser.close();
    console.error(JSON.stringify({ error: error.message, steps: result.steps, consoleErrors: result.consoleErrors, networkErrors: result.networkErrors, requests: result.requests }, null, 2));
    process.exit(1);
  }
})();