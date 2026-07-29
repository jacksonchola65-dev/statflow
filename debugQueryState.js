const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:5173/login', { waitUntil: 'networkidle' });
  await page.fill('#email','admin@example.com');
  await page.fill('#password','ChangeMe123!');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 10000 });
  await page.goto('http://127.0.0.1:5173/analytics', { waitUntil: 'networkidle' });
  await page.locator('button:has-text("Analytics Test Registry")').click();
  await page.click('button:has-text("Query Builder")');
  await page.click('button:has-text("Reset")');
  await page.click('button:has-text("Add measure")');
  const countSel = await page.locator('select[aria-label="Select measure"]').count();
  console.log('measure selects', countSel);
  for (let i = 0; i < countSel; i++) {
    const select = page.locator('select[aria-label="Select measure"]').nth(i);
    const value = await select.inputValue();
    const options = await select.locator('option').allTextContents();
    console.log('measure row', i, value, options);
  }
  const countAgg = await page.locator('select[aria-label="Select aggregation"]').count();
  console.log('agg selects', countAgg);
  for (let i = 0; i < countAgg; i++) {
    const select = page.locator('select[aria-label="Select aggregation"]').nth(i);
    const value = await select.inputValue();
    const options = await select.locator('option').allTextContents();
    console.log('agg row', i, value, options);
  }
  await browser.close();
})();
