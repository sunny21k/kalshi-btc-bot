import React from 'react';
import { chartPoints, daysInRange, rangeBounds, shiftMonth, summarizeDays } from '../../lib/performance';
import type { PerformanceData, PerformanceRange } from '../../types/performance';
import { PerformanceCalendar } from './PerformanceCalendar';
import { PerformanceChart } from './PerformanceChart';
import { PerformanceStats } from './PerformanceStats';

const ranges: Array<{ value: PerformanceRange; label: string }> = [
  { value: 'month', label: 'Month' }, { value: '7d', label: '7D' },
  { value: '30d', label: '30D' }, { value: 'all', label: 'All' },
];

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
        <PerformanceChart
          points={points} mode={mode} onModeChange={setMode} bounds={bounds} stats={stats}
          selectedDate={selectedDate} pending={data.pending} excluded={data.excluded}
        />
        <PerformanceCalendar
          data={data} month={month} selectedDate={selectedDate} onMonthChange={changeMonth}
          onSelectDate={(value) => { setSelectedDate(selectedDate === value ? null : value); setRange('month'); }}
          onClearDate={() => setSelectedDate(null)}
        />
      </div>
      <PerformanceStats stats={stats} kind={data.kind} />
    </section>
  );
}

export function PerformancePanel({ data }: { data?: PerformanceData }) {
  if (!data) return <section className="performance-section"><h2 className="text-sm font-semibold">Performance</h2><p className="muted-text py-5 text-sm">Performance data unavailable.</p></section>;
  return <PerformanceContent data={data} />;
}
