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

const { buildTasks, makeUrl, remoteQueryFor, normalizeRuntimeConfig, normalizeJob, dedupe, classify, sortFinalJobs } = context.BossAiRunnerInternals;
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

// BOSS 现役列表路由是 /web/geek/jobs（复数），旧 /web/geek/job 会 302 且追加
// _security_check 参数；翻页只依赖 query/city/page 三个参数。
const wuhanTask = tasks.find(t => t.scopeType === 'city' && t.city === '101200100');
const pageUrl = makeUrl(wuhanTask, 2);
assert.ok(pageUrl.startsWith('https://www.zhipin.com/web/geek/jobs?'), pageUrl);
assert.ok(!pageUrl.includes('/web/geek/job?'), 'must not use the legacy singular route');
assert.ok(!pageUrl.includes('_security_check'), 'collector must not replay BOSS security tokens');
const parsed = new URL(pageUrl);
assert.strictEqual(parsed.searchParams.get('query'), 'AI Agent 工程师');
assert.strictEqual(parsed.searchParams.get('city'), '101200100');
assert.strictEqual(parsed.searchParams.get('page'), '2');
assert.strictEqual([...parsed.searchParams.keys()].sort().join(','), 'city,page,query');

// BOSS 没有“只看远程”的链接参数，全国远程改用「关键词 + 远程」搜索：
// keyword 保持原样（相关度打分仍按用户填的词），只有 query 追加后缀。
const remoteTasks = tasks.filter(t => t.scopeType === 'remote');
assert.ok(remoteTasks.every(task => task.query === `${task.keyword} 远程`), 'remote task must search "keyword 远程"');
assert.deepStrictEqual(Array.from(remoteTasks, task => task.keyword), ['AI Agent 工程师', 'RAG 开发工程师']);
const remoteUrl = new URL(makeUrl(remoteTasks[0], 1));
assert.strictEqual(remoteUrl.searchParams.get('query'), 'AI Agent 工程师 远程');
assert.strictEqual(remoteUrl.searchParams.get('city'), '100010000');
assert.strictEqual(remoteQueryFor('AI 远程开发'), 'AI 远程开发', 'keyword already mentioning 远程 must not be suffixed twice');
assert.strictEqual(remoteQueryFor('Remote Backend Engineer'), 'Remote Backend Engineer');
assert.strictEqual(remoteQueryFor('AI Agent 工程师'), 'AI Agent 工程师 远程');

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
