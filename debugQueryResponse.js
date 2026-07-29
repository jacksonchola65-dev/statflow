const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("http://127.0.0.1:5173/login", { waitUntil: "networkidle" });
  await page.fill('#email', 'admin@example.com');
  await page.fill('#password', 'ChangeMe123!');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 10000 });
  await page.goto('http://127.0.0.1:5173/analytics', { waitUntil: 'networkidle' });
  await page.click('button:has-text("Analytics Test Registry")');
  await page.click('button:has-text("Query Builder")');
  await page.click('button:has-text("Reset")');
  await page.click('button:has-text("Add measure")');
  await page.locator('select[aria-label="Select aggregation"]').nth(1).selectOption('COUNT');
  const [response] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/api/v1/analytics/query') && res.request().method() === 'POST'),
    page.click('button:has-text("Run query")'),
  ]);
  const request = response.request();
  console.log('REQUEST', request.postData());
  console.log('STATUS', response.status());
  console.log('RESPONSE', await response.text());
  await browser.close();
})();
