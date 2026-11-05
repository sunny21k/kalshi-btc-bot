import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

export async function sourceFingerprint(root) {
  const files = [];
  async function visit(directory) {
    for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) await visit(file);
      else if (entry.isFile()) files.push(file);
    }
  }
  await visit(path.join(root, 'src'));
  try {
    await visit(path.join(root, 'public'));
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  for (const name of ['index.html', 'vite.config.ts', 'tailwind.config.ts', 'postcss.config.js']) {
    const file = path.join(root, name);
    try {
      await fs.access(file);
      files.push(file);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
  const hash = createHash('sha256');
  for (const file of files.sort()) {
    hash.update(path.relative(root, file).split(path.sep).join('/'));
    hash.update('\0');
    hash.update(await fs.readFile(file));
    hash.update('\0');
  }
  return hash.digest('hex');
}

export function releaseDate(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now);
}

export function planRelease(current, sourceHash, { bump, notes = [], date = releaseDate() } = {}) {
  if (!/^\d+\.\d+\.\d+$/.test(current.version) || !Array.isArray(current.releases)) {
    throw new Error('release.json must contain a major.minor.patch version and release history');
  }
  if (bump !== undefined && !['patch', 'minor', 'major'].includes(bump)) throw new Error('Choose patch, minor, or major');
  if (!bump && current.sourceHash === sourceHash) return current;
  if (!bump && !current.sourceHash) return { ...current, sourceHash };
  let [major, minor, patch] = current.version.split('.').map(Number);
  if (bump === 'major') { major += 1; minor = 0; patch = 0; }
  else if (bump === 'minor') { minor += 1; patch = 0; }
  else patch += 1;
  const version = `${major}.${minor}.${patch}`;
  return {
    ...current,
    version,
    sourceHash,
    releases: [{
      version, date, title: 'Dashboard update',
      changes: notes.length ? notes : ['Updated dashboard pages and components.'],
    }, ...current.releases],
  };
}
