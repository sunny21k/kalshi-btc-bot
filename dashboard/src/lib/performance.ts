import type { ChartPoint, PerformanceData, PerformanceDay, PerformanceRange } from '../types/performance';

const date = (key: string) => new Date(`${key}T00:00:00Z`);
const key = (value: Date) => value.toISOString().slice(0, 10);

export function shiftDay(value: string, offset: number) {
  const result = date(value);
  result.setUTCDate(result.getUTCDate() + offset);
  return key(result);
}

export function shiftMonth(value: string, offset: number) {
  const result = date(`${value}-01`);
  result.setUTCMonth(result.getUTCMonth() + offset);
  return key(result).slice(0, 7);
}

export function calendarDates(month: string) {
  const start = `${month}-01`;
  const first = shiftDay(start, -date(start).getUTCDay());
  return Array.from({ length: 42 }, (_, index) => shiftDay(first, index));
}

export function formatDay(value: string, long = false) {
  return date(value).toLocaleDateString('en-US', {
    timeZone: 'UTC', month: long ? 'long' : 'short', day: 'numeric',
    ...(long ? { weekday: 'short' as const, year: 'numeric' as const } : {}),
  });
}

export function formatMonth(value: string) {
  return date(`${value}-01`).toLocaleDateString('en-US', { timeZone: 'UTC', month: 'long', year: 'numeric' });
}

export function formatProfit(value: number, compact = false, signed = true) {
  if (!compact && value !== 0 && Math.abs(value) < 0.005) return `${value < 0 ? '-' : signed ? '+' : ''}<$0.01`;
  return value.toLocaleString('en-US', {
    style: 'currency', currency: 'USD', signDisplay: signed ? 'exceptZero' : 'auto',
    minimumFractionDigits: compact ? 0 : 2,
    maximumFractionDigits: compact ? 1 : 2,
    ...(compact ? { notation: 'compact' as const } : {}),
  });
}

export function calendarProfit(value: number) {
  if (value !== 0 && Math.abs(value) < 0.01) return value < 0 ? '-<.01' : '+<.01';
  return value.toLocaleString('en-US', {
    signDisplay: 'exceptZero', notation: 'compact',
    maximumFractionDigits: Math.abs(value) < 1 ? 2 : 1,
  });
}

export function rangeBounds(data: PerformanceData, range: PerformanceRange, month: string) {
  const end = range === 'month'
    ? [shiftDay(`${shiftMonth(month, 1)}-01`, -1), data.today].sort()[0]
    : data.today;
  const start = range === '7d' ? shiftDay(end, -6)
    : range === '30d' ? shiftDay(end, -29)
      : range === 'all' ? data.days[0]?.date ?? end : `${month}-01`;
  return { start, end };
}

export function daysInRange(data: PerformanceData, range: PerformanceRange, month: string) {
  const { start, end } = rangeBounds(data, range, month);
  return data.days.filter((day) => day.date >= start && day.date <= end).sort((a, b) => a.date.localeCompare(b.date));
}

export function summarizeDays(days: PerformanceDay[]) {
  let net = 0, trades = 0, profitable = 0, grossProfit = 0, grossLoss = 0;
  let invested = 0, fees = 0, peak = 0, maxDrawdown = 0;
  let costKnown = true, feesKnown = days.length > 0;
  let bestDay: PerformanceDay | null = null, worstDay: PerformanceDay | null = null;
  for (const day of [...days].sort((a, b) => a.date.localeCompare(b.date))) {
    const opening = net;
    maxDrawdown = Math.max(maxDrawdown, peak - (opening + Number(day.trough)), Number(day.drawdown));
    peak = Math.max(peak, opening + Number(day.peak));
    net += Number(day.profitLoss);
    trades += day.trades;
    profitable += day.profitable;
    grossProfit += Number(day.grossProfit);
    grossLoss += Number(day.grossLoss);
    costKnown = costKnown && day.invested !== null;
    feesKnown = feesKnown && day.fees !== null;
    invested += Number(day.invested ?? 0);
    fees += Number(day.fees ?? 0);
    if (!bestDay || Number(day.profitLoss) > Number(bestDay.profitLoss)) bestDay = day;
    if (!worstDay || Number(day.profitLoss) < Number(worstDay.profitLoss)) worstDay = day;
  }
  return {
    net, trades, profitable, grossProfit, grossLoss, invested,
    fees: feesKnown ? fees : null,
    roi: costKnown && invested > 0 ? net / invested * 100 : null,
    average: trades > 0 ? net / trades : null,
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : null,
    maxDrawdown, bestDay, worstDay,
  };
}

export function chartPoints(data: PerformanceData, range: PerformanceRange, month: string): ChartPoint[] {
  const days = daysInRange(data, range, month);
  if (!days.length) return [];
  const { start, end } = rangeBounds(data, range, month);
  const byDate = new Map(days.map((day) => [day.date, day]));
  const span = Math.round((date(end).getTime() - date(start).getTime()) / 86400000);
  // Preserve time spacing without creating huge SVGs for very old imports.
  const dates = span <= 3660
    ? Array.from({ length: span + 1 }, (_, index) => shiftDay(start, index))
    : [...new Set([start, ...days.map((day) => day.date), end])].sort();
  let running = 0;
  return dates.map((value) => {
    const day = byDate.get(value);
    const daily = Number(day?.profitLoss ?? 0);
    running += daily;
    return { date: value, time: date(value).getTime(), daily, cumulative: running, trades: day?.trades ?? 0 };
  });
}

export type PerformanceSummary = ReturnType<typeof summarizeDays>;
