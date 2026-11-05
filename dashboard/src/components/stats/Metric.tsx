import type React from 'react';

export function Metric({ label, value, tone, large }: { label: string; value: React.ReactNode; tone?: string; large?: boolean }) {
  return (
    <div className="surface-card metric-box border px-3 py-2">
      <div className="muted-text text-xs font-medium uppercase tracking-wide">{label}</div>
      <div className={`mt-0.5 font-semibold tabular-nums ${large ? 'text-xl' : 'text-base'} ${tone ?? ''}`}>{value}</div>
    </div>
  );
}
