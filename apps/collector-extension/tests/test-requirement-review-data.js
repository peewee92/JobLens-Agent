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

const { assessDescriptionQuality } = context.BossJobFilterLib;
const {
  normalizeJob,
  buildStatistics,
  buildRequirementReviewDataset
} = context.BossAiRunnerInternals;

const fullDescription = [
  '岗位职责：',
  '1. 负责企业级 AI Agent 应用的设计、开发和上线，建设可观测的工具调用工作流。',
  '2. 负责 RAG 检索、提示词和评测数据集的持续优化，并与产品和业务团队协作。',
  '任职要求：',
  '1. 熟悉 Python、FastAPI 和主流大模型 API，理解 Agent Loop、Tool Calling 和结构化输出。',
  '2. 有真实项目交付经验，能够编写测试、分析 Trace 并定位线上问题。',
  '3. 具备良好的沟通和文档能力，能够独立推动需求落地。'
].join('\n');

const full = assessDescriptionQuality({
  description: fullDescription,
  descriptionSource: 'selector:.job-sec-text',
  detailAttempted: true,
  detailSucceeded: true
});
assert.strictEqual(full.descriptionQuality, 'full_jd');
assert.strictEqual(full.requirementReviewEligible, true);
assert.ok(full.descriptionHash.startsWith('fnv1a32:'));

const cardOnly = assessDescriptionQuality({
  description: '',
  detailAttempted: false,
  detailSucceeded: false
});
assert.strictEqual(cardOnly.descriptionQuality, 'card_only');
assert.strictEqual(cardOnly.requirementReviewEligible, false);
assert.ok(cardOnly.requirementReviewIneligibilityReasons.includes('detail_not_attempted'));

const fallback = assessDescriptionQuality({
  description: fullDescription,
  descriptionSource: 'body_fallback',
  detailAttempted: true,
  detailSucceeded: true
});
assert.strictEqual(fallback.descriptionQuality, 'partial_jd');
assert.strictEqual(fallback.requirementReviewEligible, false);
assert.ok(fallback.requirementReviewIneligibilityReasons.includes('body_fallback_not_trusted'));

const broadWithoutStructure = assessDescriptionQuality({
  description: '这是一个很长的职位页面正文。'.repeat(30),
  descriptionSource: 'selector:.job-detail',
  detailAttempted: true,
  detailSucceeded: true
});
assert.strictEqual(broadWithoutStructure.requirementReviewEligible, false);
assert.ok(
  broadWithoutStructure.requirementReviewIneligibilityReasons.includes(
    'broad_selector_not_sanitized'
  )
);

function eligibleJob(index) {
  return normalizeJob({
    scope: '武汉',
    scopeType: 'city',
    cityName: '武汉',
    cityCode: '101200100',
    title: `AI Agent 工程师 ${index}`,
    company: `测试公司 ${index}`,
    salary: '15-25K',
    area: '武汉·洪山区',
    url: `https://www.zhipin.com/job_detail/review-${index}.html`,
    rawText: `AI Agent 工程师 ${index} 15-25K`,
    description: fullDescription,
    descriptionSource: 'selector:.job-sec-text',
    detailAttempted: true,
    detailSucceeded: true
  });
}

const normalizedExample = eligibleJob(999);
assert.strictEqual(normalizedExample.description, fullDescription);
assert.ok(normalizedExample.description.includes('\n任职要求：\n'));
assert.strictEqual(normalizedExample.descriptionLength, fullDescription.length);

const nineteen = Array.from({ length: 19 }, (_, index) => eligibleJob(index));
const blockedDataset = buildRequirementReviewDataset(nineteen, { detailMode: 'matched' }, {});
assert.strictEqual(blockedDataset.qualityGate.status, 'blocked');
assert.strictEqual(blockedDataset.qualityGate.selectedCount, 19);
assert.deepStrictEqual(
  Array.from(blockedDataset.qualityGate.blockers),
  ['insufficient_full_jd_jobs']
);

const twentyPlusCard = [
  ...Array.from({ length: 20 }, (_, index) => eligibleJob(index)),
  normalizeJob({
    scope: '武汉',
    title: '只有卡片的岗位',
    company: '卡片公司',
    salary: '15-20K',
    area: '武汉',
    url: 'https://www.zhipin.com/job_detail/card-only.html',
    rawText: '只有卡片的岗位 15-20K',
    detailAttempted: false,
    detailSucceeded: false
  })
];
const readyDataset = buildRequirementReviewDataset(twentyPlusCard, { detailMode: 'matched' }, {});
assert.strictEqual(readyDataset.qualityGate.status, 'ready');
assert.strictEqual(readyDataset.qualityGate.eligibleCount, 20);
assert.strictEqual(readyDataset.jobs.length, 20);
assert.ok(readyDataset.jobs.every(job => job.requirementReviewEligible));
assert.ok(readyDataset.jobs.every(job => job.descriptionQuality === 'full_jd'));
assert.ok(readyDataset.jobs.every(job => job.sourceVersion === '1.4.1'));

const finalJobs = [eligibleJob(1), twentyPlusCard.at(-1)];
const detailCohort = [eligibleJob(1), eligibleJob(2), eligibleJob(3), twentyPlusCard.at(-1)];
const statistics = buildStatistics(finalJobs, detailCohort);
assert.strictEqual(statistics.totals.finalJobs, 2);
assert.strictEqual(statistics.totals.fullJd, 1);
assert.strictEqual(statistics.totals.requirementReviewEligible, 1);
assert.strictEqual(statistics.totals.detailCohortFullJd, 3);
assert.strictEqual(statistics.totals.detailCohortRequirementReviewEligible, 3);

console.log('Requirement review dataset quality-gate tests passed.');
