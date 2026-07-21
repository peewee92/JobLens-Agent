const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = { console };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve('../lib.js'), 'utf8'), context);
const lib = context.BossJobFilterLib;

const cases = [
  ['-K', 15, 30],
  ['-K', 25, 50],
  ['-K·薪', 20, 40],
  ['-K', 14, 17],
  ['15K-30k', 15, 30],
  ['1.4-2万/月', 14, 20],
  ['20-40万/年', 16.67, 33.33]
];

for (const [input, minK, maxK] of cases) {
  const parsed = lib.parseSalary(input);
  assert.strictEqual(parsed.minK, minK, `${input} min`);
  assert.strictEqual(parsed.maxK, maxK, `${input} max`);
}

const daily = lib.parseSalary('-元/天');
assert.strictEqual(daily.type, 'daily');
assert.strictEqual(daily.minK, null);

const remote = lib.detectRemote({ title: 'AI Agent 工程师（全远程）' });
assert.strictEqual(remote.matched, true);
assert.strictEqual(remote.confidence, 'high');

const onsite = lib.detectRemote({ description: '该岗位不支持远程，必须到岗坐班' });
assert.strictEqual(onsite.matched, false);
assert.strictEqual(onsite.status, 'rejected');

console.log('All lib tests passed.');

const keywords = [
  'AI 应用开发工程师',
  'AI Agent 工程师',
  '智能体开发工程师',
  '大模型应用开发工程师',
  'RAG 开发工程师',
  'FDE'
];
let metadata = {};
for (let i = 0; i < 20000; i += 1) {
  metadata = lib.mergeSearchMetadata(metadata, {
    searchKeyword: keywords[i % keywords.length],
    page: (i % 5) + 1
  });
}
assert.deepStrictEqual(Array.from(metadata.searchKeywords), keywords);
assert.strictEqual(metadata.pages.length, 5);
assert.ok(metadata.searchKeyword.length < 500, 'aggregated keyword string should stay bounded');

const legacyAggregate = lib.mergeSearchMetadata(
  { searchKeyword: 'AI 应用开发工程师 | AI Agent 工程师' },
  { searchKeyword: 'AI 应用开发工程师' }
);
assert.deepStrictEqual(Array.from(legacyAggregate.searchKeywords), [
  'AI 应用开发工程师',
  'AI Agent 工程师'
]);

const bounded = lib.normalizeStringList(
  Array.from({ length: 500 }, (_, index) => `关键词-${index}`),
  { maxItems: 128 }
);
assert.strictEqual(bounded.length, 128);

console.log('All merge stability tests passed.');
