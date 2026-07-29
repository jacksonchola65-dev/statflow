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

function captureRequest(req) {
  const postData = req.postData();
  return {
    url: req.url(),
    method: req.method(),
    headers: req.headers(),
    hasPostData: !!postData,
    postDataSnippet: postData ? postData.slice(0, 200) : null,
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
    page.waitForNavigation({ url: '**/dashboard', timeout: 20000 }),
    page.click('button[type=submit]'),
  ]);
}

async function openImport(page) {
  await page.goto(`${BASE}/import`, { waitUntil: 'networkidle' });
  await page.waitForSelector('input[type=file]', { state: 'attached', timeout: 20000 });
}

async function selectFile(page, filePath) {
  const fileInput = page.locator('input[type=file]');
  const count = await fileInput.count();
  if (!count) throw new Error('No file input found');
  await fileInput.setInputFiles(filePath);
  await page.waitForTimeout(250);
  const uploadButton = page.locator('button:has-text("Upload & Preview")');
  await uploadButton.waitFor({ state: 'visible', timeout: 10000 });
  return {
    fileInputCount: count,
    uploadEnabled: !(await uploadButton.isDisabled()),
    uploadButtonText: (await uploadButton.textContent()).trim(),
  };
}

async function clickUpload(page, events) {
  const uploadButton = page.locator('button:has-text("Upload & Preview")');
  if (await uploadButton.isDisabled()) {
    return { success: false, reason: 'upload_button_disabled' };
  }
  const beforeRequests = events.requests.length;
  const [response] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/api/v1/imports/files/inspect') || res.url().includes('/api/v1/imports/csv/preview'), { timeout: 20000 }),
    uploadButton.click(),
  ]);
  const afterRequests = events.requests.length;
  const body = await response.text().catch(() => null);
  let stage = 'unknown';
  try {
    await page.waitForFunction(() => !!document.querySelector('[aria-label="Column mapping editor"]') || !!document.querySelector('button[aria-label="Confirm Import"]'), { timeout: 20000 });
    stage = await page.evaluate(() => {
      if (document.querySelector('[aria-label="Column mapping editor"]')) return 'mapping_required';
      if (document.querySelector('button[aria-label="Confirm Import"]')) return 'direct_preview';
      return 'unknown';
    });
  } catch {
    stage = 'timeout';
  }
  return {
    requestsSent: afterRequests - beforeRequests,
    status: response.status(),
    url: response.url(),
    body: body && body.length > 0 ? body.slice(0, 2000) : null,
    stage,
    alerts: await page.$$eval('[role=alert]', els => els.map(el => el.textContent.trim()).filter(Boolean)),
  };
}

async function capturePreview(page) {
  const headers = await page.$$eval('table thead th', els => els.map(e => e.textContent.trim()));
  const rows = await page.$$eval('table tbody tr', rows => rows.map(r => Array.from(r.querySelectorAll('td')).map(td => td.textContent.trim())));
  return { headers, rows };
}

async function captureMappingState(page) {
  const sourceColumns = await page.$$eval('[data-testid="source-column-chip"]', els => els.map(e => e.textContent.trim()));
  const rows = await page.$$eval('[data-testid^="mapping-row-"]', els => els.map(row => {
    const target = row.getAttribute('data-testid');
    const selects = Array.from(row.querySelectorAll('select'));
    const sourceType = selects[0]?.value;
    const sourceColumn = selects[1]?.value || null;
    const fixedValue = row.querySelector('input[type=text]')?.value || null;
    return { target, sourceType, sourceColumn, fixedValue };
  }));
  const disabled = await page.locator('button:has-text("Generate Preview")').isDisabled();
  const fieldErrors = await page.$$eval('[role=alert]', els => els.map(el => el.textContent.trim()).filter(Boolean));
  return { sourceColumns, rows, generateDisabled: disabled, fieldErrors };
}

async function setValidMappings(page) {
  const mapping = {
    province_code: 'customer_id',
    indicator_code: 'product_id',
    value: 'amount',
    reference_year: 'fixed_value',
    dataset_name: 'fixed_value',
    source_name: 'fixed_value',
  };
  for (const [target, selection] of Object.entries(mapping)) {
    const row = page.locator(`[data-testid="mapping-row-${target}"]`);
    if (selection === 'fixed_value') {
      await row.locator('select').first().selectOption('fixed_value');
      const input = row.locator('input[type=text]');
      if (await input.count()) {
        const value = target === 'reference_year' ? '2026' : target === 'dataset_name' ? 'Test Import Dataset' : target === 'source_name' ? 'Test Source' : 'N/A';
        await input.fill(value);
      }
    } else {
      await row.locator('select').nth(1).selectOption(selection);
    }
  }
}

async function simulateBackendFailure(page, events) {
  let failureAlert = null;
  await page.route('**/api/v1/imports/files/inspect', (route) => route.abort());
  const fileState = await selectFile(page, FILES.valid);
  if (!fileState.uploadEnabled) {
    await page.unroute('**/api/v1/imports/files/inspect');
    return { uploadEnabled: false };
  }
  const uploadButton = page.locator('button:has-text("Upload & Preview")');
  await uploadButton.click();
  failureAlert = await page.waitForSelector('[role=alert]', { timeout: 15000 }).then(el => el.textContent()).catch(() => null);
  await page.unroute('**/api/v1/imports/files/inspect');
  const loadingButtons = await page.$$eval('button', els => els.filter(b => /Inspecting…|Generating…|Importing…/.test(b.textContent)).map(b => b.textContent.trim()));
  return { failureAlert, loadingButtons };
}

function findSemanticFields(json) {
  const lowerKeys = new Set(['semantic_role', 'domain_prediction', 'entities', 'entity_keys', 'relationships', 'semantic_classifications']);
  const found = {};
  function recurse(obj, path = '') {
    if (obj && typeof obj === 'object') {
      if (Array.isArray(obj)) {
        obj.forEach((item, idx) => recurse(item, `${path}[${idx}]`));
      } else {
        for (const [key, value] of Object.entries(obj)) {
          if (lowerKeys.has(key.toLowerCase())) {
            found[path ? `${path}.${key}` : key] = value;
          }
          recurse(value, path ? `${path}.${key}` : key);
        }
      }
    }
  }
  recurse(json);
  return found;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const events = { console: [], requests: [], responses: [], errors: [] };

  page.on('console', (msg) => {
    events.console.push({ type: msg.type(), text: msg.text() });
    if (msg.type() === 'error') events.errors.push(msg.text());
  });
  page.on('request', (req) => {
    if (req.url().includes('/api/v1/') || req.url().includes('/auth/')) {
      events.requests.push(captureRequest(req));
    }
  });
  page.on('response', async (res) => {
    if (res.url().includes('/api/v1/') || res.url().includes('/auth/')) {
      events.responses.push(captureResponse(res));
    }
  });

  await login(page);
  await openImport(page);

  const validFileState = await selectFile(page, FILES.valid);
  const validUploadResult = await clickUpload(page, events);

  let mappingState = null;
  let mappedPreview = null;
  let semanticFields = null;

  if (validUploadResult.stage === 'mapping_required') {
    mappingState = await captureMappingState(page);
    await setValidMappings(page);
    const validationAfterMapping = await captureMappingState(page);
    const generateButton = page.locator('button:has-text("Generate Preview")');
    await generateButton.click();
    await page.waitForSelector('table', { timeout: 20000 });
    mappedPreview = await capturePreview(page);
    const response = events.responses.find((r) => r.url.includes('/api/v1/imports/files/map-preview'));
    if (response) {
      const body = await page.request.get(response.url).then((r) => r.text()).catch(() => null);
      try { semanticFields = findSemanticFields(JSON.parse(body)); } catch {}
    }
  }

  if (validUploadResult.stage === 'direct_preview') {
    const response = events.responses.find((r) => r.url.includes('/api/v1/imports/csv/preview'));
    if (response) {
      const body = await page.request.get(response.url).then((r) => r.text()).catch(() => null);
      try { semanticFields = findSemanticFields(JSON.parse(body)); } catch {}
    }
  }

  const backButton = page.locator('button:has-text("Back to file selection")');
  if (await backButton.count()) {
    await backButton.click();
    await page.waitForSelector('input[type=file]', { state: 'visible', timeout: 10000 });
  }

  const fileStateAfterReset = await selectFile(page, FILES.valid);
  const invalidPdfState = await selectFile(page, FILES.invalidPdf);
  const invalidPdfAlert = await page.$eval('#dropzone-error', (el) => el.textContent.trim()).catch(() => null);
  const emptyCsvState = await selectFile(page, FILES.empty);
  const emptyCsvAlert = await page.$eval('#dropzone-error', (el) => el.textContent.trim()).catch(() => null);

  await selectFile(page, FILES.headerOnly);
  const headerResult = await clickUpload(page, events);
  const headerErrors = await page.$$eval('[role=alert]', els => els.map(el => el.textContent.trim()).filter(Boolean));

  await selectFile(page, FILES.malformed);
  const malformedResult = await clickUpload(page, events);
  const malformedErrors = await page.$$eval('[role=alert]', els => els.map(el => el.textContent.trim()).filter(Boolean));

  const backendFailureResult = await simulateBackendFailure(page, events);

  await browser.close();
  console.log(JSON.stringify({
    validFileState,
    validUploadResult,
    mappingState,
    mappedPreview,
    semanticFields,
    fileStateAfterReset,
    invalidPdfState,
    invalidPdfAlert,
    emptyCsvState,
    emptyCsvAlert,
    headerResult,
    headerErrors,
    malformedResult,
    malformedErrors,
    backendFailureResult,
    consoleErrors: events.errors,
    recentRequests: events.requests.slice(-10),
    recentResponses: events.responses.slice(-10),
  }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});