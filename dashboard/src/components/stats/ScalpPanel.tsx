import type { ScalpStats } from '../../types/trades';
import { fmtPct, moneyClass, tableMoney } from '../../utils/format';
import { Metric } from './Metric';
import { TradedTotal } from './TradedTotal';

export function ScalpPanel({ stats }: { stats: ScalpStats }) {
  return (
    <section className="surface-panel border">
      <div className="table-header flex items-center justify-between border-b px-3 py-2">
        <h2 className="section-title text-xs font-semibold uppercase tracking-wide">5s Scalp</h2>
        <span className="muted-text text-xs font-semibold uppercase tracking-wide">5s momentum</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5 p-3 lg:grid-cols-3 2xl:grid-cols-6">
        <Metric label="Entries" value={stats.total} />
        <Metric label="Closed" value={stats.closed} />
        <Metric label="Open" value={stats.open} />
        <Metric label="Win Rate" value={fmtPct(stats.winRate)} />
        <Metric label="P/L" value={tableMoney(stats.profitLoss, true)} tone={moneyClass(stats.profitLoss)} />
        <Metric label="Peak P/L" value={tableMoney(stats.peakProfit, true)} tone={moneyClass(stats.peakProfit)} />
      </div>
      <TradedTotal value={stats.totalInvested} />
    </section>
  );
}
