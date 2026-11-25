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

const { dedupe, classify, planDetailTargets } = context.BossAiRunnerInternals;
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

const recruiterFilterConfig = {
  ...designFilterConfig,
  recruiterActivityMaxDays: 30
};
const recruiterFresh = classify({
  title: 'UI设计师',
  salary: '15-30K',
  searchKeyword: 'UI设计',
  scope: '武汉',
  scopeType: 'city',
  cityName: '武汉',
  cityCode: '101200100',
  area: '武汉·洪山区',
  company: '测试公司',
  recruiterActive: '本月活跃',
  rawText: 'UI设计师 15-30K 武汉·洪山区 本月活跃'
}, recruiterFilterConfig, 'final');
assert.strictEqual(recruiterFresh.keep, true);

const recruiterAmbiguous = classify({
  title: 'UI设计师',
  salary: '15-30K',
  searchKeyword: 'UI设计',
  scope: '武汉',
  scopeType: 'city',
  cityName: '武汉',
  cityCode: '101200100',
  area: '武汉·洪山区',
  company: '测试公司',
  recruiterActive: '2月内活跃',
  rawText: 'UI设计师 15-30K 武汉·洪山区 2月内活跃'
}, recruiterFilterConfig, 'final');
assert.strictEqual(recruiterAmbiguous.keep, true);
assert.strictEqual(recruiterAmbiguous.job.recruiterActivityUnverified, true);

const recruiterClearlyStale = classify({
  title: 'UI设计师',
  salary: '15-30K',
  searchKeyword: 'UI设计',
  scope: '武汉',
  scopeType: 'city',
  cityName: '武汉',
  cityCode: '101200100',
  area: '武汉·洪山区',
  company: '测试公司',
  recruiterActive: '半年前活跃',
  rawText: 'UI设计师 15-30K 武汉·洪山区 半年前活跃'
}, recruiterFilterConfig, 'final');
assert.strictEqual(recruiterClearlyStale.keep, false);
assert.strictEqual(recruiterClearlyStale.reason, '招聘者超过30天未活跃');

const recruiterUnknownInitial = classify({
  title: 'UI设计师',
  salary: '15-30K',
  searchKeyword: 'UI设计',
  scope: '武汉',
  scopeType: 'city',
  cityName: '武汉',
  cityCode: '101200100',
  area: '武汉·洪山区',
  company: '测试公司',
  rawText: 'UI设计师 15-30K 武汉·洪山区'
}, recruiterFilterConfig, 'initial');
assert.strictEqual(recruiterUnknownInitial.keep, true);
assert.strictEqual(recruiterUnknownInitial.pendingDetail, false);
assert.strictEqual(recruiterUnknownInitial.job.recruiterActivityUnverified, true);
assert.strictEqual(classify({
  ...recruiterUnknownInitial.job, recruiterActive: '刚刚活跃'
}, recruiterFilterConfig, 'initial').job.recruiterActivityUnverified, false);

const recruiterUnknownFinal = classify(recruiterUnknownInitial.job, recruiterFilterConfig, 'final');
assert.strictEqual(recruiterUnknownFinal.keep, true, 'unknown recruiter activity must not be treated as a dead job');
assert.strictEqual(recruiterUnknownFinal.pendingDetail, false);
assert.strictEqual(recruiterUnknownFinal.reason, '通过');
assert.strictEqual(recruiterUnknownFinal.recruiterActivityUnverified, true);

const recruiterFilterDisabled = classify(recruiterUnknownInitial.job, {
  ...recruiterFilterConfig,
  recruiterActivityMaxDays: 0
}, 'final');
assert.strictEqual(recruiterFilterDisabled.keep, true);
assert.strictEqual(recruiterFilterDisabled.recruiterActivityUnverified, false);

// 真实导出里 443 条候选有 210 条在列表页读不到活跃文案，详情页也只对在线招聘者显示。
// 这类岗位必须在终审时全部保留，否则整轮采集会归零。
const unknownActivityFlood = Array.from({ length: 60 }, (_, index) => classify({
  title: `AI 应用开发工程师 ${index}`,
  salary: '18-30K',
  searchKeyword: 'AI 应用开发工程师',
  scope: '武汉',
  scopeType: 'city',
  cityName: '武汉',
  cityCode: '101200100',
  area: '武汉·洪山区',
  company: `测试公司${index}`,
  url: `https://www.zhipin.com/job_detail/unknown-activity-${index}.html`,
  rawText: `AI 应用开发工程师 ${index} 18-30K 3-5年 本科 测试公司${index} 武汉·洪山区`
}, recruiterFilterConfig, 'final'));
assert.strictEqual(unknownActivityFlood.filter(item => item.keep).length, 60);
assert.ok(unknownActivityFlood.every(item => item.recruiterActivityUnverified));

// 全国远程改成「关键词 + 远程」搜索后，卡片地点是具体城市只代表“要打开详情才能确认”，
// 不再一票否决；额度保护交给 selectDetailTargets 的远程配额。
const onsiteInRemoteScope = classify({
  title: 'AI应用开发工程师 (MJ057222)',
  salary: '20-35K·17薪',
  searchKeyword: 'AI 应用开发工程师',
  scope: '全国远程',
  scopeType: 'remote',
  cityName: '',
  cityCode: '100010000',
  area: '宁德·蕉城区·漳湾工业园区',
  company: '宁德时代',
  url: 'https://www.zhipin.com/job_detail/onsite-in-remote.html',
  rawText: 'AI应用开发工程师 (MJ057222) 20-35K·17薪 5-10年 本科 宁德时代 宁德·蕉城区·漳湾工业园区'
}, recruiterFilterConfig, 'initial');
assert.strictEqual(onsiteInRemoteScope.keep, false);
assert.strictEqual(onsiteInRemoteScope.pendingDetail, true);
assert.strictEqual(onsiteInRemoteScope.reason, '待详情页确认远程（卡片为线下城市）');

const onsiteInRemoteScopeFinal = classify(onsiteInRemoteScope.job, recruiterFilterConfig, 'final');
assert.strictEqual(onsiteInRemoteScopeFinal.keep, false);
assert.strictEqual(onsiteInRemoteScopeFinal.reason, '未识别远程标记（详情未补采）');

const remoteWithEvidence = classify({
  title: 'AI 应用开发工程师（可远程）',
  salary: '20-35K',
  searchKeyword: 'AI 应用开发工程师',
  scope: '全国远程',
  scopeType: 'remote',
  cityName: '',
  cityCode: '100010000',
  area: '武汉·洪山区',
  company: '远程公司',
  recruiterActive: '今日活跃',
  url: 'https://www.zhipin.com/job_detail/remote-evidence.html',
  rawText: 'AI 应用开发工程师（可远程） 20-35K 5-10年 本科 远程公司 武汉·洪山区 今日活跃'
}, recruiterFilterConfig, 'initial');
assert.strictEqual(remoteWithEvidence.keep, true);

const accepted = unknownActivityFlood.map(item => item.job);
const pendingRemote = Array.from({ length: 45 }, (_, index) => ({
  ...onsiteInRemoteScope.job,
  url: `https://www.zhipin.com/job_detail/remote-pending-${index}.html`,
  sourceUrl: undefined
}));
// Same url in both scopes uses only one detail read and takes the accepted slot.
pendingRemote[0].url = accepted[0].url;
const both = [...pendingRemote, ...accepted];
function checkPlan(jobs, mode, limit, expected) {
  const { targets, deferredAccepted } = planDetailTargets(jobs, {
    ...recruiterFilterConfig, detailMode: mode, detailLimit: limit
  });
  assert.deepStrictEqual([
    targets.filter(target => target.initialClass.keep).length,
    targets.filter(target => target.initialClass.pendingDetail).length,
    deferredAccepted
  ], expected);
  assert.strictEqual(new Set(targets.map(target => target.job.url)).size, targets.length);
  return targets;
}
checkPlan(both, 'off', 40, [0, 0, 0]);
checkPlan(both, 'matched', 1, [1, 0, 59]);
const small = checkPlan(both, 'matched', 2, [1, 1, 59]);
assert.strictEqual(small[0].job.url, accepted[0].url);
assert.notStrictEqual(small[1].job.url, accepted[0].url);
checkPlan(both, 'matched', 40, [30, 10, 30]);
checkPlan(both, 'matched', 48, [38, 10, 22]);
checkPlan(accepted, 'matched', 40, [40, 0, 20]);
checkPlan([...accepted.slice(0, 3), ...pendingRemote], 'matched', 40, [3, 37, 0]);
checkPlan([...accepted, ...pendingRemote.slice(0, 2)], 'matched', 40, [39, 1, 21]);
checkPlan(both, 'remote', 40, [0, 40, 0]);
checkPlan(accepted, 'remote', 40, [0, 0, 0]);
assert.strictEqual(planDetailTargets(both, recruiterFilterConfig).targets.length, 40);

console.log('Runner merge, query relevance and recruiter activity filter tests passed.');
