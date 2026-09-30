// Canonical layout, palette and walkthrough copy for the framework illustration.
// No browser/runtime dependencies; outputs are deterministic and self-contained.
import { writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const output = fileURLToPath(new URL('../docs/diagrams/', import.meta.url));
const themes = {
  light: { bg: '#f3f6fa', panel: '#ffffff', ink: '#132b44', muted: '#486079', line: '#698097', border: '#c6d3e1', blue: '#245eb0', amber: '#885209', teal: '#126f69', gate: '#fff4de' },
  dark: { bg: '#0b1422', panel: '#142236', ink: '#eef4fc', muted: '#aec0d5', line: '#8097b1', border: '#3b526e', blue: '#8db9ff', amber: '#ffd08a', teal: '#7cdbca', gate: '#302719' },
};
const steps = [
  ['Validate & persist', 'Intent + typed action', 'Record a proposal', 'An application, person or model can originate a proposal. The runtime validates its action schema and records the revision. An optional model assessment is a signal, never execution authority.'],
  ['Policy & review', 'Facts + versioned rules', 'Decide against trusted facts', 'The domain resolves authoritative evidence and evaluates deterministic policy. Missing evidence, denial or evaluation errors block execution. Required review must reference the evaluated evidence; approval cannot waive mandatory checks.'],
  ['Bind authorization', 'Exact action + expiry', 'Authorize a specific action', 'Authorization binds the action, evidence, proposal revision, executor, policy and expiry. A favorable assessment or a human approval alone is not a reusable permission to execute.'],
  ['Check & reserve', 'Atomic resource claims', 'Check again before dispatch', 'Immediately before dispatch, the runtime revalidates authority and atomically claims applicable resources. Stale facts, expired authorization or insufficient resources stop this execution attempt.'],
  ['Dispatch', 'Durable idempotency key', 'Invoke the registered executor', 'The registered executor applies the authorized action using a durable idempotency key. Reference examples simulate effects. Production integrations must prevent alternate execution paths and isolate credentials.'],
  ['Resolve outcome', 'Reconcile when unknown', 'Recover without blind retries', 'A timeout is not proof of failure. Unknown outcomes retain reservations until authoritative reconciliation resolves them, including after restart. Never retry an ambiguous action with a new idempotency key. Signed records support receipts, replay and investigation.'],
];
const escape = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
const text = (x, y, value, cls = '') => `<text x="${x}" y="${y}" class="${cls}">${escape(value)}</text>`;
const path = (d, cls = '') => `<path d="${d}" class="wire ${cls}" marker-end="url(#arrow)"/>`;
const variables = t => Object.entries(t).map(([k, v]) => `--${k}:${v}`).join(';');
function svg(theme, adaptive = false) {
  const css = `.architecture{${variables(themes[theme])}}${adaptive ? `.dark .architecture{${variables(themes.dark)}}.light .architecture{${variables(themes.light)}}` : ''}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 900" class="architecture" role="img" aria-labelledby="diagram-title diagram-description">
<title id="diagram-title">Decision Firewall architecture</title>
<desc id="diagram-description">A proposal and optional assessment enter a shared governance runtime. Trusted domain evidence and policy govern authorization. Revalidation and resource reservation precede idempotent execution. Unknown outcomes reconcile without blind retries. Linked audit records support receipts and investigation. Models cannot grant authority.</desc>
<style>${css}
text{font-family:'Segoe UI',Arial,sans-serif;fill:var(--ink);font-size:18px} .heading{font-family:Bahnschrift,'Segoe UI',sans-serif;font-size:42px;font-weight:600}.eyebrow{font-size:14px;font-weight:700;letter-spacing:2px;fill:var(--muted)}.sub{fill:var(--muted);font-size:17px}.title{font-size:22px;font-weight:600}.step-title{font-size:18px;font-weight:600}.number{font:600 16px Consolas,monospace;fill:var(--blue)}.panel{fill:var(--panel);stroke:var(--border);stroke-width:1.5}.wire{stroke:var(--line);stroke-width:2;fill:none}.dependency{stroke-dasharray:5 5}.gate{fill:var(--gate);stroke:var(--amber);stroke-width:2}.amber{fill:var(--amber)}.blue{fill:var(--blue)}.teal{fill:var(--teal)}.stage.active rect{stroke:var(--blue);stroke-width:4}.stage.active .number{fill:var(--ink)}
</style>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="var(--line)" stroke-width="1.5"/></marker></defs>
<rect width="1400" height="900" rx="16" fill="var(--bg)"/>
${text(52, 48, 'ARCHITECTURE / REFERENCE IMPLEMENTATION', 'eyebrow')}
${text(52, 105, 'Decision Firewall', 'heading')}
${text(52, 140, 'From a proposed action to an accountable outcome.', 'sub')}
${text(1348, 105, 'MODEL OPTIONAL', 'eyebrow').replace('class="eyebrow"', 'class="eyebrow" text-anchor="end"')}
${[
  [52, '01 / PROPOSAL', 'Your application', 'Independent intent + typed action', 'Human, program or model originated'],
  [494, '02 / ASSESSMENT', 'Decision model', 'Typed signals and recommendations', 'Cannot grant execution authority'],
  [936, '03 / TRUSTED FACTS', 'Evidence resolver', 'Authoritative records + versions', 'Model claims are not evidence'],
].map(([x, label, title, a, b]) => `<rect x="${x}" y="186" width="412" height="146" rx="10" class="panel"/>${text(x + 22, 217, label, 'eyebrow')}${text(x + 22, 251, title, 'title')}${text(x + 22, 282, a, 'sub')}${text(x + 22, 307, b, 'sub')}`).join('')}
${path('M 147 332 V 442')}
${path('M 700 332 V 353 H 200 V 442')}
${path('M 1142 332 V 372 H 371 V 442')}
<rect x="52" y="398" width="1296" height="208" rx="12" fill="none" stroke="var(--border)"/>
${text(960, 425, 'SHARED GOVERNANCE RUNTIME', 'eyebrow')}
${steps.map(([title, sub], i) => { const x = 72 + i * 214; return `<g class="stage" data-step="${i}"><rect x="${x}" y="448" width="184" height="108" rx="8" class="${i === 2 ? 'gate' : 'panel'}"/>${text(x + 14, 474, String(i + 1).padStart(2, '0'), `number${i === 2 ? ' amber' : ''}`)}${text(x + 14, 507, title, 'step-title')}${text(x + 14, 536, sub, 'sub').replace('class="sub"', 'class="sub" style="font-size:14px"')}</g>${i < 5 ? path(`M ${x + 185} 503 H ${x + 211}`, `flow flow-${i + 1}`) : ''}`; }).join('')}
${text(405, 584, 'Execution continues only when all prerequisites pass.', 'sub')}
${path('M 168 675 V 622 H 308 V 556', 'dependency')}
${path('M 1020 556 V 641 H 700 V 675')}
${path('M 906 728 H 917 V 629 H 1234 V 556')}
${path('M 1265 556 V 675')}
${[
  [52, 'EXTEND / DOMAIN PACK', 'Your rules, your use case', 'Action schema · evidence · policy', 'Refunds / access / deployment / custom'],
  [494, 'EXECUTE / ADAPTER', 'Idempotent effects', 'Dispatch → authoritative reconciliation', 'Reference effects are simulated'],
  [936, 'RECORD / INVESTIGATE', 'Linked audit + receipts', 'SQLite · signatures · historical replay', 'Lifecycle records, not just final results'],
].map(([x, label, title, a, b]) => `<rect x="${x}" y="675" width="412" height="144" rx="10" class="panel"/>${text(x + 22, 706, label, 'eyebrow')}${text(x + 22, 741, title, 'title')}${text(x + 22, 772, a, 'sub')}${text(x + 22, 797, b, 'sub')}`).join('')}
${text(52, 857, 'AUTHORITY IS EXPLICIT', 'eyebrow amber')}
${text(340, 857, 'Unknown ≠ failed. Retain reservations; reconcile using the original key.', 'sub')}
${text(52, 883, 'Embedded SQLite runtime. Trusted adapters. Deployment authentication and credential isolation remain integration responsibilities.', 'sub').replace('class="sub"', 'class="sub" style="font-size:14px"')}
</svg>`;
}

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Decision Firewall — architecture walkthrough</title>
<style>
:root{color-scheme:light;${variables(themes.light)};--accent:var(--blue)}html.dark{color-scheme:dark;${variables(themes.dark)}}html.light{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 'Segoe UI',Arial,sans-serif}main{max-width:1440px;margin:auto;padding:24px}header{display:flex;gap:20px;align-items:center;justify-content:space-between}h1{font-size:20px;margin:0}p{margin:8px 0;color:var(--muted)}button{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:9px 15px;cursor:pointer;min-height:44px}button:hover{border-color:var(--accent)}button:focus-visible,.canvas:focus-visible{outline:3px solid var(--accent);outline-offset:4px}button:disabled{opacity:.5;cursor:default}button[aria-current=step]{border:2px solid var(--accent);padding:8px 14px;color:var(--accent)}.canvas{overflow-x:auto;margin:24px 0 12px;scrollbar-color:var(--border) var(--bg)}svg{display:block;width:100%;min-width:1000px}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}.steps{display:flex;gap:8px;flex-wrap:wrap}.details{margin-top:24px;border-left:4px solid var(--accent);padding:4px 24px;max-width:920px;min-height:155px}.details h2{font-size:24px;margin:0}.note{font-size:14px}.running .flow.current{stroke:var(--blue);stroke-dasharray:5 4;animation:travel .7s linear infinite}@keyframes travel{to{stroke-dashoffset:-18}}@media(prefers-reduced-motion:reduce){*{animation:none!important;scroll-behavior:auto!important}}@media(max-width:700px){main{padding:16px}header{align-items:flex-start}h1{font-size:18px}.details{padding:4px 16px;min-height:240px}}@media(forced-colors:active){button[aria-current=step]{outline:2px solid Highlight}.details{border-color:Highlight}}
</style><script>document.documentElement.className = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';</script></head><body><main>
<header><div><h1>Architecture walkthrough</h1><p>Explore the lifecycle. No actions are executed.</p></div><button id="theme" type="button">Toggle theme</button></header>
<div class="canvas" tabindex="0" role="region" aria-label="Architecture diagram. Scroll horizontally on small screens.">${svg('light', true)}</div>
<p class="note">On a narrow screen, scroll the diagram horizontally. The step descriptions below remain readable.</p>
<div class="controls" aria-label="Walkthrough controls"><button id="play" type="button">Play flow</button><button id="prev" type="button">Previous</button><button id="next" type="button">Next</button><button id="reset" type="button">Reset</button></div>
<nav class="steps" aria-label="Lifecycle steps">${steps.map(([title], i) => `<button type="button" data-select="${i}">${i + 1}. ${escape(title)}</button>`).join('')}</nav>
<section class="details" aria-live="polite" aria-atomic="true"><h2 id="step-title"></h2><p id="step-description"></p></section>
<p class="note">Illustration of the reference implementation, not a live trace or a claim of improved model accuracy. Optional telemetry exports help navigation; signed local records support audit verification.</p>
<noscript><p>JavaScript is disabled. The full static architecture remains available above; lifecycle navigation requires JavaScript.</p></noscript>
</main><script>
const steps = ${JSON.stringify(steps)};
const root = document.documentElement;
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let current = 0, timer = null;
function render() {
  document.querySelectorAll('[data-step]').forEach((node, i) => node.classList.toggle('active', i === current));
  document.querySelectorAll('[data-select]').forEach((node, i) => { if(i === current) node.setAttribute('aria-current','step'); else node.removeAttribute('aria-current'); });
  document.querySelectorAll('.flow').forEach(node => node.classList.toggle('current', node.classList.contains('flow-' + current)));
  document.getElementById('step-title').textContent = (current + 1) + ' / ' + steps[current][2];
  document.getElementById('step-description').textContent = steps[current][3];
  const canvas = document.querySelector('.canvas');
  const diagram = canvas.querySelector('svg');
  if (canvas.clientWidth < diagram.clientWidth) canvas.scrollLeft = Math.max(0, (72 + current * 214 + 92) * diagram.clientWidth / 1400 - canvas.clientWidth / 2);
  document.getElementById('prev').disabled = current === 0;
  document.getElementById('next').disabled = current === steps.length - 1;
}
function stop() { clearInterval(timer); timer = null; root.classList.remove('running'); document.getElementById('play').textContent = 'Play flow'; }
function select(i) { stop(); current = i; render(); }
document.querySelectorAll('[data-select]').forEach(node => node.addEventListener('click', () => select(Number(node.dataset.select))));
document.getElementById('prev').onclick = () => select(Math.max(0,current - 1));
document.getElementById('next').onclick = () => select(Math.min(steps.length - 1,current + 1));
document.getElementById('reset').onclick = () => select(0);
document.getElementById('play').onclick = () => {
  if (timer) { stop(); return; }
  if (current === steps.length - 1) current = 0;
  root.classList.add('running'); document.getElementById('play').textContent = 'Pause flow'; render();
  timer = setInterval(() => { current++; render(); if(current === steps.length - 1) stop(); }, 5000);
};
document.getElementById('theme').onclick = () => { const dark = root.classList.contains('dark'); root.classList.toggle('dark', !dark); root.classList.toggle('light', dark); };
document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
reduced.addEventListener('change', stop);
render();
</script></body></html>`;

await writeFile(`${output}framework.svg`, svg('light') + '\n');
await writeFile(`${output}framework-dark.svg`, svg('dark') + '\n');
await writeFile(`${output}framework.html`, html + '\n');
console.log('Rendered framework.svg, framework-dark.svg and framework.html');
