import { Activity } from 'lucide-react';
import { APP_VERSION } from '../../lib/releases';
import { AppLink } from './AppLink';

export function DashboardFooter({ updated, showUpdates = true }: { updated: string; showUpdates?: boolean }) {
  return (
    <footer className="dashboard-footer muted-text">
      {showUpdates && <span><Activity size={14} /> {updated ? `Dashboard updated ${updated}.` : 'Auto-refreshes every 5 seconds.'}</span>}
      <AppLink href="/info/updates">{APP_VERSION} <span aria-hidden="true">/</span> What's new</AppLink>
    </footer>
  );
}
