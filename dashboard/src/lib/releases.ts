import release from '../../release.json';
import type { ReleaseInfo } from '../types/releases';

export const APP_RELEASE: ReleaseInfo = release;
export const APP_VERSION = `v${APP_RELEASE.version}`;

export function formatReleaseDate(value: string) {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString('en-US', {
    timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric',
  });
}
