import assert from 'node:assert/strict';
import test from 'node:test';
import { loadModule } from './helpers/load-module.mjs';

const api = await loadModule('../../src/api/dashboard.ts');

function fakeFetch(context, payload = {}, status = 200) {
  const calls = [];
  context.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push({ path, options });
    return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });
  });
  return calls;
}

test('dashboard and result status polling use read-only requests', async (context) => {
  const calls = fakeFetch(context, { running: true });
  assert.deepEqual(await api.fetchDashboardStats(), { running: true });
  assert.deepEqual(await api.fetchResultSync(), { running: true });
  assert.deepEqual(calls, [
    { path: '/api/stats', options: undefined },
    { path: '/api/results/status', options: undefined },
  ]);
});

test('result refresh and cancellation keep their own endpoints and empty bodies', async (context) => {
  const calls = fakeFetch(context, { resultSync: { running: true } });
  await api.startResultSync();
  await api.cancelResultSync();
  assert.deepEqual(calls.map(({ path }) => path), ['/api/results/refresh', '/api/results/cancel']);
  for (const { options } of calls) {
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(options.body), {});
  }
});

test('explicit trade budgets and disabled daily caps survive request serialization', async (context) => {
  const calls = fakeFetch(context);
  await api.sendBotAction('btc15_dual_live', 'start', '100.00', '0');
  assert.equal(calls[0].path, '/api/bots/start');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    botId: 'btc15_dual_live', tradeBudget: '100.00', dailyLiveOrderLimit: '0',
  });
});

test('stop commands omit sizing fields and unspecified start settings remain unspecified', async (context) => {
  const calls = fakeFetch(context);
  await api.sendBotAction('btc15_dual_live', 'stop', '100.00', '30');
  await api.sendBotAction('scalp_paper', 'start');
  assert.equal(calls[0].path, '/api/bots/stop');
  assert.deepEqual(JSON.parse(calls[0].options.body), { botId: 'btc15_dual_live' });
  assert.deepEqual(JSON.parse(calls[1].options.body), { botId: 'scalp_paper' });
});

test('rejected commands expose the server explanation and are never retried', async (context) => {
  const calls = fakeFetch(context, { message: 'Stop the bot before changing its budget' }, 409);
  await assert.rejects(api.sendBotAction('btc15_live', 'start', '100'), /Stop the bot before changing its budget/);
  assert.equal(calls.length, 1);
});

test('API errors use the supplied explanation or operation fallback', async (context) => {
  fakeFetch(context, { error: 'Refresh already stopped' }, 400);
  await assert.rejects(api.cancelResultSync(), /Refresh already stopped/);
  fakeFetch(context, {}, 503);
  await assert.rejects(api.fetchResultSync(), /Could not check results update/);
});
