import { AlertTriangle } from 'lucide-react';
import type { ShadowStats } from '../../types/trades';
import { Metric } from './Metric';

export function ShadowPanel({ shadow }: { shadow: ShadowStats }) {
  const blockedReasons = Object.entries(shadow.blockedReasons ?? {});

  return (
    <section className="surface-card border p-4">
      <div className="mb-3 flex items-center gap-2">
        <AlertTriangle size={16} className="warning-text" />
        <h2 className="section-title text-sm font-semibold uppercase tracking-wide">Blocked Signals</h2>
      </div>
      <Metric label="Shadow Signals" value={shadow.total} />
      <div className="mt-3 grid gap-2">
        {blockedReasons.map(([reason, count]) => (
          <div className="surface-soft flex items-center justify-between rounded border px-3 py-2 text-sm" key={reason}>
            <span>{reason}</span>
            <span className="font-semibold tabular-nums">{count}</span>
          </div>
        ))}
        {!blockedReasons.length && (
          <div className="surface-soft muted-text rounded border px-3 py-2 text-sm">No blocked signals yet</div>
        )}
      </div>
    </section>
  );
}
