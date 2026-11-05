import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadModule } from './helpers/load-module.mjs';

const { entryMovement } = await loadModule('../../src/lib/entryMovement.ts');
const { TradeDetails } = await loadModule('../../src/components/trades/TradeDetails.tsx');
const { RecentTrades } = await loadModule('../../src/components/trades/RecentTrades.tsx');
const { tableMoney } = await loadModule('../../src/utils/format.ts');
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));

test('currency displays two decimals without changing the saved amount', () => {
  const value = '100.4364';
  assert.equal(tableMoney(value), '$100.44');
  assert.equal(value, '100.4364');
  assert.equal(tableMoney('-16.5057', true), '-$16.51');
  assert.equal(tableMoney('1.0443'), '$1.04');
  assert.equal(tableMoney(''), '--');
});

test('BTC movement is independent of the bought contract and final result', () => {
  const row = { side: 'NO', actual_result: 'NO', entry_direction: 'UP', entry_direction_basis: 'INFERRED', entry_btc_price: '101', entry_btc_change_pct: '1' };
  const movement = entryMovement(row);
  assert.equal(movement.current, 101);
  assert.equal(movement.previous, 100);
  assert.equal(movement.change, 1);
  assert.equal(movement.direction, 'UP');
  assert.equal(movement.matches, false);
  const html = render(TradeDetails, { row, live: true, onClose() {} });
  assert.match(html, /BTC appears to have been rising/);
  assert.match(html, /Opposite to NO/);
  assert.match(html, /Inferred previous BTC/);
  assert.match(html, /exact exchange fill time was not recorded/);
  assert.match(html, /role="dialog"/);
  assert.doesNotMatch(html, /aria-modal="true"/);
  assert.match(html, /aria-label="Close trade details"/);
});

test('recorded windows show actual prices while absent evidence stays unknown', () => {
  const row = { side: 'NO', entry_direction: 'DOWN', entry_direction_basis: 'RECORDED', entry_btc_price: '940', entry_btc_change_usd: '-2', entry_window_prices: '[946,944,942,940]' };
  const movement = entryMovement(row);
  assert.deepEqual(movement.prices, [946, 944, 942, 940]);
  assert.equal(movement.previous, 942);
  assert.equal(movement.matches, true);
  const html = render(TradeDetails, { row, onClose() {} });
  assert.match(html, /BTC was falling/);
  assert.match(html, /Saved BTC prices/);
  assert.match(html, /\$942\.00/);
  const unknown = entryMovement({ side: 'YES', prediction: 'UP', actual_result: 'YES', entry_window_prices: 'invalid' });
  assert.equal(unknown.direction, 'UNKNOWN');
  assert.equal(unknown.current, null);
  assert.equal(unknown.previous, null);
  assert.deepEqual(unknown.prices, []);
});

test('trade IDs expose a keyboard-accessible detail control without submitting commands', context => {
  const fetch = context.mock.method(globalThis, 'fetch', () => { throw new Error('Viewing details must be read-only'); });
  const html = render(RecentTrades, { title: 'Trades', rows: [{ trade_id: 'live-12345678', ticker: 'T', side: 'NO', entry_price: '0.80' }] });
  assert.match(html, /aria-label="View trade 12345678 details"/);
  assert.match(html, /trade-row-clickable/);
  assert.equal(fetch.mock.calls.length, 0);
});
