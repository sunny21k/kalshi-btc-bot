import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { buildDashboard } from '../scripts/build.mjs';
import { planRelease, releaseDate, sourceFingerprint } from '../scripts/releases.mjs';

const initial = () => ({ version: '1.0.0', sourceHash: '', releases: [{ version: '1.0.0', date: '2026-10-28', title: 'First release', changes: ['Help pages'] }] });

async function fixture(context) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'dashboard-release-'));
  context.after(() => fs.rm(root, { recursive: true, force: true }));
  await fs.mkdir(path.join(root, 'src'));
  await fs.writeFile(path.join(root, 'src/App.tsx'), 'export const App = () => "Bots";');
  await fs.writeFile(path.join(root, 'index.html'), '<div id="root"></div>');
  await fs.writeFile(path.join(root, 'release.json'), JSON.stringify(initial(), null, 2) + '\n');
  await fs.writeFile(path.join(root, 'package.json'), JSON.stringify({ name: 'test-dashboard', version: '1.0.0' }, null, 2) + '\n');
  await fs.writeFile(path.join(root, 'package-lock.json'), JSON.stringify({ version: '1.0.0', packages: { '': { name: 'test-dashboard', version: '1.0.0' } } }, null, 2) + '\n');
  return root;
}

const read = async (root, name) => JSON.parse(await fs.readFile(path.join(root, name), 'utf8'));

test('first release establishes a baseline and unchanged builds preserve its history', () => {
  const first = initial();
  const baseline = planRelease(first, 'abc');
  assert.equal(baseline.version, '1.0.0');
  assert.equal(baseline.sourceHash, 'abc');
  assert.deepEqual(baseline.releases, first.releases);
  assert.equal(planRelease(baseline, 'abc'), baseline);
  assert.equal(first.sourceHash, '');
});

test('changed source advances patch with notes; larger releases reset lower numbers', () => {
  const current = { ...initial(), version: '1.4.9', sourceHash: 'before' };
  const next = planRelease(current, 'after', { notes: ['Added FAQ search', 'Removed old navigation'], date: '2026-11-05' });
  assert.equal(next.version, '1.4.10');
  assert.deepEqual(next.releases[0], { version: '1.4.10', date: '2026-11-05', title: 'Dashboard update', changes: ['Added FAQ search', 'Removed old navigation'] });
  assert.equal(next.releases[1], current.releases[0]);
  assert.equal(planRelease(current, 'before', { bump: 'minor' }).version, '1.5.0');
  assert.equal(planRelease(current, 'before', { bump: 'major' }).version, '2.0.0');
  assert.throws(() => planRelease(current, 'x', { bump: 'small' }), /patch, minor, or major/);
});

test('release dates use the dashboard New York calendar', () => {
  assert.equal(releaseDate(new Date('2026-11-06T02:00:00Z')), '2026-11-05');
});

test('same-day builds combine notes while another date keeps a separate version', () => {
  const first = planRelease({ ...initial(), sourceHash: 'old' }, 'first', { notes: ['Added settings'], date: '2026-11-05' });
  const second = planRelease(first, 'second', { notes: ['Added rule editing', 'Added settings'], date: '2026-11-05' });
  assert.equal(second.releases.length, 2);
  assert.equal(second.releases[0].version, second.version);
  assert.deepEqual(second.releases[0].changes, ['Added rule editing', 'Added settings']);
  assert.equal(second.releases[1].date, '2026-10-28');
  const tomorrow = planRelease(second, 'third', { notes: ['New day'], date: '2026-11-06' });
  assert.equal(tomorrow.releases.length, 3);
});

test('fingerprints detect added, changed, and removed page content and assets, ignoring build output', async context => {
  const root = await fixture(context);
  const baseline = await sourceFingerprint(root);
  await fs.mkdir(path.join(root, 'dist'));
  await fs.writeFile(path.join(root, 'dist/index.html'), 'compiled output');
  await fs.writeFile(path.join(root, 'release.json'), JSON.stringify({ ...initial(), version: '9.0.0' }));
  assert.equal(await sourceFingerprint(root), baseline);
  await fs.writeFile(path.join(root, 'src/icon.svg'), '<svg/>');
  assert.notEqual(await sourceFingerprint(root), baseline);
  await fs.rm(path.join(root, 'src/icon.svg'));
  assert.equal(await sourceFingerprint(root), baseline);
  await fs.writeFile(path.join(root, 'src/App.tsx'), 'export const App = () => "Info";');
  assert.notEqual(await sourceFingerprint(root), baseline);
  await fs.mkdir(path.join(root, 'public'));
  const withSourceChange = await sourceFingerprint(root);
  await fs.writeFile(path.join(root, 'public/logo.svg'), '<svg/>');
  assert.notEqual(await sourceFingerprint(root), withSourceChange);
});

test('successful builds synchronize metadata before compilation and skip unchanged bumps', async context => {
  const root = await fixture(context);
  await buildDashboard(root, {}, async () => {});
  await fs.writeFile(path.join(root, 'src/App.tsx'), 'export const App = () => "FAQ";');
  let called = false;
  const next = await buildDashboard(root, { notes: ['Added FAQ'] }, async () => {
    called = true;
    assert.equal((await read(root, 'release.json')).version, '1.0.1');
    assert.equal((await read(root, 'package.json')).version, '1.0.1');
    const lock = await read(root, 'package-lock.json');
    assert.equal(lock.version, '1.0.1');
    assert.equal(lock.packages[''].version, '1.0.1');
  });
  assert.equal(called, true);
  assert.equal(next.releases[0].changes[0], 'Added FAQ');
  const unchanged = await buildDashboard(root, {}, async () => {});
  assert.equal(unchanged.version, '1.0.1');
  assert.equal(unchanged.releases.length, 2);
});

test('failed builds restore exact metadata and preview builds do not record releases', async context => {
  const root = await fixture(context);
  const names = ['release.json', 'package.json', 'package-lock.json'];
  const before = await Promise.all(names.map(name => fs.readFile(path.join(root, name), 'utf8')));
  await assert.rejects(buildDashboard(root, { bump: 'minor' }, async () => { throw new Error('Type error'); }), /Type error/);
  assert.deepEqual(await Promise.all(names.map(name => fs.readFile(path.join(root, name), 'utf8'))), before);
  const preview = await buildDashboard(root, { noVersion: true }, async () => {});
  assert.equal(preview.version, '1.0.0');
  assert.equal(preview.sourceHash, '');
  assert.deepEqual(await read(root, 'release.json'), initial());
});
