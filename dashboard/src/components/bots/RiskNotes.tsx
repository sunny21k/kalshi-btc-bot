import { CircleDollarSign } from 'lucide-react';

export function RiskNotes({ dailyLimit }: { dailyLimit?: number }) {
  return (
    <section className="surface-card border p-4">
      <div className="section-title mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide">
        <CircleDollarSign size={16} /> Risk Notes
      </div>
      <div className="grid gap-2 text-sm">
        <div className="surface-soft border px-3 py-2">
          Shared daily live order cap (UTC): {dailyLimit === undefined ? 'Not reported' : dailyLimit === 0 ? 'No daily cap' : dailyLimit}
        </div>
        <div className="surface-soft border px-3 py-2">No daily loss stop</div>
      </div>
    </section>
  );
}
