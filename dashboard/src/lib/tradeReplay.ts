import type { ReplayData, ReplayPoint } from '../types/replay';

type ReplayPeriod = Pick<ReplayData, 'startTime' | 'endTime' | 'entry'>;

export function replayBounds(data: ReplayPeriod) {
  return { min: (data.startTime - data.entry.at * 1000) / 1000, max: (data.endTime - data.entry.at * 1000) / 1000 };
}

export function replayCursorAt(data: ReplayPeriod, fraction: number): number {
  const bounds = replayBounds(data);
  return bounds.min + Math.max(0, Math.min(1, fraction)) * (bounds.max - bounds.min);
}

export function replayTicks(data: ReplayPeriod & { window?: string }): Array<{ time: number; label: string }> {
  const full = data.window === 'market';
  const count = full ? 5 : 4;
  const clock = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  return Array.from({ length: count + 1 }, (_, index) => {
    const time = data.startTime + (data.endTime - data.startTime) * index / count;
    const seconds = (time - data.entry.at * 1000) / 1000;
    return { time, label: full ? clock.format(time) : Math.abs(seconds) < .01 ? 'Entry' : relativeTime(seconds) };
  });
}

export type SampledCandle = { time: number; open: number; high: number; low: number; close: number; count: number };

export function sampledCandles(points: ReplayPoint[], intervalSeconds: number, start: number, end: number, cursor: number): SampledCandle[] {
  if (![5, 15, 60].includes(intervalSeconds)) return [];
  const candles = new Map<number, SampledCandle>();
  for (const point of [...points].sort((a, b) => a.time - b.time)) {
    if (point.time < start || point.time > end || point.time > cursor || !Number.isFinite(point.btcPrice) || point.btcPrice <= 0) continue;
    const time = Math.floor(point.time / (intervalSeconds * 1000)) * intervalSeconds * 1000;
    const candle = candles.get(time);
    if (candle) { candle.high = Math.max(candle.high, point.btcPrice); candle.low = Math.min(candle.low, point.btcPrice); candle.close = point.btcPrice; candle.count++; }
    else candles.set(time, { time, open: point.btcPrice, high: point.btcPrice, low: point.btcPrice, close: point.btcPrice, count: 1 });
  }
  return [...candles.values()];
}

export function observationAt(points: ReplayPoint[], cursor: number): ReplayPoint | null {
  let latest: ReplayPoint | null = null;
  for (const point of points) if (point.time <= cursor && (!latest || point.time >= latest.time)) latest = point;
  return latest;
}

export function relativeTime(seconds: number): string {
  const whole = Math.round(Math.abs(seconds));
  return `${seconds < 0 ? '−' : '+'}${String(Math.floor(whole / 60)).padStart(2, '0')}:${String(whole % 60).padStart(2, '0')}`;
}

export function quotePath(points: ReplayPoint[], field: 'yesBid' | 'yesAsk' | 'noBid' | 'noAsk', cursor: number,
  x: (time: number) => number, y: (price: number) => number, maxGapMs: number): string {
  let result = '', previous: number | null = null;
  for (const point of points) {
    if (point.time > cursor) break;
    const price = point[field];
    if (price === null || !Number.isFinite(price)) { previous = null; continue; }
    result += `${previous === null || point.time - previous > maxGapMs ? 'M' : 'L'}${x(point.time).toFixed(2)},${y(price).toFixed(2)} `;
    previous = point.time;
  }
  return result.trim();
}
