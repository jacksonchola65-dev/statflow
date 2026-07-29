const { chromium } = require('playwright');
const path = require('path');
const BASE = 'http://127.0.0.1:5173';
const EMAIL = 'admin@statflow.test';
const PASSWORD = 'ChangeMe123!';
const CSV_FILE = path.resolve(__dirname, 'temp_valid_import.csv');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const events = { requests: [], responses: [], errors: [] };
  page.on('console', (msg) => {
    if (msg.type() === 'error') events.errors.push(msg.text());
  });
  page.on('request', (req) => {
    if (req.url().includes('/api/v1/')) {
      events.requests.push({ url: req.url(), method: req.method(), headers: req.headers(), postData: req.postData()?.slice(0, 200) || null });
    }
  });
  page.on('response', async (res) => {
    if (res.url().includes('/api/v1/')) {
      events.responses.push({ url: res.url(), status: res.status(), headers: res.headers() });
    }
  });

  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL('**/dashboard', { timeout: 20000 });
  console.log('After login URL:', page.url());

  await page.goto(`${BASE}/import`, { waitUntil: 'networkidle' });
  await page.waitForURL('**/import', { timeout: 20000 });
  console.log('Import URL:', page.url());

  const fileInput = page.locator('input[type=file]');
  console.log('file input count', await fileInput.count());
  console.log('file input outer html', await fileInput.first().evaluate((el) => el.outerHTML));

  await fileInput.setInputFiles(CSV_FILE);
  await page.waitForTimeout(250);

  const uploadButton = page.locator('button:has-text("Upload & Preview")');
  console.log('upload button count', await uploadButton.count());
  console.log('upload button disabled', await uploadButton.isDisabled());
  console.log('upload button text', await uploadButton.first().textContent());

  const inspectResponse = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/api/v1/imports/files/inspect') || res.url().includes('/api/v1/imports/csv/preview'), { timeout: 20000 }),
    uploadButton.click(),
  ]).then(([res]) => res).catch((err) => ({ error: err.message }));

  console.log('inspectResponse', inspectResponse.url ? { url: inspectResponse.url(), status: inspectResponse.status() } : inspectResponse);

  const mappingEditorCountAfter = await page.locator('[aria-label="Column mapping editor"]').count();
  console.log('mapping editor count after upload', mappingEditorCountAfter);
  const previewButtonCount = await page.locator('button:has-text("Generate Preview")').count();
  console.log('generate preview button count', previewButtonCount);
  const confirmButtonCount = await page.locator('button:has-text("Confirm Import")').count();
  console.log('confirm import button count', confirmButtonCount);

  if (mappingEditorCountAfter > 0) {
    const sourceColumns = await page.$$eval('[data-testid="source-column-chip"]', els => els.map(el => el.textContent.trim()));
    console.log('source columns', sourceColumns);
  }

  console.log('last requests', events.requests.slice(-5));
  console.log('last responses', events.responses.slice(-5));
  console.log('console errors', events.errors.slice(-5));

  await browser.close();
})();
