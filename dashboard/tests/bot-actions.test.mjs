import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { dashboardFixture } from './helpers/fixtures.mjs';
import { loadModule } from './helpers/load-module.mjs';

const { useBotActions } = await loadModule('../../src/hooks/useBotActions.ts');

function actionsHarness(context, approved = true) {
  const previousWindow = globalThis.window;
  const confirm = context.mock.fn(() => approved);
  globalThis.window = { confirm };
  context.after(() => {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  });
  const requests = [];
  context.mock.method(globalThis, 'fetch', async (path, options) => {
    requests.push({ path, body: JSON.parse(options.body) });
    return new Response('{}', { status: 200 });
  });
  const load = context.mock.fn(async () => {});
  let actions;
  function Harness() {
    actions = useBotActions(dashboardFixture().bots, load);
    return null;
  }
  renderToStaticMarkup(React.createElement(Harness));
  return { ...actions, requests, confirm, load };
}

test('declining live-money confirmation submits no command or refresh', async (context) => {
  const harness = actionsHarness(context, false);
  await harness.botAction('btc15_dual_live', 'start', '100.00', '0');
  assert.equal(harness.confirm.mock.calls.length, 1);
  const message = harness.confirm.mock.calls[0].arguments[0];
  assert.match(message, /REAL MONEY/);
  assert.match(message, /\$100\.00 entry cost PER TRADE/);
  assert.match(message, /NO DAILY ORDER CAP/);
  assert.equal(harness.requests.length, 0);
  assert.equal(harness.load.mock.calls.length, 0);
});

test('invalid live sizing is rejected before confirmation or transport', async (context) => {
  const harness = actionsHarness(context);
  for (const budget of ['', '0', '-1', 'NaN', 'Infinity', '1.001']) {
    await harness.botAction('btc15_dual_live', 'start', budget, '30');
  }
  for (const limit of ['-1', '1.5', 'NaN', '9007199254740992']) {
    await harness.botAction('btc15_dual_live', 'start', '1.00', limit);
  }
  assert.equal(harness.requests.length, 0);
  assert.equal(harness.confirm.mock.calls.length, 0);
});

test('approved live start preserves the chosen budget and shared cap', async (context) => {
  const harness = actionsHarness(context);
  await harness.botAction('btc15_dual_live', 'start', '100.00', '30');
  assert.equal(harness.confirm.mock.calls.length, 1);
  assert.deepEqual(harness.requests, [{
    path: '/api/bots/start', body: { botId: 'btc15_dual_live', tradeBudget: '100.00', dailyLiveOrderLimit: '30' },
  }]);
  assert.equal(harness.load.mock.calls.length, 1);
});

test('paper starts and stop commands do not request live-start confirmation', async (context) => {
  const harness = actionsHarness(context);
  await harness.botAction('btc15_dual_paper', 'start', '100.00');
  await harness.botAction('btc15_dual_live', 'stop');
  assert.equal(harness.confirm.mock.calls.length, 0);
  assert.deepEqual(harness.requests, [
    { path: '/api/bots/start', body: { botId: 'btc15_dual_paper', tradeBudget: '100.00' } },
    { path: '/api/bots/stop', body: { botId: 'btc15_dual_live' } },
  ]);
  assert.equal(harness.load.mock.calls.length, 2);
});
