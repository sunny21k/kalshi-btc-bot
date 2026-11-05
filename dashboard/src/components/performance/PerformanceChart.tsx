import { ChartColumn, TrendingUp } from 'lucide-react';
import {
  Bar, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { formatDay, formatProfit } from '../../lib/performance';
import type { PerformanceSummary } from '../../lib/performance';
import type { ChartPoint, PerformanceData } from '../../types/performance';
import { profitTone } from '../../utils/format';

function PnlTooltip({ active, point, mode }: { active?: boolean; point?: ChartPoint; mode: 'daily' | 'cumulative' }) {
  if (!active || !point) return null;
  const value = mode === 'daily' ? point.daily : point.cumulative;
  return (
    <div className="pnl-tooltip">
      <div className="muted-heading">{formatDay(point.date, true)}</div>
      <div className={`mt-1 font-semibold tabular-nums ${profitTone(value)}`}>{formatProfit(value)}</div>
      <div className="muted-text mt-1">{point.trades} settled {point.trades === 1 ? 'trade' : 'trades'} | Daily {formatProfit(point.daily)}</div>
    </div>
  );
}

type Props = {
  points: ChartPoint[];
  mode: 'daily' | 'cumulative';
  onModeChange: (mode: 'daily' | 'cumulative') => void;
  bounds: { start: string; end: string };
  stats: PerformanceSummary;
  selectedDate: string | null;
  pending: number;
  excluded: PerformanceData['excluded'];
};

export function PerformanceChart({ points, mode, onModeChange, bounds, stats, selectedDate, pending, excluded }: Props) {
  const omitted = Object.values(excluded).reduce((sum, count) => sum + count, 0);
  return (
    <div className="performance-chart-column">
      <div className="performance-chart-heading">
        <div className="min-w-0">
          <div className={`performance-net ${profitTone(stats.net)}`}>{formatProfit(stats.net)}</div>
          <div className="muted-text mt-1 text-[11px]">
            {formatDay(bounds.start)} - {formatDay(bounds.end)} | {stats.trades} settled
            {stats.roi !== null && ` | ${stats.roi.toFixed(2)}% ROI`}
          </div>
        </div>
        <div className="performance-modes" role="group" aria-label="P/L chart display">
          <button title="Daily profit and loss" aria-label="Daily profit and loss" aria-pressed={mode === 'daily'} onClick={() => onModeChange('daily')}><ChartColumn size={14} /> Daily</button>
          <button title="Cumulative profit and loss in selected range" aria-label="Cumulative profit and loss" aria-pressed={mode === 'cumulative'} onClick={() => onModeChange('cumulative')}><TrendingUp size={14} /> Cumulative</button>
        </div>
      </div>
      <div className="performance-plot" role="img" aria-label={`${mode === 'daily' ? 'Daily' : 'Cumulative'} P/L, ${formatDay(bounds.start)} through ${formatDay(bounds.end)}, total ${formatProfit(stats.net)}`}>
        {points.length ? (
          <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 600, height: 242 }}>
            <ComposedChart data={points} margin={{ top: 12, right: 10, left: 0, bottom: 0 }} accessibilityLayer>
              <CartesianGrid stroke="var(--row-border)" vertical={false} />
              <XAxis dataKey="time" type="number" scale="time" domain={['dataMin', 'dataMax']} tickCount={5}
                tickFormatter={(value: number) => formatDay(new Date(value).toISOString().slice(0, 10))}
                tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={28} />
              <YAxis width={62} tickCount={5} tickFormatter={(value: number) => formatProfit(value, true)}
                tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <ReferenceLine y={0} stroke="var(--muted)" strokeOpacity={0.5} />
              {selectedDate && <ReferenceLine x={new Date(`${selectedDate}T00:00:00Z`).getTime()} stroke="var(--muted)" strokeDasharray="3 3" />}
              <Tooltip cursor={{ stroke: 'var(--muted)', strokeDasharray: '3 3' }}
                content={(props) => <PnlTooltip active={props.active} point={props.payload?.[0]?.payload as ChartPoint | undefined} mode={mode} />} />
              {mode === 'daily' ? (
                <Bar dataKey="daily" name="Daily P/L" maxBarSize={26} isAnimationActive={false}>
                  {points.map((point) => <Cell key={point.date} fill={point.daily > 0 ? 'var(--chart-positive)' : point.daily < 0 ? 'var(--chart-negative)' : 'var(--muted)'} />)}
                </Bar>
              ) : <Line type="stepAfter" dataKey="cumulative" name="Cumulative P/L" stroke={stats.net >= 0 ? 'var(--chart-positive)' : 'var(--chart-negative)'} strokeWidth={2} dot={points.length === 1} activeDot={{ r: 4 }} isAnimationActive={false} />}
            </ComposedChart>
          </ResponsiveContainer>
        ) : <div className="performance-empty">No settled trades in this period.</div>}
      </div>
      <div className="performance-footnote muted-text">
        <span>{stats.profitable} profitable / {stats.trades} settled</span>
        {pending > 0 && <span title="Open trades or results awaiting verified outcomes and fees across this bot's history">{pending} pending overall</span>}
        {omitted > 0 && <span title={`${excluded.invalidDate} invalid dates, ${excluded.invalidProfitLoss} invalid P/L records, ${excluded.duplicates} duplicates`}>{omitted} records excluded</span>}
      </div>
    </div>
  );
}
