import type { AppLocation, InfoSection } from '../types/navigation';

export const INFO_SECTIONS: Array<{ id: InfoSection; label: string }> = [
  { id: 'overview', label: 'Getting started' },
  { id: 'bots', label: 'Bot guide' },
  { id: 'faq', label: 'Common questions' },
  { id: 'updates', label: 'What\'s new' },
];

export function readAppLocation(pathname: string): AppLocation {
  const [page, section] = pathname.replace(/^\/+|\/+$/g, '').split('/');
  if (page !== 'info') return { page: 'bots', section: 'overview' };
  return { page: 'info', section: INFO_SECTIONS.some(item => item.id === section) ? section as InfoSection : 'overview' };
}
