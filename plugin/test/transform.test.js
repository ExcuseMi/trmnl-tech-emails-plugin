// node --test plugin/test/transform.test.js ; TRANSFORM=path runs the tests against another transform (used to see them fail)
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const file = process.env.TRANSFORM || path.join(__dirname, '..', 'src', 'transform.js');
const run = new Function(fs.readFileSync(file, 'utf8') + '\nreturn run;')();
const realNow = Date.now;
const at = (iso) => { const t = typeof iso === "number" ? iso : Date.parse(iso); Date.now = () => t; };
test.afterEach(() => { Date.now = realNow; });

const rec = (n, date = '2012-02-27') => ({
  from: 'Person ' + n, to: ['A'], cc: [], date, subject: 'Subject ' + n, excerpt: 'Body ' + n + '.', context: 'ctx', company: [], people: [],
  source: { title: 'Src', url: 'https://x', locator: 'p. 1' }
});
const list = (n) => Array.from({ length: n }, (_, i) => rec(i, '20' + String(10 + i).padStart(2, '0') + '-03-0' + (1 + (i % 9))));
const cfg = (mode) => ({ plugin_settings: { custom_fields_values: { mode } } });
const input = (data, mode, state) => ({ data, trmnl: { ...cfg(mode), state } });

test('newest: the latest date wins, a year-only date counts as its year end', () => {
  const l = [rec(1, '2015-06-01'), rec(2, '2019'), rec(3, '2019-03')];
  const out = run(input(l, 'newest'));
  assert.equal(out.email.messages[0].from, 'Person 2');
  assert.equal(out.count, 3);
  assert.equal(out.index, 2);
});

test('output holds one record only, not the list', () => {
  const out = run(input(list(30), 'random'));
  assert.ok(JSON.stringify(out).length < 3000);
  assert.equal(out.count, 30);
});

test('random: no repeat until the list is through, one step per 15 minutes', () => {
  const l = list(10), seen = new Set();
  // one full round of the shuffle: from the step where the round starts
  const day = Math.floor(Date.UTC(2026, 9, 16) / 86400000);
  let k = 0;
  while ((day * 96 + k) % 10 !== 0) k++;
  for (let s = 0; s < 10; s++) {
    at(Date.UTC(2026, 9, 16, 0, 0) + (k + s) * 15 * 60000);
    seen.add(run(input(l, 'random')).email.title);
  }
  assert.equal(seen.size, 10);
});

test('random: the same slot gives the same email, the next day another order', () => {
  const l = list(10);
  at('2026-10-16T08:05:00Z');
  const a = run(input(l, 'random')).email.title;
  at('2026-10-16T08:10:00Z');
  assert.equal(run(input(l, 'random')).email.title, a);
});

test('on_this_day: month and day match in any year', () => {
  const l = [rec(1, '2012-02-27'), rec(2, '2016-10-16'), rec(3, '2020-06-01')];
  at('2026-10-16T12:00:00Z');
  assert.equal(run(input(l, 'on_this_day')).email.messages[0].from, 'Person 2');
});

test('on_this_day: no match gives the nearest day, a year-only record is never "nearest"', () => {
  const l = [rec(1, '2012-02-27'), rec(2, '2016-10-20'), rec(3, '2020')];
  at('2026-10-16T12:00:00Z');
  assert.equal(run(input(l, 'on_this_day')).email.messages[0].from, 'Person 2');
  at('2026-12-30T12:00:00Z'); // near the year turn: 1 Jan is closer than 27 Feb
  assert.equal(run(input([rec(1, '2012-02-27'), rec(2, '2016-01-02')], 'on_this_day')).email.messages[0].from, 'Person 2');
});

test('a malformed record is skipped, the good ones stay', () => {
  const bad = [null, 5, 'x', {}, { ...rec(1), date: 'yesterday' }, { ...rec(2), excerpt: '' }, { ...rec(3), from: 7 }];
  const out = run(input([...bad, rec(9)], 'newest'));
  assert.equal(out.email.messages[0].from, 'Person 9');
  assert.equal(out.count, 1);
});

test('texts are cut and lists bounded', () => {
  const out = run(input([{ ...rec(1), excerpt: 'x'.repeat(5000), to: Array.from({ length: 50 }, (_, i) => 'n' + i) }], 'newest'));
  assert.ok(out.email.messages[0].text.length <= 700);
  assert.ok(out.email.to.length <= 12);
});

test('a JSON string and { data: [...] } work as the array does', () => {
  assert.equal(run(input(JSON.stringify([rec(1)]), 'newest')).email.messages[0].from, 'Person 1');
  assert.equal(run(input({ data: [rec(1)] }, 'newest')).email.messages[0].from, 'Person 1');
});

test('first-ever bad poll: email null, never a throw', () => {
  for (const d of [undefined, null, [], 'not json', '{', {}, 42, [null], [{}]]) {
    const out = run(input(d, 'random'));
    assert.equal(out.email, null);
  }
  assert.equal(run({}).email, null);
});

test('the state keeps the last picks, bounded', () => {
  let state;
  for (let i = 0; i < 20; i++) {
    at(Date.UTC(2026, 9, 16, 0, 0) + i * 15 * 60000);
    state = run(input(list(30), 'random', state)).trmnl_state;
  }
  assert.ok(state.recent.length <= 8);
  assert.ok(JSON.stringify(state).length < 14000);
});

test('a failed poll after a good one shows the kept email', () => {
  const good = run(input([rec(1)], 'newest'));
  const out = run(input(undefined, 'newest', good.trmnl_state));
  assert.equal(out.email.messages[0].from, 'Person 1');
  assert.equal(out.stale, true);
});

test('an empty array, non-JSON and only-bad records also fall back to the kept emails', () => {
  const state = run(input([rec(1)], 'newest')).trmnl_state;
  for (const d of [[], 'oops <html>', [{ bad: 1 }]]) assert.equal(run(input(d, 'newest', state)).email.messages[0].from, 'Person 1');
});

test('while the poll is down the kept set rotates, the state keeps', () => {
  let state;
  for (let i = 0; i < 3; i++) {
    at(Date.UTC(2026, 9, 16, 0, 0) + i * 15 * 60000);
    state = run(input(list(30), 'random', state)).trmnl_state;
  }
  const seen = new Set();
  for (let i = 0; i < 3; i++) {
    const out = run(input(null, 'random', state));
    seen.add(out.email.title);
    state = out.trmnl_state;
    assert.equal(state.recent.length, 3);
  }
  assert.equal(seen.size, 3);
});

test('a damaged state is ignored, not a crash', () => {
  for (const s of [null, 5, 'x', { recent: 'x' }, { recent: [null, {}] }]) assert.equal(run(input(null, 'random', s)).email, null);
});

const chat = (n, extra = {}) => ({
  kind: 'chat', date: '2023-11-19', source: { title: 'Src' },
  messages: Array.from({ length: n }, (_, i) => ({ from: ['Sam', 'Mira', 'Ilya', 'Greg', 'Zed'][i % 5 === 4 ? 4 : i % 2], text: 'Message ' + i })), ...extra
});

test('chat: every message kept in order, title from the first two senders, date label', () => {
  const e = run(input([chat(3)], 'newest')).email;
  assert.equal(e.kind, 'chat');
  assert.equal(e.title, 'Sam texts Mira');
  assert.deepEqual(e.messages.map((m) => m.text), ['Message 0', 'Message 1', 'Message 2']);
  assert.equal(e.date_label, 'November 19, 2023');
});

test('chat: the record title wins; one sender uses the recipient; more than two senders are counted', () => {
  assert.equal(run(input([chat(2, { title: 'Late night' })], 'newest')).email.title, 'Late night');
  assert.equal(run(input([{ ...chat(1), to: ['Mira'] }], 'newest')).email.title, 'Sam texts Mira');
  const three = { ...chat(3), messages: [{ from: 'A', text: 'x' }, { from: 'B', text: 'y' }, { from: 'C', text: 'z' }] };
  assert.equal(run(input([three], 'newest')).email.title, 'A, B and 1 more');
});

test('colour slots follow the first appearance of each person, at most 4', () => {
  const msgs = ['A', 'B', 'A', 'C', 'D', 'E', 'B'].map((f, i) => ({ from: f, text: 't' + i }));
  const e = run(input([{ ...chat(1), messages: msgs }], 'newest')).email;
  assert.deepEqual(e.messages.map((m) => m.p), [0, 1, 0, 2, 3, 3, 1]);
});

test('chat: bad messages are skipped; no good message drops the record; counts and sizes are bounded', () => {
  const mixed = { ...chat(1), messages: [null, { from: 'A' }, { text: 'x' }, { from: 'A', text: 'ok' }, 5] };
  assert.equal(run(input([mixed], 'newest')).email.messages.length, 1);
  assert.equal(run(input([{ ...chat(1), messages: [null, {}] }], 'newest')).email, null);
  assert.equal(run(input([{ ...chat(1), messages: 'x' }], 'newest')).email, null);
  const big = run(input([chat(200)], 'newest')).email;
  assert.ok(big.messages.length <= 40);
  const long = run(input([{ ...chat(1), messages: Array.from({ length: 30 }, () => ({ from: 'A', text: 'y'.repeat(600) })) }], 'newest')).email;
  assert.ok(JSON.stringify(long).length < 8000);
});

test('an email carries its recipients and subject as the title', () => {
  const e = run(input([{ ...rec(1), to: ['A', 'B'], cc: ['C'] }], 'newest')).email;
  assert.equal(e.kind, 'email');
  assert.deepEqual([e.title, e.to, e.cc], ['Subject 1', ['A', 'B'], ['C']]);
});

test('date labels: full, month only, year only', () => {
  const l = (d) => run(input([rec(1, d)], 'newest')).email.date_label;
  assert.deepEqual([l('2012-02-07'), l('2012-02'), l('2012')], ['February 7, 2012', 'February 2012', '2012']);
});

test('a kept chat comes back from the state unchanged', () => {
  const good = run(input([chat(3)], 'newest'));
  const out = run(input(null, 'newest', good.trmnl_state));
  assert.deepEqual(out.email, good.email);
});

test('a text over the limit is cut at a word end with an ellipsis, never inside a word', () => {
  const out = run(input([{ ...rec(1), excerpt: 'alpha '.repeat(300) }], 'newest')).email.messages[0].text;
  assert.ok(out.length <= 700);
  assert.match(out, /alpha…$/);
});

test('title without a subject: the record title, else "<from> emails <first to>", never "(no subject)"', () => {
  const t = (x) => run(input([{ ...rec(1), ...x }], 'newest')).email.title;
  assert.equal(t({ subject: '(no subject)' }), 'Person 1 emails A');
  assert.equal(t({ subject: '' }), 'Person 1 emails A');
  assert.equal(t({ subject: undefined, title: 'Given title' }), 'Given title');
  assert.equal(t({ subject: '(No Subject)', to: [] }), 'Person 1 writes');
  assert.equal(t({ subject: 'Real' }), 'Real');
});
