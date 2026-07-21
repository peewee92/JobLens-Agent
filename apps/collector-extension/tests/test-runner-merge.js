const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = {
  console,
  __BOSS_JOB_FILTER_TEST__: true,
  URLSearchParams,
  setTimeout,
  clearTimeout
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve('../lib.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(require.resolve('../runner.js'), 'utf8'), context);

const { dedupe } = context.BossAiRunnerInternals;
const keywords = [
  'AI 应用开发工程师',
  'AI Agent 工程师',
  '智能体开发工程师',
  '大模型应用开发工程师',
  'RAG 开发工程师',
  'FDE'
];

const jobs = Array.from({ length: 3000 }, (_, index) => ({
  scope: '武汉',
  searchKeyword: keywords[index % keywords.length],
  title: 'AI应用开发工程师',
  salary: '15-30K',
  area: '武汉·洪山区·光谷',
  company: '测试公司',
  url: 'https://www.zhipin.com/job_detail/stable-merge-test.html',
  page: (index % 5) + 1,
  rawText: 'AI应用开发工程师 15-30K 武汉·洪山区·光谷',
  collectedAt: new Date(2026, 6, 15, 10, 0, index % 60).toISOString()
}));

const result = dedupe(jobs, true);
assert.strictEqual(result.length, 1);
assert.deepStrictEqual(Array.from(result[0].searchKeywords), keywords);
assert.deepStrictEqual(Array.from(result[0].pages), [1, 2, 3, 4, 5]);
assert.strictEqual(result[0].hitCount, 3000);
assert.ok(result[0].searchKeyword.length < 500);
assert.strictEqual(result[0].salaryMinK, 15);
assert.strictEqual(result[0].salaryMaxK, 30);

console.log('Runner merge stress test passed.');
