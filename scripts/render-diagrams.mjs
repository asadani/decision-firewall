import { readdir } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
for (const name of await readdir(`${root}/docs/diagrams`)) {
  if (!name.endsWith('.mmd')) continue;
  const config = process.platform === 'win32' ? ['-p', `${root}/scripts/puppeteer.json`] : [];
  const result = spawnSync(process.execPath, [`${root}/node_modules/@mermaid-js/mermaid-cli/src/cli.js`, ...config, '-i', `${root}/docs/diagrams/${name}`, '-o', `${root}/docs/diagrams/${name.replace('.mmd','.svg')}`, '-t', 'neutral', '-b', 'transparent'], {stdio:'inherit'});
  if (result.status !== 0) process.exit(result.status || 1);
}

