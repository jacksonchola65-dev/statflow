const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.goto('http://127.0.0.1:5173/login', { waitUntil: 'load', timeout: 30000 });
    console.log('URL=', page.url());
    console.log('content-length=', (await page.content()).length);
    const formCount = await page.locator('form[aria-label="Sign in form"]').count();
    console.log('form count=', formCount);
    for (let i=0; i<formCount; i++) {
      console.log('form visible=', await page.locator('form[aria-label="Sign in form"]').nth(i).isVisible());
    }
    await browser.close();
  } catch (err) {
    console.error('ERR', err.message);
    try { console.log('URL=', page.url()); } catch {};
    try { console.log('content-length=', (await page.content()).length); } catch {}
    await browser.close();
    process.exit(1);
  }
})();
