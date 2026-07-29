const { chromium } = require('playwright');
const path = require('path');

const BASE = 'http://127.0.0.1:5173';
const EMAIL = 'admin@statflow.test';
const PASSWORD = 'ChangeMe123!';
const TEMP_CSV = path.resolve(__dirname, 'temp_valid_import.csv');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const events = { requests: [], responses: [], errors: [] };
  page.on('console', msg => { if (msg.type() === 'error') events.errors.push(msg.text()); });
  page.on('request', req => { if (req.url().includes('/api/v1/')) { const postData = req.postData(); events.requests.push({url:req.url(), method:req.method(), headers:req.headers(), postData: postData ? postData.slice(0,200) : null}); }});
  page.on('response', async res => { if (res.url().includes('/api/v1/')) { const body = await res.text().catch(() => null); events.responses.push({url:res.url(), status:res.status(), body: body && body.slice(0,500)}); }});

  try {
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    await page.fill('#email', EMAIL);
    await page.fill('#password', PASSWORD);
    await Promise.all([page.waitForNavigation({ timeout: 20000 }), page.click('button[type=submit]')]);
    await page.goto(`${BASE}/import`, { waitUntil: 'networkidle' });
    const fileInput = page.locator('input[type=file]');
    await fileInput.waitFor({ state: 'attached', timeout: 20000 });
    await fileInput.setInputFiles(TEMP_CSV);
    const uploadButton = page.locator('button:has-text("Upload & Preview")');
    await uploadButton.waitFor({ state: 'visible', timeout: 10000 });
    const enabled = !(await uploadButton.isDisabled());
    const before = events.requests.length;
    const responsePromise = page.waitForResponse(r => r.url().includes('/api/v1/imports/files/inspect') || r.url().includes('/api/v1/imports/csv/preview'), { timeout: 20000 });
    await uploadButton.click({ force: true });
    const response = await responsePromise;
    const after = events.requests.length;
    // Wait for either mapping editor or direct preview to appear.
    await page.waitForFunction(() => {
      return !!document.querySelector('[aria-label="Column mapping editor"]') ||
             !!document.querySelector('button[aria-label="Confirm Import"]') ||
             !!document.querySelector('table');
    }, { timeout: 20000 });

    const mappingEditorCount = await page.locator('[aria-label="Column mapping editor"]').count();
    const previewHeaders = await page.$$eval('table thead th', els => els.map(e => e.textContent.trim()).slice(0,10));
    const sampleRows = await page.$$eval('table tbody tr', rows => rows.map(r => Array.from(r.querySelectorAll('td')).map(td => td.textContent.trim())));
    const sourceColumns = await page.$$eval('[data-testid="source-column-chip"]', els => els.map(e => e.textContent.trim())).catch(() => []);
    const mappingRows = await page.$$eval('[data-testid^="mapping-row-"]', els => els.map(row => row.getAttribute('data-testid'))).catch(() => []);
    const mappingMode = mappingEditorCount > 0 ? 'mapping_required' : 'direct_preview';

    let mappingDetail = null;
    if (mappingEditorCount > 0) {
      mappingDetail = await page.$$eval('[data-testid^="mapping-row-"]', rows => rows.map(row => {
        const target = row.getAttribute('data-testid');
        const selects = Array.from(row.querySelectorAll('select'));
        const sourceType = selects[0]?.value;
        const sourceColumn = selects[1]?.value || null;
        const fixedValue = row.querySelector('input[type=text]')?.value || null;
        return { target, sourceType, sourceColumn, fixedValue };
      }));
    }

    console.log(JSON.stringify({
      enabled,
      requestsSent: after - before,
      response: { url: response.url(), status: response.status(), bodySnippet: (await response.text()).slice(0,500) },
      mappingMode,
      mappingEditorCount,
      sourceColumns,
      mappingRows,
      mappingDetail,
      previewHeaders,
      sampleRows,
      consoleErrors: events.errors,
    }, null, 2));
  } catch (err) {
    console.error(err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
