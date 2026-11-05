import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadModule } from './helpers/load-module.mjs';

const { readAppLocation, INFO_SECTIONS } = await loadModule('../../src/lib/navigation.ts');
const { filterQuestions } = await loadModule('../../src/lib/help.ts');
const { FAQ_QUESTIONS } = await loadModule('../../src/content/help.ts');
const { InfoPage } = await loadModule('../../src/components/info/InfoPage.tsx');
const { DashboardHeader } = await loadModule('../../src/components/layout/DashboardHeader.tsx');
const { DashboardFooter } = await loadModule('../../src/components/layout/DashboardFooter.tsx');
const { App } = await loadModule('../../src/App.tsx');
const { APP_VERSION } = await loadModule('../../src/lib/releases.ts');
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const noAction = () => { throw new Error('Help must not send bot commands'); };

test('navigation handles direct help links and safely defaults unknown routes', () => {
  for (const path of ['/', '/bots', '/unknown']) assert.deepEqual(readAppLocation(path), { page: 'bots', section: 'overview' });
  for (const section of INFO_SECTIONS) assert.deepEqual(readAppLocation(`/info/${section.id}`), { page: 'info', section: section.id });
  assert.deepEqual(readAppLocation('/info'), { page: 'info', section: 'overview' });
  assert.deepEqual(readAppLocation('/info/faq/'), { page: 'info', section: 'faq' });
  assert.deepEqual(readAppLocation('/info/missing'), { page: 'info', section: 'overview' });
  assert.deepEqual(readAppLocation('/info/ideas'), { page: 'info', section: 'overview' });
});

test('FAQ search matches all terms across category, question, and answer without changing source', () => {
  const before = JSON.stringify(FAQ_QUESTIONS);
  assert.equal(filterQuestions(FAQ_QUESTIONS, '   ').length, FAQ_QUESTIONS.length);
  assert.deepEqual(filterQuestions(FAQ_QUESTIONS, ' ORDERS immediate-or-cancel ').map(item => item.id), ['unfilled']);
  assert.ok(filterQuestions(FAQ_QUESTIONS, 'dollars 80').some(item => item.id === 'budget'));
  assert.deepEqual(filterQuestions(FAQ_QUESTIONS, 'nonexistent question xyz'), []);
  assert.equal(JSON.stringify(FAQ_QUESTIONS), before);
});

test('help renders guide, searchable FAQ, and release history without future ideas or requests', context => {
  const fetch = context.mock.method(globalThis, 'fetch', noAction);
  const html = render(InfoPage, { section: 'faq' });
  assert.match(html, /id="info\/faq"/);
  assert.match(html, /<a(?=[^>]*href="\/info\/faq")(?=[^>]*aria-current="location")[^>]*>/);
  assert.match(html, /aria-label="Search help questions"/);
  assert.equal((html.match(/class="faq-item"/g) || []).length, FAQ_QUESTIONS.length);
  assert.match(html, /Bot controls and trading insights/);
  assert.ok(html.includes(APP_VERSION));
  assert.doesNotMatch(html, />Proposed<|id="info\/ideas"|href="\/info\/ideas"|href="#/);
  assert.match(html, /class="info-eyebrow">Product guide<\/div>/);
  assert.doesNotMatch(html, /<button[^>]*>Start<|<form/);
  assert.equal(fetch.mock.calls.length, 0);
});

test('version stays in the footer while the header keeps page, theme, and refresh controls', () => {
  const props = { theme: 'dark', onToggleTheme: noAction, onUpdateResults: noAction, onStopRefresh: noAction, syncRequestPending: false, stopRequestPending: false };
  const help = render(DashboardHeader, { ...props, activePage: 'info', dashboardReady: false });
  assert.match(help, /href="\/info"/);
  assert.match(help, /aria-current="page"/);
  assert.ok(!help.includes(APP_VERSION));
  assert.doesNotMatch(help, /href="#/);
  const footer = render(DashboardFooter, { updated: '', showUpdates: false });
  assert.match(footer, /href="\/info\/updates"/);
  assert.ok(footer.includes(APP_VERSION));
  assert.match(help, />Light</);
  assert.doesNotMatch(help, /Update results/);
  const running = render(DashboardHeader, { ...props, activePage: 'info', sync: { running: true } });
  assert.match(running, /Updating\.\.\./);
  assert.match(running, /Stop refresh/);
  const loading = render(DashboardHeader, { ...props, dashboardReady: false });
  assert.match(loading, /disabled=""[^>]*title="Update fills/);
});

test('direct help navigation works before dashboard data loads and does not trigger API commands', context => {
  const fetch = context.mock.method(globalThis, 'fetch', noAction);
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { pathname: '/info/updates' } } });
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => 'dark' } });
  try {
    const html = render(App);
    assert.match(html, /Get to know Kalshi BTC/);
    assert.match(html, /id="info\/updates"/);
    assert.doesNotMatch(html, /Connecting to the dashboard|Loading dashboard/);
    assert.equal(fetch.mock.calls.length, 0);
  } finally {
    if (previousWindow) Object.defineProperty(globalThis, 'window', previousWindow);
    else delete globalThis.window;
    if (previousStorage) Object.defineProperty(globalThis, 'localStorage', previousStorage);
    else delete globalThis.localStorage;
  }
});
