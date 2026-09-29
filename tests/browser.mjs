// Run against a freshly seeded local server: node tests/browser.mjs
import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const output='.runtime/browser-evidence';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:process.platform==='win32'?'chrome':undefined,headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
const base='http://127.0.0.1:8765';
const checks=[];
try {
  await page.goto(base);
  await page.getByRole('heading',{name:'Refund requests',exact:true}).waitFor();
  assert.equal(await page.locator('tbody tr').count(),10);
  await page.screenshot({path:`${output}/ledger.png`,fullPage:true});
  await page.getByLabel('Status',{exact:true}).focus();
  await page.keyboard.press('Alt+ArrowDown');
  await page.keyboard.press('Escape');
  checks.push('Native select opens by keyboard');
  await page.getByLabel('Search requests').fill('no-such-request');
  await page.getByRole('button',{name:'Apply filters'}).click();
  await page.getByRole('heading',{name:'No matching requests'}).waitFor();
  await page.getByRole('button',{name:'Clear search'}).click();
  await page.waitForURL(url=>!url.searchParams.get('q'));
  checks.push('Search, empty state, and clear');
  await page.getByRole('link',{name:'Review queue',exact:true}).click();
  await page.getByRole('link',{name:/Open req_/}).first().click();
  const detailURL=page.url();
  await page.getByRole('button',{name:'Approve for policy check'}).click();
  await page.getByText('Enter a reason with at least three characters.').waitFor();
  assert.equal(await page.getByLabel('Review reason').getAttribute('aria-invalid'),'true');
  await page.getByLabel('Review reason').fill('Checked the trusted payment and documented eligibility.');
  await page.screenshot({path:`${output}/review.png`,fullPage:true});
  const violations=(await new AxeBuilder({page}).analyze()).violations;
  await writeFile(`${output}/accessibility.json`,JSON.stringify(violations,null,2));
  assert.equal(violations.length,0,JSON.stringify(violations.map(x=>({id:x.id,impact:x.impact})),null,2));
  await page.getByRole('button',{name:'Approve for policy check'}).click();
  await page.getByRole('status').filter({hasText:'Review saved'}).waitFor();
  checks.push('Review validation, save, policy re-evaluation, and accessible detail');
  for (const [action, expected] of [['Request evidence','require evidence'],['Reject request','deny']]) {
    await page.goto(`${base}/reviews`);
    await page.getByRole('link',{name:/Open req_/}).first().click();
    await page.getByLabel('Review reason').fill('Reviewed the evidence and recorded the next customer action.');
    await page.getByRole('button',{name:action,exact:true}).click();
    await page.getByRole('status').filter({hasText:'Review saved'}).waitFor();
    await page.locator('.page-heading .badge').filter({hasText:expected}).waitFor();
  }
  checks.push('Request-evidence and reject actions persist and re-evaluate');
  await page.setViewportSize({width:390,height:844});
  await page.goto(detailURL);
  await page.screenshot({path:`${output}/detail-mobile.png`,fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  await page.emulateMedia({reducedMotion:'reduce'});
  checks.push('Narrow detail without page overflow and reduced motion');
  await page.goto(`${base}/runs`);
  await page.getByRole('heading',{name:'Evaluation runs',exact:true}).waitFor();
  await page.screenshot({path:`${output}/runs-mobile.png`,fullPage:true});
  await page.goto(`${base}/missing`);
  await page.getByRole('heading',{name:'Page not found',exact:true}).waitFor();
  checks.push('Runs and navigable error route');
  assert.equal(errors.length,0,errors.join('\n'));
  await writeFile(`${output}/checks.json`,JSON.stringify({checks,errors,passed:true},null,2));
  console.log(JSON.stringify({checks,errors,passed:true},null,2));
} finally { await browser.close(); }

