// Browser checks for the standalone documentation walkthrough (no app server).
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const browser = await chromium.launch({
  channel: process.platform === 'win32' ? 'chrome' : undefined,
  headless: true,
});
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.clock.install();
  await page.goto(new URL('../docs/diagrams/framework.html', import.meta.url).href);
  assert.equal(await page.locator('html').getAttribute('class'), 'dark');
  assert.equal(await page.getByRole('button', { name: 'Previous', exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole('button', { name: 'Pause flow', exact: true }).count(), 0);
  for (const theme of ['dark', 'light']) {
    assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations.map(v => v.id), [], `${theme} accessibility`);
    if (theme === 'dark') await page.getByRole('button', { name: 'Toggle theme' }).click();
  }
  const overflow = await page.locator('.stage').evaluateAll(nodes => nodes.flatMap(node => {
    const bounds = node.querySelector('rect').getBBox();
    return [...node.querySelectorAll('text')].filter(t => t.getBBox().x + t.getBBox().width > bounds.x + bounds.width - 8).map(t => t.textContent);
  }));
  assert.deepEqual(overflow, [], 'Stage labels fit their cards');
  await page.getByRole('button', { name: 'Next', exact: true }).focus();
  await page.keyboard.press('Enter');
  assert.match(await page.locator('#step-title').textContent(), /^2 /);
  await page.getByRole('button', { name: 'Play flow', exact: true }).click();
  await page.clock.runFor(5001);
  assert.match(await page.locator('#step-title').textContent(), /^3 /);
  await page.getByRole('button', { name: 'Pause flow', exact: true }).click();
  await page.clock.runFor(10000);
  assert.match(await page.locator('#step-title').textContent(), /^3 /, 'Pause holds the selected stage');
  await page.getByRole('button', { name: 'Play flow', exact: true }).click();
  await page.clock.runFor(15001);
  assert.equal(await page.getByRole('button', { name: 'Next', exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole('button', { name: 'Play flow', exact: true }).count(), 1, 'Playback stops at completion');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('button', { name: 'Play flow', exact: true }).click();
  await page.clock.runFor(5001);
  assert.equal(await page.locator('.flow.current').evaluate(el => getComputedStyle(el).animationName), 'none');
  await page.getByRole('button', { name: 'Pause flow', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '6. Resolve outcome', exact: true }).click();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'No page overflow');
  assert.equal(await page.locator('.canvas').evaluate(el => el.scrollLeft > 0), true, 'Mobile selection reveals its stage');
  assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations.map(v => v.id), [], 'Narrow-screen accessibility');
  assert.deepEqual(errors, [], 'No browser errors');
  console.log('Framework walkthrough: themes, accessibility, label fit, keyboard, playback, reduced motion and mobile checks passed.');
} finally {
  await browser.close();
}
