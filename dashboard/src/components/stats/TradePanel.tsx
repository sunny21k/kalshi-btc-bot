import type { TradeStats } from '../../types/trades';
import { fmtPct, moneyClass, tableMoney } from '../../utils/format';
import { SideBreakdown } from './SideBreakdown';

export function TradePanel({ title, stats, live }: { title: string; stats: TradeStats; live?: boolean }) {
  return (
    <section className="trade-summary" aria-label={title}>
      <h2 className="trade-summary-heading">Trading results</h2>
      <dl className="trade-summary-overview">
        <div className="trade-summary-pnl"><dt>{live ? 'Net P/L' : 'P/L'}</dt><dd className={moneyClass(stats.profitLoss)}>{tableMoney(stats.profitLoss, true)}</dd></div>
        <div><dt>Win rate</dt><dd>{fmtPct(stats.winRate)}</dd></div>
        <div><dt>ROI</dt><dd>{fmtPct(stats.roi)}</dd></div>
        <div><dt>Total traded</dt><dd>{tableMoney(stats.totalTraded)}</dd></div>
      </dl>
      <dl className="trade-summary-counts">
        <div><dt>Total trades</dt><dd>{stats.total}</dd></div>
        <div><dt>Settled</dt><dd>{stats.settled}</dd></div>
        <div><dt>Unsettled</dt><dd>{stats.unsettled}</dd></div>
      </dl>
      <SideBreakdown yes={stats.yes} no={stats.no} live={live} />
    </section>
  );
}
