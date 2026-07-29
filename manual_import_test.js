const { chromium } = require('playwright');
const path = require('path');
const BASE = 'http://127.0.0.1:5173';
const EMAIL = 'admin@statflow.test';
const PASSWORD = 'ChangeMe123!';
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const results = { console: [], requests: [], responses: [] };
  page.on('console', (msg) => results.console.push({ type: msg.type(), text: msg.text() }));
  page.on('requestfailed', (req) => results.requests.push({ url: req.url(), failed: true, failure: req.failure()?.errorText }));
  page.on('request', async (req) => {
    if (req.url().includes('/imports/csv/preview')) {
      const headers = req.headers();
      const postData = req.postData();
      results.requests.push({ url: req.url(), method: req.method(), headers, postDataSnippet: postData ? postData.slice(0,200) : null });
    }
  });
  page.on('response', async (res) => {
    try {
      if (res.url().includes('/imports/csv/preview')) {
        const status = res.status();
        const text = await res.text();
        results.responses.push({ url: res.url(), status, bodySnippet: text.slice(0,200) });
      }
    } catch (e) {
      results.responses.push({ url: res.url(), error: String(e) });
    }
  });

  try {
    await page.goto(BASE + '/login', { waitUntil: 'networkidle' });
    await page.fill('#email', EMAIL);
    await page.fill('#password', PASSWORD);
    await Promise.all([page.waitForURL('**/dashboard'), page.click('button[type=submit]')]);
    console.log('Logged in, go to import page');
    await page.goto(BASE + '/import', { waitUntil: 'networkidle' });
    // set file
    const filePath = path.resolve(__dirname, 'frontend/test-data/sample.csv');
    const input = await page.$('input[type=file]');
    console.log('found input', !!input);
    await input.setInputFiles(filePath);
    // confirm filename visible
    const filenameVisible = await page.locator('text=sample.csv').count();
    console.log('filename visible count', filenameVisible);
    // click upload
    await Promise.all([
      page.waitForResponse(r => r.url().includes('/imports/csv/preview')),
      page.click('button:has-text("Upload & Preview")')
    ]);
    // wait a bit for UI rendering
    await page.waitForTimeout(500);

    // capture rendered sample records table headers and rows if present
    try {
      const table = await page.$('table[aria-label="Sample import records"]');
      if (table) {
        const headers = await table.$$eval('thead th', ths => ths.map(t => t.textContent.trim()));
        const rows = await table.$$eval('tbody tr', trs => trs.map(r => {
          const cells = Array.from(r.querySelectorAll('td')).map(td => td.textContent.trim());
          return cells;
        }));
        results.rendered = { headers, rows };
      } else {
        results.rendered = { headers: null, rows: null };
      }
    } catch (e) {
      results.rendered = { headers: null, rows: null, error: String(e) };
    }

    console.log(JSON.stringify(results, null, 2));
    await browser.close();
  } catch (err) {
    console.error(err);
    await browser.close();
    process.exit(1);
  }
})();
