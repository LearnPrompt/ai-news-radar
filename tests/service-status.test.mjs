import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../assets/service-status.js', import.meta.url), 'utf8');

async function render(payload, { script = 'https://news.learnprompt.pro/assets/service-status.js', search = '', fail = false } = {}) {
  const element = () => ({
    children: [], hidden: true, classList: { toggle() {} },
    append(...items) { this.children.push(...items); },
    appendChild(item) { this.children.push(item); },
    replaceChildren() { this.children = []; },
    setAttribute() {},
  });
  const panel = element();
  let requested;
  vm.runInNewContext(source, {
    document: { getElementById: () => panel, createElement: element, currentScript: { src: script } },
    window: { location: { search }, setTimeout, clearTimeout },
    localStorage: { getItem: () => '' }, URL, URLSearchParams, AbortController, Intl, Date,
    fetch: async (url) => {
      requested = url;
      if (fail) throw new Error('offline');
      return { ok: true, json: async () => payload };
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  return { panel, requested };
}

const active = { provider: 'OpenAI', title: 'Test incident', status: 'monitoring', impact: 'minor', url: 'https://status.openai.com/incidents/test' };
const snapshot = (incidents = [active]) => ({ ok: true, generated_at: new Date().toISOString(), incidents });

test('shows active incidents with text and official link', async () => {
  const { panel } = await render(snapshot());
  assert.equal(panel.hidden, false);
  const title = panel.children[1].children[0].children[0].children[1];
  assert.equal(title.textContent, 'Test incident');
  assert.equal(title.href, active.url);
});

test('hides resolved, failed and stale snapshots', async () => {
  for (const payload of [snapshot([]), snapshot([{ ...active, status: 'resolved' }]),
    { ...snapshot(), ok: false }, { ...snapshot(), generated_at: '2000-01-01T00:00:00Z' }]) {
    assert.equal((await render(payload)).panel.hidden, true);
  }
  assert.equal((await render(null, { fail: true })).panel.hidden, true);
});

test('shared script resolves data correctly from either page and accepts an explicit data base', async () => {
  assert.equal((await render(snapshot())).requested, 'https://news.learnprompt.pro/data/service-status.json');
  assert.equal((await render(snapshot(), { search: '?data=https://example.com/demo/data' })).requested,
    'https://example.com/demo/data/service-status.json');
});

test('does not turn nonofficial incident URLs into clickable links', async () => {
  const { panel } = await render(snapshot([{ ...active, url: 'javascript:alert(1)' }]));
  assert.equal(panel.children[1].children[0].children[0].children[1].href, 'https://status.openai.com/');
});
