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

const { dedupe, classify } = context.BossAiRunnerInternals;
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

const designFilterConfig = {
  minSalaryK: 13,
  salaryMode: 'minGte',
  minRelevanceScore: 20,
  excludePartTime: false,
  excludeIntern: false,
  excludeAssistant: false,
  remotePolicy: 'cardOrDetail',
  detailMode: 'matched'
};

for (const job of [
  { title: '视觉设计师资深视觉设计', salary: '15-25K', searchKeyword: '视觉设计' },
  { title: '餐饮空间设计师', salary: '20-21K', searchKeyword: '餐饮设计' },
  { title: '教育-UI设计/创意/视觉设计师-武汉/合肥', salary: '25-40K', searchKeyword: '教育设计' },
  { title: '平面设计师', salary: '15-25K', searchKeywords: ['教育设计', '平面设计'] },
  { title: 'UI设计师', salary: '15-30K', searchKeyword: 'ui设计' }
]) {
  const classified = classify({
    ...job,
    scope: '武汉',
    scopeType: 'city',
    cityName: '武汉',
    cityCode: '101200100',
    area: '武汉·洪山区',
    company: '测试公司',
    rawText: `${job.title} ${job.salary} 武汉·洪山区`
  }, designFilterConfig);
  assert.strictEqual(classified.keep, true, `${job.title} should pass relevance + salary filtering`);
}

const irrelevantSolution = classify({
  title: '解决方案专家（教育行业）',
  salary: '15-25K',
  searchKeyword: '教育设计',
  scope: '武汉',
  scopeType: 'city',
  cityName: '武汉',
  cityCode: '101200100',
  area: '武汉·洪山区',
  company: '测试公司',
  rawText: '解决方案专家（教育行业） 15-25K 武汉·洪山区'
}, designFilterConfig);
assert.strictEqual(irrelevantSolution.keep, false);
assert.strictEqual(irrelevantSolution.reason, '岗位相关度低于阈值');

console.log('Runner merge and query relevance tests passed.');
