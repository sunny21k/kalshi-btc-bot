import type React from 'react';
import { formatDay, formatProfit } from '../../lib/performance';
import type { PerformanceSummary } from '../../lib/performance';
import type { PerformanceData } from '../../types/performance';
import { profitTone } from '../../utils/format';

export function PerformanceStats({ stats, kind }: { stats: PerformanceSummary; kind: PerformanceData['kind'] }) {
  const metric = (label: string, value: React.ReactNode, detail?: string, help?: string) => (
    <div className="performance-stat" title={help}>
      <dt>{label}</dt>
      <dd>{value}</dd>
      {detail && <div className="muted-text text-[10px]">{detail}</div>}
    </div>
  );

  return (
    <dl className="performance-statistics">
      {metric('Avg / trade', <span className={profitTone(stats.average ?? 0)}>{stats.average === null ? '--' : formatProfit(stats.average)}</span>)}
      {metric('Profit factor', stats.profitFactor !== null ? stats.profitFactor.toFixed(2) : stats.grossProfit > 0 ? 'No losses' : '--', undefined, 'Net profits from profitable trades divided by net losses from losing trades')}
      {metric('Max drawdown', <span className={stats.maxDrawdown > 0 ? 'money-negative' : ''}>{formatProfit(-stats.maxDrawdown)}</span>, undefined, 'Largest peak-to-trough loss within this range, including intraday trades')}
      {metric('Best day', stats.bestDay ? <span className={profitTone(Number(stats.bestDay.profitLoss))}>{formatProfit(Number(stats.bestDay.profitLoss))}</span> : '--', stats.bestDay ? formatDay(stats.bestDay.date) : undefined)}
      {metric('Worst day', stats.worstDay ? <span className={profitTone(Number(stats.worstDay.profitLoss))}>{formatProfit(Number(stats.worstDay.profitLoss))}</span> : '--', stats.worstDay ? formatDay(stats.worstDay.date) : undefined)}
      {kind === 'live'
        ? metric('Settled fees', formatProfit(stats.fees ?? 0, false, false), undefined, 'Actual exchange fees for the settled trades in this range')
        : metric('Net ROI', stats.roi === null ? '--' : `${stats.roi.toFixed(2)}%`)}
    </dl>
  );
}
