const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = { console };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve('../lib.js'), 'utf8'), context);
const lib = context.BossJobFilterLib;

assert.strictEqual(
  lib.cleanMultiline('岗位职责：\r\n  1. 负责 Agent  开发\n\n\n任职要求：\n\t2. 熟悉 Python'),
  '岗位职责：\n1. 负责 Agent 开发\n\n任职要求：\n2. 熟悉 Python'
);
assert.strictEqual(
  lib.limitMultilineText('职责：\n1. 开发\n2. 测试', 100),
  '职责：\n1. 开发\n2. 测试'
);
assert.strictEqual(
  lib.decodeBossMultilineText('岗位职责：\n. 负责 Agent 开发').text,
  '岗位职责：\n1. 负责 Agent 开发'
);

const noisyBossPage = [
  '下载App, 不错过Boss每一条消息',
  '微信扫码分享 举报 职位描述',
  '岗位职责：',
  '1. 负责企业级 AI Agent 应用设计、开发和上线。',
  '2. 建设工具调用、RAG 和可观测工作流。',
  '任职要求：',
  '1. 熟悉 Python、FastAPI 和主流大模型 API。',
  '2. 具备真实项目交付与测试经验。',
  '3. 能够编写自动化测试、分析 Trace、定位工具调用失败并持续改进系统可靠性。',
  '4. 与产品和业务团队协作，完成需求分析、方案评审、上线验证和持续迭代。',
  '认证资质 人力资源服务许可证',
  '竞争力分析 查看完整个人竞争力',
  'BOSS 安全提示',
  '更多职位 看过该职位的人还看了'
].join('\n');
const segment = lib.extractJobDescriptionSegment(noisyBossPage);
assert.strictEqual(segment.startMarker, '职位描述');
assert.strictEqual(segment.stopMarker, '认证资质');
assert.ok(segment.sanitized);
assert.ok(segment.text.startsWith('岗位职责：'));
assert.ok(!segment.text.includes('BOSS 安全提示'));
assert.ok(!segment.text.includes('更多职位'));

const sanitizedQuality = lib.assessDescriptionQuality({
  description: segment.text,
  descriptionSource: 'selector:[class*="job-detail"]',
  descriptionSelectorTrust: 'broad',
  descriptionSanitized: true,
  detailAttempted: true,
  detailSucceeded: true
});
assert.strictEqual(sanitizedQuality.descriptionQuality, 'full_jd');
assert.strictEqual(sanitizedQuality.requirementReviewEligible, true);
assert.strictEqual(sanitizedQuality.descriptionNoiseCount, 0);

const noisyQuality = lib.assessDescriptionQuality({
  description: noisyBossPage,
  descriptionSource: 'selector:[class*="job-detail"]',
  descriptionSelectorTrust: 'broad',
  descriptionSanitized: false,
  detailAttempted: true,
  detailSucceeded: true
});
assert.strictEqual(noisyQuality.descriptionQuality, 'partial_jd');
assert.strictEqual(noisyQuality.requirementReviewEligible, false);
assert.ok(noisyQuality.requirementReviewIneligibilityReasons.includes('page_noise_detected'));

const recruiterTailDescription = [
  '岗位职责:',
  '1. 参与大模型相关应用的设计与开发工作',
  '2. 协同团队完成技术方案的实施与优化',
  '3. 探索大模型在实际业务场景中的创新应用',
  '任职要求：',
  '1. 善于沟通、按时完成工作',
  '2. 拥有良好的团队合作精神',
  '3. 具备良好的学习能力',
  '周先生',
  '2月内活跃',
  '谷宇云',
  '·',
  'HR'
].join('\n');
const recruiterSegment = lib.extractJobDescriptionSegment(recruiterTailDescription);
assert.strictEqual(recruiterSegment.stopMarker, 'recruiter_profile');
assert.ok(recruiterSegment.sanitized);
assert.ok(!recruiterSegment.text.includes('周先生'));
assert.ok(!recruiterSegment.text.includes('2月内活跃'));
assert.ok(!recruiterSegment.text.endsWith('HR'));
const unsanitizedRecruiterQuality = lib.assessDescriptionQuality({
  description: `${'补充职责与要求。\n'.repeat(20)}${recruiterTailDescription}`,
  descriptionSource: 'selector:.job-sec-text',
  descriptionSelectorTrust: 'trusted',
  descriptionSanitized: false,
  detailAttempted: true,
  detailSucceeded: true
});
assert.strictEqual(unsanitizedRecruiterQuality.requirementReviewEligible, false);
assert.ok(unsanitizedRecruiterQuality.requirementReviewIneligibilityReasons.includes('page_noise_detected'));

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
