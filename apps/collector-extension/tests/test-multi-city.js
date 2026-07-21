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

const { buildTasks, normalizeRuntimeConfig, normalizeJob, dedupe, classify, sortFinalJobs } = context.BossAiRunnerInternals;
const config = normalizeRuntimeConfig({
  keywords: ['AI Agent 工程师', 'RAG 开发工程师'],
  selectedCities: [
    { name: '武汉', code: '101200100', province: '湖北' },
    { name: '成都', code: '101270100', province: '四川' }
  ],
  scopes: { cities: true, remote: true },
  cityCodes: { nationwide: '100010000' },
  minSalaryK: 14,
  salaryMode: 'minGte',
  minRelevanceScore: 0,
  excludePartTime: false,
  excludeIntern: false,
  excludeAssistant: false,
  remotePolicy: 'loose',
  detailMode: 'off'
});

const tasks = buildTasks(config);
assert.strictEqual(tasks.length, 6);
assert.deepStrictEqual(Array.from(new Set(tasks.filter(t => t.scopeType === 'city').map(t => t.city))), ['101200100', '101270100']);
assert.strictEqual(tasks.filter(t => t.scopeType === 'remote').length, 2);

const cityJob = normalizeJob({
  scope: '成都', scopeType: 'city', cityName: '成都', provinceName: '四川', cityCode: '101270100',
  title: 'AI Agent 开发工程师', salary: '20-30K', company: '测试公司', area: '成都·高新区',
  url: 'https://www.zhipin.com/job_detail/multi-city-test.html', searchKeyword: 'AI Agent 工程师'
});
const decision = classify(cityJob, config, 'final');
assert.strictEqual(decision.keep, true);
assert.strictEqual(decision.reason, '通过');
assert.deepStrictEqual(Array.from(cityJob.searchCities), ['成都']);

const sameJobWuhan = { ...cityJob, scope: '武汉', cityName: '武汉', provinceName: '湖北', cityCode: '101200100', searchCities: ['武汉'], searchCityCodes: ['101200100'], searchProvinces: ['湖北'] };
const sameJobChengdu = { ...cityJob, scope: '成都', cityName: '成都', provinceName: '四川', cityCode: '101270100', searchCities: ['成都'], searchCityCodes: ['101270100'], searchProvinces: ['四川'] };
assert.strictEqual(dedupe([sameJobWuhan, sameJobChengdu], true).length, 2);
const merged = dedupe([sameJobWuhan, sameJobChengdu], false);
assert.strictEqual(merged.length, 1);
assert.deepStrictEqual(Array.from(merged[0].searchCities), ['武汉', '成都']);
const sorted = sortFinalJobs([sameJobChengdu, sameJobWuhan], config);
assert.strictEqual(sorted[0].searchCities[0], '武汉');

const legacy = normalizeRuntimeConfig({
  keywords: ['AI 应用开发'], scopes: { wuhan: true, remote: false }, cityCodes: { wuhan: '101200100' }
});
assert.strictEqual(legacy.selectedCities[0].name, '武汉');

console.log('Multi-city task, classification, merge and sorting tests passed.');
