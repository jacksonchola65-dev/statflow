const { chromium } = require('playwright');
const path = require('path');

const BASE = 'http://127.0.0.1:5173';
const EMAIL = 'admin@statflow.test';
const PASSWORD = 'ChangeMe123!';

const FILES = {
  valid: path.resolve(__dirname, 'temp_valid_import.csv'),
  malformed: path.resolve(__dirname, 'temp_malformed.csv'),
  empty: path.resolve(__dirname, 'temp_empty.csv'),
  headerOnly: path.resolve(__dirname, 'temp_header_only.csv'),
  invalidPdf: path.resolve(__dirname, 'temp_invalid.pdf'),
};

function capturePayload(req) {
  return {
    url: req.url(),
    method: req.method(),
    headers: req.headers(),
    postData: req.postData ? req.postData() : null,
  };
}

function captureResponse(res) {
  return {
    url: res.url(),
    status: res.status(),
    headers: res.headers(),
  };
}

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASSWORD);
  await Promise.all([
    page.waitForURL('**/dashboard', { timeout: 20000 }),
    page.click('button[type=submit]'),
  ]);
}

async function openImport(page) {
  await page.goto(`${BASE}/import`, { waitUntil: 'networkidle' });
  await page.waitForSelector('input[type=file]', { state: 'attached', timeout: 20000 });
}

async function setFile(page, filePath) {
  const fileInput = page.locator('input[type=file]');
  await fileInput.setInputFiles(filePath);
  return {
    fileInputCount: await fileInput.count(),
    uploadButtonEnabled: !(await page.locator('button:has-text("Upload & Preview")').isDisabled()),
  };
}

async function clickUpload(page, events) {
  const uploadButton = page.locator('button:has-text("Upload & Preview")');
  await uploadButton.waitFor({ state: 'visible', timeout: 10000 });
  const before = events.requests.length;
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/imports/files/inspect') || r.url().includes('/api/v1/imports/csv/preview'), { timeout: 20000 }),
    uploadButton.click(),
  ]);
  const after = events.requests.length;

  let phase = 'unknown';
  try {
    await page.waitForFunction(() => !!document.querySelector('[aria-label="Column mapping editor"]') || !!document.querySelector('button[aria-label="Confirm Import"]') || !!document.querySelector('table'), { timeout: 20000 });
    phase = await page.evaluate(() => {
      if (document.querySelector('[aria-label="Column mapping editor"]')) return 'mapping_required';
      if (document.querySelector('button[aria-label="Confirm Import"]')) return 'direct_preview';
      return 'unknown';
    });
  } catch (e) {
    phase = 'timeout';
  }

  const errors = await page.$$eval('[role=alert]', els => els.map(el => el.textContent.trim()).filter(Boolean));
  const previewHeaders = await page.$$eval('table thead th', els => els.map(e => e.textContent.trim()));
  const sampleRecords = await page.$$eval('table tbody tr', rows => rows.map(r => Array.from(r.querySelectorAll('td')).map(td => td.textContent.trim())));

  return {
    phase,
    requestsSent: after - before,
    response: captureResponse(response),
    alerts: errors,
    previewHeaders,
    sampleRecords,
  };
}

async function mapRequiredValidation(page) {
  const errors = await page.$$eval('[role=alert]', els => els.map(el => el.textContent.trim()).filter(Boolean));
  const generateBtn = page.locator('button:has-text("Generate Preview")');
  const enabled = !(await generateBtn.isDisabled());
  return {enabled, errors};
}

async function setMappings(page) {
  const mappingTargets = {
    province_code: 'customer_id',
    indicator_code: 'product_id',
    value: 'amount',
    reference_year: 'fixed_value',
    dataset_name: 'fixed_value',
    source_name: 'fixed_value',
  };

  for (const target of Object.keys(mappingTargets)) {
    const row = page.locator(`[data-testid="mapping-row-${target}"]`);
    const sourceType = mappingTargets[target];
    if (sourceType === 'fixed_value') {
      await row.locator('select').nth(0).selectOption('fixed_value');
      const input = row.locator('input[type=text]');
      if (await input.count() > 0) {
        const value = target === 'reference_year' ? '2026' : target === 'dataset_name' ? 'Test Import Dataset' : 'Imported';
        await input.fill(value);
      }
    } else {
      await row.locator('select').nth(1).selectOption(sourceType);
    }
  }
}

async function captureMappingState(page) {
  const sourceColumns = await page.$$eval('[data-testid="source-column-chip"]', els => els.map(e => e.textContent.trim()));
  const mappingRows = await page.$$eval('[data-testid^="mapping-row-"]', rows => rows.map((row) => {
    const target = row.getAttribute('data-testid');
    const selects = Array.from(row.querySelectorAll('select'));
    const sourceType = selects[0]?.value || null;
    const sourceColumn = selects[1]?.value || null;
    const fixedInput = row.querySelector('input[type=text]')?.value || null;
    return {target, sourceType, sourceColumn, fixedInput};
  }));
  return {sourceColumns, mappingRows};
}

async function simulateBackendFailure(page, route) {
  await page.route('**/api/v1/imports/files/inspect', async (route) => {
    await route.abort();
  });
  const result = await setFile(page, FILES.valid);
  if (!result.uploadButtonEnabled) return {uploadButtonEnabled: false};
  const uploadButton = page.locator('button:has-text("Upload & Preview")');
  await uploadButton.click();
  const alert = await page.waitForSelector('[role=alert]', {timeout: 15000}).then(el => el.textContent()).catch(() => null);
  const loadingButtons = await page.$$eval('button', els => els.filter(b => /Inspecting…|Generating…|Importing…/.test(b.textContent)).map(b => b.textContent.trim()));
  await page.unroute('**/api/v1/imports/files/inspect');
  return {alert, loadingButtons};
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const events = {console: [], requests: [], responses: [], errors: []};

  page.on('console', msg => { events.console.push({type: msg.type(), text: msg.text()}); if (msg.type()==='error') events.errors.push(msg.text()); });
  page.on('request', req => { if (req.url().includes('/api/v1/') || req.url().includes('/auth/')) events.requests.push(capturePayload(req)); });
  page.on('response', async res => { if (res.url().includes('/api/v1/') || res.url().includes('/auth/')) events.responses.push(captureResponse(res)); });

  await login(page);
  await openImport(page);
  const importState = {hasFileInput: await page.locator('input[type=file]').count() > 0};

  const validSet = await setFile(page, FILES.valid);
  const validUpload = await clickUpload(page, events);
  let mappingState = null;
  if (validUpload.phase === 'mapping_required') {
    mappingState = await captureMappingState(page);
    const invalidValidation = await mapRequiredValidation(page);
    await setMappings(page);
    const postSetValidation = await mapRequiredValidation(page);
    const generateBtn = page.locator('button:has-text("Generate Preview")');
    await generateBtn.click();
    const mappedPreview = await page.waitForSelector('button[aria-label="Confirm Import"], [data-testid="mapping-error-banner"]', {timeout:20000}).then(async () => {
      const previewTableHeaders = await page.$$eval('table thead th', els => els.map(e => e.textContent.trim()));
      const previewRecords = await page.$$eval('table tbody tr', rows => rows.map(r => Array.from(r.querySelectorAll('td')).map(td => td.textContent.trim())));
      return {previewTableHeaders, previewRecords};
    }).catch(() => null);
    mappingState = {mappingState, invalidValidation, postSetValidation, mappedPreview};
  }

  // Reset mapping state by going back to file selection
  const backButton = page.locator('button:has-text("Back to file selection")');
  if (await backButton.count() > 0) {
    await backButton.click();
    await page.waitForSelector('input[type=file]', {state:'visible', timeout:10000});
  }
  await setFile(page, FILES.valid);
  const postResetMapping = await captureMappingState(page);

  // Validate client-side file errors
  const invalidPdfState = await setFile(page, FILES.invalidPdf);
  const invalidPdfError = await page.$eval('#dropzone-error', el => el.textContent.trim()).catch(() => null);
  const emptyCsvState = await setFile(page, FILES.empty);
  const emptyCsvError = await page.$eval('#dropzone-error', el => el.textContent.trim()).catch(() => null);

  await setFile(page, FILES.headerOnly);
  const headerUpload = await clickUpload(page, events);
  await page.waitForTimeout(1000);
  const headerErrors = await page.$$eval('[role=alert]', els => els.map(e => e.textContent.trim()).filter(Boolean));

  await setFile(page, FILES.malformed);
  const malformedUpload = await clickUpload(page, events);
  await page.waitForTimeout(1000);
  const malformedErrors = await page.$$eval('[role=alert]', els => els.map(e => e.textContent.trim()).filter(Boolean));

  const backendFailure = await simulateBackendFailure(page);

  await browser.close();
  return {
    importState,
    validSet,
    validUpload,
    mappingState,
    postResetMapping,
    invalidPdfState,
    invalidPdfError,
    emptyCsvState,
    emptyCsvError,
    headerUpload,
    headerErrors,
    malformedUpload,
    malformedErrors,
    backendFailure,
    consoleErrors: events.errors,
    requestSummary: events.requests.slice(-10),
    responseSummary: events.responses.slice(-10),
  };
}

main().then((results) => {
  console.log(JSON.stringify(results, null, 2));
  process.exit(0);
}).catch((error) => {
  console.error(error);
  process.exit(1);
});