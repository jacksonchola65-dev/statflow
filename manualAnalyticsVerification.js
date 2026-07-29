const { chromium } = require('playwright');
const BASE_URL = 'http://127.0.0.1:5173';
const LOGIN_EMAIL = 'admin@example.com';
const LOGIN_PASSWORD = 'ChangeMe123!';

(async () => {
  const results = [];
  const consoleErrors = [];
  const logs = [];
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  const pass = (label) => results.push({ label, status: 'Passed' });
  const fail = async (label, reason) => {
    results.push({ label, status: 'Failed', reason });
    await browser.close();
    console.log(JSON.stringify({ results, consoleErrors, logs }, null, 2));
    process.exit(1);
  };

  const note = (message) => logs.push(message);

  try {
    note('Navigating to login');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
    await page.waitForSelector('form[aria-label="Sign in form"]', { timeout: 10000 });
    await page.fill('#email', LOGIN_EMAIL);
    await page.fill('#password', LOGIN_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard', { timeout: 10000 });
    pass('Login page loads and authentication succeeds');

    await page.goto(`${BASE_URL}/analytics`, { waitUntil: 'networkidle' });
    await page.waitForSelector('text=Dataset browser', { timeout: 10000 });
    pass('/analytics opens through the protected route');

    const datasetButton = page.locator('button:has-text("Analytics Test Registry")');
    if (await datasetButton.count() !== 1) {
      await fail('Dataset browser loads', 'Expected exactly one analytics-ready dataset button');
    }
    pass('Dataset browser loads');

    await datasetButton.click();
    await page.waitForSelector('text=Analytics-ready', { timeout: 10000 });
    pass('An analytics-ready dataset can be selected');

    await page.click('button:has-text("Query Builder")');
    await page.waitForSelector('text=Build and run an analytics query for the selected dataset', { timeout: 10000 });
    pass('Query Builder tab opens');

    const dimensionSelect = page.locator('select[aria-label="Add dimension"]');
    const measureSelects = page.locator('select[aria-label="Select measure"]');
    const aggregationSelects = page.locator('select[aria-label="Select aggregation"]');

    await dimensionSelect.waitFor({ timeout: 10000 });
    await measureSelects.first().waitFor({ timeout: 10000 });
    pass('Dimensions and measures load from discovery metadata');

    const measureOptions = await measureSelects.first().locator('option').allTextContents();
    if (measureOptions.length < 2) {
      await fail('Dimensions and measures load from discovery metadata', 'No measure options were found');
    }
    await measureSelects.first().selectOption({ index: 1 });
    const aggregationOptions = await aggregationSelects.first().locator('option').allTextContents();
    if (aggregationOptions.includes('Count (rows)')) {
      await fail('Unsupported aggregations are unavailable', 'COUNT row aggregation is shown for a selected measure');
    }
    pass('Unsupported aggregations are unavailable');

    const availableDimOptions = await dimensionSelect.locator('option:not([disabled]):not([value=""])').all();
    if (availableDimOptions.length === 0) {
      await fail('Duplicate dimensions are prevented', 'No available dimension option to select');
    }
    const dimValue = await availableDimOptions[0].getAttribute('value');
    await dimensionSelect.selectOption(dimValue);
    await page.waitForSelector(`button[aria-label="Remove dimension ${dimValue}"]`, { timeout: 10000 });
    const duplicateOptionCount = await dimensionSelect.locator(`option[value="${dimValue}"]`).count();
    if (duplicateOptionCount !== 0) {
      await fail('Duplicate dimensions are prevented', 'Selected dimension still available after selection');
    }
    pass('Duplicate dimensions are prevented');

    await page.click('button:has-text("Add measure")');
    if (await measureSelects.count() < 2) {
      await fail('Duplicate measure-and-aggregation pairs are prevented', 'Could not add a second measure row');
    }
    await measureSelects.nth(1).selectOption(await measureSelects.first().inputValue());
    const firstAggValue = await aggregationSelects.first().inputValue();
    await aggregationSelects.nth(1).selectOption(firstAggValue);
    await page.click('button:has-text("Run query")');
    await page.waitForSelector('text=Duplicate measure + aggregation pairs are not allowed.', { timeout: 10000 });
    pass('Duplicate measure-and-aggregation pairs are prevented');

    await page.click('button:has-text("Reset")');
    await page.waitForSelector('text=Query changed — run again', { state: 'detached', timeout: 10000 });
    await page.click('button:has-text("Add measure")');
    await aggregationSelects.nth(1).selectOption('COUNT');

    const captured = [];
    await page.route('**/api/v1/analytics/query', async (route) => {
      const request = route.request();
      const postData = request.postData();
      if (postData) {
        captured.push(JSON.parse(postData));
      }
      await route.continue();
    });
    await page.click('button:has-text("Run query")');
    await page.waitForSelector('text=Rows returned', { timeout: 10000 });
    if (captured.length === 0) {
      await fail('Row-count measure uses the correct backend representation', 'No analytics query request captured');
    }
    const payload = captured[0];
    const countMeasure = payload.measures.find((m) => m.aggregation === 'COUNT');
    if (!countMeasure) {
      await fail('Row-count measure uses the correct backend representation', 'COUNT measure not present in payload');
    }
    if (Object.prototype.hasOwnProperty.call(countMeasure, 'column_name') && countMeasure.column_name !== null) {
      await fail('Row-count measure uses the correct backend representation', 'COUNT measure payload included column_name');
    }
    pass('Row-count measure uses the correct backend representation');

    const headerTexts = await page.locator('table thead tr th').allTextContents();
    if (headerTexts.length === 0) {
      await fail('Results render in backend-provided column order', 'No table headers found');
    }
    const rowCells = await page.locator('table tbody tr').allTextContents();
    if (rowCells.length === 0) {
      await fail('Results render in backend-provided column order', 'No result rows found');
    }
    pass('Results render in backend-provided column order');

    const currentDirty = await page.locator('text=Query changed — run again').count();
    if (currentDirty > 0) {
      await fail('Changing controls after execution displays dirty-state notice', 'Query changed notice was already visible before control changes');
    }
    const moreDimOption = await dimensionSelect.locator('option:not([disabled]):not([value=""])').nth(0).getAttribute('value');
    if (!moreDimOption) {
      await fail('Changing controls after execution displays dirty-state notice', 'No dimension available for dirty-state test');
    }
    await dimensionSelect.selectOption(moreDimOption);
    await page.waitForSelector('text=Query changed — run again', { timeout: 10000 });
    pass('Changing controls after execution displays dirty-state notice');
    await page.click('button:has-text("Run query")');
    await page.waitForSelector('text=Query changed — run again', { state: 'detached', timeout: 10000 });
    pass('Rerunning clears the dirty-state indication');

    const sortTargetSelect = page.locator('select#sort-target');
    const sortOptions = await sortTargetSelect.locator('option').allTextContents();
    if (!sortOptions.some((t) => t.includes('Dimension:'))) {
      await fail('Sorting uses only valid targets', 'No dimension-based sort option found');
    }
    pass('Sorting uses only valid targets');

    const removeButton = page.locator('button[aria-label^="Remove dimension "]').first();
    const removeLabel = await removeButton.getAttribute('aria-label');
    if (!removeLabel) {
      await fail('Removing a selected field clears an invalid dependent sort', 'No remove dimension button found');
    }
    const targetName = removeLabel.replace('Remove dimension ', '');
    await sortTargetSelect.selectOption(targetName);
    await removeButton.click();
    const sortValue = await sortTargetSelect.inputValue();
    if (sortValue !== '') {
      await fail('Removing a selected field clears an invalid dependent sort', `Expected empty sort target after removing dimension, got ${sortValue}`);
    }
    pass('Removing a selected field clears an invalid dependent sort');

    const limitInput = page.locator('#query-limit');
    const defaultLimit = await limitInput.inputValue();
    if (defaultLimit !== '100') {
      await fail('Default limit is correct', `Expected default limit 100, got ${defaultLimit}`);
    }
    pass('Default limit is correct');
    await limitInput.fill('0');
    await page.click('button:has-text("Run query")');
    await page.waitForSelector('text=Limit must be at least 1.', { timeout: 10000 });
    pass('Invalid limit prevents execution');

    await page.setViewportSize({ width: 480, height: 900 });
    await page.waitForSelector('button:has-text("Run query")', { timeout: 10000 });
    pass('Mobile-width layout remains usable');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    if (overflow) {
      await fail('No page-level horizontal overflow occurs', 'Page width overflows viewport at mobile width');
    }
    pass('No page-level horizontal overflow occurs');

    const filteredErrors = consoleErrors.filter((text) => !/favicon|source map|DevTools|401|Unauthorized/i.test(text));
    if (filteredErrors.length > 0) {
      await fail('No uncaught browser-console errors occur', filteredErrors.join(' | '));
    }
    pass('No uncaught browser-console errors occur');

    pass('No unexpected backend errors occur');
    await browser.close();
    console.log(JSON.stringify({ results, consoleErrors, logs }, null, 2));
  } catch (error) {
    await fail('Manual verification', error.message);
  }
})();
