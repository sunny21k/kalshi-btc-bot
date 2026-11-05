import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadModule } from './helpers/load-module.mjs';
import { botPreferences, dashboardFixture } from './helpers/fixtures.mjs';

const { settingsDraft, serializeSettings, newRule, reorderRule } = await loadModule('../../src/lib/botSettings.ts');
const { saveBotSettings, sendBotAction } = await loadModule('../../src/api/dashboard.ts');
const { BotSettings } = await loadModule('../../src/components/bots/BotSettings.tsx');

test('rule additions, edits, deletions and ordering survive settings serialization', () => {
  const original = botPreferences('btc15_dual_live');
  const draft = settingsDraft(original);
  draft.rules[0].maxMinutesLeft = '3'; draft.rules[0].minBtcDistance = '25';
  draft.rules[0].minPercent = '75.25'; draft.rules[0].maxPercent = '90';
  draft.rules.push(newRule('btc15_dual_live', 'test-rule'));
  draft.rules = reorderRule(draft.rules, 2, -1);
  const result = serializeSettings(draft, original);
  assert.equal(result.entryRules[0].maxMinutesLeft, '3');
  assert.equal(result.entryRules[0].minBtcDistance, '25');
  assert.deepEqual(result.entryRules[0].priceRange, { min: '0.7525', max: '0.9000' });
  assert.equal(result.entryRules[1].id, 'test-rule');
  assert.equal(original.entryRules[0].maxMinutesLeft, '5');
  draft.rules = [];
  assert.deepEqual(serializeSettings(draft, original).entryRules, []);
});

test('invalid rule values and duplicate identities fail before saving', () => {
  const original = botPreferences('btc15_dual_live');
  for (const [key, value] of [['maxMinutesLeft', '16'], ['maxMinutesLeft', '0'], ['minBtcDistance', '-1'], ['minPercent', '95'], ['name', '']]) {
    const draft = settingsDraft(original); draft.rules[0][key] = value;
    assert.throws(() => serializeSettings(draft, original));
  }
  const draft = settingsDraft(original); draft.rules.push({ ...draft.rules[0] });
  assert.throws(() => serializeSettings(draft, original), /unique/);
});

test('settings save uses only the settings endpoint and start carries a reviewed fingerprint', async context => {
  const calls = [];
  context.mock.method(globalThis, 'fetch', async (url, options) => { calls.push({ url, body: JSON.parse(options.body) }); return new Response(JSON.stringify({ settings: botPreferences('btc15_dual_live') })); });
  await saveBotSettings('btc15_dual_live', botPreferences('btc15_dual_live'));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/bots/settings');
  await sendBotAction('btc15_dual_live', 'start', '100', '30', null, 'reviewed-settings');
  assert.equal(calls[1].body.expectedSettingsFingerprint, 'reviewed-settings');
});

test('popup supports rule editing for 15m bots and optional candle-entry filters for scalp', context => {
  const fetch = context.mock.method(globalThis, 'fetch', () => { throw new Error('Rendering cannot save or start'); });
  for (const bot of dashboardFixture().bots) {
    const html = renderToStaticMarkup(React.createElement(BotSettings, { bot, onClose() {} }));
    assert.match(html, /role="dialog"/);
    assert.match(html, /Restore defaults/);
    assert.match(html, /Save settings/);
    if (bot.id === 'scalp_paper') assert.match(html, /Extra entry filters/);
    else { assert.match(html, /Minutes left · at most/); assert.match(html, /BTC distance \(\$\) · at least/); }
  }
  assert.equal(fetch.mock.calls.length, 0);
});
