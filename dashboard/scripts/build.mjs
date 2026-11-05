import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { planRelease, sourceFingerprint } from './releases.mjs';

function runCommands(root) {
  const require = createRequire(path.join(root, 'package.json'));
  const commands = [
    [require.resolve('typescript/bin/tsc'), '-b'],
    [path.join(path.dirname(require.resolve('vite/package.json')), 'bin/vite.js'), 'build'],
  ];
  for (const command of commands) {
    const result = spawnSync(process.execPath, command, { cwd: root, stdio: 'inherit' });
    if (result.error) throw result.error;
    if (result.status !== 0) throw new Error(`Build failed (${result.signal || result.status}); release version was not advanced`);
  }
}

export async function buildDashboard(root, { bump, notes = [], noVersion = false } = {}, run = runCommands) {
  const names = ['release.json', 'package.json', 'package-lock.json'];
  const originals = await Promise.all(names.map(name => fs.readFile(path.join(root, name), 'utf8')));
  const [current, pkg, lock] = originals.map(text => JSON.parse(text));
  const next = noVersion ? current : planRelease(current, await sourceFingerprint(root), { bump, notes });
  pkg.version = next.version;
  lock.version = next.version;
  if (lock.packages?.['']) lock.packages[''].version = next.version;
  const updated = [next, pkg, lock].map(value => JSON.stringify(value, null, 2) + '\n');
  const changed = names.map((_, index) => updated[index] !== originals[index]);
  try {
    for (let index = 0; index < names.length; index++) {
      if (changed[index]) await fs.writeFile(path.join(root, names[index]), updated[index]);
    }
    await run(root);
  } catch (error) {
    for (let index = 0; index < names.length; index++) {
      if (changed[index]) await fs.writeFile(path.join(root, names[index]), originals[index]);
    }
    throw error;
  }
  return next;
}

async function main() {
  const { values } = parseArgs({ options: {
    bump: { type: 'string' }, note: { type: 'string', multiple: true }, 'no-version': { type: 'boolean', default: false },
  } });
  const root = fileURLToPath(new URL('..', import.meta.url));
  const release = await buildDashboard(root, { bump: values.bump, notes: values.note, noVersion: values['no-version'] });
  console.log(`Dashboard v${release.version}${values['no-version'] ? ' (preview build)' : ''}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
