import React from 'react';
import { ChartColumn, ChevronLeft, ChevronRight, TrendingUp, X } from 'lucide-react';
import {
  Bar, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  calendarDates, calendarProfit, chartPoints, daysInRange, formatDay, formatMonth,
  formatProfit, rangeBounds, shiftMonth, summarizeDays,
} from './performance';
import type { ChartPoint, PerformanceData, PerformanceRange } from './performance';

const tone = (value: number) => value > 0 ? 'money-positive' : value < 0 ? 'money-negative' : 'muted-heading';
const ranges: Array<{ value: PerformanceRange; label: string }> = [
  { value: 'month', label: 'Month' }, { value: '7d', label: '7D' },
  { value: '30d', label: '30D' }, { value: 'all', label: 'All' },
];

function PnlTooltip({ active, point, mode }: { active?: boolean; point?: ChartPoint; mode: 'daily' | 'cumulative' }) {
  if (!active || !point) return null;
  const value = mode === 'daily' ? point.daily : point.cumulative;
  return (
    <div className="pnl-tooltip">
      <div className="muted-heading">{formatDay(point.date, true)}</div>
      <div className={`mt-1 font-semibold tabular-nums ${tone(value)}`}>{formatProfit(value)}</div>
      <div className="muted-text mt-1">{point.trades} settled {point.trades === 1 ? 'trade' : 'trades'} | Daily {formatProfit(point.daily)}</div>
    </div>
  );
}

function PerformanceContent({ data }: { data: PerformanceData }) {
  const lastDay = data.days[data.days.length - 1];
  const [range, setRange] = React.useState<PerformanceRange>('month');
  const [mode, setMode] = React.useState<'daily' | 'cumulative'>('daily');
  const [month, setMonth] = React.useState(lastDay?.date.slice(0, 7) ?? data.today.slice(0, 7));
  const [selectedDate, setSelectedDate] = React.useState<string | null>(null);
  const days = daysInRange(data, range, month);
  const stats = summarizeDays(days);
  const points = chartPoints(data, range, month);
  const bounds = rangeBounds(data, range, month);
  const monthDays = data.days.filter((day) => day.date.startsWith(month));
  const monthStats = summarizeDays(monthDays);
  const dayByDate = new Map(data.days.map((day) => [day.date, day]));
  const selected = selectedDate ? dayByDate.get(selectedDate) : undefined;
  const firstMonth = data.days[0]?.date.slice(0, 7) ?? data.today.slice(0, 7);
  const maxDayProfit = Math.max(0.0001, ...monthDays.map((day) => Math.abs(Number(day.profitLoss))));
  const omitted = Object.values(data.excluded).reduce((sum, count) => sum + count, 0);

  const changeRange = (value: PerformanceRange) => {
    setRange(value);
    setSelectedDate(null);
    if (value !== 'month') {
      setMonth(value === 'all' ? lastDay?.date.slice(0, 7) ?? data.today.slice(0, 7) : data.today.slice(0, 7));
    }
  };
  const changeMonth = (offset: number) => {
    setMonth(shiftMonth(month, offset));
    setRange('month');
    setSelectedDate(null);
  };

  const metric = (label: string, value: React.ReactNode, detail?: string, help?: string) => (
    <div className="performance-stat" title={help}>
      <dt>{label}</dt>
      <dd>{value}</dd>
      {detail && <div className="muted-text text-[10px]">{detail}</div>}
    </div>
  );

  return (
    <section className="performance-section" aria-label="Bot profit and loss">
      <header className="performance-toolbar">
        <div>
          <h2 className="section-title text-sm font-semibold">Performance</h2>
          <div className="muted-text mt-0.5 text-[11px]">{data.kind === 'live' ? 'Verified net P/L' : 'Paper P/L'} | {data.dateBasis === 'close' ? 'Close date' : 'Entry date'} | New York</div>
        </div>
        <div className="performance-ranges" role="group" aria-label="Performance date range">
          {ranges.map((item) => (
            <button key={item.value} aria-pressed={range === item.value} onClick={() => changeRange(item.value)}>{item.label}</button>
          ))}
        </div>
      </header>

      <div className="performance-grid">
        <div className="performance-chart-column">
          <div className="performance-chart-heading">
            <div className="min-w-0">
              <div className={`performance-net ${tone(stats.net)}`}>{formatProfit(stats.net)}</div>
              <div className="muted-text mt-1 text-[11px]">
                {formatDay(bounds.start)} - {formatDay(bounds.end)} | {stats.trades} settled
                {stats.roi !== null && ` | ${stats.roi.toFixed(2)}% ROI`}
              </div>
            </div>
            <div className="performance-modes" role="group" aria-label="P/L chart display">
              <button title="Daily profit and loss" aria-label="Daily profit and loss" aria-pressed={mode === 'daily'} onClick={() => setMode('daily')}><ChartColumn size={14} /> Daily</button>
              <button title="Cumulative profit and loss in selected range" aria-label="Cumulative profit and loss" aria-pressed={mode === 'cumulative'} onClick={() => setMode('cumulative')}><TrendingUp size={14} /> Cumulative</button>
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
            {data.pending > 0 && <span title="Open trades or results awaiting verified outcomes and fees across this bot's history">{data.pending} pending overall</span>}
            {omitted > 0 && <span title={`${data.excluded.invalidDate} invalid dates, ${data.excluded.invalidProfitLoss} invalid P/L records, ${data.excluded.duplicates} duplicates`}>{omitted} records excluded</span>}
          </div>
        </div>

        <div className="performance-calendar">
          <div className="performance-calendar-heading">
            <h3>{formatMonth(month)}</h3>
            <div className="flex gap-1">
              <button className="performance-icon" aria-label="Previous month" title="Previous month" disabled={month <= firstMonth} onClick={() => changeMonth(-1)}><ChevronLeft size={16} /></button>
              <button className="performance-icon" aria-label="Next month" title="Next month" disabled={month >= data.today.slice(0, 7)} onClick={() => changeMonth(1)}><ChevronRight size={16} /></button>
            </div>
          </div>
          <div className="performance-weekdays" aria-hidden="true">{['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map((day) => <span key={day}>{day}</span>)}</div>
          <div className="performance-calendar-grid" aria-label={`${formatMonth(month)} P/L calendar`}>
            {calendarDates(month).map((value) => {
              const day = dayByDate.get(value);
              const profit = Number(day?.profitLoss ?? 0);
              const inMonth = value.startsWith(month);
              const tradeLabel = day?.trades === 1 ? 'trade' : 'trades';
              const alpha = 6 + Math.abs(profit) / maxDayProfit * 16;
              const background = day && inMonth && profit !== 0 ? `color-mix(in srgb, var(--chart-${profit > 0 ? 'positive' : 'negative'}) ${alpha}%, transparent)` : undefined;
              return (
                <button
                  key={value}
                  className={`performance-day ${inMonth ? '' : 'outside-month'} ${inMonth && value === data.today ? 'is-today' : ''}`}
                  disabled={!inMonth || !day || value > data.today}
                  aria-pressed={selectedDate === value}
                  aria-current={inMonth && value === data.today ? 'date' : undefined}
                  aria-label={`${formatDay(value, true)}: ${day && inMonth ? `${formatProfit(profit)}, ${day.trades} settled ${tradeLabel}` : 'no settled trades'}`}
                  title={day && inMonth ? `${formatDay(value, true)}: ${formatProfit(profit)} across ${day.trades} ${tradeLabel}` : `${formatDay(value, true)}: no settled trades`}
                  style={{ backgroundColor: background }}
                  onClick={() => { setSelectedDate(selectedDate === value ? null : value); setRange('month'); }}
                >
                  <span className="day-number">{Number(value.slice(-2))}</span>
                  <span className={`day-profit ${tone(profit)}`}>{inMonth && day ? calendarProfit(profit) : ''}</span>
                </button>
              );
            })}
          </div>
          <div className="performance-day-detail">
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="muted-heading text-xs">{selected ? formatDay(selected.date) : 'Month P/L'} <span className="muted-text">USD</span></span>
              <div className="flex min-w-0 items-center gap-1">
                <strong className={`break-all text-sm tabular-nums ${tone(selected ? Number(selected.profitLoss) : monthStats.net)}`}>{formatProfit(selected ? Number(selected.profitLoss) : monthStats.net)}</strong>
                {selected && <button className="performance-icon" aria-label="Clear selected day" title="Clear selected day" onClick={() => setSelectedDate(null)}><X size={13} /></button>}
              </div>
            </div>
            <div className="muted-text mt-1 text-[11px]">
              {selected ? `${selected.trades} trades | ${selected.profitable} profitable | ${selected.losing} losing | ${selected.flat} flat` : `${monthStats.trades} settled trades | ${monthDays.filter((day) => Number(day.profitLoss) > 0).length} profitable days`}
            </div>
            {selected?.fees !== null && selected?.fees !== undefined && <div className="muted-text mt-1 text-[11px]">Settled fees: {formatProfit(Number(selected.fees), false, false)}</div>}
          </div>
        </div>
      </div>

      <dl className="performance-statistics">
        {metric('Avg / trade', <span className={tone(stats.average ?? 0)}>{stats.average === null ? '--' : formatProfit(stats.average)}</span>)}
        {metric('Profit factor', stats.profitFactor !== null ? stats.profitFactor.toFixed(2) : stats.grossProfit > 0 ? 'No losses' : '--', undefined, 'Net profits from profitable trades divided by net losses from losing trades')}
        {metric('Max drawdown', <span className={stats.maxDrawdown > 0 ? 'money-negative' : ''}>{formatProfit(-stats.maxDrawdown)}</span>, undefined, 'Largest peak-to-trough loss within this range, including intraday trades')}
        {metric('Best day', stats.bestDay ? <span className={tone(Number(stats.bestDay.profitLoss))}>{formatProfit(Number(stats.bestDay.profitLoss))}</span> : '--', stats.bestDay ? formatDay(stats.bestDay.date) : undefined)}
        {metric('Worst day', stats.worstDay ? <span className={tone(Number(stats.worstDay.profitLoss))}>{formatProfit(Number(stats.worstDay.profitLoss))}</span> : '--', stats.worstDay ? formatDay(stats.worstDay.date) : undefined)}
        {data.kind === 'live'
          ? metric('Settled fees', formatProfit(stats.fees ?? 0, false, false), undefined, 'Actual exchange fees for the settled trades in this range')
          : metric('Net ROI', stats.roi === null ? '--' : `${stats.roi.toFixed(2)}%`)}
      </dl>
    </section>
  );
}

export function PerformancePanel({ data }: { data?: PerformanceData }) {
  if (!data) return <section className="performance-section"><h2 className="text-sm font-semibold">Performance</h2><p className="muted-text py-5 text-sm">Performance data unavailable.</p></section>;
  return <PerformanceContent data={data} />;
}
