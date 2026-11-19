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

const { dedupe, classify, selectDetailTargets } = context.BossAiRunnerInternals;
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

const recruiterStale = classify({
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
assert.strictEqual(recruiterStale.keep, false);
assert.strictEqual(recruiterStale.reason, '招聘者活跃无法确认在30天内');

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
assert.strictEqual(recruiterUnknownInitial.keep, false);
assert.strictEqual(recruiterUnknownInitial.pendingDetail, true);
assert.strictEqual(recruiterUnknownInitial.reason, '待详情页确认招聘者活跃');

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

const detailTargets = selectDetailTargets([
  {
    job: { url: 'https://example.test/accepted', title: '已通过岗位', company: 'A', area: '武汉', salary: '20-30K' },
    initialClass: { keep: true, pendingDetail: false, reason: '通过' }
  },
  {
    job: { url: 'https://example.test/activity', title: '活跃待确认岗位', company: 'B', area: '武汉', salary: '20-30K' },
    initialClass: { keep: false, pendingDetail: true, reason: '待详情页确认招聘者活跃' }
  },
  {
    job: { url: 'https://example.test/remote', title: '远程待确认岗位', company: 'C', area: '全国', salary: '20-30K' },
    initialClass: { keep: false, pendingDetail: true, reason: '待详情页确认远程' }
  }
], 'matched', 2);
assert.deepStrictEqual(Array.from(detailTargets, target => target.job.url), [
  'https://example.test/accepted',
  'https://example.test/activity'
]);

// 活跃待确认队列远大于详情上限时，已通过岗位仍要拿到 Requirement 验收名额。
const acceptedPlusFlood = selectDetailTargets([
  {
    job: { url: 'https://example.test/accepted-1', title: '已通过岗位', company: 'A', area: '武汉', salary: '20-30K' },
    initialClass: { keep: true, pendingDetail: false, reason: '通过' }
  },
  ...Array.from({ length: 50 }, (_, index) => ({
    job: {
      url: `https://example.test/pending-${index}`,
      title: '活跃待确认岗位',
      company: 'B',
      area: '武汉',
      salary: '20-30K'
    },
    initialClass: { keep: false, pendingDetail: true, reason: '待详情页确认招聘者活跃' }
  }))
], 'matched', 10);
assert.strictEqual(acceptedPlusFlood.length, 10);
assert.strictEqual(acceptedPlusFlood[0].job.url, 'https://example.test/accepted-1');

// 远程候选有自己的小额度：活跃待确认队列几百条时，远程仍然拿得到 10 个详情名额；
// 反过来远程也不能像 v1.4.9 那样把 40 个额度全吃光。
const remotePlusFlood = selectDetailTargets([
  ...Array.from({ length: 40 }, (_, index) => ({
    job: {
      url: `https://example.test/remote-${index}`,
      title: '远程待确认岗位',
      company: 'R',
      area: index % 2 ? '全国' : '杭州·西湖区',
      salary: '20-30K',
      scope: '全国远程',
      scopeType: 'remote'
    },
    initialClass: {
      keep: false,
      pendingDetail: true,
      reason: index % 2 ? '待详情页确认远程' : '待详情页确认远程（卡片为线下城市）'
    }
  })),
  ...Array.from({ length: 200 }, (_, index) => ({
    job: {
      url: `https://example.test/activity-${index}`,
      title: '活跃待确认岗位',
      company: 'B',
      area: '武汉',
      salary: '20-30K'
    },
    initialClass: { keep: false, pendingDetail: true, reason: '待详情页确认招聘者活跃' }
  }))
], 'matched', 40);
const remotePicked = remotePlusFlood.filter(target => target.job.scopeType === 'remote');
assert.strictEqual(remotePicked.length, 10, 'remote candidates get a fixed quota of 10 details');
assert.strictEqual(remotePlusFlood.length, 40);
assert.ok(remotePlusFlood.slice(0, 10).every(target => target.job.scopeType === 'remote'));

console.log('Runner merge, query relevance and recruiter activity filter tests passed.');
