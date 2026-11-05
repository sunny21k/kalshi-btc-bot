import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { calendarDates, calendarProfit, formatDay, formatMonth, formatProfit, summarizeDays } from '../../lib/performance';
import type { PerformanceData } from '../../types/performance';
import { profitTone } from '../../utils/format';

type Props = {
  data: PerformanceData;
  month: string;
  selectedDate: string | null;
  onMonthChange: (offset: number) => void;
  onSelectDate: (date: string) => void;
  onClearDate: () => void;
};

export function PerformanceCalendar({ data, month, selectedDate, onMonthChange, onSelectDate, onClearDate }: Props) {
  const monthDays = data.days.filter((day) => day.date.startsWith(month));
  const monthStats = summarizeDays(monthDays);
  const dayByDate = new Map(data.days.map((day) => [day.date, day]));
  const selected = selectedDate ? dayByDate.get(selectedDate) : undefined;
  const firstMonth = data.days[0]?.date.slice(0, 7) ?? data.today.slice(0, 7);
  const maxDayProfit = Math.max(0.0001, ...monthDays.map((day) => Math.abs(Number(day.profitLoss))));
  return (
    <div className="performance-calendar">
      <div className="performance-calendar-heading">
        <h3>{formatMonth(month)}</h3>
        <div className="flex gap-1">
          <button className="performance-icon" aria-label="Previous month" title="Previous month" disabled={month <= firstMonth} onClick={() => onMonthChange(-1)}><ChevronLeft size={16} /></button>
          <button className="performance-icon" aria-label="Next month" title="Next month" disabled={month >= data.today.slice(0, 7)} onClick={() => onMonthChange(1)}><ChevronRight size={16} /></button>
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
              onClick={() => onSelectDate(value)}
            >
              <span className="day-number">{Number(value.slice(-2))}</span>
              <span className={`day-profit ${profitTone(profit)}`}>{inMonth && day ? calendarProfit(profit) : ''}</span>
            </button>
          );
        })}
      </div>
      <div className="performance-day-detail">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <span className="muted-heading text-xs">{selected ? formatDay(selected.date) : 'Month P/L'} <span className="muted-text">USD</span></span>
          <div className="flex min-w-0 items-center gap-1">
            <strong className={`break-all text-sm tabular-nums ${profitTone(selected ? Number(selected.profitLoss) : monthStats.net)}`}>{formatProfit(selected ? Number(selected.profitLoss) : monthStats.net)}</strong>
            {selected && <button className="performance-icon" aria-label="Clear selected day" title="Clear selected day" onClick={onClearDate}><X size={13} /></button>}
          </div>
        </div>
        <div className="muted-text mt-1 text-[11px]">
          {selected ? `${selected.trades} trades | ${selected.profitable} profitable | ${selected.losing} losing | ${selected.flat} flat` : `${monthStats.trades} settled trades | ${monthDays.filter((day) => Number(day.profitLoss) > 0).length} profitable days`}
        </div>
        {selected?.fees !== null && selected?.fees !== undefined && <div className="muted-text mt-1 text-[11px]">Settled fees: {formatProfit(Number(selected.fees), false, false)}</div>}
      </div>
    </div>
  );
}
