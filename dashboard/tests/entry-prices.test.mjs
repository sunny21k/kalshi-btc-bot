import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadModule } from './helpers/load-module.mjs';
import { dashboardFixture } from './helpers/fixtures.mjs';

const { entryRangeFromPercent, entryPriceDraft, validateEntryPriceRange } = await loadModule('../../src/lib/entryPrices.ts');
const { EntryPriceSettings } = await loadModule('../../src/components/bots/EntryPriceSettings.tsx');
const { BotControl } = await loadModule('../../src/components/bots/BotControl.tsx');
const { BotSettings } = await loadModule('../../src/components/bots/BotSettings.tsx');

test('percent inputs convert to probability units without losing sub-cent precision', () => {
  assert.deepEqual(entryRangeFromPercent({ useDefaults: false, min: '75.25', max: '90' }), { min: '0.7525', max: '0.9000' });
  assert.deepEqual(entryRangeFromPercent({ useDefaults: false, min: '.01', max: '99.99' }), { min: '0.0001', max: '0.9999' });
  assert.equal(entryRangeFromPercent({ useDefaults: true, min: '', max: '' }), null);
  const bot = { entryPriceRange: { min: '.7525', max: '.9' } };
  assert.deepEqual(entryPriceDraft(bot), { useDefaults: false, min: '75.25', max: '90' });
});

test('bad bounds are rejected before a bot command can be built', () => {
  for (const min of ['', '0', '100', '-1', 'NaN', 'Infinity', '75.001', '0x10']) {
    assert.throws(() => entryRangeFromPercent({ useDefaults: false, min, max: '90' }));
  }
  assert.throws(() => entryRangeFromPercent({ useDefaults: false, min: '90', max: '75' }));
  for (const range of [{ min: 'NaN', max: '.9' }, { min: '.9', max: '.75' }, { min: '.75001', max: '.9' }, { min: '0x0.8', max: '.9' }]) {
    assert.throws(() => validateEntryPriceRange(range));
  }
  assert.doesNotThrow(() => validateEntryPriceRange({ min: '.75', max: '.9' }));
});

test('each bot opens settings separately and edits describe application on the next start', () => {
  for (const bot of dashboardFixture().bots) {
    const html = renderToStaticMarkup(React.createElement(BotControl, { bot, onAction() { throw new Error('Rendering must not launch a bot'); } }));
    assert.match(html, /Settings<\/button>/);
    assert.doesNotMatch(html, /<input/);
    const popup = renderToStaticMarkup(React.createElement(BotSettings, { bot: { ...bot, running: true }, onClose() {} }));
    assert.match(popup, /Save settings/);
    assert.match(popup, /Add rule/);
    assert.match(popup, /running bot keeps its current rules/);
    const editor = renderToStaticMarkup(React.createElement(EntryPriceSettings, {
      bot, value: { useDefaults: false, min: '75', max: '90' }, disabled: true, onChange() {},
    }));
    assert.match(editor, /<fieldset[^>]*disabled=""/);
    assert.match(editor, /Minimum \(%\)/);
    assert.match(editor, /Maximum \(%\)/);
    assert.match(editor, /Stop the bot to edit/);
  }
});
