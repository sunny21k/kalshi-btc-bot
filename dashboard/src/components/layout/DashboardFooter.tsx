import { Activity } from 'lucide-react';

export function DashboardFooter({ updated }: { updated: string }) {
  return (
    <div className="muted-text flex items-center gap-2 pb-4 pt-2 text-xs">
      <Activity size={14} /> {updated ? `Dashboard updated ${updated}.` : 'Auto-refreshes every 5 seconds.'}
    </div>
  );
}
