const { chromium } = require('playwright');
const path = require('path');

const BASE = 'http://127.0.0.1:5173';
const EMAIL = 'admin@statflow.test';
const PASSWORD = 'ChangeMe123!';
const files = {
  valid: path.resolve(__dirname, 'temp_valid_import.csv'),
  headerOnly: path.resolve(__dirname, 'temp_header_only.csv'),
  malformed: path.resolve(__dirname, 'temp_malformed.csv'),
  empty: path.resolve(__dirname, 'temp_empty.csv'),
  invalidPdf: path.resolve(__dirname, 'temp_invalid.pdf'),
};

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.fill('#email', EMAIL);
  await page.fill('#password', PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL('**/dashboard', { timeout: 20000 });
}

async function openImport(page) {
  await page.goto(`${BASE}/import`, { waitUntil: 'networkidle' });
  await page.waitForURL('**/import', { timeout: 20000 });
  await page.waitForSelector('input[type=file]', { state: 'attached', timeout: 20000 });
}

async function selectFile(page, filePath) {
  const fileInput = page.locator('input[type=file]').first();
  const count = await fileInput.count();
  if (!count) throw new Error('No file input found when selecting file')
  await fileInput.setInputFiles(filePath);
  await page.waitForTimeout(250);
  const uploadButton = page.locator('button:has-text("Upload & Preview")');
  await uploadButton.waitFor({ state: 'visible', timeout: 10000 });
  return {
    fileInputCount: count,
    uploadEnabled: !(await uploadButton.isDisabled()),
    uploadText: (await uploadButton.textContent()).trim(),
    fileName: await page.locator('text=' + path.basename(filePath)).count() ? path.basename(filePath) : null,
  };
}

async function clickUpload(page) {
  const uploadButton = page.locator('button:has-text("Upload & Preview")');
  if (await uploadButton.isDisabled()) {
    return { success: false, reason: 'disabled' };
  }
  try {
    const [resp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/v1/imports/files/inspect') || r.url().includes('/api/v1/imports/csv/preview'), { timeout: 20000 }),
      uploadButton.click(),
    ])
    return { response: resp };
  } catch (err) {
    return { error: err.message };
  }
}

async function getAlerts(page) {
  return await page.$$eval('[role=alert]', els => els.map(el => el.textContent.trim()).filter(Boolean));
}

async function getMappingState(page) {
  const sourceColumns = await page.$$eval('[data-testid="source-column-chip"]', els => els.map(e => e.textContent.trim()));
  const mappingRows = await page.$$eval('[data-testid^="mapping-row-"]', els => els.map(el => ({
    target: el.getAttribute('data-testid'),
    sourceType: el.querySelector('select')?.value || null,
    sourceColumn: el.querySelectorAll('select')[1]?.value || null,
    fixedValue: el.querySelector('input[type=text]')?.value || null,
  })));
  const generateDisabled = await page.locator('button:has-text("Generate Preview")').isDisabled().catch(() => null);
  const backButton = await page.locator('button:has-text("Back to file selection")').count();
  return { sourceColumns, mappingRows, generateDisabled, hasBack: backButton > 0 };
}

async function setMappings(page) {
  const rules = {
    province_code: 'customer_id',
    indicator_code: 'product_id',
    value: 'amount',
    reference_year: 'fixed_value',
    dataset_name: 'fixed_value',
    source_name: 'fixed_value',
  };
  for (const [target, value] of Object.entries(rules)) {
    const row = page.locator(`[data-testid="mapping-row-${target}"]`);
    if (await row.count() === 0) continue;
    if (value === 'fixed_value') {
      await row.locator('select').first().selectOption('fixed_value');
      const input = row.locator('input[type=text]');
      if (await input.count()) {
        const fill = target === 'reference_year' ? '2026' : target === 'dataset_name' ? 'Test Import Dataset' : 'Test Source';
        await input.fill(fill);
      }
    } else {
      const select = row.locator('select').nth(1);
      await select.selectOption(value);
    }
  }
}

async function generateMappedPreview(page) {
  const generateButton = page.locator('button:has-text("Generate Preview")');
  const response = await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/v1/imports/files/map-preview'), { timeout: 20000 }),
    generateButton.click(),
  ]).then(([resp]) => resp).catch((err) => ({ error: err.message }));
  return response;
}

async function capturePreview(page) {
  const headers = await page.$$eval('table thead th', els => els.map(e => e.textContent.trim()).slice(0, 10)).catch(() => []);
  const rows = await page.$$eval('table tbody tr', rows => rows.map(r => Array.from(r.querySelectorAll('td')).map(td => td.textContent.trim()))).catch(() => []);
  return { headers, rows };
}

async function captureSemanticFields(body) {
  try {
    const json = JSON.parse(body);
    const keys = ['semantic_role', 'domain_prediction', 'entities', 'entity_keys', 'relationships', 'semantic_classifications'];
    const found = {};
    const recurse = (obj, prefix = '') => {
      if (obj && typeof obj === 'object') {
        if (Array.isArray(obj)) {
          obj.forEach((item, idx) => recurse(item, `${prefix}[${idx}]`));
        } else {
          for (const [k, v] of Object.entries(obj)) {
            const path = prefix ? `${prefix}.${k}` : k;
            if (keys.includes(k)) found[path] = v;
            recurse(v, path);
          }
        }
      }
    };
    recurse(json);
    return found;
  } catch {
    return {};
  }
}

async function run() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const logs = [];
  const requests = [];
  const responses = [];

  page.on('console', message => {
    if (message.type() === 'error') logs.push(message.text());
  });

  page.on('request', request => {
    if (request.url().includes('/api/v1/')) {
      const postData = request.postData();
      requests.push({
        url: request.url(),
        method: request.method(),
        headers: request.headers(),
        postData: typeof postData === 'string' ? postData.slice(0, 200) : null,
      });
    }
  });

  page.on('response', async response => {
    if (response.url().includes('/api/v1/')) {
      const body = await response.text().catch(() => null);
      responses.push({ url: response.url(), status: response.status(), body: body ? body.slice(0, 1000) : null });
    }
  });

  await login(page);
  await openImport(page);

  const validSelect = await selectFile(page, files.valid);
  const validUploadResponse = await clickUpload(page);
  const validAlerts = await getAlerts(page);
  const validMapping = await getMappingState(page);
  let validPreview = null;
  let validSemantic = {};

  if (validUploadResponse?.response) {
    const resp = validUploadResponse.response;
    if (resp.url().includes('/api/v1/imports/files/inspect')) {
      const body = await resp.text().catch(() => null);
      validSemantic = await captureSemanticFields(body);
    }
  }

  if (validMapping && validMapping.sourceColumns.length > 0) {
    await setMappings(page);
    const afterMapping = await getMappingState(page);
    const mapPreviewResponse = await generateMappedPreview(page);
    const preview = await capturePreview(page);
    const semanticFromMap = mapPreviewResponse?.response
      ? await captureSemanticFields(await mapPreviewResponse.response.text().catch(() => null))
      : {};
    validPreview = { mapPreviewResponse, preview, semanticFromMap };
  } else {
    validPreview = await capturePreview(page);
  }

  const fileReset = await page.locator('button:has-text("Back to file selection")').count() > 0 ? await page.locator('button:has-text("Back to file selection")').click().then(() => page.waitForSelector('input[type=file]', { state: 'attached', timeout: 10000 })).then(() => true).catch(() => false) : false;
  const validResetSelect = await selectFile(page, files.valid);
  const invalidPdfSelect = await selectFile(page, files.invalidPdf);
  const invalidPdfAlert = await getAlerts(page);
  const emptySelect = await selectFile(page, files.empty);
  const emptyAlert = await getAlerts(page);
  await selectFile(page, files.headerOnly);
  const headerUploadResponse = await clickUpload(page);
  const headerAlerts = await getAlerts(page);
  await selectFile(page, files.malformed);
  const malformedUploadResponse = await clickUpload(page);
  const malformedAlerts = await getAlerts(page);

  await browser.close();

  console.log(JSON.stringify({
    validSelect,
    validUploadResponse: {
      url: validUploadResponse?.response?.url || null,
      status: validUploadResponse?.response?.status || null,
      bodySnippet: validUploadResponse?.response
        ? (await validUploadResponse.response.text().catch(() => null))?.slice(0, 500)
        : null,
      error: validUploadResponse?.error || null,
    },
    validAlerts,
    validMapping,
    validPreview,
    validSemantic,
    fileReset,
    validResetSelect,
    invalidPdfSelect,
    invalidPdfAlert,
    emptySelect,
    emptyAlert,
    headerUploadResponse: {
      url: headerUploadResponse?.response?.url || null,
      status: headerUploadResponse?.response?.status || null,
      bodySnippet: headerUploadResponse?.response
        ? (await headerUploadResponse.response.text().catch(() => null))?.slice(0, 500)
        : null,
      error: headerUploadResponse?.error || null,
    },
    headerAlerts,
    malformedUploadResponse: {
      url: malformedUploadResponse?.response?.url || null,
      status: malformedUploadResponse?.response?.status || null,
      bodySnippet: malformedUploadResponse?.response
        ? (await malformedUploadResponse.response.text().catch(() => null))?.slice(0, 500)
        : null,
      error: malformedUploadResponse?.error || null,
    },
    malformedAlerts,
    consoleErrors: logs,
    recentRequests: requests.slice(-10),
    recentResponses: responses.slice(-10),
  }, null, 2));
}

run().catch(err => {
  console.error(err);
  process.exit(1);
});
