import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadModule } from './helpers/load-module.mjs';
import { dashboardFixture } from './helpers/fixtures.mjs';

const { BotDetails } = await loadModule('../../src/components/bots/BotDetails.tsx');
const { BotControl } = await loadModule('../../src/components/bots/BotControl.tsx');
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const profile = source => ({ schemaVersion: 1, botId: 'btc15_dual_live', mode: 'live', fingerprint: 'test', source,
  sections: [{ title: 'Entry rules', items: [{ label: '5-minute rule', detail: '80¢–92¢; BTC at least $50.00 from target.' }] }] });

test('rule details are collapsed and expose entry rules without API requests', context => {
  const fetch = context.mock.method(globalThis, 'fetch', () => { throw new Error('Details must not send commands'); });
  const html = render(BotDetails, { rules: profile('current'), name: 'YES/NO Live' });
  assert.match(html, /<details class="bot-details"/);
  assert.doesNotMatch(html, /<details[^>]*\bopen/);
  assert.match(html, /<summary>/);
  assert.match(html, /Bot Details/);
  assert.match(html, /80¢–92¢/);
  assert.match(html, /Current code rules/);
  assert.equal(fetch.mock.calls.length, 0);
});

test('all bot controls include their own details affordance', () => {
  for (const bot of dashboardFixture().bots) {
    const html = render(BotControl, { bot, onAction() { throw new Error('Opening details must not control a bot'); } });
    assert.match(html, /Bot Details/);
    assert.ok(html.includes(`aria-label="${bot.name} trading rules"`));
  }
});

test('running snapshots and unreported old processes are clearly distinguished', () => {
  const running = render(BotDetails, { rules: { ...profile('running'), matchesCurrent: false }, name: 'Live' });
  assert.match(running, /Running bot snapshot/);
  assert.match(running, /current launch configuration differs/);
  const legacy = render(BotDetails, { rules: { ...profile('current'), runningWithoutSnapshot: true }, name: 'Live' });
  assert.match(legacy, /has not reported a rule snapshot/);
  assert.doesNotMatch(legacy, /Running bot snapshot/);
  assert.match(render(BotDetails, { name: 'Live' }), /Restart the dashboard server/);
});
