const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    console.log('goto start');
    const response = await page.goto('http://127.0.0.1:5173/login', { waitUntil: 'load', timeout: 30000 });
    console.log('goto end', response && response.status(), page.url());
    const body = await page.content();
    console.log('body starts', body.slice(0, 500));
    const count = await page.locator('form[aria-label="Sign in form"]').count();
    console.log('count', count);
    if (count > 0) {
      const visible = await page.locator('form[aria-label="Sign in form"]').first().isVisible();
      console.log('visible', visible);
    }
    const emailCount = await page.locator('#email').count();
    console.log('email count', emailCount);
    await browser.close();
  } catch (err) {
    console.error('ERR', err);
    try { console.log('page url after err', page.url()); } catch {};
    await browser.close();
    process.exit(1);
  }
})();
