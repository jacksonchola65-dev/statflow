const { chromium } = require('playwright');
const path = require('path');

const BASE = 'http://127.0.0.1:5173';
const EMAIL = 'admin@statflow.test';
const PASSWORD = 'ChangeMe123!';
const FILES = {
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
  await Promise.all([
    page.waitForURL('**/dashboard', { timeout: 20000 }),
    page.click('button[type=submit]'),
  ]);
}

async function openImport(page) {
  await page.goto(`${BASE}/import`, { waitUntil: 'networkidle' });
  await page.waitForURL('**/import', { timeout: 20000 });
  await page.waitForSelector('input[type=file]', { state: 'attached', timeout: 20000 });
}

async function attachFile(page, filePath) {
  await page.waitForSelector('input[type=file]', { state: 'attached', timeout: 20000 });
  const input = page.locator('input[type=file]').first();
  const count = await input.count();
  console.log('debug attachFile input count', count);
  if (!count) throw new Error('No file input found');
  await input.setInputFiles(filePath);
  await page.waitForTimeout(250);
  return {
    fileInputCount: count,
    file: path.basename(filePath),
    uploadButtonText: await page.locator('button:has-text("Upload & Preview")').first().textContent(),
    uploadEnabled: !(await page.locator('button:has-text("Upload & Preview")').first().isDisabled()),
  };
}

async function clickUpload(page) {
  const uploadButton = page.locator('button:has-text("Upload & Preview")').first();
  if (await uploadButton.isDisabled()) {
    return { success: false, reason: 'button_disabled' };
  }
  try {
    const response = await Promise.all([
      page.waitForResponse((res) => res.url().includes('/api/v1/imports/files/inspect') || res.url().includes('/api/v1/imports/csv/preview'), { timeout: 20000 }),
      uploadButton.click(),
    ]);
    return { success: true, response: response[0] };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function nextAlert(page) {
  const alert = await page.locator('[role=alert]').first();
  if (await alert.count()) {
    return (await alert.textContent()).trim();
  }
  const dropzone = await page.locator('#dropzone-error').first();
  if (await dropzone.count()) {
    return (await dropzone.textContent()).trim();
  }
  return null;
}

async function captureMappingState(page) {
  const editorCount = await page.locator('[aria-label="Column mapping editor"]').count();
  const sourceColumns = await page.$$eval('[data-testid="source-column-chip"]', els => els.map(el => el.textContent.trim()));
  const mappingRows = await page.$$eval('[data-testid^="mapping-row-"]', els => els.map((el) => {
    const selects = Array.from(el.querySelectorAll('select'));
    return {
      target: el.getAttribute('data-testid'),
      sourceType: selects[0]?.value || null,
      sourceColumn: selects[1]?.value || null,
      fixedValue: el.querySelector('input[type=text]')?.value || null,
    };
  }));
  return { editorCount, sourceColumns, mappingRows };
}

async function setMappings(page) {
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
    if (await row.count() === 0) continue;
    if (selection === 'fixed_value') {
      await row.locator('select').first().selectOption('fixed_value');
      const input = row.locator('input[type=text]');
      if (await input.count()) {
        const value = target === 'reference_year' ? '2026' : target === 'dataset_name' ? 'Test Import Dataset' : 'Test Source';
        await input.fill(value);
      }
    } else {
      await row.locator('select').nth(1).selectOption(selection);
    }
  }
}

async function clickGeneratePreview(page) {
  const button = page.locator('button:has-text("Generate Preview")').first();
  if (await button.isDisabled()) {
    return { success: false, reason: 'generate_disabled' };
  }
  try {
    const [response] = await Promise.all([
      page.waitForResponse((res) => res.url().includes('/api/v1/imports/files/map-preview'), { timeout: 20000 }),
      button.click(),
    ]);
    await page.waitForSelector('table', { timeout: 20000 });
    return { success: true, response };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function capturePreview(page) {
  const headers = await page.$$eval('table thead th', els => els.map(el => el.textContent.trim()));
  const rows = await page.$$eval('table tbody tr', rows => rows.map((row) => Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim())));
  return { headers, rows: rows.slice(0, 5) };
}

function extractSemanticFields(json) {
  const keys = new Set(['semantic_role', 'domain_prediction', 'entities', 'entity_keys', 'relationships', 'semantic_classifications']);
  const found = {};
  function recur(value, path = '') {
    if (value && typeof value === 'object') {
      if (Array.isArray(value)) {
        value.forEach((item, idx) => recur(item, `${path}[${idx}]`));
      } else {
        Object.entries(value).forEach(([k, v]) => {
          const full = path ? `${path}.${k}` : k;
          if (keys.has(k.toLowerCase())) {
            found[full] = v;
          }
          recur(v, full);
        });
      }
    }
  }
  recur(json);
  return found;
}

async function run() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const events = { requests: [], responses: [], console: [] };

  page.on('console', (msg) => {
    events.console.push({ type: msg.type(), text: msg.text() });
  });
  page.on('request', (req) => {
    if (req.url().includes('/api/v1/') || req.url().includes('/auth/')) {
      events.requests.push({ url: req.url(), method: req.method(), headers: req.headers(), postData: req.postData()?.slice(0, 200) || null });
    }
  });
  page.on('response', async (res) => {
    if (res.url().includes('/api/v1/') || res.url().includes('/auth/')) {
      const body = await res.text().catch(() => null);
      events.responses.push({ url: res.url(), status: res.status(), body: body ? body.slice(0, 1000) : null });
    }
  });

  await login(page);
  await openImport(page);

  const validAttach = await attachFile(page, FILES.valid);
  const validUpload = await clickUpload(page);
  const validAlert = await nextAlert(page);
  const validMapState = await captureMappingState(page);

  let mapPreviewResult = null;
  let previewData = null;
  let semanticData = {};

  if (validMapState.editorCount > 0) {
    await setMappings(page);
    mapPreviewResult = await clickGeneratePreview(page);
    if (mapPreviewResult.success) {
      previewData = await capturePreview(page);
      if (mapPreviewResult.response) {
        const text = await mapPreviewResult.response.text().catch(() => null);
        if (text) {
          try {
            semanticData = extractSemanticFields(JSON.parse(text));
          } catch (_) {
            semanticData = {};
          }
        }
      }
    }
  }

  const page2 = await browser.newPage();
  await login(page2);
  await openImport(page2);

  const invalidPdfState = await attachFile(page2, FILES.invalidPdf).catch((err) => ({ error: err.message }));
  const invalidPdfAlert = await nextAlert(page2);
  await openImport(page2);
  const emptyFileState = await attachFile(page2, FILES.empty).catch((err) => ({ error: err.message }));
  const emptyAlert = await nextAlert(page2);
  await openImport(page2);
  const headerOnlyState = await attachFile(page2, FILES.headerOnly).catch((err) => ({ error: err.message }));
  const headerUpload = headerOnlyState?.error ? { success: false, error: headerOnlyState.error } : await clickUpload(page2);
  const headerAlert = await nextAlert(page2);
  await openImport(page2);
  const malformedState = await attachFile(page2, FILES.malformed).catch((err) => ({ error: err.message }));
  const malformedUpload = malformedState?.error ? { success: false, error: malformedState.error } : await clickUpload(page2);
  const malformedAlert = await nextAlert(page2);

  await browser.close();

  console.log(JSON.stringify({
    validAttach,
    validUpload: {
      success: validUpload.success,
      url: validUpload.response?.url || null,
      status: validUpload.response?.status || null,
      error: validUpload.error || null,
    },
    validAlert,
    validMapState,
    mapPreviewResult: mapPreviewResult ? {
      success: mapPreviewResult.success,
      url: mapPreviewResult.response?.url || null,
      status: mapPreviewResult.response?.status || null,
      error: mapPreviewResult.error || null,
    } : null,
    previewData,
    semanticData,
    invalidPdfState,
    invalidPdfAlert,
    emptyFileState,
    emptyAlert,
    headerOnlyState,
    headerUpload: {
      success: headerUpload.success,
      url: headerUpload.response?.url || null,
      status: headerUpload.response?.status || null,
      error: headerUpload.error || null,
    },
    headerAlert,
    malformedState,
    malformedUpload: {
      success: malformedUpload.success,
      url: malformedUpload.response?.url || null,
      status: malformedUpload.response?.status || null,
      error: malformedUpload.error || null,
    },
    malformedAlert,
    events: {
      lastRequests: events.requests.slice(-10),
      lastResponses: events.responses.slice(-10),
      consoleErrors: events.console.filter((e) => e.type === 'error').slice(-10),
    },
  }, null, 2));
}

run().catch((err) => {
  console.error('script error', err);
  process.exit(1);
});
