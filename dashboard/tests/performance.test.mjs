import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import test from 'node:test';
import { transform } from 'esbuild';

const source = await fs.readFile(new URL('../src/lib/performance.ts', import.meta.url), 'utf8');
const compiled = await transform(source, { loader: 'ts', format: 'cjs' });
const module = { exports: {} };
new Function('module', 'exports', compiled.code)(module, module.exports);
const { calendarDates, shiftDay, shiftMonth, daysInRange, summarizeDays, chartPoints, formatProfit, calendarProfit } = module.exports;

function day(date, profits, overrides = {}) {
  let net = 0, peak = 0, trough = 0, drawdown = 0;
  for (const profit of profits) {
    net += profit;
    peak = Math.max(peak, net);
    trough = Math.min(trough, net);
    drawdown = Math.max(drawdown, peak - net);
  }
  return {
    date, profitLoss: String(net), cumulative: '9999', trades: profits.length,
    profitable: profits.filter((value) => value > 0).length,
    losing: profits.filter((value) => value < 0).length,
    flat: profits.filter((value) => value === 0).length,
    grossProfit: String(profits.filter((value) => value > 0).reduce((a, b) => a + b, 0)),
    grossLoss: String(-profits.filter((value) => value < 0).reduce((a, b) => a + b, 0)),
    invested: String(profits.length * 100), fees: null,
    peak: String(peak), trough: String(trough), drawdown: String(drawdown), ...overrides,
  };
}
const data = (days) => ({ days, today: '2026-11-04' });

test('calendar has 42 stable UTC date cells and supports leap years', () => {
  const dates = calendarDates('2024-02');
  assert.equal(dates.length, 42);
  assert.equal(dates[0], '2024-01-28');
  assert.ok(dates.includes('2024-02-29'));
  assert.equal(dates.at(-1), '2024-03-09');
});

test('civil date helpers cross DST, year, and month boundaries', () => {
  assert.equal(shiftDay('2026-11-01', 1), '2026-11-02');
  assert.equal(shiftDay('2026-11-01', -1), '2026-10-31');
  assert.equal(shiftDay('2024-03-01', -1), '2024-02-29');
  assert.equal(shiftMonth('2026-12', 1), '2027-01');
  assert.equal(shiftMonth('2026-01', -1), '2025-12');
});

test('7D includes seven calendar dates, not earlier history or future rows', () => {
  const result = daysInRange(data([day('2026-10-28', [1]), day('2026-10-29', [2]), day('2026-11-04', [3]), day('2026-11-05', [4])]), '7d', '2026-11');
  assert.deepEqual(result.map((item) => item.date), ['2026-10-29', '2026-11-04']);
});

test('month range does not leak another month into the calendar totals', () => {
  const result = daysInRange(data([day('2026-10-31', [100]), day('2026-11-01', [2])]), 'month', '2026-11');
  assert.equal(summarizeDays(result).net, 2);
});

test('cumulative chart rebases within the selected range and fills inactive days', () => {
  const points = chartPoints(data([day('2026-11-01', [10]), day('2026-11-03', [-3])]), 'month', '2026-11');
  assert.deepEqual(points.map((point) => point.cumulative), [10, 10, 7, 7]);
  assert.deepEqual(points.map((point) => point.daily), [10, 0, -3, 0]);
  assert.equal(points[1].trades, 0);
});

test('drawdown includes intraday paths and losses from prior daily peaks', () => {
  const stats = summarizeDays([day('2026-11-02', [-10, 20, -70]), day('2026-11-01', [100, -20])]);
  assert.equal(stats.net, 20);
  assert.equal(stats.maxDrawdown, 80);
  assert.equal(stats.trades, 5);
  assert.equal(stats.bestDay.date, '2026-11-01');
  assert.equal(stats.worstDay.date, '2026-11-02');
});

test('positive-net days can still contain substantial intraday drawdown', () => {
  const stats = summarizeDays([day('2026-11-01', [100, -90, 20])]);
  assert.equal(stats.net, 30);
  assert.equal(stats.maxDrawdown, 90);
});

test('fees are reported but never subtracted a second time', () => {
  const stats = summarizeDays([day('2026-11-01', [16.5057], { fees: '1.0443', invested: '99.45' })]);
  assert.equal(stats.net, 16.5057);
  assert.equal(stats.fees, 1.0443);
  assert.equal(stats.average, 16.5057);
});

test('unknown cost leaves ROI unknown and paper fees are not invented', () => {
  const stats = summarizeDays([day('2026-11-01', [5], { invested: null })]);
  assert.equal(stats.net, 5);
  assert.equal(stats.roi, null);
  assert.equal(stats.fees, null);
});

test('empty ranges have no fabricated average, ratio, or chart', () => {
  const stats = summarizeDays([]);
  assert.equal(stats.average, null);
  assert.equal(stats.profitFactor, null);
  assert.equal(stats.roi, null);
  assert.deepEqual(chartPoints(data([]), 'all', '2026-11'), []);
});

test('tiny scalp returns are not rounded into apparently flat calendar days', () => {
  assert.equal(calendarProfit(0.002), '+<.01');
  assert.equal(calendarProfit(-0.002), '-<.01');
  assert.equal(formatProfit(0.002), '+<$0.01');
});
