const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on('console', msg => console.log('console>', msg.type(), msg.text()));
  page.on('requestfailed', req => console.log('requestfailed>', req.url(), req.failure()?.errorText));
  page.on('requestfinished', req => console.log('requestfinished>', req.method(), req.url()));
  try {
    console.log('goto start');
    await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    console.log('goto success', page.url());
    const html = await page.content();
    console.log('html length', html.length);
  } catch (err) {
    console.error('goto error', err.message);
  } finally {
    await browser.close();
  }
})();
