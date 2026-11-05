import assert from 'node:assert/strict';
import test from 'node:test';
import { loadModule } from './helpers/load-module.mjs';

const { AppLink } = await loadModule('../../src/components/layout/AppLink.tsx');

function browser(context) {
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const previousPopState = Object.getOwnPropertyDescriptor(globalThis, 'PopStateEvent');
  const visits = ['/bots'];
  let index = 0;
  const listeners = [];
  const window = {
    location: new URL('http://localhost:8765/bots'),
    dispatchEvent(event) { listeners.push({ type: event.type, path: this.location.pathname, hash: this.location.hash }); },
    history: {
      pushState(state, title, path) {
        visits.splice(++index, visits.length, path);
        window.location = new URL(path, window.location);
      },
      back() { window.location = new URL(visits[--index], window.location); window.dispatchEvent(new Event('popstate')); },
      forward() { window.location = new URL(visits[++index], window.location); window.dispatchEvent(new Event('popstate')); },
    },
  };
  Object.defineProperty(globalThis, 'window', { configurable: true, value: window });
  Object.defineProperty(globalThis, 'PopStateEvent', { configurable: true, value: Event });
  context.after(() => {
    if (previousWindow) Object.defineProperty(globalThis, 'window', previousWindow);
    else delete globalThis.window;
    if (previousPopState) Object.defineProperty(globalThis, 'PopStateEvent', previousPopState);
    else delete globalThis.PopStateEvent;
  });
  return { window, visits, listeners };
}

const click = overrides => ({ button: 0, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...overrides });

test('internal page links update history without hashes or page reloads', context => {
  const { window, visits, listeners } = browser(context);
  const event = click();
  AppLink({ href: '/info/faq' }).props.onClick(event);
  assert.equal(event.defaultPrevented, true);
  assert.deepEqual(visits, ['/bots', '/info/faq']);
  assert.equal(window.location.hash, '');
  assert.deepEqual(listeners, [{ type: 'popstate', path: '/info/faq', hash: '' }]);
  window.history.back();
  assert.equal(listeners.at(-1).path, '/bots');
  window.history.forward();
  assert.equal(listeners.at(-1).path, '/info/faq');
  AppLink({ href: '/info/faq' }).props.onClick(click());
  assert.equal(visits.length, 2);
});

test('modified clicks, new tabs, downloads, cancelled clicks, and external links keep native behavior', context => {
  const { visits, listeners } = browser(context);
  for (const overrides of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }, { defaultPrevented: true }]) {
    const event = click(overrides);
    AppLink({ href: '/info', onClick: () => {} }).props.onClick(event);
    assert.equal(event.defaultPrevented, !!overrides.defaultPrevented);
  }
  for (const props of [{ href: '/info', target: '_blank' }, { href: '/file.csv', download: '' }, { href: 'https://example.com/info' }, { href: '/info', onClick: event => event.preventDefault() }]) {
    AppLink(props).props.onClick(click());
  }
  assert.deepEqual(visits, ['/bots']);
  assert.deepEqual(listeners, []);
});
