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
  buildRequirementReviewDataset,
  descriptionSimilarity,
  selectDetailTargets,
  prioritizeAcceptedTargetsForReview,
  detailCardIdentity,
  uniqueJobsByUrl
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

function uniqueDescription(index) {
  return [
    fullDescription,
    `专项领域 ${index}：`,
    ...Array.from({ length: 12 }, (_, part) => (
      `${part + 1}. 场景 ${index}-${part} 负责独立业务链路、工具契约、评测样本和上线证据治理。`
    ))
  ].join('\n');
}

function eligibleJob(index, description = uniqueDescription(index)) {
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
    description,
    descriptionSource: 'selector:.job-sec-text',
    detailAttempted: true,
    detailSucceeded: true
  });
}

const normalizedExample = eligibleJob(999);
assert.strictEqual(normalizedExample.description, uniqueDescription(999));
assert.ok(normalizedExample.description.includes('\n任职要求：\n'));
assert.strictEqual(normalizedExample.descriptionLength, uniqueDescription(999).length);

const nineteen = Array.from({ length: 19 }, (_, index) => eligibleJob(index));
const blockedDataset = buildRequirementReviewDataset(nineteen, { detailMode: 'matched' }, {});
assert.strictEqual(blockedDataset.qualityGate.status, 'blocked');
assert.strictEqual(blockedDataset.qualityGate.selectedCount, 19);
assert.deepStrictEqual(
  Array.from(blockedDataset.qualityGate.blockers),
  ['insufficient_distinct_full_jd_jobs']
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
assert.strictEqual(readyDataset.qualityGate.distinctEligibleCount, 20);
assert.strictEqual(readyDataset.qualityGate.nearDuplicateCount, 0);
assert.strictEqual(readyDataset.jobs.length, 20);
assert.ok(readyDataset.jobs.every(job => job.requirementReviewEligible));
assert.ok(readyDataset.jobs.every(job => job.descriptionQuality === 'full_jd'));
assert.ok(readyDataset.jobs.every(job => job.sourceVersion === '1.4.8'));

const companyProfileOnlyJob = normalizeJob({
  scope: '武汉',
  title: 'FDE 工程师',
  company: '公司介绍样本',
  salary: '20-30K',
  area: '武汉',
  url: 'https://www.zhipin.com/job_detail/company-profile-only.html',
  rawText: 'FDE 工程师 20-30K 公司介绍样本 武汉',
  description: [
    '某科技公司成立多年，总部位于北京，在武汉、上海和深圳设有分支机构。',
    '公司提供云计算、应用软件研发与运维、技术服务和行业解决方案。',
    '团队拥有多年企业级服务经验，持续推动技术创新和业务发展。',
    '1. 获得行业优秀服务商称号',
    '2. 成为大型活动软件服务提供商',
    '3. 入选地区创新企业榜单'
  ].join('\n'),
  descriptionSource: 'selector:.job-sec-text',
  descriptionSelectorTrust: 'trusted',
  detailAttempted: true,
  detailSucceeded: true
});
assert.strictEqual(companyProfileOnlyJob.descriptionQuality, 'partial_jd');
assert.strictEqual(companyProfileOnlyJob.requirementReviewEligible, false);
assert.ok(companyProfileOnlyJob.requirementReviewIneligibilityReasons.includes('missing_job_evidence'));
const readyWithCompanyProfile = buildRequirementReviewDataset(
  [...twentyPlusCard.slice(0, 20), companyProfileOnlyJob],
  { detailMode: 'matched' },
  {}
);
assert.strictEqual(readyWithCompanyProfile.qualityGate.status, 'ready');
assert.strictEqual(readyWithCompanyProfile.qualityGate.eligibleCount, 20);
assert.ok(!readyWithCompanyProfile.jobs.some(job => job.url === companyProfileOnlyJob.url));

const duplicateDescription = uniqueDescription(50);
const nearDuplicateJobs = [
  ...Array.from({ length: 20 }, (_, index) => eligibleJob(index)),
  eligibleJob(50, duplicateDescription),
  eligibleJob(51, duplicateDescription.replace('专项领域 50', '专项领域 51')),
  eligibleJob(52, duplicateDescription.replace('专项领域 50：', '专项领域 50'))
];
assert.ok(
  descriptionSimilarity(
    nearDuplicateJobs.at(-3).description,
    nearDuplicateJobs.at(-2).description
  ) >= 0.82
);
const diverseDataset = buildRequirementReviewDataset(
  nearDuplicateJobs,
  { detailMode: 'matched' },
  {}
);
assert.strictEqual(diverseDataset.qualityGate.status, 'ready');
assert.strictEqual(diverseDataset.qualityGate.eligibleCount, 23);
assert.strictEqual(diverseDataset.qualityGate.distinctEligibleCount, 21);
assert.strictEqual(diverseDataset.qualityGate.nearDuplicateCount, 2);
assert.strictEqual(diverseDataset.jobs.length, 20);
assert.strictEqual(diverseDataset.excludedNearDuplicates.length, 2);
assert.ok(diverseDataset.excludedNearDuplicates.every(item => item.similarity >= 0.82));

function detailTarget(index, kind = 'accepted', overrides = {}) {
  const job = {
    title: `AI Agent 工程师 ${index}`,
    company: `详情公司 ${index}`,
    area: '武汉·洪山区',
    salary: '20-30K',
    url: `https://www.zhipin.com/job_detail/detail-target-${kind}-${index}.html`,
    ...overrides
  };
  return {
    job,
    initialClass: {
      keep: kind === 'accepted',
      pendingDetail: kind === 'remote'
    }
  };
}

const acceptedDetailTargets = Array.from({ length: 35 }, (_, index) => detailTarget(index));
const duplicateCardTarget = detailTarget(999, 'accepted', {
  title: 'AI  Agent工程师 0',
  company: '详情公司 0',
  area: '武汉·洪山区',
  salary: '20-30K'
});
assert.strictEqual(
  detailCardIdentity(acceptedDetailTargets[0].job),
  detailCardIdentity(duplicateCardTarget.job)
);
const prioritizedAccepted = prioritizeAcceptedTargetsForReview([
  acceptedDetailTargets[0],
  duplicateCardTarget,
  ...acceptedDetailTargets.slice(1)
]);
assert.strictEqual(prioritizedAccepted.at(-1).job.url, duplicateCardTarget.job.url);

const remoteDetailTargets = Array.from({ length: 20 }, (_, index) => detailTarget(index, 'remote'));
const plannedDetailTargets = selectDetailTargets(
  [acceptedDetailTargets[0], duplicateCardTarget, ...acceptedDetailTargets.slice(1), ...remoteDetailTargets],
  'matched',
  40
);
assert.strictEqual(plannedDetailTargets.length, 40);
assert.strictEqual(plannedDetailTargets.filter(target => target.initialClass.keep).length, 30);
assert.strictEqual(plannedDetailTargets.filter(target => target.initialClass.pendingDetail).length, 10);
assert.ok(!plannedDetailTargets.some(target => target.job.url === duplicateCardTarget.job.url));
assert.strictEqual(selectDetailTargets(remoteDetailTargets, 'remote', 12).length, 12);

const finalJobs = [eligibleJob(1), twentyPlusCard.at(-1)];
const duplicateScopeJob = {
  ...eligibleJob(1),
  scope: '全国远程',
  scopeType: 'remote'
};
const detailCohort = [
  eligibleJob(1),
  duplicateScopeJob,
  eligibleJob(2),
  eligibleJob(3),
  twentyPlusCard.at(-1)
];
assert.strictEqual(uniqueJobsByUrl(detailCohort.filter(job => job.detailSucceeded)).length, 3);
const statistics = buildStatistics(finalJobs, detailCohort);
assert.strictEqual(statistics.totals.finalJobs, 2);
assert.strictEqual(statistics.totals.fullJd, 1);
assert.strictEqual(statistics.totals.requirementReviewEligible, 1);
assert.strictEqual(statistics.totals.detailCohortFullJd, 3);
assert.strictEqual(statistics.totals.detailCohortRequirementReviewEligible, 3);

console.log('Requirement review dataset quality-gate tests passed.');
