import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { dashboardFixture } from './helpers/fixtures.mjs';
import { loadModule } from './helpers/load-module.mjs';

const { BotWorkspace } = await loadModule('../../src/components/bots/BotWorkspace.tsx');
const { BotControl } = await loadModule('../../src/components/bots/BotControl.tsx');
const { DashboardHeader } = await loadModule('../../src/components/layout/DashboardHeader.tsx');
const { normalizeDashboard } = await loadModule('../../src/lib/dashboard.ts');
const { EntryDirection } = await loadModule('../../src/components/trades/EntryDirection.tsx');
const { PerformanceStats } = await loadModule('../../src/components/performance/PerformanceStats.tsx');
const { summarizeDays } = await loadModule('../../src/lib/performance.ts');
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const noAction = () => { throw new Error('Rendering must not submit bot commands'); };

test('each bot workspace renders its controls, diagnostics, and distinct trade view without requests', (context) => {
  const fetch = context.mock.method(globalThis, 'fetch', noAction);
  const data = dashboardFixture();
  for (const active of ['btc15_paper', 'btc15_dual_paper', 'btc15_direction_paper', 'btc15_live', 'btc15_dual_live', 'scalp_paper', 'shadow']) {
    const html = render(BotWorkspace, { active, data, onAction: noAction });
    assert.match(html, active === 'shadow' ? /Recent Blocked Signals/ : /Bot diagnostics/);
    assert.match(html, /role="region"/);
    if (active.includes('live')) {
      assert.match(html, /Recent Live Orders/);
      assert.match(html, /\$1\.04/);
      assert.match(html, /\+\$16\.51/);
    }
    if (active === 'scalp_paper') assert.match(html, /\$0\.00/);
    if (active.startsWith('btc15_')) assert.match(html, /title="KXBTC15M-26NOV040915-15"/);
  }
  assert.equal(fetch.mock.calls.length, 0);
});

test('missing legacy API fields are normalized without overwriting existing history', () => {
  const original = dashboardFixture();
  const payload = Object.freeze({ paper: original.paper, live: original.live, shadow: original.shadow });
  const normalized = normalizeDashboard(payload);
  assert.equal(normalized.paper, original.paper);
  assert.equal(normalized.live, original.live);
  assert.equal(normalized.shadow, original.shadow);
  assert.equal(normalized.dualPaper.total, 0);
  assert.equal(normalized.directionPaper.total, 0);
  assert.equal(normalized.dualLive.total, 0);
  assert.equal(normalized.scalp.open, 0);
  assert.deepEqual(normalized.bots, []);
  assert.equal(payload.dualPaper, undefined);
});

test('populated newer payloads retain their per-bot data and health', () => {
  const payload = dashboardFixture();
  const normalized = normalizeDashboard(payload);
  for (const key of ['paper', 'dualPaper', 'directionPaper', 'live', 'dualLive', 'scalp', 'bots']) assert.equal(normalized[key], payload[key]);
});

test('terminal-managed bots do not expose a misleading dashboard start button', () => {
  const bot = dashboardFixture().bots[0];
  bot.runtime = { ...bot.runtime, processAlive: true, managed: false, pid: 1234, state: 'healthy' };
  const html = render(BotControl, { bot, onAction: noAction });
  assert.match(html, /Running in terminal/);
  assert.match(html, /Terminal control/);
  assert.doesNotMatch(html, />Start<|>Stop</);
  assert.match(html, /disabled=""/);
});

test('header keeps theme and refresh controls with the same busy states', () => {
  const props = { onToggleTheme: noAction, onUpdateResults: noAction, onStopRefresh: noAction, syncRequestPending: false, stopRequestPending: false };
  const dark = render(DashboardHeader, { ...props, theme: 'dark' });
  const light = render(DashboardHeader, { ...props, theme: 'light', sync: { running: true, stopping: true } });
  assert.match(dark, /Light/);
  assert.match(dark, /Update results/);
  assert.match(light, /Dark/);
  assert.match(light, /Updating\.\.\./);
  assert.match(light, /Stopping\.\.\./);
  assert.match(light, /disabled=""/);
});

test('entry directions distinguish saved evidence, historical inference, and uncertainty', () => {
  const recorded = render(EntryDirection, { row: { entry_direction: 'DOWN', entry_direction_basis: 'RECORDED', entry_direction_match: 'MATCH' } });
  assert.match(recorded, />BTC falling</);
  assert.match(recorded, /Recorded/);
  const inferred = render(EntryDirection, { row: { entry_direction: 'UP', entry_direction_basis: 'INFERRED', entry_direction_match: 'OPPOSITE' } });
  assert.match(inferred, /Inferred/);
  assert.match(inferred, /money-negative/);
  assert.match(inferred, /exact bot source is unverified/);
  assert.match(render(EntryDirection, { row: { entry_direction_basis: 'AMBIGUOUS' } }), /Uncertain/);
  assert.match(render(EntryDirection, { row: {} }), /Unknown/);
  assert.match(render(EntryDirection, { row: { fill_status: 'UNFILLED' } }), /No entry/);
});

test('performance metrics omit the removed drawdown tile', () => {
  const html = render(PerformanceStats, { stats: summarizeDays([]), kind: 'paper' });
  assert.doesNotMatch(html, /Max drawdown/);
  assert.match(html, /Avg \/ trade/);
  assert.match(html, /Net ROI/);
});
