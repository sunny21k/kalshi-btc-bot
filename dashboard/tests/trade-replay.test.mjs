import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadModule } from './helpers/load-module.mjs';

const { sampledCandles, observationAt, quotePath, relativeTime, replayBounds, replayCursorAt, replayTicks } = await loadModule('../../src/lib/tradeReplay.ts');
const { ReplayChart } = await loadModule('../../src/components/trades/ReplayChart.tsx');
const { TradeDetails } = await loadModule('../../src/components/trades/TradeDetails.tsx');
const { fetchTradeReplay } = await loadModule('../../src/api/dashboard.ts');
const point = (time, btcPrice, fields = {}) => ({ time, btcPrice, yesBid: .2, yesAsk: .22, noBid: .78, noAsk: .8, ticker: 'T', ...fields });

test('candles use only observations available at the playback cursor, including partial bars', () => {
  const points = [point(1000, 100), point(3000, 102), point(4000, 99), point(6000, 110)];
  const partial = sampledCandles(points, 5, 0, 10000, 3000);
  assert.deepEqual(partial, [{ time: 0, open: 100, high: 102, low: 100, close: 102, count: 2 }]);
  assert.equal(sampledCandles(points, 5, 0, 10000, 6000).length, 2);
  assert.equal(partial[0].low, 100);
  assert.equal(sampledCandles(points, 7, 0, 10000, 6000).length, 0);
});

test('gaps are not turned into synthetic candles or continuous quote paths', () => {
  const points = [point(1000, 100), point(61000, 101)];
  assert.equal(sampledCandles(points, 15, 0, 120000, 120000).length, 2);
  assert.equal(observationAt(points, 0), null);
  assert.equal(observationAt(points, 5000), points[0]);
  const path = quotePath(points, 'noAsk', 120000, time => time, price => price, 15000);
  assert.equal((path.match(/M/g) || []).length, 2);
  assert.equal((quotePath(points, 'noAsk', 5000, time => time, price => price, 15000).match(/M/g) || []).length, 1);
  assert.equal(relativeTime(-120), '−02:00');
  assert.equal(relativeTime(90), '+01:30');
});

test('charts label sampled candles and order attempts and do not render future BTC prices', () => {
  const data = { startTime: 0, endTime: 240000, entry: { at: 120, side: 'NO', filled: false, entryPrice: .8, anchorLabel: 'Order attempt' },
    points: [point(1000, 100), point(200000, 999999)], targetPrice: null, targetBasis: 'inferred', coverage: { typicalSeconds: 5, gaps: [{ start: 10000, end: 60000 }] } };
  const html = renderToStaticMarkup(React.createElement(ReplayChart, { data, cursorSeconds: -110, interval: 15, onSeek() {} }));
  assert.match(html, /sampled 15s candles/);
  assert.match(html, /Order attempt · unfilled/);
  assert.match(html, /replay-gap/);
  assert.doesNotMatch(html, /sampled open 999999|999,999/);
});

test('opening trade details exposes replay without sending requests or starting a bot', context => {
  const fetch = context.mock.method(globalThis, 'fetch', () => { throw new Error('Details render must be read only'); });
  const html = renderToStaticMarkup(React.createElement(TradeDetails, { botId: 'btc15_dual_live', row: { trade_id: 'live-test', ticker: 'T', side: 'NO' }, onClose() {} }));
  assert.match(html, />Replay<\/button>/);
  assert.equal(fetch.mock.calls.length, 0);
});

test('replay loading uses a bounded GET query with cancellation support', async context => {
  const calls = [];
  const controller = new AbortController();
  context.mock.method(globalThis, 'fetch', async (url, options) => { calls.push({ url, options }); return new Response(JSON.stringify({ status: 'preparing', rows: 100, files: 0, totalFiles: 2 }), { status: 202 }); });
  const result = await fetchTradeReplay('btc15_dual_live', 'live-test', true, controller.signal);
  assert.equal(result.status, 'preparing');
  assert.equal(calls[0].url, '/api/trades/replay?botId=btc15_dual_live&tradeId=live-test&refresh=1&window=entry');
  assert.equal(calls[0].options.signal, controller.signal);
  assert.equal(calls[0].options.method, undefined);
});

test('full-market playback bounds and chart seeking use the whole period rather than ±120 seconds', () => {
  const data = { window: 'market', startTime: Date.parse('2026-11-06T20:45:00Z'), endTime: Date.parse('2026-11-06T21:00:00Z'), entry: { at: Date.parse('2026-11-06T20:55:00Z') / 1000 } };
  assert.deepEqual(replayBounds(data), { min: -600, max: 300 });
  assert.equal(replayCursorAt(data, 0), -600);
  assert.equal(replayCursorAt(data, 1), 300);
  assert.equal(replayCursorAt(data, .5), -150);
  assert.equal(replayCursorAt(data, -1), -600);
  const ticks = replayTicks(data);
  assert.equal(ticks[0].label, '15:45');
  assert.equal(ticks[ticks.length - 1].label, '16:00');
  assert.equal(ticks.length, 6);
});

test('full-market chart keeps the entry marker at its real position and hides future candles', () => {
  const start = Date.parse('2026-11-06T20:45:00Z');
  const data = { window: 'market', startTime: start, endTime: start + 900000,
    entry: { at: (start + 600000) / 1000, side: 'NO', filled: true, entryPrice: .8, anchorLabel: 'Order attempt' },
    points: [point(start + 1000, 100), point(start + 850000, 999999)], targetPrice: null, targetBasis: 'inferred', coverage: { typicalSeconds: 5, gaps: [] } };
  const html = renderToStaticMarkup(React.createElement(ReplayChart, { data, cursorSeconds: -500, interval: 15, onSeek() {} }));
  assert.match(html, /full 15-minute market/);
  assert.match(html, /x1="446" x2="446"[^>]*replay-entry-line/);
  assert.match(html, />15:45</);
  assert.match(html, />16:00</);
  assert.doesNotMatch(html, /sampled open 999999/);
});

test('the market window is sent to the replay endpoint', async context => {
  let requested;
  context.mock.method(globalThis, 'fetch', async url => { requested = url; return new Response(JSON.stringify({ status: 'preparing' })); });
  await fetchTradeReplay('btc15_dual_live', 'live-test', false, undefined, 'market');
  assert.match(requested, /window=market/);
});
